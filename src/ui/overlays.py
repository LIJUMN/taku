# -*- coding: utf-8 -*-
"""
Taku 管理台 · 弹层系统（对标大厂工具型应用）

★ 图纸依据（`管理台界面原型-v3.html` 第 1583~1632 行）：
    规格书 V4.10 定死：**全站只有两种弹层形式**
      ① **居中遮罩弹层**（Modal）—— 要用户确认 / 输入 / 看清一段话的，一律走这个
      ② **右下角 toast** —— 轻提示，1.9 秒自动消失
    另有两个全局件：
      ③ **命令面板**（Ctrl+K）—— 键盘直达
      ④ **新手引导卡片** —— 4 步，随时可重看

★ 为什么必须集中到一个文件：
    大厂（VS Code / Linear / Figma）的做法是"**全站只有一套弹层**"。
    如果每个页面各写各的，就会出现"这个页面的确认框长这样、那个页面长那样"——
    用户会觉得软件是拼凑的。集中一处，样式和行为天然统一。

★ 用法（在主窗口里）：
    self.overlay = OverlayHost(self)
    self.overlay.toast("已保存")
    self.overlay.modal("确认删除？", "删了就找不回来了。", [("取消", None), ("删除", fn, "danger")])
    self.overlay.palette()
    self.overlay.guide()
"""

from PySide6.QtCore import (
    Qt, QObject, QEvent, QPropertyAnimation, QEasingCurve,
    QTimer, QSize, QPoint, Signal,
)
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit,
    QListWidget, QListWidgetItem, QGraphicsOpacityEffect, QSizePolicy,
    QScrollArea, QPushButton,
)
from PySide6.QtGui import QColor, QPainter

from . import theme as TH
from . import icons as IC
from .widgets import Btn, add_shadow


# ============================================================
# 遮罩（半透明、点空白关闭）
# ============================================================
class _Mask(QWidget):
    """
    全窗遮罩。

    ★ 大厂做法：弹层出现时把背后内容压暗（不是黑掉），
      用 62% 透明（图纸 `--overlay: rgba(4,7,12,.62)`）。
      点遮罩空白 = 关闭，这是用户的肌肉记忆。
    """

    def __init__(self, parent, on_close=None, alpha=0.62):
        super().__init__(parent)
        self._on_close = on_close
        self._alpha = alpha
        self.setAttribute(Qt.WA_StyledBackground, False)

    def paintEvent(self, e):
        p = QPainter(self)
        t = TH.get(getattr(self, "_theme_name", "dark"))
        base = QColor(4, 7, 12) if getattr(self, "_theme_name", "dark") == "dark" \
            else QColor(20, 30, 50)
        base.setAlphaF(self._alpha)
        p.fillRect(self.rect(), base)

    def mousePressEvent(self, e):
        # 只有点在遮罩本身（不是子控件）才关
        if self.childAt(e.position().toPoint()) is None and self._on_close:
            self._on_close()

    def set_theme(self, name):
        self._theme_name = name
        self.update()


# ============================================================
# ① Toast —— 右下角轻提示
# ============================================================
class _Toast(QFrame):
    """
    图纸 `#toast` —— 右下角浮出，1.9 秒自动消失。

    ★ 大厂细节：不要"啪"地出现、"啪"地消失，要有 160ms 的淡入淡出。
      这一点点动画就是"做得细"和"做得糙"的分界。
    """

    KINDS = {
        "info":    ("info",    "blue"),
        "ok":      ("check",   "green"),
        "warn":    ("warn",    "gold"),
        "error":   ("close",   "red"),
    }

    def __init__(self, parent, text, kind="info", ms=2600):
        super().__init__(parent)
        self.setObjectName("ToastBox")

        icon_name, color_key = self.KINDS.get(kind, self.KINDS["info"])
        t = TH.get("dark")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(13, 10, 15, 10)
        lay.setSpacing(9)

        ico = QLabel()
        ico.setPixmap(IC.render(icon_name, 15, t[color_key]))
        ico.setFixedSize(16, 16)

        lb = QLabel(text)
        lb.setStyleSheet("font-size:12px;")

        lay.addWidget(ico)
        lay.addWidget(lb)

        self.setStyleSheet(
            "QFrame#ToastBox{background:%s; border:1px solid %s;"
            "border-radius:%s;}" % (t["card2"], t["line2"], t["r_md"])
        )
        add_shadow(self, blur=24, dy=6, alpha=140)

        self._ms = ms
        self.adjustSize()

        # 淡入
        self._eff = QGraphicsOpacityEffect(self)
        self._eff.setOpacity(0.0)
        self.setGraphicsEffect(self._eff)
        self._anim = QPropertyAnimation(self._eff, b"opacity", self)
        self._anim.setDuration(160)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def pop_in(self):
        self.show()
        self.raise_()
        self._anim.start()
        QTimer.singleShot(self._ms, self._fade_out)

    def _fade_out(self):
        a = QPropertyAnimation(self._eff, b"opacity", self)
        a.setDuration(220)
        a.setStartValue(1.0)
        a.setEndValue(0.0)
        a.setEasingCurve(QEasingCurve.InCubic)
        a.finished.connect(self.deleteLater)
        a.start()
        self._out_anim = a


