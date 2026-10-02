# -*- coding: utf-8 -*-
"""
Taku · 设备管家（把手机画面接到界面上）

★ 干什么：
    后台每隔一会儿拍一张手机屏幕，发给界面显示。
    界面从此能"看见"手机 —— 这是所有功能的地基。
    没连上手机时，它负责说清楚"为什么没连上"，而不是默默不动。

★★★ 三个必须守住的设计（别改，改了会出问题）★★★

  ① **投屏和 AI 截图分成两条通道**（规格书 1.10.6）
     投屏是给人看的：2 秒一帧、允许丢帧、画面糊一点没关系；
     AI 截图要准：要高清、不能被投屏抢走 adb。
     两条通道抢同一个 adb，会互相拖慢 —— 所以 AI 干活时投屏要**主动让路**。
     → 本模块提供 `pause()` / `resume()`，AI 操作前后调用。

  ② **绝不阻塞界面**
     一次 adb 截图 300~800ms。放在主线程里，窗口就会"卡住不动"。
     所以整个循环跑在后台线程，界面只收信号。

  ③ **断了要能自己回来**
     手机拔了 → 显示"没连上"；插回来 → 自动恢复。
     用户不用重开软件（他就是插拔数据线的人）。

★ 为什么设备信息可以读（不违反"只走视觉"）：
    `getprop` / `wm size` 读的是**系统配置参数**，不是屏幕上的内容。
    规格书 1.2.1 白名单里明确允许。
"""

import time
from collections import deque

from PySide6.QtCore import QThread, Signal, QObject


# ============================================================
# 连接状态
# ============================================================
NOT_CONNECTED = {
    "connected": False,
    "serial": "—", "model": "—", "brand": "—", "android": "—",
    "width": "—", "height": "—", "density": "—",
    "why": "还没查手机",
}


# ============================================================
# 把截图缩小再给界面用
# ============================================================
def _shrink(png_bytes, max_w=420, quality=72):
    """
    1080×2400 的 PNG（2.5MB）→ 宽 420 的 JPEG（约 150KB）。

    ★ 为什么值得做：跨线程每 2 秒搬 2.5MB，一天下来是几百 GB 的内存拷贝。
      给人看的画面缩到 1/4 就够了，眼睛看不出区别。
    ★ 注意：**AI 看图不走这里**，它自己调 phone.screenshot_bytes() 拿原图。
    """
    try:
        import io
        from PIL import Image
        im = Image.open(io.BytesIO(png_bytes))
        w, h = im.size
        if w > max_w:
            im = im.resize((max_w, max(1, int(h * max_w / float(w)))),
                           Image.LANCZOS)
        if im.mode != "RGB":
            im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=quality, optimize=True)
        return buf.getvalue()
    except Exception:
        return None


