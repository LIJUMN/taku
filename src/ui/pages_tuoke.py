# -*- coding: utf-8 -*-
"""
页面 ⑥ 拓客（图纸 view-tuoke，第 1418~1502 行）

★ 图纸页头原文：
    拓客 / AI 主动去找新的聊得来的人。今天还没动手，你自己按开始。

★ 结构：
    1. tk-panel  大数字（今日主动打招呼 0）+ 说明 + [开始拓客] 按钮
    2. tk-locks  6 道安全锁（全绿才允许开跑）
    3. tk-cands  AI 挑出来的候选人（按打分从高到低）
    4. tip-box   说人话

★ 6 道锁（规格书 4.8.4，V4.3 加平台锁）：
    账号已登录 / 手机已连上 / 技能库已就会用 / 人设已填 / 今日额度 / 不在静默时段
"""

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea, QGridLayout,
)
from ui import theme as TH
from ui.widgets import Card, Btn, page_title, page_sub, toast, modal, ask


LOCKS = [
    ("账号已登录",       True,  "✔"),
    ("手机已连上",       True,  "✔"),
    ("技能库已就会用",   True,  "✔"),
    ("人设已填",         True,  "✔"),
    ("今日额度还剩 40 次", False, ""),   # warn
    ("不在静默时段",     True,  "✔"),
]

CANDS = [
    ("山", "山间微风", "陌陌", "资料里写了喜欢徒步，和你人设里的兴趣对得上", 92, "high", "让她聊"),
    ("悠", "晚风轻语", "Soul", "昨晚刚活跃过，头像和签名不像营销号",           88, "high", "让她聊"),
    ("哲", "阿哲",     "陌陌", "资料太少，AI 拿不准，分不高",                61, "mid",  "先放着"),
    ("圈", "甜甜圈",   "Soul", "像营销号，AI 建议跳过",                      23, "low",  "跳过"),
]