# ============================================================
# ② Modal —— 全站唯一的居中弹层
# ============================================================
class _ModalCard(QFrame):
    """图纸 `.modal-box`：标题栏 + 内容 + 底部按钮。"""

    def __init__(self, parent, title, body, buttons, on_close):
        super().__init__(parent)
        self.setObjectName("ModalCard")
        t = TH.get("dark")

        self.setStyleSheet(
            "QFrame#ModalCard{background:%s; border:1px solid %s;"
            "border-radius:%s;}" % (t["card"], t["line2"], t["r_xl"])
        )
        add_shadow(self, blur=40, dy=14, alpha=170)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ---- 标题栏 ----
        head = QWidget()
        hl = QHBoxLayout(head)
        hl.setContentsMargins(18, 14, 12, 12)
        hl.setSpacing(8)

        tt = QLabel(title)
        tt.setStyleSheet("font-size:14px; font-weight:700;")
        hl.addWidget(tt)
        hl.addStretch(1)

        x = QPushButton()
        x.setObjectName("IconBtn")
        x.setFixedSize(26, 26)
        x.setIconSize(QSize(14, 14))
        x.setIcon(IC.make_icon("close", 14, on=t["ink"], off=t["sub"]))
        x.setCursor(Qt.PointingHandCursor)
        x.clicked.connect(on_close)
        hl.addWidget(x)

        lay.addWidget(head)

        sep = QFrame(); sep.setFixedHeight(1)
        sep.setStyleSheet("background:%s;" % t["line"])
        lay.addWidget(sep)

        # ---- 内容 ----
        bodyw = QWidget()
        bl = QVBoxLayout(bodyw)
        bl.setContentsMargins(18, 14, 18, 14)
        bl.setSpacing(9)

        if isinstance(body, str):
            lb = QLabel(body)
            lb.setWordWrap(True)
            lb.setStyleSheet("font-size:12.5px; color:%s; line-height:20px;" % t["sub"])
            bl.addWidget(lb)
        elif isinstance(body, QWidget):
            bl.addWidget(body)

        lay.addWidget(bodyw)

        # ---- 底部 ----
        if buttons:
            sep2 = QFrame(); sep2.setFixedHeight(1)
            sep2.setStyleSheet("background:%s;" % t["line"])
            lay.addWidget(sep2)

            foot = QWidget()
            fl = QHBoxLayout(foot)
            fl.setContentsMargins(18, 12, 18, 14)
            fl.setSpacing(9)
            fl.addStretch(1)

            for item in buttons:
                text = item[0]
                fn = item[1] if len(item) > 1 else None
                kind = item[2] if len(item) > 2 else "ghost"
                b = Btn(text, kind)
                if fn:
                    b.clicked.connect(lambda _=False, f=fn: (f() if callable(f) else None))
                b.clicked.connect(on_close)
                fl.addWidget(b)

            lay.addWidget(foot)


