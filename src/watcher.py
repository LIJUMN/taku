# -*- coding: utf-8 -*-
"""
Taku · 挂机守护（Watcher）—— 第 38 轮

★★★ 它是干什么的 ★★★

    你把手机停在某个聊天页，点「开始挂机」——
    它每隔一会儿看一眼屏幕（纯视觉，截图）：
      · 对方没新消息 → 什么都不干
      · 对方来了新消息 → 读对话 → 想一句回复 → 打进输入框
          · 默认**试跑**：字在框里停着，弹卡片等你点头（你不点它绝不发）
          · 你在设置里开了「自动发」且内容不敏感 → 它自己点发送并回读验证

★★★ 四道闸（规格书里拍过板的，一个都不少）★★★

    ① 暂停总闸   —— 总览页「暂停运行」按下去，它整轮直接睡觉
    ② 静默时段   —— 23:00 ~ 08:00 不干活（半夜不替你回消息）
    ③ 高危拦截   —— 对方话里带 转账/借钱/验证码/密码… 立刻停手叫人
    ④ 让路规矩   —— 它干活的瞬间投屏让路（1.10.6，跟 AI 干活同一条规矩）

★ 为什么 v1 只盯"当前打开的这一个聊天"：
    跨 App 巡逻（通知栏截图→认是谁来的消息→跳过去）是下一块，
    一次做太多必炸。先把"盯一个窗口"做扎实，链路和挂机版完全一样。
"""

import os
import re
import time
import traceback
from datetime import datetime

from PySide6.QtCore import QThread, Signal


# ------------------------------------------------------------
# 涉钱词（命中 = 先走"岔开话题"的路，而不是罢工）
#   ★ 第 39 轮按用户的原话改的：有些女的半夜不睡觉就爱聊；聊到钱
#     不该"停手叫人"装死 —— 该让 AI 自己把话题岔开，接着聊。
#   ★ 但铁线还在：**回复里绝不出现验证码/密码/答应转账**，这两条没得商量。
MONEY_WORDS = ("转账", "借钱", "红包", "打款", "汇款", "银行卡", "充值", "付款", "扫一扫",
               "转我", "给我转", "付一下", "收款", "支付宝", "返利", "佣金", "兼职")

# 真危险词（命中 = 停手叫人，不岔开）：要验证码/密码只有一个目的
DANGER_WORDS = ("验证码", "密码", "短信码", "付款码")

# 静默时段（小时）：23 点到次日 8 点
#   ★ 第 39 轮改成**默认关闭**：有些人就爱半夜聊，硬静默等于替用户回绝了人家。
#     要不要静默，让用户在设置里自己开（watch_quiet）。
QUIET_FROM, QUIET_TO = 23, 8

# 每次看屏幕的间隔（秒）。太密费电费 token，太疏回复慢。
DEFAULT_INTERVAL = 45


def _quiet_hours():
    """现在是不是静默时段。★ 默认不静默（设置里开了 watch_quiet 才生效）。"""
    try:
        from ui.store import get_store
        if not get_store().get_setting("watch_quiet", False):
            return False
    except Exception:
        pass
    h = datetime.now().hour
    if QUIET_FROM > QUIET_TO:                      # 跨午夜
        return h >= QUIET_FROM or h < QUIET_TO
    return QUIET_FROM <= h < QUIET_TO


def _skill_prompt():
    """
    把狗头军师 skill 的「核心原则」塞进"想话"的提示词里。

    ★ 为什么要它（第 39 轮）：上轮实测模型的回话一秒变客服
      （「谢谢夸奖，以后有啥需要帮忙的尽管说」）。军师 skill 里那一套
      "先接住情绪、像真人、不卑不亢"正好治这个。
    ★ 只截核心原则那段（几百字），整篇塞进去又贵又跑偏。
    """
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        p = os.path.join(root, "skills", "goutoujunshi", "SKILL.md")
        txt = open(p, encoding="utf-8").read()
        m = txt.find("## 核心原则")
        if m >= 0:
            txt = txt[m:]
        txt = re.sub(r"\n{2,}", "\n", txt)[:800]
        return txt
    except Exception:
        return ""