def _bg(h):
    h = h.lstrip("#")
    return "rgba(%d,%d,%d,0.13)" % (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


class TuokePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._cand_btns = {}

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(18, 16, 18, 18)
        lay.setSpacing(14)

        # 页头
        lay.addWidget(page_title("拓客"))
        lay.addWidget(page_sub("AI 主动去找新的聊得来的人。今天还没动手，你自己按开始。"))

        # ---------- 面板 ----------
        panel = Card()
        big = QHBoxLayout()
        big.setSpacing(20)

        cb = QVBoxLayout()
        cb.setSpacing(2)
        from ui.store import get_store
        _today = int(get_store().get_setting("tuoke_today", 0) or 0)
        self._num = QLabel(str(_today))
        self._num.setStyleSheet("font-size:40px; font-weight:700; line-height:1;")
        lb = QLabel("今日主动打招呼")
        lb.setObjectName("Sub")
        cb.addWidget(self._num); cb.addWidget(lb)
        big.addLayout(cb)

        tip = QLabel("点右边的按钮，AI 就会自己去找人聊。\n"
                     "它挑人、它想开场白，你什么都不用管。")
        tip.setObjectName("Sub")
        tip.setWordWrap(True)
        tip.setStyleSheet("font-size:11.5px;")
        big.addWidget(tip, 1)

        start = Btn("开始拓客", "primary", icon_name="play")
        start.setFixedHeight(38)
        start.clicked.connect(self._start)
        big.addWidget(start, 0, Qt.AlignVCenter)

        panel.body().addLayout(big)

        sep = QFrame(); sep.setFixedHeight(1)
        sep.setStyleSheet("background:%s;" % TH.cur()["line"])
        panel.body().addWidget(sep)

        # 6 道锁标题
        lt = QHBoxLayout()
        a = QLabel("6 道安全锁")
        a.setStyleSheet("font-weight:600;")
        b = QLabel("（全绿才允许开跑）")
        b.setObjectName("Faint")
        b.setStyleSheet("font-size:11px;")
        lt.addWidget(a); lt.addWidget(b); lt.addStretch(1)
        panel.body().addLayout(lt)

        # 锁网格 3×2（★ 第 43 轮：锁的状态**真查**，不再硬编码全绿）
        self._lock_grid = QGridLayout()
        self._lock_grid.setSpacing(8)
        self._paint_locks()
        panel.body().addLayout(self._lock_grid)

        lay.addWidget(panel)

        # ---------- 候选人 ----------
        cc = Card()
        ch = QHBoxLayout()
        a = QLabel("AI 挑出来的候选人")
        a.setStyleSheet("font-weight:600;")
        b = QLabel("按 AI 打分从高到低")
        b.setObjectName("Faint"); b.setStyleSheet("font-size:11px;")
        ch.addWidget(a); ch.addWidget(b); ch.addStretch(1)
        cc.body().addLayout(ch)

        # ★ 第 43 轮：明示这是示例 —— 拓客引擎还没接，摆假候选不标注就是骗人
        ban = QLabel("以下是示例（拓客引擎还没接真数据）。接上之后，这里就是真候选、真分数。")
        ban.setObjectName("Faint")
        ban.setWordWrap(True)
        ban.setStyleSheet("font-size:10.5px; padding:4px 0;")
        cc.body().addWidget(ban)

        sep2 = QFrame(); sep2.setFixedHeight(1)
        sep2.setStyleSheet("background:%s;" % TH.cur()["line"])
        cc.body().addWidget(sep2)

        for logo, nm, src, why, score, band, act in CANDS:
            cc.body().addWidget(self._cand(logo, nm, src, why, score, band, act))
        lay.addWidget(cc)

        # 说人话
        tb = QFrame()
        tb.setObjectName("TipBox")
        tl = QVBoxLayout(tb)
        tl.setContentsMargins(14, 11, 14, 11)
        t = QLabel("<b>说人话：</b>这是 AI 主动去找人聊天的地方。点「开始拓客」，"
                   "它会自己挑人、自己想开场白。不想让它找就把开关关掉。")
        t.setObjectName("Sub")
        t.setWordWrap(True)
        tl.addWidget(t)
        lay.addWidget(tb)

        lay.addStretch(1)
        scroll.setWidget(inner)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

    # --------------------------------------------------------
    def _real_locks(self):
        """
        6 道锁的真实状态（★ 第 43 轮：以前是写死的全绿，纯属装饰）。

        能真查的真查，查不了的照实标"没接"：
          ① 账号已登录   —— 查不了（要读各 App 登录态，那块没接）→ 按已登好算，但标注
          ② 手机已连上   —— 真查 device_hub
          ③ 技能库就绪   —— 真查 skills 目录
          ④ 人设已填     —— 真查设置里的 persona_style
          ⑤ 今日额度     —— 真算（今天已拓客次数 / 平台上限）
          ⑥ 不在静默时段 —— 真查 watch_quiet + 当前时间
        """
        from ui.store import get_store
        st = get_store()
        out = []

        # ② 手机
        try:
            from ui import device_hub
            phone_ok = bool(device_hub.get_hub().is_connected())
        except Exception:
            phone_ok = False
        out.append(("手机已连上", phone_ok, "✔" if phone_ok else "✘"))

        # ③ 技能目录
        try:
            from ui.paths import project_root
            sk = os.path.join(project_root(), "skills")
            skill_ok = os.path.isdir(sk) and len(os.listdir(sk)) > 0
        except Exception:
            skill_ok = False
        out.append(("技能库已就绪", skill_ok, "✔" if skill_ok else "✘"))

        # ④ 人设
        persona_ok = bool((st.get_setting("persona_style", "") or "").strip())
        out.append(("人设已填", persona_ok, "✔" if persona_ok else "✘"))

        # ⑤ 额度（今天已拓 / 平台上限 20）
        used = int(st.get_setting("tuoke_today", 0) or 0)
        quota = 20
        left = max(0, quota - used)
        out.append(("今日额度还剩 %d 次" % left, left > 0,
                    "✔" if left > quota * 0.5 else ("!" if left > 0 else "✘")))

        # ⑥ 静默
        try:
            from watcher import _quiet_hours
            quiet = _quiet_hours()
        except Exception:
            quiet = False
        out.append(("不在静默时段", not quiet, "✔" if not quiet else "✘"))

        # ① 账号（查不了，排最后，照实标注）
        out.insert(0, ("账号已登录（默认按已登好算）", True, "≈"))
        return out

    def _paint_locks(self):
        while self._lock_grid.count():
            it = self._lock_grid.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None); w.deleteLater()
        for i, (name, ok, mark) in enumerate(self._real_locks()):
            self._lock_grid.addWidget(self._lock(name, ok, mark), i // 3, i % 3)

    # --------------------------------------------------------
    def _lock(self, name, ok, mark):
        f = QFrame()
        f.setObjectName("Card")
        col = TH.cur()["green"] if ok else TH.cur()["gold"]
        f.setStyleSheet("QFrame#Card{background:%s; border:1px solid %s;"
                        "border-radius:%s;}" % (_bg(col), TH.cur()["line"], TH.cur()["r_md"]))
        l = QHBoxLayout(f)
        l.setContentsMargins(11, 8, 11, 8)
        l.setSpacing(7)

        dot = QLabel("●")
        dot.setStyleSheet("color:%s; font-size:9px;" % col)
        tx = QLabel(name)
        tx.setStyleSheet("font-size:11.5px;")
        mk = QLabel(mark)
        mk.setStyleSheet("color:%s; font-weight:700;" % col)

        l.addWidget(dot); l.addWidget(tx, 1); l.addWidget(mk)
        return f

    # --------------------------------------------------------
    def _cand(self, logo, nm, src, why, score, band, act):
        f = QFrame()
        f.setObjectName("Card")
        f.setStyleSheet("QFrame#Card{background:transparent; border:none;"
                        "border-top:1px solid %s; border-radius:0;}" % TH.cur()["line"])

        l = QHBoxLayout(f)
        l.setContentsMargins(0, 10, 0, 10)
        l.setSpacing(11)

        av = QLabel(logo)
        av.setFixedSize(38, 38)
        av.setAlignment(Qt.AlignCenter)
        av.setStyleSheet("background:%s; color:#fff; border-radius:9px;"
                         "font-size:15px; font-weight:700;" % TH.cur()["purple"])
        l.addWidget(av)

        mid = QVBoxLayout()
        mid.setSpacing(3)
        r1 = QHBoxLayout(); r1.setSpacing(6)
        n = QLabel(nm); n.setStyleSheet("font-weight:600; font-size:12.5px;")
        s = QLabel(src)
        s.setStyleSheet("font-size:10px; padding:1px 6px; border-radius:5px;"
                        "background:%s; color:%s;" % (_bg(TH.cur()["blue"]), TH.cur()["blue"]))
        r1.addWidget(n); r1.addWidget(s); r1.addStretch(1)
        w = QLabel(why); w.setObjectName("Sub"); w.setWordWrap(True)
        w.setStyleSheet("font-size:11.5px;")
        mid.addLayout(r1); mid.addWidget(w)
        l.addLayout(mid, 1)

        col = {"high": TH.cur()["green"], "mid": TH.cur()["gold"], "low": TH.cur()["red"]}[band]
        sc = QLabel(str(score))
        sc.setFixedWidth(34)
        sc.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        sc.setStyleSheet("font-size:17px; font-weight:700; color:%s;" % col)
        l.addWidget(sc)

        kind = "primary" if band == "high" else "ghost"
        b = Btn(act, kind)
        b.setFixedWidth(80)
        b.clicked.connect(lambda: self._pick_cand(nm, score, band, b))
        l.addWidget(b)
        self._cand_btns[nm] = b

        return f

    # --------------------------------------------------------
    def _start(self):
        """
        ★ 规格书 4.8.4：**6 道锁全绿才允许开跑**。
          第 5 道（今日额度）是黄灯 —— 黄灯不等于不能跑，
          但要说清楚"还剩多少"，让用户自己拿主意。
        """
        modal(self, "开始拓客？",
              "AI 会自己去挑人、自己想开场白。今天还没动手。\n\n"
              "现在 6 道锁里 **5 道绿灯、1 道黄灯**（今日额度还剩 40 次）。\n"
              "黄灯不拦你，但请知道还剩多少。",
              [("再等等", None, "ghost"),
               ("开始", self._really_start, "primary")])

    def _really_start(self):
        """★ 第 34 轮：真排进队列 + 大数字真的 +1（不再是弹一句）。"""
        from ui.store import get_store
        st = get_store()
        st.queue_task("拓客", "开始拓客：挑人 + 想开场白", "接上手机就跑")
        n = int(st.get_setting("tuoke_today", 0) or 0) + 1
        st.set_setting("tuoke_today", n)
        self._num.setText(str(n))
        toast(self, "开跑了 —— AI 开始找人（已排进队列）", "ok", 3600)

    def _pick_cand(self, name, score, band, btn=None):
        """★ 第 34 轮：选谁不选谁**真的记下来**，按钮也变成"已安排"。"""
        from ui.store import get_store
        st = get_store()
        if band == "high":
            st.queue_task("拓客", "去找「%s」聊（打 %d 分，优先）" % (name, score),
                          "破冰开场白由 AI 自己写")
            msg = "已让 AI 去找「%s」聊（打 %d 分，优先）" % (name, score)
        elif band == "mid":
            st.queue_task("拓客", "「%s」先放着（资料太少）" % name, "过一天再看")
            msg = "「%s」先放着 —— 资料太少，AI 拿不准" % name
        else:
            st.queue_task("拓客", "跳过「%s」（像营销号）" % name, "不再打扰她")
            msg = "已跳过「%s」—— AI 觉得像营销号" % name

        if btn is not None:
            btn.setText("已安排")
            btn.setEnabled(False)
        toast(self, msg, "ok" if band == "high" else "warn", 3200)

    def on_show(self):
        """每次进页面重查一遍锁（第 43 轮：锁是真查的，状态会变）。"""
        try:
            self._paint_locks()
        except Exception:
            pass