# ============================================================
# ③ 命令面板（Ctrl+K）
# ============================================================
class _CmdRow(QWidget):
    """
    命令面板的一行：左边标题、右边分组标签（右对齐）。

    ★ 为什么不用纯文本：一开始我用空格把"分组"顶到右边，
      结果字体一变就全乱了。大厂都是"两列布局"，右边那列真右对齐。
    """

    def __init__(self, title, group, parent=None):
        super().__init__(parent)
        t = TH.get("dark")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(11, 7, 11, 7)
        lay.setSpacing(10)

        self.a = QLabel(title)
        self.b = QLabel(group)
        self.b.setStyleSheet("font-size:10.5px;")
        self.set_color(t["sub"], t["faint"])

        lay.addWidget(self.a, 1)
        lay.addWidget(self.b)

    def set_color(self, main, side):
        """选中 → 主色；未选中 → 灰。"""
        self.a.setStyleSheet("font-size:12.5px; color:%s;" % main)
        self.b.setStyleSheet("font-size:10.5px; color:%s;" % side)


class _Palette(QFrame):
    """
    对标 VS Code / Linear / Notion 的 Ctrl+K 命令面板。

    ★ 大厂做法：一个输入框 + 一个列表，输入即过滤，
      上下键选择、Enter 执行、Esc 退出。**全程不用碰鼠标。**
    """

    picked = Signal(str)

    def __init__(self, parent, commands, on_close):
        super().__init__(parent)
        self.setObjectName("PaletteCard")
        self._on_close = on_close
        self._all = commands            # [(标题, 分组, 关键字, 回调)]
        self._shown = []
        t = TH.get("dark")

        self.setStyleSheet(
            "QFrame#PaletteCard{background:%s; border:1px solid %s;"
            "border-radius:%s;}" % (t["card"], t["line2"], t["r_lg"])
        )
        add_shadow(self, blur=40, dy=16, alpha=180)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # 输入行
        top = QWidget()
        tl = QHBoxLayout(top)
        tl.setContentsMargins(14, 11, 14, 11)
        tl.setSpacing(9)

        ico = QLabel()
        ico.setPixmap(IC.render("search", 16, t["faint"]))
        ico.setFixedSize(17, 17)

        self.input = QLineEdit()
        self.input.setPlaceholderText("输入命令或搜客户…（如「客户」「设置」「主题」）")
        self.input.setStyleSheet(
            "QLineEdit{background:transparent; border:none; padding:2px 0;"
            "font-size:13.5px;}"
        )
        self.input.textChanged.connect(self._filter)
        self.input.installEventFilter(self)

        esc = QLabel("Esc")
        esc.setStyleSheet(
            "font-size:10px; color:%s; border:1px solid %s;"
            "border-radius:4px; padding:1px 5px;" % (t["faint"], t["line"])
        )

        tl.addWidget(ico)
        tl.addWidget(self.input, 1)
        tl.addWidget(esc)
        lay.addWidget(top)

        sep = QFrame(); sep.setFixedHeight(1)
        sep.setStyleSheet("background:%s;" % t["line"])
        lay.addWidget(sep)

        # 列表
        self.list = QListWidget()
        self.list.setObjectName("PaletteList")
        self.list.setFrameShape(QFrame.NoFrame)
        self.list.setStyleSheet("""
            QListWidget { background:transparent; padding:6px; }
            QListWidget::item {
                border-radius:8px; color:%s;
            }
            QListWidget::item:selected { background:%s; }
        """ % (t["sub"], t["blue_bg"]))
        self.list.setFixedHeight(250)
        self.list.itemClicked.connect(self._run)
        self.list.currentRowChanged.connect(self._highlight)
        lay.addWidget(self.list)

        self.setFixedWidth(520)
        self._filter("")

    # ---- 高亮（选中行文字变主色） ----
    def _highlight(self, row):
        t = TH.get("dark")
        for i in range(self.list.count()):
            w = self.list.itemWidget(self.list.item(i))
            if w is None:
                continue
            if i == row:
                w.set_color(t["blue"], t["blue"])
            else:
                w.set_color(t["sub"], t["faint"])

    # ---- 过滤 ----
    def _filter(self, kw):
        kw = (kw or "").strip().lower()
        self.list.clear()
        self._shown = []
        for title, group, keys, fn in self._all:
            hay = (title + group + keys).lower()
            if kw and kw not in hay:
                continue
            it = QListWidgetItem()
            it.setSizeHint(QSize(0, 36))
            self.list.addItem(it)
            self.list.setItemWidget(it, _CmdRow(title, group))
            self._shown.append(fn)
        if self._shown:
            self.list.setCurrentRow(0)
            self._highlight(0)

    def _run(self, item):
        row = self.list.row(item)
        if 0 <= row < len(self._shown):
            fn = self._shown[row]
            self._on_close()
            if callable(fn):
                fn()

    # ---- 键盘 ----
    def eventFilter(self, obj, ev):
        if obj is self.input and ev.type() == QEvent.KeyPress:
            k = ev.key()
            if k == Qt.Key_Down:
                self.list.setCurrentRow(min(self.list.currentRow() + 1,
                                            self.list.count() - 1))
                return True
            if k == Qt.Key_Up:
                self.list.setCurrentRow(max(self.list.currentRow() - 1, 0))
                return True
            if k in (Qt.Key_Return, Qt.Key_Enter):
                it = self.list.currentItem()
                if it:
                    self._run(it)
                return True
            if k == Qt.Key_Escape:
                self._on_close()
                return True
        return super().eventFilter(obj, ev)

    def focus_input(self):
        self.input.setFocus()