class DeviceHub(QThread):
    """
    后台线程：连着手机 → 定时截图 → 发信号给界面。
    """

    frame = Signal(bytes)      # 新的一帧 PNG
    status = Signal(dict)      # 连接状态（连上 / 断了 / 为什么）
    acted = Signal(str)        # 动作执行完了（"点了" / "按了返回"…）

    def __init__(self, interval_ms=2000, retry_ms=3000, parent=None):
        super().__init__(parent)
        self._interval = max(600, int(interval_ms))   # 别低于 0.6 秒，会占满 adb
        self._retry = max(1000, int(retry_ms))
        self._alive = True
        self._paused = False
        self._last_png = None
        self._info = None
        self._phone = None
        self._state = dict(NOT_CONNECTED)
        self._fail_streak = 0
        self._ok_streak = 0
        # ★ 命令队列：所有"动手"的操作（点击/返回/主页…）都排在这里，
        #   由**同一个线程**按顺序执行 —— 天然不会和截图抢数据线。
        self._cmds = deque()
        self._tick = 0
        self.setObjectName("DeviceHub")

    # --------------------------------------------------------
    # ★★ 动手（第 28 轮）：点画面 = 点手机
    #
    #   为什么不直接调 phone.tap()：
    #     phone 对象只归后台线程用。如果主线程也去调它，
    #     两个线程会同时抢 adb（截图和点击撞一起 → 都失败）。
    #   所以：界面只管**往队列里丢命令**，由后台线程按顺序执行。
    #     天然串行，永远不会抢。
    # --------------------------------------------------------
    def tap(self, x, y):
        """点手机屏幕的 (x, y)，单位是**手机真实像素**（如 1080×2400 里）。"""
        self._cmds.append(("tap", int(x), int(y)))

    def swipe(self, x1, y1, x2, y2, ms=300):
        self._cmds.append(("swipe", int(x1), int(y1), int(x2), int(y2), int(ms)))

    def back(self):
        self._cmds.append(("back",))

    def home(self):
        self._cmds.append(("home",))

    def wake(self):
        self._cmds.append(("wake",))

    def busy(self):
        return bool(self._cmds)

    # --------------------------------------------------------
    # 对外接口
    # --------------------------------------------------------
    def run(self):
        import sys
        import os
        # 让子线程也能 import phone（打包成 exe 后路径不同）
        src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if src not in sys.path:
            sys.path.insert(0, src)

        from phone import Phone, PhoneError

        if self._phone is None:
            self._phone = Phone()

        while self._alive:
            # ---- ① 手机还连着吗（每 5 轮查一次，别每帧都问 adb） ----
            self._tick += 1
            if self._tick % 5 == 1 or self._fail_streak:
                try:
                    self._phone.connect()
                except PhoneError as e:
                    self._go_offline(str(e))
                    self._sleep(self._retry)
                    continue
                except Exception as e:
                    self._go_offline("读手机出错：%s" % str(e)[:48])
                    self._sleep(self._retry)
                    continue

                # 刚连上：读一次设备信息
                if self._info is None:
                    try:
                        self._info = self._phone.device_info()
                    except Exception as e:
                        self._info = dict(NOT_CONNECTED)
                        self._info["why"] = "读设备信息失败：%s" % str(e)[:40]
                    self._emit_status(True)

            # ---- ② ★ 先干"动手"的活（点击 / 返回 / 主页…） ----
            #   动作排在最前面执行，做完立刻截图 —— 用户点一下马上看到变化。
            if self._cmds:
                self._do_cmd()
                self._shot_once()
                continue

            # ---- ③ AI 在干活时，投屏让路（不抢 adb） ----
            if self._paused:
                self._sleep(200)
                continue

            # ---- ④ 拍一帧 ----
            self._shot_once()
            self._sleep(self._interval)

    # --------------------------------------------------------
    def _shot_once(self):
        try:
            png = self._phone.screenshot_bytes(retries=3)
        except Exception as e:
            self._fail("截图失败：%s" % str(e)[:44])
            return

        self._ok_streak += 1
        self._fail_streak = 0
        self._last_png = png

        # ★ 转小图再发给界面
        #   2.5MB 的 PNG 每 2 秒跨线程拷一次，长期跑是浪费。
        #   缩到 1/4 尺寸 + JPEG 后只有 ~37KB，给人看足够了。
        #   （AI 看图走的是**另一条通道**，拿的仍是原始高清图，不受影响）
        small = _shrink(png)
        self.frame.emit(small if small else png)

    def _do_cmd(self):
        """执行队列里的一个命令。全在这个线程里跑，所以天然串行、不抢 adb。"""
        if not self._cmds:
            return
        cmd = self._cmds.popleft()
        name = cmd[0]
        try:
            if name == "tap":
                self._phone.tap(cmd[1], cmd[2])
                self.acted.emit("点了手机屏幕")
            elif name == "swipe":
                self._phone.swipe(cmd[1], cmd[2], cmd[3], cmd[4], cmd[5])
                self.acted.emit("划了一下")
            elif name == "back":
                self._phone.back()
                self.acted.emit("按了返回")
            elif name == "home":
                self._phone.home()
                self.acted.emit("回到手机桌面")
            elif name == "wake":
                self._phone.wake()
                self.acted.emit("点亮了屏幕")
            else:
                self.acted.emit("不认识的动作")
        except Exception as e:
            self.acted.emit("没做成：%s" % str(e)[:40])
        # 动作后停一下：让手机把界面画完，再截图才拍得到变化
        self.msleep(360)

    # --------------------------------------------------------
    def pause(self):
        """
        让投屏先停一下（AI 要用 adb 干活时调用）。
        ★ 规格书 1.10.6：投屏只管给人看，AI 另拍照 —— 两者抢 adb，要让路。
        """
        self._paused = True

    def resume(self):
        self._paused = False

    def stop(self):
        self._alive = False
        self.wait(3000)

    def last_png(self):
        """最近一帧（界面重画时用，不用等下一帧）。"""
        return self._last_png

    def state(self):
        return dict(self._state)

    def is_connected(self):
        return bool(self._state.get("connected"))

    def device_info(self):
        return dict(self._info) if self._info else dict(NOT_CONNECTED)

    def poke(self):
        """催一下：立刻重连 + 重拍（用户点「检测连接」时用）。"""
        self._info = None

    # --------------------------------------------------------
    # 内部
    # --------------------------------------------------------
    def _go_offline(self, why):
        changed = self._state.get("connected") or self._state.get("why") != why
        self._info = None
        s = dict(NOT_CONNECTED)
        s["why"] = why
        self._state = s
        if changed:
            self.status.emit(dict(self._state))

    def _fail(self, why):
        """
        截图失败。

        ★ 别一次失败就喊"手机断了"（实测偶发失败很常见：adb 忙、手机卡一下）。
          规则：**连着失败 3 次**才认定断开，否则只记一笔、继续试。
          这样顶栏不会因为一次抖动就闪一条黄条吓唬用户。
        """
        self._fail_streak += 1
        if self._fail_streak < 3:
            return
        self._go_offline(why)

    def _emit_status(self, ok):
        info = self._info or {}
        s = {
            "connected": bool(ok),
            "serial": info.get("serial", "—"),
            "model": info.get("model", "—"),
            "brand": info.get("brand", "—"),
            "android": info.get("android", "—"),
            "width": info.get("width", "—"),
            "height": info.get("height", "—"),
            "density": info.get("density", "—"),
            "why": "",
        }
        self._state = s
        self.status.emit(dict(s))

    def _sleep(self, ms):
        """分段睡 —— 这样 stop() 能很快生效，不用等一整轮。"""
        step = 100
        left = int(ms)
        while left > 0 and self._alive:
            self.msleep(min(step, left))
            left -= step


# ============================================================
# 单例（全软件就一个，别开第二个 —— 两个线程抢 adb 会互相打架）
# ============================================================
_HUB = None


def get_hub():
    global _HUB
    if _HUB is None:
        _HUB = DeviceHub()
    return _HUB


def start_hub():
    hub = get_hub()
    if not hub.isRunning():
        hub.start()
    return hub


def stop_hub():
    global _HUB
    if _HUB is not None and _HUB.isRunning():
        _HUB.stop()
    _HUB = None
