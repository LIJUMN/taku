# -*- coding: utf-8 -*-
"""
Taku · AI 干活的过程（AgentRunner）

★ 干什么：
    后台跑一轮"看消息 → 想回复 → 打字 → 发送 → 验证"，
    **每一步都实时送到界面上** —— 用户能看着 AI 干活，
    而不是对着一个转圈的加载图标干等。

★ 为什么要有它（而不是让界面直接调 ChatLoop）：
    1. ChatLoop 跑起来要十几秒到一分钟，放主线程界面就冻住了 → 必须后台线程
    2. 用户要"看得见" → 每一步都得往外报
    3. AI 干活时**投屏必须让路**（规格书 1.10.6），这需要人统一管

★★★ 三条铁规矩（规格书里的，不能破）★★★
    ① **AI 干活时投屏让路** —— 两条通道抢同一根数据线，必须一个停一个走
    ② **全程留痕**（决策 #21）—— 每一步的截图都存进 data/shots/ai_runs/
    ③ **默认试跑**（P35）—— 只把字打进输入框、**不点发送**，
       让用户亲眼看见"AI 打算说什么"，他点头才真发

★ 试跑模式为什么这么设计：
    现在是凌晨，用户的朋友可能在线。**AI 真发出去的话，是真实的社交行为**，
    收不回来。所以第一版一律试跑：看得见、摸得着、但零风险。
"""

import os
import time
from datetime import datetime

from PySide6.QtCore import QThread, Signal


# ============================================================
# 8 个步骤（跟规格书"8 步 / 120 秒硬闸"对齐）
# ============================================================
STEPS = [
    "看一眼手机",
    "认清这是哪个 App",
    "读最近的对话",
    "想一句回复",
    "找输入框在哪",
    "把字打进去",
    "发送",
    "确认发出去了",
]

# 硬闸：一轮最多跑这么久（规格书 1.8）
# ★ 2026-10-02 放宽：加了「AI 自己认路」（回桌面→开 App→搜人→进聊天页），
#   光认路就可能花 1~2 分钟，原来 120 秒会在半路拉警报。
MAX_SECONDS = 300


def _shots_dir():
    """留痕目录：data/shots/ai_runs/"""
    here = os.path.dirname(os.path.abspath(__file__))          # src/ui
    root = os.path.dirname(os.path.dirname(here))              # 项目根
    d = os.path.join(root, "data", "shots", "ai_runs")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