# ============================================================
# ④ 新手引导卡片（图纸 4 步，文案一字不改）
# ============================================================
GUIDE_STEPS = [
    ("先插手机", "这一步不做，后面全不动",
     "用数据线把手机插到电脑上。手机会弹一个窗口问「允许 USB 调试吗」，"
     "勾选「始终允许」再点确定。<b>顶栏左上角出现绿点</b>，就说明电脑认出手机了。", True),
    ("填一个模型", "",
     "左边「设置」→「模型设置」，把你买的那个 AI 的连接地址和钥匙填进去，点「测一下」。<br>"
     "只填这一个就行，整个软件都用它。", False),
    ("让它先自己学一遍", "",
     "左边「技能库」看看陌陌、Soul 学会没有。没学会的点「现在就去学」，"
     "它会自己认路，大概 3 分钟。", False),
    ("不想让它自己聊，随时抢回来", "",
     "「客户」页右上角有个红色「接管」按钮。点一下，AI 立刻停手让位，你自己打字。<br>"
     "聊完再点一下，还给它。", False),
]


class _GuideCard(QFrame):
    def __init__(self, parent, on_close):
        super().__init__(parent)
        self.setObjectName("GuideCard")
        t = TH.get("dark")

        self.setStyleSheet(
            "QFrame#GuideCard{background:%s; border:1px solid %s;"
            "border-radius:%s;}" % (t["card"], t["line2"], t["r_xl"])
        )
        add_shadow(self, blur=48, dy=18, alpha=190)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 可滚动主体（4 步在一屏里可能放不下）
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(26, 24, 26, 14)
        lay.setSpacing(0)

        badge = QLabel("第 1 次打开")
        badge.setStyleSheet(
            "font-size:10.5px; color:%s; background:%s; border-radius:9px;"
            "padding:3px 10px;" % (t["blue"], t["blue_bg"])
        )
        badge.setFixedWidth(76)
        badge.setAlignment(Qt.AlignCenter)

        h2 = QLabel("这台软件怎么用？一句话：<br>你插上手机，AI 替你聊，你看着就行。")
        h2.setStyleSheet("font-size:16px; font-weight:700; line-height:25px;")

        gsub = QLabel("照下面 4 步走一遍，大约 3 分钟。以后不用再看。")
        gsub.setStyleSheet("font-size:11.5px; color:%s;" % t["faint"])

        lay.addWidget(badge, 0, Qt.AlignLeft)
        lay.addSpacing(11)
        lay.addWidget(h2)
        lay.addSpacing(6)
        lay.addWidget(gsub)
        lay.addSpacing(18)

        for i, (title, must, desc, is_must) in enumerate(GUIDE_STEPS, 1):
            lay.addWidget(self._step(i, title, must, desc, is_must, t))
            if i < len(GUIDE_STEPS):
                lay.addSpacing(11)

        lay.addStretch(1)

        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setWidget(inner)
        outer.addWidget(sc, 1)

        # 底部
        sep = QFrame(); sep.setFixedHeight(1)
        sep.setStyleSheet("background:%s;" % t["line"])
        outer.addWidget(sep)

        foot = QWidget()
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(26, 13, 26, 16)
        fl.setSpacing(12)

        ok = Btn("知道了，开始用", "primary")
        ok.clicked.connect(on_close)
        hint = QLabel("以后想再看：点右上角 <b>?</b> 按钮")
        hint.setStyleSheet("font-size:11.5px; color:%s;" % t["faint"])

        fl.addWidget(ok)
        fl.addWidget(hint)
        fl.addStretch(1)
        outer.addWidget(foot)

    def _step(self, n, title, must, desc, is_must, t):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(13)

        # 序号圆点
        num = QLabel(str(n))
        num.setFixedSize(26, 26)
        num.setAlignment(Qt.AlignCenter)
        if is_must:
            num.setStyleSheet(
                "background:%s; color:#ffffff; border-radius:13px;"
                "font-size:12.5px; font-weight:700;" % t["blue"])
        else:
            num.setStyleSheet(
                "background:%s; color:%s; border-radius:13px;"
                "font-size:12.5px; font-weight:700;" % (t["card3"], t["sub"]))
        lay.addWidget(num, 0, Qt.AlignTop)

        box = QVBoxLayout()
        box.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(7)
        tt = QLabel(title)
        tt.setStyleSheet("font-size:13px; font-weight:700;")
        top.addWidget(tt)
        if must:
            mk = QLabel(must)
            mk.setStyleSheet(
                "font-size:10px; color:%s; background:%s; border-radius:8px;"
                "padding:2px 8px;" % (t["gold"], t["gold_bg"]))
            top.addWidget(mk)
        top.addStretch(1)

        dd = QLabel(desc)
        dd.setWordWrap(True)
        dd.setStyleSheet("font-size:12px; color:%s; line-height:19px;" % t["sub"])

        box.addLayout(top)
        box.addWidget(dd)
        lay.addLayout(box, 1)
        return w


