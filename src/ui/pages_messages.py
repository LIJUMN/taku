# -*- coding: utf-8 -*-
"""
页面 ③ 消息（图纸 view-messages，第 1222~1234 行）

★ 结构：工具条（全部/待处理/命中信号/已回复 + 计数）+ 消息列表
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea,
)
from ui import theme as TH
from ui import icons
from ui.widgets import Chip, toast


class _MsgRow(QFrame):
    """
    消息列表的一行 —— **可以点的**。

    ★ 第 32 轮补的（用户实测反馈）：
      原来这页是"死的"：列表行看着像个能点的东西，但点了没反应。
      用户的感受是"点进去根本动不了"。
      → 现在：鼠标移上去会变色（告诉用户"我能点"），点一下跳到那个人的聊天。
    """

    clicked = Signal(str)      # 传出客户名

    def __init__(self, nm, src, tx, tm, tag, parent=None):
        super().__init__(parent)
        self.setObjectName("MsgRow")
        self._nm = nm
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(66)
        self._hover = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(17, 10, 17, 10)
        lay.setSpacing(11)

        # 头像
        av = QLabel(nm[:1])
        av.setFixedSize(38, 38)
        av.setAlignment(Qt.AlignCenter)
        av.setStyleSheet("background:%s; color:#fff; border-radius:9px;"
                         "font-size:15px; font-weight:700;" % _pick(nm))
        lay.addWidget(av)

        mid = QVBoxLayout()
        mid.setSpacing(3)
        r1 = QHBoxLayout(); r1.setSpacing(6)
        a = QLabel(nm); a.setStyleSheet("font-weight:600; font-size:12.5px;")
        b = QLabel(src)
        b.setStyleSheet("font-size:10px; padding:1px 6px; border-radius:5px;"
                        "background:%s; color:%s;" % (_bg(TH.cur()["blue"]), TH.cur()["blue"]))
        r1.addWidget(a); r1.addWidget(b); r1.addStretch(1)
        r2 = QLabel(tx); r2.setObjectName("Sub"); r2.setStyleSheet("font-size:11.5px;")
        mid.addLayout(r1); mid.addWidget(r2)
        lay.addLayout(mid, 1)

        # 右侧：标签 + 时间 + 进去的箭头
        right = QHBoxLayout()
        right.setSpacing(7)

        col = {"待处理": TH.cur()["gold"], "命中信号": TH.cur()["purple"],
               "已回复": TH.cur()["green"]}.get(tag, TH.cur()["sub"])
        t = QLabel(tag)
        t.setAlignment(Qt.AlignCenter)
        t.setFixedWidth(58)
        t.setStyleSheet("font-size:10.5px; padding:2px 0; border-radius:6px;"
                        "color:%s; background:%s;" % (col, _bg(col)))

        tt = QLabel(tm); tt.setObjectName("Faint")
        tt.setAlignment(Qt.AlignRight)
        tt.setFixedWidth(40)
        tt.setStyleSheet("font-size:10.5px;")

        arrow = QLabel()
        arrow.setPixmap(icons.render("chevron_right", 14, TH.cur()["faint"]))

        right.addWidget(t)
        right.addWidget(tt)
        right.addWidget(arrow)
        lay.addLayout(right)

        self._set_bg(False)

    def _set_bg(self, on):
        t = TH.cur()
        self.setStyleSheet(
            "QFrame#MsgRow{background:%s; border-bottom:1px solid %s;}"
            % (t["card"] if on else "transparent", t["line"]))

    def enterEvent(self, e):
        self._set_bg(True)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._set_bg(False)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self._nm)


class MessagesPage(QWidget):
    """
    消息页。

    ★ 第 33 轮改：数据不再写死，改从 store 读。
      原来这里的 MSGS 是个常量表 —— 也是"假数据"的一种：
      用户看到的 4 条消息，代码里其实一直就是那 4 条，永远不动。
      现在：从 store 读，能标记已读、能删。
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # 数据变了就重画（别的页面删了东西，这边跟着变）
        try:
            from ui.store import get_store
            get_store().changed.connect(lambda _k: self._reload())
        except Exception:
            pass

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # 工具条
        tb = QWidget()
        tl = QHBoxLayout(tb)
        tl.setContentsMargins(16, 12, 16, 12)
        tl.setSpacing(7)

        self._chips = []
        for i, n in enumerate(["全部", "待处理", "命中信号", "已回复"]):
            c = Chip(n)
            c.setChecked(i == 0)
            c.clicked.connect(lambda _=False, x=n: self._filter(x))
            tl.addWidget(c)
            self._chips.append(c)

        tl.addStretch(1)
        self.cnt = QLabel("")
        self.cnt.setObjectName("Faint")
        self.cnt.setStyleSheet("font-size:11.5px;")
        tl.addWidget(self.cnt)
        lay.addWidget(tb)

        sep = QFrame(); sep.setFixedHeight(1)
        sep.setStyleSheet("background:%s;" % TH.cur()["line"])
        lay.addWidget(sep)

        # 列表
        self.box = QVBoxLayout()
        self.box.setContentsMargins(0, 6, 0, 6)
        self.box.setSpacing(0)

        holder = QWidget()
        holder.setLayout(self.box)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setWidget(holder)
        lay.addWidget(sc, 1)

        # 空态提示（用户分不清"没有内容"和"坏了"）
        self.empty_tip = QLabel("")
        self.empty_tip.setObjectName("Faint")
        self.empty_tip.setAlignment(Qt.AlignCenter)
        self.empty_tip.hide()
        lay.addWidget(self.empty_tip)

        self._filter_name = "全部"
        self._render("全部")

    def _msgs(self):
        """
        从**真库**攒消息列表 —— 每个客户一条：他/我最后说了什么。

        ★★ 第 42 轮大修 ★★
          之前这页读的是 store 里的**假种子表**（后来清空了），于是库里有
          真实的往来（张三 3 条），这页却显示"共 0 条"——
          总览页都有事件流了，消息页却是空的，用户不炸才怪。

          现在：客户列表（datasource，库为正文）里每个**聊过的人**生成一行，
          标签按真数据算：
            · 有命中信号（hit_signals）        → 命中信号
            · 最后开口的是我这边（ai/me/user） → 已回复
            · 最后开口的是对方                → 待处理
          没聊过的人不进这个列表（他们住在客户页）。
        """
        try:
            from ui import datasource as DS
            rows = DS.customers()
            if rows is None:
                return None
            out = []
            for r in rows:
                tx = (r.get("last_content") or "").strip()
                if not tx:
                    continue
                if (r.get("hit_signals") or "").strip():
                    tag = "命中信号"
                elif (r.get("last_sender") or "") in ("ai", "me", "user"):
                    tag = "已回复"
                else:
                    tag = "待处理"
                plat = (r.get("platform") or "").strip()
                out.append({
                    "id": r.get("id"),
                    "name": (r.get("nickname") or r.get("name") or "?"),
                    "src": DS.platform_cn(plat) if plat else (r.get("src") or "—"),
                    "tx": tx,
                    "tm": DS.when(r.get("last_at") or r.get("last_msg_time") or ""),
                    "tag": tag,
                })
            return out
        except Exception:
            return []

    def _reload(self):
        self._render(self._filter_name)

    def _render(self, f):
        while self.box.count():
            it = self.box.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()

        allms = self._msgs()
        n = 0
        for m in (allms or []):
            if f != "全部" and m.get("tag") != f:
                continue
            row = _MsgRow(m.get("name", "?"), m.get("src", "—"),
                          m.get("tx", ""), m.get("tm", ""), m.get("tag", ""))
            row.clicked.connect(self._open_chat)
            self.box.addWidget(row)
            n += 1
        self.box.addStretch(1)

        if n == 0:
            # ★ 空态画进列表里（原来挂在页面最底下，一条小字，看着像坏了）
            if allms is None:
                tip = QLabel("🔌  读不到消息数据 —— data/tuoke.db 打不开。重启程序试试。")
            elif allms:
                tip = QLabel("这个分类下暂时没有消息")
            else:
                tip = QLabel("还没有消息。等 AI 开始干活，这里就会出现往来。")
            tip.setObjectName("Faint")
            tip.setAlignment(Qt.AlignCenter)
            tip.setStyleSheet("padding:40px 0; font-size:12px;")
            self.box.addWidget(tip)
            self.empty_tip.hide()
        else:
            self.empty_tip.hide()

        self.cnt.setText("共 <b style='color:%s'>%d</b> 条"
                         % (TH.cur()["ink"], len(allms or [])))

    def _filter(self, n):
        self._filter_name = n
        for c in self._chips:
            c.setChecked(c.text() == n)
        self._render(n)

    def _open_chat(self, name):
        """点一条消息 → 跳到客户页，并把这个人选中。"""
        w = self.window()
        if not hasattr(w, "goto"):
            return
        w.goto("customers")
        page = getattr(w, "_pages", {}).get("customers")
        if page is not None and hasattr(page, "select_by_name"):
            page.select_by_name(name)

    def on_show(self):
        self._reload()


_PAL = ["#4c8dff", "#a479f5", "#3ecf8e", "#e8b34b", "#e06ab0", "#3ec9cf"]


def _pick(s):
    return _PAL[sum(ord(c) for c in (s or "?")) % len(_PAL)]


def _bg(h):
    h = h.lstrip("#")
    return "rgba(%d,%d,%d,0.13)" % (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
