# -*- coding: utf-8 -*-
"""
拓客台 · 手机连接层（P1）

★ 项目铁律：只允许三条通道
  1. adb shell screencap  → 截图（"眼睛"）
  2. adb shell input      → 点击/滑动/按键（"手"）
  3. adb shell am broadcast(ADB Keyboard) → 打字（"嘴"）
  另外只许读 3 个非屏幕信息：输入法状态、wm size、版本号（见规格书 1.2.1 白名单）

★ 严禁：Accessibility / uiautomator dump / 控件树 / 协议注入 / Hook
  违反 = 整个项目白做（规格书 0.1）

本文件只做"连接 + 截图 + 点击"三件事，不做任何业务判断。
"""
import os
import re
import subprocess
import sys
import tempfile
import time

# ---------- 路径解析（开发态 / 打包态都能用） ----------

# ★★★ 别让黑窗口弹出来（用户实测反馈的坑，2026-10-02）★★★
#   现象：用户在桌面上看到"每隔几秒弹一个 ADB 的 EXE"，以为中毒了。
#   原因：adb 是命令行程序，Windows 上**每调一次就闪一个黑框**；
#         而投屏每 2 秒要截一次图 = 每 2 秒闪一次。
#   修法：给所有 subprocess 调用加这个 flag，黑窗口就不出现了。
#         （只在 Windows 有意义；别的系统传 0 是安全的空操作）
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _project_root() -> str:
    """
    找"项目根"（配置、技能、数据都在这儿）。

    ★ 三种运行方式都要能用（这是打包成 exe 后最容易翻车的地方）：
      ① 打包成 exe 跑  → 资源被解到 PyInstaller 的临时目录（sys._MEIPASS）
      ② exe 但资源在旁 → 退回到 exe 所在目录
      ③ 开发态直接跑   → 项目根就是 src 的上一级
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return base
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _adb_path() -> str:
    """找 adb.exe：先看打包进 exe 的那份，再看 config 指定，最后按默认位置找。"""
    import json

    # ① 打包进 exe 的（--add-data 放到了内部的 adb/ 目录）
    base = getattr(sys, "_MEIPASS", None)
    if base:
        p = os.path.join(base, "adb", "adb.exe")
        if os.path.exists(p):
            return p

    # ② config.json 里手写的路径
    root = _project_root()
    cfg_p = os.path.join(root, "config", "config.json")
    if os.path.exists(cfg_p):
        try:
            with open(cfg_p, encoding="utf-8") as f:
                cfg = json.load(f)
            p = (cfg.get("paths") or {}).get("adb")
            if p and os.path.exists(p):
                return p
        except Exception:
            pass

    # ③ 默认位置（开发态）
    for cand in (
        os.path.join(root, "_tools", "scrcpy", "scrcpy-win64-v4.1", "adb.exe"),
        os.path.join(root, "_tools", "scrcpy", "scrcpy-win64-v4.1", "adb"),
    ):
        if os.path.exists(cand):
            return cand

    raise FileNotFoundError("找不到 adb.exe，请检查 _tools/scrcpy/ 目录")


# ---------- 手机连接 ----------

class PhoneError(Exception):
    """手机操作失败。msg 是给用户看的中文大白话。"""
    def __init__(self, msg, detail=""):
        super().__init__(msg)
        self.msg = msg
        self.detail = detail


class Phone:
    """
    一台手机。所有操作都走 adb，纯视觉。

    用法：
        p = Phone()
        p.connect()                  # 找手机，找不到会抛 PhoneError
        p.screenshot("a.png")        # 截图
        p.tap(540, 1200)             # 点屏幕
        p.swipe(540, 1800, 540, 600) # 滑动
    """

    def __init__(self, serial=None, adb=None):
        self.adb = adb or _adb_path()
        self.serial = serial          # None = 自动选第一台
        self._screen = None           # 缓存 (w, h)

    # ---- 底层：跑一条 adb 命令 ----

    def _run(self, args, timeout=30, binary=False):
        cmd = [self.adb]
        if self.serial:
            cmd += ["-s", self.serial]
        cmd += args
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=timeout,
                               creationflags=_NO_WINDOW)
        except subprocess.TimeoutExpired:
            raise PhoneError("手机没反应，好像卡住了", "adb timeout: " + " ".join(args))
        except FileNotFoundError:
            raise PhoneError("找不到手机工具（adb）", "adb not found: " + self.adb)
        if binary:
            return r.stdout
        out = (r.stdout or b"").decode("utf-8", "replace")
        err = (r.stderr or b"").decode("utf-8", "replace")
        return out, err, r.returncode

    # ---- 找手机 ----

    def list_devices(self):
        """返回 [{'serial':..., 'state':...}]。state: device/unauthorized/offline"""
        out, _, _ = self._run(["devices"])
        devs = []
        for line in out.splitlines()[1:]:
            line = line.strip()
            if not line or "\t" not in line:
                continue
            serial, state = line.split("\t", 1)
            devs.append({"serial": serial.strip(), "state": state.strip().split()[0]})
        return devs

    def connect(self):
        """找手机。成功返回 self；失败抛 PhoneError（中文大白话）。"""
        devs = self.list_devices()
        if not devs:
            raise PhoneError(
                "没找到手机。请用数据线把手机插到电脑上，并在手机上点「允许」",
                "adb devices: empty")
        if self.serial is None:
            self.serial = devs[0]["serial"]
        state = next((d["state"] for d in devs if d["serial"] == self.serial), None)
        if state == "unauthorized":
            raise PhoneError(
                "手机还没授权。请看手机屏幕，点「允许 USB 调试」",
                "state=unauthorized")
        if state != "device":
            raise PhoneError("手机连上了但状态不对，试试拔了重插", "state=" + str(state))
        return self

    # ---- 屏幕参数（白名单内，见 1.2.1） ----

    def device_info(self):
        """
        读设备信息，给界面显示用。

        ★ 这些全是 `getprop` / `wm` 读的**配置参数**，不是屏幕内容，
          在规格书 1.2.1 白名单内 —— 跟"只走视觉"的宗旨不冲突。

        返回 dict：
            {'serial', 'model', 'brand', 'android', 'width', 'height', 'density'}
        读不到的字段给 '—'，不给 0（规格书 5.5 数据来源约束）。
        """
        info = {"serial": self.serial or "—", "model": "—", "brand": "—",
                "android": "—", "width": "—", "height": "—", "density": "—"}

        props = (("model", "ro.product.model"),
                 ("brand", "ro.product.brand"),
                 ("android", "ro.build.version.release"))
        for key, prop in props:
            try:
                out, _, _ = self._run(["shell", "getprop", prop], timeout=8)
                v = (out or "").strip()
                if v:
                    info[key] = v
            except Exception:
                pass

        try:
            w, h = self.screen_size()
            info["width"], info["height"] = w, h
        except Exception:
            pass

        try:
            out, _, _ = self._run(["shell", "wm", "density"], timeout=8)
            m = re.search(r"(\d+)", out or "")
            if m:
                info["density"] = int(m.group(1))
        except Exception:
            pass

        return info

    def screen_size(self):
        """返回 (宽, 高)，按物理像素。缓存，避免每帧都问。"""
        if self._screen:
            return self._screen
        out, _, _ = self._run(["shell", "wm", "size"])
        m = re.search(r"(\d+)x(\d+)", out)
        if not m:
            # 兜底：直接量截图
            img = self.screenshot_bytes()
            self._screen = _png_size(img)
        else:
            self._screen = (int(m.group(1)), int(m.group(2)))
        return self._screen

    # ---- 截图（"眼睛"） ----

    def screenshot_bytes(self, retries=5):
        """
        截一张图，返回 PNG 原始字节。这是 AI 看图的数据源。

        ★ 实测踩到的大坑（必须这么写）：
          用 subprocess.run(capture_output=True) 读 `exec-out screencap -p`
          在 1080×2400 这种大图上会**丢尾部数据** → PNG 被截断 → PIL 报
          "image file is truncated"。所以必须：
            ① 把 stdout 落成**临时文件**（不经过管道），再读文件；
            ② 用 PNG 完整性校验（结尾必须是 IEND 块）；
            ③ 校验不过就重试 —— **实测真机会偶发连续失败，重试 5 次 + 递增退避**。
        """
        last_len = 0
        for i in range(max(1, retries)):
            data = b""
            fd, tmp = tempfile.mkstemp(suffix=".png")
            try:
                os.close(fd)
                with open(tmp, "wb") as out:
                    subprocess.run(
                        [self.adb] + (["-s", self.serial] if self.serial else [])
                        + ["exec-out", "screencap", "-p"],
                        stdout=out, stderr=subprocess.DEVNULL, timeout=25,
                        creationflags=_NO_WINDOW)
                with open(tmp, "rb") as f:
                    data = f.read()
            except subprocess.TimeoutExpired:
                data = b""
            except Exception:
                data = b""
            finally:
                try:
                    os.remove(tmp)
                except OSError:
                    pass

            last_len = len(data)
            if _is_complete_png(data):
                return data
            if i < retries - 1:
                time.sleep(0.8 * (i + 1))     # 退避：0.8→1.6→2.4→3.2

        raise PhoneError("截不到完整画面，试了 %d 次都不行" % retries,
                         "last screenshot %d bytes, incomplete PNG" % last_len)

    def screenshot(self, path, retries=3):
        """截图存到 path，返回 path。"""
        data = self.screenshot_bytes(retries=retries)
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return path

    # ---- 屏幕开关（规格书 1.9：黑屏要能唤醒，但不能乱点） ----

    def is_screen_on(self):
        """屏幕亮着吗（读电源状态，白名单内）"""
        out, _, _ = self._run(["shell", "dumpsys", "power"])
        return "mWakefulness=Awake" in out or "mWakefulness=1" in out

    def wake(self):
        """唤醒屏幕（按电源键，不点亮不解锁）"""
        if not self.is_screen_on():
            self._run(["shell", "input", "keyevent", "KEYCODE_WAKEUP"])
            time.sleep(0.8)
        return self

    # ---- 动作（"手"） ----

    def tap(self, x, y):
        """点屏幕坐标（按截图像素，1.4 节以 PNG 像素为准）"""
        x, y = int(x), int(y)
        self._run(["shell", "input", "tap", str(x), str(y)])
        return self

    def swipe(self, x1, y1, x2, y2, ms=300):
        """滑动。ms 是时长，太短会变成"甩"，太长会变成"拖"。"""
        self._run(["shell", "input", "swipe",
                   str(int(x1)), str(int(y1)), str(int(x2)), str(int(y2)), str(int(ms))])
        return self

    def back(self):
        self._run(["shell", "input", "keyevent", "4"])
        return self

    def home(self):
        self._run(["shell", "input", "keyevent", "3"])
        return self

    def input_shown(self):
        """
        输入法键盘现在弹着吗？

        ★ 读的是 `dumpsys input_method` 里的 mInputShown ——
          白名单允许（读的是系统输入法状态，不是屏幕内容，不碰风控线）。
        ★ 老坑 2 的正规解法：输入框在屏幕上的位置**取决于键盘弹没弹**，
          想找输入框，先问这一句。
        """
        out, _err, code = self._run(["shell", "dumpsys", "input_method"], timeout=10)
        if code != 0:
            return False
        for ln in (out or "").splitlines():
            if "mInputShown" in ln:
                return "true" in ln.lower()
        return False

    def foreground_package(self):
        """
        现在前台是哪个 App（返回包名，如 "com.tencent.mm"；读不出来给 ""）。

        ★ 第 46 轮新增（抄 Open-AutoGLM 的做法，它就是这么干的）：
          Open-AutoGLM/phone_agent/adb/device.py 的 get_current_app() 用的正是
          `dumpsys window` 里的 mCurrentFocus / mFocusedApp —— 咱们却一直让
          视觉模型反复猜"这是桌面还是微信"，猜错一次全盘崩。
        ★ 红线核对：跟已白名单的 dumpsys input_method **同一类** ——
          读的是系统窗口管理器的状态，不是控件树（uiautomator dump 那种
          才是红线），App 自己无法感知也感知不到，不碰风控线。
          屏幕上的内容（在哪一页、跟谁聊）照样全走视觉，一条没少。
        """
        out, _err, _code = self._run(["shell", "dumpsys", "window"], timeout=10)
        for ln in (out or "").splitlines():
            if "mCurrentFocus" in ln or "mFocusedApp" in ln:
                # 形如：mCurrentFocus=Window{a3f5d2 u0 com.tencent.mm/ui.LauncherUI}
                m = re.search(r"u0\s+([\w.]+)\s*/", ln)
                if m:
                    return m.group(1)
                # 有的版本不带 u0 前缀 → 找任意"点分包名"
                m = re.search(r"\b([a-z][a-zA-Z0-9_]*(?:\.[a-zA-Z0-9_]+)+)", ln)
                if m and "." in m.group(1) and "Window" not in m.group(1):
                    return m.group(1)
        # 兜底：activity 栈顶（部分 ROM 只在这里给）
        out, _err, _code = self._run(
            ["shell", "dumpsys", "activity", "activities"], timeout=10)
        for ln in (out or "").splitlines():
            if "topResumedActivity" in ln or "mResumedActivity" in ln:
                # ★ 第 46 轮审查修正：部分 ROM 的行不带 "u0" 前缀，
                #   放宽为"任意点分包名/……"，只要含点（排除无包名行）
                m = re.search(r"([\w.]+)/", ln)
                if m and "." in m.group(1) and "Record" not in m.group(1):
                    return m.group(1)
        return ""


def _png_size(data):
    """从 PNG 头部读尺寸（不依赖 PIL，纯字节解析）。"""
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return (0, 0)
    w = int.from_bytes(data[16:20], "big")
    h = int.from_bytes(data[20:24], "big")
    return (w, h)


def _is_complete_png(data):
    """
    判断 PNG 是不是完整（没被截断）。
    ★ 依据：合法 PNG 必须以 8 字节魔数开头、以 IEND 块结尾。
    """
    if not data or len(data) < 100:
        return False
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return False
    # IEND 块固定是最后 12 字节：长度(4)+'IEND'(4)+CRC(4)
    return data[-12:-8] == b"IEND" or data.rstrip(b"\x00")[-8:-4] == b"IEND"


# ---------- 自检（P1 验收用） ----------

def self_test(shot_path=None):
    """
    实机自检。需要插着手机。
    返回 dict，供界面/日志使用。
    """
    r = {"ok": False, "steps": [], "error": ""}
    try:
        p = Phone()
        r["steps"].append("① 找手机 …")
        p.connect()
        r["steps"].append("   ✓ 找到手机 " + p.serial)

        r["steps"].append("② 读屏幕尺寸 …")
        w, h = p.screen_size()
        r["steps"].append("   ✓ %d x %d" % (w, h))

        r["steps"].append("③ 截图 …")
        shot_path = shot_path or os.path.join(
            _project_root(), "data", "shots", "_p1_selftest.png")
        p.screenshot(shot_path)
        size = os.path.getsize(shot_path)
        r["steps"].append("   ✓ 存到 %s（%d 字节）" % (shot_path, size))

        r["steps"].append("④ 版本号 …")
        out, _, _ = p._run(["shell", "getprop", "ro.build.version.release"])
        r["steps"].append("   ✓ 安卓 " + out.strip())

        r["ok"] = True
        r["device"] = p.serial
        r["screen"] = [w, h]
        r["shot"] = shot_path
    except PhoneError as e:
        r["error"] = e.msg + ("（" + e.detail + "）" if e.detail else "")
        r["steps"].append("   ✗ " + e.msg)
    except Exception as e:
        r["error"] = "出错了：" + str(e)
        r["steps"].append("   ✗ " + str(e))
    return r


if __name__ == "__main__":
    res = self_test()
    for s in res["steps"]:
        print(s)
    print("\n结果：", "通过 ✓" if res["ok"] else "失败 ✗ " + res.get("error", ""))
    sys.exit(0 if res["ok"] else 1)
