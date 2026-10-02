# -*- coding: utf-8 -*-
"""
页面 ④ 策略（图纸 view-strategy，第 1235~1251 行）

★ 关键设计（第 20 轮拍板）：
    这一页只管"AI 聊天时用哪几招"；
    "AI 会不会用某个 App"（认路）已经挪到**技能库**页 —— 两件事不许混。

★ 图纸原文提示框：
    「说人话：这里是"AI 聊天时用哪几招"的开关。
      至于"AI 会不会用某个 App"（认路那条），已经挪到左边的 技能库 了 —— 两件事别混。」
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea,
    QCheckBox, QGridLayout,
)
from ui import theme as TH
from ui.widgets import Card, Btn, page_title, page_sub, faint, toast, modal


# ★ 图纸 .strategy-foot：6 个技能，其中 4 个已开；1 个是安全必开，关不掉
SKILLS = [
    ("破冰开场",     "第一次说话怎么开头，不让对方觉得是营销号",  True,  True),
    ("话题接续",     "对方说了一句，怎么自然地接下去",            True,  False),
    ("情绪读解",     "察觉对方是不是烦了、是不是敷衍",            True,  False),
    ("安全刹车",     "碰到要钱、要验证码这种，立刻停手",          True,  True),   # 必开
    ("主动推进",     "聊到一定程度，主动把话题往前带一带",        False, False),
    ("冷场唤醒",     "对方两天没回，怎么自然地再开一次口",        False, False),
]


class SkillCard(QFrame):
    def __init__(self, name, desc, on, locked, on_change=None, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.name = name
        self.locked = locked

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(6)

        r = QHBoxLayout()
        r.setSpacing(8)
        nm = QLabel(name)
        nm.setStyleSheet("font-weight:700; font-size:13px;")
        r.addWidget(nm)

        if locked:
            lk = QLabel("安全必开")
            lk.setStyleSheet("font-size:10px; padding:1px 6px; border-radius:5px;"
                             "color:%s; background:%s;"
                             % (TH.cur()["green"], _bg(TH.cur()["green"])))
            r.addWidget(lk)

        r.addStretch(1)

        self.cb = QCheckBox()
        self.cb.setChecked(on)
        self.cb.setEnabled(not locked)
        # ★ 第 32 轮修：**禁用的开关不能再显示手型光标**
        #   原来锁死的「安全刹车」也是手型，用户以为能点，
        #   点下去没反应 —— 又一处"这软件坏了"。
        #   禁用就该有禁用的样子：箭头光标 + 说清楚为什么。
        if locked:
            self.cb.setCursor(Qt.ForbiddenCursor)
            self.cb.setToolTip("这一项不能关 —— 它是保护你的：\n"
                               "碰到要钱、要验证码这类事，AI 会立刻停手叫你。")
        else:
            self.cb.setCursor(Qt.PointingHandCursor)
        self.cb.setStyleSheet("""
            QCheckBox::indicator {{
                width:34px; height:18px; border-radius:9px;
                background:{off};
            }}
            QCheckBox::indicator:checked {{ background:{on}; }}
        """.format(off=TH.cur()["line2"], on=TH.cur()["blue"]))
        if on_change:
            self.cb.toggled.connect(lambda v: on_change(name, v))
        r.addWidget(self.cb)

        lay.addLayout(r)

        d = QLabel(desc)
        d.setObjectName("Sub")
        d.setWordWrap(True)
        lay.addWidget(d)


def _bg(h):
    h = h.lstrip("#")
    return "rgba(%d,%d,%d,0.13)" % (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


class StrategyPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._cards = {}
        self._cnt = None

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(18, 16, 18, 18)
        lay.setSpacing(14)

        # 说人话提示框
        tip = QFrame()
        tip.setObjectName("TipBox")
        tl = QVBoxLayout(tip)
        tl.setContentsMargins(14, 11, 14, 11)
        tl.setSpacing(4)

        t1 = QLabel("说人话：这里是「AI 聊天时用哪几招」的开关。")
        t1.setStyleSheet("font-weight:600;")
        t2 = QLabel("至于「AI 会不会用某个 App」（认路那条），已经挪到左边的 "
                    "<b>技能库</b> 了 —— 两件事别混。")
        t2.setObjectName("Sub")
        t2.setWordWrap(True)
        tl.addWidget(t1)
        tl.addWidget(t2)

        hl = QHBoxLayout()
        hl.addStretch(1)
        goto = Btn("去技能库看看 →", "ghost")
        goto.clicked.connect(self._goto_skills)
        hl.addWidget(goto)
        tl.addLayout(hl)

        lay.addWidget(tip)

        # 技能网格
        # ★ 第 34 轮：开关状态**真的存下来**（重开软件还在）。
        from ui.store import get_store
        st = get_store()

        grid = QGridLayout()
        grid.setSpacing(12)
        for i, (nm, ds, on, lk) in enumerate(SKILLS):
            saved = st.get_setting("strategy_" + nm, None)
            real_on = bool(saved) if saved is not None else on
            card = SkillCard(nm, ds, real_on, lk, self._on_change)
            self._cards[nm] = card
            grid.addWidget(card, i // 3, i % 3)
        lay.addLayout(grid)

        # 页脚统计
        foot = Card()
        fr = QHBoxLayout()
        fr.setSpacing(24)

        self._cnt = QLabel(self._count_text())
        self._cnt.setStyleSheet("font-size:21px; font-weight:700;")
        lab = QLabel(self._count_label())
        lab.setObjectName("Sub")
        lab.setStyleSheet("font-size:11.5px;")
        b = QVBoxLayout()
        b.setSpacing(2)
        b.addWidget(self._cnt); b.addWidget(lab)
        fr.addLayout(b)

        b2 = QVBoxLayout()
        b2.setSpacing(2)
        n2 = QLabel("2")
        n2.setStyleSheet("font-size:21px; font-weight:700;")
        s2 = QLabel("个是安全必开，关不掉")
        s2.setObjectName("Sub")
        s2.setStyleSheet("font-size:11.5px;")
        b2.addWidget(n2); b2.addWidget(s2)
        fr.addLayout(b2)

        note = QLabel("不确定要不要开？<b>保持默认就行</b>。\n这些是 AI 聊天的「习惯」，不影响它会不会用手机。")
        note.setObjectName("Faint")
        note.setWordWrap(True)
        note.setStyleSheet("font-size:11.5px;")
        fr.addStretch(1)
        fr.addWidget(note)
        foot.body().addLayout(fr)
        lay.addWidget(foot)

        lay.addStretch(1)
        scroll.setWidget(inner)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

        self._ct = QLabel()   # 预留：以后显示"已改"提示

    # --------------------------------------------------------
    def _on_count(self):
        """现在有几个开着（锁死的那两个也算开着）。"""
        n = 0
        for nm, _ds, on, lk in SKILLS:
            if lk:
                n += 1                       # 必开的永远是开的
                continue
            from ui.store import get_store
            saved = get_store().get_setting("strategy_" + nm, None)
            if bool(saved) if saved is not None else on:
                n += 1
        return n

    def _count_text(self):
        return "%d" % self._on_count()

    def _count_label(self):
        return ("个技能，其中 <b style='color:%s'>%d</b> 个已开"
                % (TH.cur()["green"], self._on_count()))

    def _goto_skills(self):
        w = self.window()
        if hasattr(w, "goto"):
            w.goto("skills")

    def _on_change(self, name, val):
        """
        ★ 这一页管的是"聊天用哪几招"。
          「安全刹车」是**安全必开**，界面里锁死不给关（规格书 4.4）。
        ★ 第 34 轮：每翻一下都**真的存下来**，页脚那个数字也真的跟着变。
        """
        if name == "安全刹车" and not val:
            return
        from ui.store import get_store
        get_store().set_setting("strategy_" + name, bool(val))
        if self._cnt is not None:
            self._cnt.setText(self._count_text())
        toast(self, "「%s」已%s" % (name, "打开" if val else "关掉"),
              "ok" if val else "info", 2200)

    def on_show(self):
        pass