class AgentRunner(QThread):
    """
    跑一轮 AI 干活，全程报进度。

    信号：
      step(dict)  每一步的状态
                  {no, total, name, state, detail, shot}
                  state: running 正在做 / ok 成了 / fail 没成 / wait 停下等人
      done(dict)  本轮结束
                  {ok, title, summary, reply, shot, shots[]}
    """

    step = Signal(dict)
    done = Signal(dict)

    def __init__(self, dry_run=True, reply_to=None, customer_id=None, parent=None):
        super().__init__(parent)
        self.dry_run = bool(dry_run)
        self.reply_to = reply_to
        # ★ 第 33 轮补：把「这一轮算在哪个客户头上」传下去。
        #   没有它 → ChatLoop 跑完**不落库** → 总览页的数字永远是 0。
        #   （客户页现在还没接库，所以传进来的多半是 None；
        #     客户页接库那一轮，这里就能直接用了。）
        self.customer_id = customer_id
        self._alive = True
        self._t0 = 0.0
        self._shots = []
        self._reply = ""
        self._last_shot = None
        self._run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    # --------------------------------------------------------
    def stop(self):
        self._alive = False

    def _out_of_time(self):
        return (time.time() - self._t0) > MAX_SECONDS

    # --------------------------------------------------------
    # 主循环（跑在后台线程里）
    # --------------------------------------------------------
    def run(self):
        self._t0 = time.time()

        # ★ 第 34 轮：「暂停运行」是个真闸门 —— 按了它，AI 就别想开工。
        #   （规格书 1.10.1：用户叫停是最高优先级，1 秒内停手。）
        try:
            from ui.store import get_store
            if get_store().get_setting("paused", False):
                self.done.emit({
                    "ok": False, "title": "你按了暂停",
                    "summary": "现在 AI 不动手。想让它干活，先回总览页点「继续运行」。",
                    "reply": "", "shot": None, "shots": [],
                })
                return
        except Exception:
            pass

        src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        import sys
        if src not in sys.path:
            sys.path.insert(0, src)

        from ui import device_hub

        hub = device_hub.get_hub()
        hub.pause()            # ★ 规矩①：AI 干活，投屏让路
        try:
            self._run_once()
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.done.emit({
                "ok": False, "title": "出错了",
                "summary": str(e)[:200], "reply": "", "shot": None,
                "shots": list(self._shots),
            })
        finally:
            hub.resume()       # 干完把投屏放回来

    def _run_once(self):
        from tt_loop_chat import ChatLoop

        # ★★★ 认路的依据（2026-10-02 用户拍板）★★★
        #   客户档案里写着 platform（wechat/momo/soul）+ 昵称 ——
        #   把它们传给 ChatLoop，AI 就自己走到那个 App 的聊天页，
        #   不再弹窗叫用户"先用手切过去"。
        target_app, contact_name = None, None
        if self.customer_id is not None:
            try:
                from tt_db import TuokeDB
                row = TuokeDB().get_customer(self.customer_id)
                if row:
                    d = dict(row)
                    target_app = (d.get("platform") or "").strip() or None
                    contact_name = (d.get("nickname") or "").strip() or None
            except Exception:
                pass

        loop = ChatLoop(on_step=self._on_step, verbose=True)
        rep = loop.run_once(dry_run=self.dry_run, reply_to=self.reply_to,
                            customer_id=self.customer_id,
                            target_app=target_app, contact_name=contact_name)

        self._reply = rep.get("reply", "") or ""

        if rep.get("ok"):
            if self.dry_run and rep.get("typed"):
                title = "想好了，等你点头"
                summary = "AI 已经把这句话打进手机的输入框了 —— 「%s」\n\n" \
                          "你看着行，就点「让它发出去」；不行就点「不发了」。" % self._reply
            elif rep.get("sent"):
                title = "发出去了"
                summary = "「%s」已经发出，并且回读确认过气泡出现了。" % self._reply
            else:
                title = "做完了"
                summary = rep.get("why", "")
        else:
            title = "这一轮没跑完"
            summary = rep.get("why") or rep.get("error") or "原因不明"

        # ★ 干完活 → 让统计缓存作废，界面上的数字立刻跟着变
        #   （不然要等 datasource 的 3 秒缓存过期，用户会以为"没反应"）
        try:
            from ui import datasource as DS
            DS.invalidate()
        except Exception:
            pass

        self.done.emit({
            "ok": bool(rep.get("ok")),
            "dry_run": self.dry_run,
            "title": title,
            "summary": summary,
            "reply": self._reply,
            "heard": rep.get("heard", ""),
            "app": rep.get("app", ""),
            "shot": self._last_shot,
            "shots": list(self._shots),
        })

    # --------------------------------------------------------
    # 收进度（ChatLoop 每做一步喊一声）
    # --------------------------------------------------------
    def _on_step(self, no, name, state, detail="", png=None):
        if not self._alive:
            return

        shot_path = None
        if png:
            shot_path = self._save_shot(png, no, state)
            self._last_shot = png

        # 超时硬闸：到点了就提醒（不硬杀，让当前这一步做完）
        if self._out_of_time() and state == "running":
            detail = (detail + "  ⚠ 已经跑超过 %d 秒了" % MAX_SECONDS).strip()

        self.step.emit({
            "no": int(no),
            "total": len(STEPS),
            "name": name,
            "state": state,
            "detail": detail,
            "shot": shot_path,
            "elapsed": time.time() - self._t0,
        })

    def _save_shot(self, png, no, state):
        """★ 规矩②：每一步都留痕（以后要能回看 AI 当时看到了什么）。"""
        try:
            fn = os.path.join(_shots_dir(),
                              "%s_%02d_%s.png" % (self._run_id, no, state))
            with open(fn, "wb") as f:
                f.write(png)
            self._shots.append(fn)
            return fn
        except Exception:
            return None

    _last_shot = None


class SendWorker(QThread):
    """
    只干一件事：把已经在输入框里的那句话发出去。

    ★ 为什么单独一个线程：发送要"点按钮 + 回读验证 + 最多重试 3 次"，
      整个过程十几秒，放主线程界面会冻住。
    ★ 为什么不让 AgentRunner 干：AgentRunner 是"从头跑一轮"；
      这里是"接着刚才那一步往下走"，两回事。
    """

    done = Signal(bool, str)

    def __init__(self, reply, parent=None):
        super().__init__(parent)
        self._reply = reply

    def run(self):
        src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        import sys
        if src not in sys.path:
            sys.path.insert(0, src)

        # ★ 第 34 轮：发送也是一样的总闸 —— 暂停时不许发。
        try:
            from ui.store import get_store
            if get_store().get_setting("paused", False):
                self.done.emit(False, "你按了暂停 —— 先点「继续运行」再发")
                return
        except Exception:
            pass

        from ui import device_hub
        hub = device_hub.get_hub()
        hub.pause()            # 规矩①：AI 干活，投屏让路
        try:
            from phone import Phone
            from vision import VisionEngine
            from tt_send import Sender

            ph = Phone().connect()
            s = Sender(ph, VisionEngine())
            r = s.send_and_verify(self._reply)
            self.done.emit(bool(r.get("ok")), r.get("how", "") or "")
        except Exception as e:
            self.done.emit(False, str(e)[:100])
        finally:
            hub.resume()