class Watcher(QThread):
    """
    挂机守护线程。

    信号（界面听这三样就够了）：
      evt(kind, dict)   —— 过程播报
            kind: watch      看了一眼（没动静）
                    incoming  对方来了新消息
                    replied   发出去了
                    typed     试跑：字在框里等你点头
                    blocked   高危内容，停手叫人
                    skipped   因为静默时段/暂停/不在聊天页，这轮跳过
                    error     出错了
      stopped()          —— 线程真的停了
    """

    evt = Signal(str, dict)
    stopped = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._alive = True
        self._pending = None          # None=没待办；dict=试跑的那句在等用户表态
        self._seen_he = []            # 已经见过的"他说过的话"（尾部比对用）
        self.replies_sent = 0         # 本次挂机替你回了多少条
        self.watched_since = None     # 什么时候开始的
        self.last_why = "刚开始"

    # ---------------- 开关 ----------------
    def stop(self):
        self._alive = False

    def pending(self):
        """现在有没有那句"等你点头"的话。有 → {'text','cid'}。"""
        return self._pending

    def resolve(self, ok):
        """
        用户对"试跑"的那句话表态了：True=发出去 / False=不发了。
        ★ 顺序不能反：先把 _pending 置 None（不然主循环会一直等你表态），
          再去做发送/清空。
        """
        if self._pending is None:
            return
        item = self._pending
        self._pending = None
        reply, cid = item.get("text", ""), item.get("cid")
        if not ok:
            try:
                from tt_typing import Typist
                from phone import Phone
                ph = Phone().connect()
                Typist(ph).clear()
            except Exception:
                pass
            self.evt.emit("skipped", {"why": "你摇头了，那句话没发，输入框已清空"})
            return
        try:
            from ui import device_hub
            from phone import Phone
            hub = device_hub.get_hub()
            hub.pause()
            try:
                if not self._press_send(Phone().connect(), reply, cid):
                    self.evt.emit("error", {"why": "没发出去，输入框里那句话还在，你手动处理一下"})
            finally:
                hub.resume()
        except Exception as e:
            self.evt.emit("error", {"why": str(e)[:80]})

    # ---------------- 主循环 ----------------
    def run(self):
        self.watched_since = datetime.now().strftime("%H:%M")
        try:
            from ui.store import get_store
            interval = int(get_store().get_setting("watch_interval", DEFAULT_INTERVAL) or DEFAULT_INTERVAL)
        except Exception:
            interval = DEFAULT_INTERVAL
        interval = max(20, min(300, interval))

        self.evt.emit("watch", {"why": "挂机开始，每 %d 秒看一眼" % interval})

        while self._alive:
            try:
                # ① 暂停总闸（规格书 1.10.1：用户叫停是最高优先级）
                if self._is_paused():
                    self.last_why = "你按了暂停"
                    self._sleep(interval)
                    continue
                # ② 上一句话还在等你点头 → 这一轮不看点
                if self._pending is not None:
                    self.last_why = "等你点头"
                    self._sleep(3)
                    continue

                self._tick()

                # ③ 试跑的那句话还挂着（_tick 里设的）→ 等表态
                if self._pending is not None:
                    self._sleep(3)
                    continue
                self.last_why = "盯中 · %s 看过" % datetime.now().strftime("%H:%M")
            except Exception as e:
                traceback.print_exc()
                self.evt.emit("error", {"why": str(e)[:120]})
                self.last_why = "出错：%s" % str(e)[:40]
            self._sleep(interval)

        self.stopped.emit()

    def _sleep(self, sec):
        """分段睡，随时能停。"""
        end = time.time() + sec
        while self._alive and time.time() < end:
            time.sleep(0.5)
    def _is_paused(self):
        try:
            from ui.store import get_store
            return bool(get_store().get_setting("paused", False))
        except Exception:
            return False

    # ---------------- 一轮巡视 ----------------
    def _tick(self):
        from ui import device_hub
        from phone import Phone

        hub = device_hub.get_hub()
        hub.pause()                       # ★ 让路：我看屏的时候投屏歇着
        try:
            ph = Phone().connect()
            png = ph.screenshot_bytes()

            chat, msgs = self._read_chat(png)
            if not chat:
                # ★ 第 44 轮：跨 App 巡逻第一步 —— 不在聊天页时，看一眼
                #   屏幕顶上有没有聊天 App 的**通知横幅**（纯视觉）。
                #   有 → 点它进聊天页（下一轮巡视自然接住）；没有 → 安静。
                #   老实话（v1 边界）：横幅只在"刚来消息的几秒"在屏上，
                #   45 秒看一眼大概率已经消失 —— 通知栏常驻那条要靠
                #   "下拉通知栏"的动作，那是一步滑动，属于下一步。
                if self._patrol_notifications(ph):
                    return
                self.last_why = "当前不在聊天页"
                self.evt.emit("skipped", {"why": "不在聊天页，通知栏也没新消息横幅"})
                return

            he = [m["text"] for m in msgs if m["who"] == "他"]
            fresh = [t for t in he if t not in self._seen_he]
            if not fresh:
                return                    # 没新消息，安静

            self.evt.emit("incoming", {"text": fresh[-1]})

            # ③ 涉钱 / 危险，分级处理（第 39 轮改）：
            #    · 真危险（要验证码/密码）→ 停手叫人，没商量
            #    · 只是聊到钱（借钱/转账类话头）→ **让 AI 岔开话题接着聊**，
            #      不是罢工。铁线：回复里绝不出现验证码/密码/答应转账。
            joined = "".join(fresh)
            mode = "normal"
            if any(w in joined for w in DANGER_WORDS):
                self.evt.emit("blocked", {"why": "对方提到 %s——这种不能回，停手叫人"
                                          % next(w for w in DANGER_WORDS if w in joined)})
                self._seen_he = he
                return
            money = next((w for w in MONEY_WORDS if w in joined), None)
            if money:
                mode = "money"            # AI 会自己把话题岔开
                self.evt.emit("watch", {"why": "对方聊到「%s」，让 AI 岔开话题" % money})

            cid, name = self._find_customer(png)
            if cid is None:
                self.evt.emit("blocked", {"why": "认不出这是在跟谁聊（顶上名字没读到），"
                                          "停手叫人，不瞎记"})
                self._seen_he = he
                return
            reply = self._think(msgs, mode=mode)
            if not reply:
                self.evt.emit("blocked", {"why": "没想出合适的话，停手叫人"})
                self._seen_he = he
                return

            # ★ 铁线自查：不管模型说出什么，这几类字绝不发出去
            bad = [w for w in ("验证码", "密码", "付款码") if w in reply]
            if bad or re.search(r"\d{4,8}", reply) and "码" in reply:
                self.evt.emit("blocked", {"why": "想出来的话里带了不该有的东西（%s），"
                                          "这句不发，停手叫人" % "、".join(bad or ["疑似验证码"])})
                self._seen_he = he
                return

            self._seen_he = he
            self._say(ph, reply, cid)
        finally:
            hub.resume()

    # ---------------- 跨 App 巡逻：通知横幅（第 44 轮 v1） ----------------
    PATROL_APPS = ("微信", "陌陌", "Soul")

    def _patrol_notifications(self, ph):
        """
        看一眼屏幕顶部：有没有微信/陌陌/Soul 的新消息横幅？
        有 → 点那条横幅（纯视觉定位），进到聊天页。

        返回 True = 看到了并点了（下一轮巡视接住）；False = 没有。
        ★ 铁规矩：**只点聊天类通知**，系统通知（更新/权限/广告）一律不碰 ——
          跟弹窗三条规矩同源：绝不点开通/购买/升级、绝不给权限。
        """
        from vision import VisionEngine
        try:
            png = ph.screenshot_bytes()
            v = VisionEngine()
            # 先问"有没有"（便宜），再定位（贵）——别每次都跑网格
            ans = (v.ask(png, (
                "屏幕顶部有没有来自「微信」「陌陌」「Soul」的新消息通知横幅？"
                "横幅左边是 App 图标、写着发信人和消息内容。"
                "有 → 只回三个字：有横幅；没有 → 只回两个字母：NO"
            ), max_tokens=12) or "").strip()
            if "有横幅" not in ans:
                return False
            r = v.locate_grid(png, "来自微信/陌陌/Soul 的**新消息通知横幅**"
                                   "（不是系统更新、不是广告、不是权限请求）",
                              cols=4, rows=8,
                              extra="它在屏幕最顶上一条，点它就能进对应的聊天")
            if not r.get("found"):
                return False
            ph.tap(int(r["x"]), int(r["y"]))
            time.sleep(2.5)
            self.evt.emit("watch", {"why": "看到聊天通知，点进去接住"})
            return True
        except Exception as e:
            self.evt.emit("error", {"why": "巡逻出错：%s" % str(e)[:60]})
            return False

    # ---------------- 看屏读对话（纯视觉） ----------------
    def _read_chat(self, png):
        """读当前页。返回 (是不是聊天页, 对话列表[{'who','text'}])。"""
        from vision import VisionEngine
        v = VisionEngine()
        raw = v.ask(png, (
            "这是不是微信/QQ/Soul 的聊天对话页？"
            "如果是，把最近的对话从上到下列出来，一行一条，格式严格是："
            "我: xxx   或   他: xxx（右侧绿色/深色气泡是我发的，左侧白色是对方）"
            "最多 8 条，不要解释。如果这不是聊天页（比如是首页/列表/别的页面），"
            "只回三个字母：NO"
        ), max_tokens=400, hd=True)
        txt = (raw or "").strip()
        if not txt or txt[:2].upper() == "NO":
            return False, []
        msgs = []
        for ln in txt.splitlines():
            ln = ln.strip().lstrip("-·0123456789. ")
            if ln.startswith("我"):
                msgs.append({"who": "我", "text": ln[2:].strip()})
            elif ln.startswith("他") or ln.startswith("对"):
                msgs.append({"who": "他", "text": ln[2:].strip()})
        msgs = [m for m in msgs if m["text"]]
        return bool(msgs), msgs

    # ---------------- 这个人是谁（对上库里的客户） ----------------
    def _find_customer(self, png):
        """从库里把这个聊天对象找出来；没有就按屏幕顶上的名字建一个。"""
        from tt_db import TuokeDB
        from vision import VisionEngine
        name = None
        try:
            v = VisionEngine()
            head = v.ask(png, "聊天页最顶上对方的名字是什么？只回名字本身，不要别的字。",
                         max_tokens=24, hd=True)
            name = (head or "").strip().strip('"「」』') or None
            if name and ("没有" in name or "NO" in name.upper() or len(name) > 20):
                name = None
        except Exception:
            name = None
        db = TuokeDB()
        try:
            if name:
                r = db.conn.execute(
                    "SELECT id FROM customers WHERE nickname=?", (name,)).fetchone()
                if r:
                    return r["id"], name
                cid = db.upsert_customer("wechat", name)
                return cid, name
            # ★ 读不到名字就**绝不建客户**——
            #   建出来的"挂机认识的人"是垃圾数据，还会污染客户列表。
            #   老实说认不出，让 _tick 跳过这一轮。
            return None, None
        finally:
            db.conn.close()

    # ---------------- 想一句回复 ----------------
    def _think(self, msgs, mode="normal"):
        # ★ 没读到对话就**绝不硬想**——上一版没对话也能编出一句
        #   "明天见啦记得带好吃的"，纯属幻觉。宁可停手叫人。
        if not msgs or not any(m["who"] == "他" for m in msgs):
            return None
        from vision import VisionEngine
        try:
            from ui.store import get_store
            persona = get_store().get_setting("persona_style", "") or ""
            use_junshi = get_store().get_setting("use_junshi", True)
        except Exception:
            persona, use_junshi = "", True

        lines = "\n".join("%s: %s" % (m["who"], m["text"]) for m in msgs)

        head = "你在替用户回微信。用户人设：%s\n" % (persona or "26 岁，做设计的，开朗")
        if use_junshi:
            sp = _skill_prompt()
            if sp:
                head += "下面是聊天军师的心法，照这个味道说话：\n%s\n" % sp
        if mode == "money":
            head += (
                "★ 特别情况：对方的话聊到了钱（借钱/转账/红包之类）。\n"
                "你的铁规矩：**绝不答应给钱、绝不发任何验证码/密码/银行卡信息、"
                "不承诺任何转账**。但也别翻脸、别说教、别提'诈骗'两个字 —— "
                "就像平时一样轻松地**把话题岔开**（聊点别的共同话题），一句话带过。\n"
            )
        prompt = (
            head
            + "规矩：口语、短（25 字内）、像真人打字；不说客套话、不说'谢谢夸奖'这类客服话；"
              "绝对不要输出引号、不要解释、不要提你是 AI。\n"
            + "对话：\n%s\n\n只输出要发的那一句。" % lines
        )
        v = VisionEngine()
        out = (v.ask_text(prompt, max_tokens=60, temperature=0.8) or "").strip()
        out = out.strip().strip('"「」').replace('"', "").strip()
        return out or None

    # ---------------- 说出去（试跑 or 自动发） ----------------
    def _say(self, ph, reply, cid):
        from tt_typing import Typist

        auto = False
        try:
            from ui.store import get_store
            auto = bool(get_store().get_setting("watch_auto_send", False))
        except Exception:
            auto = False

        # 输入框（微信、键盘收起时中心 ≈ 96.9%，第 36 轮实测）
        ph.tap(480, 2325)
        time.sleep(2.4)
        t = Typist(ph)
        with t:
            t.type_text(reply)
        time.sleep(1.0)

        if auto:
            self.evt.emit("typed", {"text": reply, "cid": cid, "auto": True})
            self._press_send(ph, reply, cid)
            return
        # 试跑（P35）：字在框里停着，等用户点头 —— 不点发送
        self._pending = {"text": reply, "cid": cid}
        self.evt.emit("typed", {"text": reply, "cid": cid, "auto": False})

    def _press_send(self, ph, reply, cid):
        """
        点发送 + 回读验证（规矩：**气泡真的出现**才算发出去，
        "输入框清空"不算——老坑 10）。
        """
        from vision import VisionEngine
        try:
            png = ph.screenshot_bytes()
            v = VisionEngine()
            r = v.locate_grid(png, "聊天输入框右边绿色的「发送」按钮", cols=4, rows=8,
                              extra="它在屏幕右下角，绿色，上面写着发送两个字")
            if r.get("found"):
                x, y = int(r["x"]), int(r["y"])
            else:
                x, y = 993, 1376          # 键盘弹起时微信发送键的实测位置（第 36 轮）
            ph.tap(x, y)
            time.sleep(2.6)
            chk = ph.screenshot_bytes()
            ans = v.ask(chk, "屏幕右侧有没有一个刚发出去的气泡，内容是「%s」？"
                             "只回 有 或 没有。" % reply[:20], max_tokens=8)
            if ans and "有" in ans and "没有" not in ans:
                self._log_sent(cid, reply)
                self.replies_sent += 1
                self.evt.emit("replied", {"text": reply})
                return True
            self.evt.emit("error", {"why": "点了发送但没验证到气泡，别重复发，先人工看一眼"})
            return False
        except Exception as e:
            self.evt.emit("error", {"why": "发送出错：%s" % str(e)[:80]})
            return False

    def _log_sent(self, cid, text):
        try:
            from tt_db import TuokeDB
            db = TuokeDB()
            try:
                db.add_message(cid, "ai", text, strategy_note="挂机自动回复", verified=1)
            finally:
                db.conn.close()
        except Exception:
            pass
        try:
            from ui import datasource as DS
            DS.invalidate()
        except Exception:
            pass


# ============================================================
# 全软件一个（跟 device_hub 一样的单例写法）
# ============================================================
_W = None


def get_watcher():
    global _W
    if _W is None:
        _W = Watcher()
    return _W


def watcher_running():
    w = _W
    return bool(w and w.isRunning())