# ============================================================
# 弹层总管
# ============================================================
class OverlayHost(QObject):
    """
    挂在主窗口上，管所有弹层。

    ★ 为什么做成一个"总管"：遮罩层要铺满整个窗口、要跟着窗口缩放，
      还得保证同时只有一个弹层。这些事集中在一个人身上最省事。
    """

    def __init__(self, window):
        super().__init__(window)
        self.win = window
        self._layer = None
        self._toasts = []
        window.installEventFilter(self)

    # ---- 跟随窗口缩放 ----
    def eventFilter(self, obj, ev):
        if obj is self.win and ev.type() == QEvent.Resize:
            if self._layer is not None:
                self._layer.setGeometry(0, 0, self.win.width(), self.win.height())
            self._place_toasts()
        return super().eventFilter(obj, ev)

    # ---- 内部：开一个遮罩层 ----
    def _open_layer(self, on_close, alpha=0.62):
        self.close()
        m = _Mask(self.win, on_close=on_close, alpha=alpha)
        m.set_theme(getattr(self.win, "_theme_name", "dark"))
        m.setGeometry(0, 0, self.win.width(), self.win.height())
        m.show()
        m.raise_()
        self._layer = m
        return m

    def _center(self, card, w=None, h=None, y_ratio=0.5, top_min=34):
        """把卡片摆到中间（y_ratio 控制偏上还是居中）。"""
        card.adjustSize()
        if w:
            card.setFixedWidth(w)
        if h:
            card.setFixedHeight(h)
        p = self._layer
        y = int(p.height() * y_ratio - card.height() / 2.0)
        y = max(top_min, y)
        card.move((p.width() - card.width()) // 2, y)
        card.show()
        card.raise_()

    def close(self):
        if self._layer is not None:
            self._layer.hide()
            self._layer.deleteLater()
            self._layer = None

    # ========================================================
    # ① Toast
    # ========================================================
    def toast(self, text, kind="info", ms=2600):
        # ★ 第 34 轮：留一个**只增不减**的计数器。
        #   为什么要它：自检工具想知道"这一下到底弹没弹提示"。
        #   原来靠"数当前可见的 toast 条数"，但 toast 会自己过期消失 ——
        #   旧的刚消失、新的刚出现，条数可能**正好抵消**，工具就误判成
        #   "什么都没发生"。计数器只增不减，永远不会抵消。
        self._toast_seq = getattr(self, "_toast_seq", 0) + 1
        self._toast_log = getattr(self, "_toast_log", [])
        self._toast_log.append(text)
        del self._toast_log[:-20]              # 只留最近 20 条
        t = _Toast(self.win, text, kind, ms)
        self._toasts.append(t)
        # ★ 顺序不能反（第 34 轮修的坑）：
        #   原来先 _place_toasts() 再 pop_in()。而 _place_toasts 里会
        #   把"不可见的"从列表里剔掉 —— 此时新 toast 还没 show，
        #   于是**刚建出来就被扔掉**，位置也算不对。
        #   正确顺序：先让它显示出来，再统一摆位置。
        t.pop_in()
        self._place_toasts()

    def _place_toasts(self):
        # ★ 第 34 轮修：toast 是带自动关闭的动画控件，到点会自己 deleteLater。
        #   如果这时它还在 `_toasts` 列表里，`x.isVisible()` 会抛
        #     RuntimeError: Internal C++ object (_Toast) already deleted
        #   ——在信号回调里抛异常会被 Qt 吞掉，但整条 toast 链就断了，
        #     后面的提示全都不显示（表现就是"点了没反应"）。
        #   所以这里逐个 try，已经没了的直接扔掉。
        alive = []
        for x in self._toasts:
            try:
                if x.isVisible():
                    alive.append(x)
            except Exception:
                pass                 # 已经被回收，忽略
        self._toasts = alive
        y = self.win.height() - 22
        for t in reversed(self._toasts):
            try:
                y -= (t.height() + 9)
                t.move(self.win.width() - t.width() - 22, y)
            except Exception:
                pass

    # ========================================================
    # ② Modal
    # ========================================================
    def modal(self, title, body, buttons=None, width=430):
        """
        buttons: [(文字, 回调 or None, 类型)]  类型 = ghost / primary / danger
        ★ 不传 buttons 时给个默认「知道了」，避免弹出关不掉的框。
        """
        def _close():
            self.close()

        if not buttons:
            buttons = [("知道了", None, "primary")]

        m = self._open_layer(_close)
        card = _ModalCard(m, title, body, buttons, _close)
        self._center(card, w=width)

    # ========================================================
    # ③ 命令面板
    # ========================================================
    def palette(self, extra_commands=None):
        cmds = list(extra_commands or []) + self._default_commands()

        def _close():
            self.close()

        m = self._open_layer(_close, alpha=0.66)
        card = _Palette(m, cmds, _close)
        # ★ 大厂习惯：命令面板靠上（VS Code 大约在 1/4 处），
        #   留出下方空间给"还能看到的背景"，让人有上下文感。
        self._center(card, y_ratio=0.30)
        card.focus_input()

    def _default_commands(self):
        """默认命令表：跳页 + 常用动作。"""
        w = self.win
        out = []
        pages = getattr(w, "PAGE_LABELS", None) or []
        for key, label in pages:
            out.append(("跳到「%s」" % label, "页面", key,
                        lambda k=key: w.goto(k)))
        out += [
            ("切换深色 / 浅色", "外观", "theme dark light 主题",
             lambda: w.toggle_theme()),
            ("打开使用引导", "帮助", "guide help 引导",
             lambda: self.guide()),
            ("去设置 · 模型设置", "设置", "model api key 模型",
             lambda: w._goto_settings_panel("model")),
            ("去设置 · 账号与设备", "设置", "device phone 设备 手机",
             lambda: w._goto_settings_panel("account")),
            ("去设置 · 数据与备份", "设置", "backup data 备份 数据",
             lambda: w._goto_settings_panel("data")),
        ]
        return out

    # ========================================================
    # ⑤ 自定义卡片（内容自己会变的，比如"AI 干活的过程面板"）
    # ========================================================
    def custom(self, make_card, width=None, height=None, y_ratio=0.5):
        """
        make_card(mask) 返回一个卡片控件。用它是因为有些弹层的内容
        是**实时变化**的（8 步进度），不能像 modal 那样一次摆好就不动。
        """
        def _close():
            self.close()

        m = self._open_layer(_close, alpha=0.66)
        card = make_card(m)
        self._center(card, w=width, h=height, y_ratio=y_ratio)
        return card

    # ========================================================
    # ④ 新手引导
    # ========================================================
    def guide(self):
        def _close():
            self.close()

        m = self._open_layer(_close, alpha=0.68)
        card = _GuideCard(m, _close)
        # ★ 高度按内容实需给（4 步 + 头 + 脚约 580），窗口矮时按比例缩
        h = min(580, int(self.win.height() * 0.88))
        h = max(400, h)
        self._center(card, w=560, h=h, y_ratio=0.5)
