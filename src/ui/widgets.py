# -*- coding: utf-8 -*-
"""
Taku 管理台 · 常用小控件

★ 只放"图纸里到处都用、但 Qt 里没有现成对应物"的东西。
★ 规矩：命名跟图纸 CSS 类名对齐（Card / Chip / IconBtn / Btn / BtnPrimary …），
        这样以后拿图纸核对时能一行一行对上。
"""

from PySide6.QtCore import Qt, Signal, QSize, QEvent
from PySide6.QtWidgets import (
    QFrame, QLabel, QPushButton, QHBoxLayout, QVBoxLayout,
    QWidget, QSizePolicy, QGraphicsDropShadowEffect,
)
from PySide6.QtGui import QColor

from . import theme as _TH
from . import icons as _IC


# ============================================================
# 卡片
# ============================================================
class Card(QFrame):
    """图纸 .card —— 圆角 + 1px 边 + 卡片底色。"""

    def __init__(self, parent=None, padding=14, spacing=10, pad_side=None):
        super().__init__(parent)
        self.setObjectName("Card")
        lay = QVBoxLayout(self)
        h = pad_side if pad_side is not None else padding
        lay.setContentsMargins(h, padding, h, padding)
        lay.setSpacing(spacing)
        self._lay = lay

    def body(self):
        return self._lay

    def add(self, w):
        self._lay.addWidget(w)
        return w


# ============================================================
# 标题 / 文字
# ============================================================
def title(text, size=13, weight=700):
    lb = QLabel(text)
    lb.setObjectName("CardTitle")
    lb.setStyleSheet("font-size:%dpx; font-weight:600;" % size)
    return lb


def sub(text):
    lb = QLabel(text)
    lb.setObjectName("Sub")
    return lb


def faint(text):
    lb = QLabel(text)
    lb.setObjectName("Faint")
    return lb


def page_title(text):
    lb = QLabel(text)
    lb.setObjectName("PageTitle")
    return lb


def page_sub(text):
    lb = QLabel(text)
    lb.setObjectName("PageSub")
    lb.setWordWrap(True)
    return lb


# ============================================================
# 按钮
# ============================================================
class Btn(QPushButton):
    """普通按钮（图纸 .btn）。"""

    def __init__(self, text, kind="", parent=None, icon_name=None):
        super().__init__(text, parent)
        if kind == "primary":
            self.setObjectName("BtnPrimary")
        elif kind == "ghost":
            self.setObjectName("BtnGhost")
        elif kind == "danger":
            self.setObjectName("BtnDanger")
        else:
            self.setObjectName("Btn")
        self.setCursor(Qt.PointingHandCursor)
        self._icon_name = icon_name
        if icon_name:
            self.setIconSize(QSize(14, 14))
        self.set_theme("dark")

    def set_theme(self, name):
        """图标颜色跟着主题走（大厂做法：按钮图标跟文字同色）。"""
        self._theme_name = name
        if not self._icon_name:
            return
        t = _TH.get(name)
        col = {
            "BtnPrimary": "#ffffff",
            "BtnDanger": t["red"],
        }.get(self.objectName(), t["sub"])
        self.setIcon(_IC.make_icon_simple(self._icon_name, 14, col))

    def set_icon(self, icon_name):
        """换图标（比如锁定按钮在 锁 ↔ 开锁 之间切）。"""
        self._icon_name = icon_name
        self.set_theme(getattr(self, "_theme_name", "dark"))


class IconBtn(QPushButton):
    """
    顶栏图标按钮（图纸 .icon-btn）。
    ★ 第 26 轮：emoji → **图纸原版线条 SVG**（描边随选中状态变色）。
    """

    def __init__(self, icon_name, tip="", parent=None, size=30, icon_size=17):
        super().__init__("", parent)
        self.setObjectName("IconBtn")
        self.setToolTip(tip)
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self._icon_name = icon_name
        self.setIconSize(QSize(icon_size, icon_size))
        self.set_theme("dark")

    def set_theme(self, name):
        self._theme_name = name
        t = _TH.get(name)
        self.setIcon(_IC.make_icon(self._icon_name, 17,
                                   on=t["blue"], off=t["sub"]))

    def set_icon(self, icon_name):
        """换图标（比如主题按钮在 月亮 ↔ 太阳 之间切）。"""
        self._icon_name = icon_name
        self.set_theme(getattr(self, "_theme_name", "dark"))


class LinkLabel(QLabel):
    """
    长得像文字、点得动的"查看全部 →"这类入口。

    ★ 大厂做法：既不占按钮的位置，又要有 hover 反馈和手型光标。
      QLabel 本身点不动，包一层发出 clicked 信号。
    """

    clicked = Signal()

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setObjectName("LinkLabel")
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()


class Chip(QPushButton):
    """筛选小胶囊（图纸 .chip-btn）—— 可选中的那种。"""

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setObjectName("Chip")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)


# ============================================================
# 导航项（带图标 + 可选角标）
# ============================================================
class NavItem(QPushButton):
    """
    左侧导航按钮（图纸 .nav-item）。

    ★ 第 26 轮改造（对标大厂）：
      - 图标：emoji → **图纸原版 SVG 线条**，未选中灰、选中变主色
      - 角标：原来是"文字里拼个 (3)"，现在改成**右侧真角标**（红底白字小圆）
        大厂（飞书 / 微信桌面版）都是这个做法。
    """

    def __init__(self, icon_name, text, parent=None):
        super().__init__(text, parent)
        self.setObjectName("NavItem")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(38)
        self.setIconSize(QSize(17, 17))
        self._icon_name = icon_name

        # 角标（绝对定位在右边）
        self._badge = 0
        self._badge_lb = QLabel(self)
        self._badge_lb.setObjectName("NavBadge")
        self._badge_lb.setAlignment(Qt.AlignCenter)
        self._badge_lb.hide()

        self.set_theme("dark")

    def set_badge(self, n):
        self._badge = int(n or 0)
        if self._badge > 0:
            self._badge_lb.setText(str(self._badge))
            self._badge_lb.setFixedHeight(16)
            self._badge_lb.setMinimumWidth(16)
            self._badge_lb.adjustSize()
            self._badge_lb.show()
            self._place_badge()
        else:
            self._badge_lb.hide()

    def _place_badge(self):
        w = max(16, self._badge_lb.width())
        self._badge_lb.setFixedWidth(w)
        self._badge_lb.move(self.width() - w - 11,
                            (self.height() - 16) // 2)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._badge > 0:
            self._place_badge()

    def set_theme(self, name):
        t = _TH.get(name)
        self.setIcon(_IC.make_icon(self._icon_name, 17,
                                   on=t["blue"], off=t["sub"]))
        self._badge_lb.setStyleSheet(
            "background:%s; color:#ffffff; border-radius:8px;"
            "font-size:10px; font-weight:700; padding:0 4px;" % t["red"]
        )


# ============================================================
# 分隔线
# ============================================================
def hline():
    f = QFrame()
    f.setObjectName("NavSep")
    f.setFixedHeight(1)
    f.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    return f


def vline():
    f = QFrame()
    f.setObjectName("NavSep")
    f.setFixedWidth(1)
    f.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
    return f


# ============================================================
# 投影（给弹层用）
# ============================================================
def add_shadow(w, blur=30, dy=8, alpha=110):
    eff = QGraphicsDropShadowEffect(w)
    eff.setBlurRadius(blur)
    eff.setOffset(0, dy)
    eff.setColor(QColor(0, 0, 0, alpha))
    w.setGraphicsEffect(eff)
    return eff


# ============================================================
# ★ 页面 → 弹层的便捷通道（第 26 轮）
#
#   问题：页面是主窗口的子控件，但弹层总管挂在主窗口上。
#         每个页面都写一遍"往上找主窗口、再找 overlay"太啰嗦。
#   做法：两个小函数，任何控件都能用。
#   ★ 拿不到弹层时**静默不报错** —— 单独跑某个页面的调试脚本时不该崩。
# ============================================================
def get_overlay(widget):
    try:
        w = widget.window()
        return getattr(w, "overlay", None)
    except Exception:
        return None


def toast(widget, text, kind="info", ms=2600):
    """右下角轻提示。kind: info / ok / warn / error"""
    ov = get_overlay(widget)
    if ov is not None:
        ov.toast(text, kind, ms)


def modal(widget, title, body, buttons=None, width=430):
    """居中弹层。buttons: [(文字, 回调 or None, 类型)]"""
    ov = get_overlay(widget)
    if ov is not None:
        ov.modal(title, body, buttons, width)


def ask(widget, title, body, on_yes, yes_text="确定", danger=False):
    """要用户点一下头才做的事，统一走这个（大厂：破坏性操作必须二次确认）。"""
    modal(widget, title, body, [
        ("再想想", None, "ghost"),
        (yes_text, on_yes, "danger" if danger else "primary"),
    ])


# ============================================================
# 空态块（图纸 .empty —— 7 页各一句文案，规格书第 16 章）
# ============================================================
class Empty(QWidget):
    """
    空态。可以带一个"引导按钮"（大厂做法：空态不是死胡同，
    要让用户知道下一步点哪）。
    """
    def __init__(self, ico, title_text, desc, action=None, parent=None):
        """
        action: 可选。给空态挂"下一步"的入口。
                · 一个：(按钮文字, 回调)
                · 多个：[(文字, 回调), (文字, 回调)]
          ★ 为什么允许多个：空态不该是死胡同。用户点进来什么都干不了，
            就会觉得"这页是坏的"。给他几个真能点的去处。
        """
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 40, 0, 40)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignCenter)

        i = QLabel(ico)
        i.setAlignment(Qt.AlignCenter)
        i.setStyleSheet("font-size:34px;")

        t = QLabel(title_text)
        t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet("font-size:13.5px; font-weight:600;")

        d = QLabel(desc)
        d.setAlignment(Qt.AlignCenter)
        d.setObjectName("Faint")
        d.setWordWrap(True)

        lay.addWidget(i)
        lay.addWidget(t)
        lay.addWidget(d)

        if action:
            acts = action if isinstance(action, (list, tuple)) and action \
                and isinstance(action[0], (list, tuple)) else [action]
            row = QHBoxLayout()
            row.setAlignment(Qt.AlignCenter)
            row.setSpacing(8)
            for label, cb in acts:
                b = Btn(label, "ghost")
                b.setCursor(Qt.PointingHandCursor)
                b.clicked.connect(cb)
                row.addWidget(b)
            lay.addLayout(row)


# ============================================================
# 键值行（图纸 .acct-kv —— 设置页到处用）
# ============================================================
class KV(QWidget):
    """键值行（图纸 .acct-kv —— 设置页到处用）。值可以随时改。"""

    def __init__(self, k, v, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 5, 0, 5)
        lay.setSpacing(8)

        self._lk = QLabel(k)
        self._lk.setObjectName("Sub")

        self._lv = QLabel(str(v))
        self._lv.setStyleSheet("font-weight:600;")

        lay.addWidget(self._lk)
        lay.addStretch(1)
        lay.addWidget(self._lv)

    def set_value(self, v):
        self._lv.setText(str(v))

    def set_value_color(self, color):
        self._lv.setStyleSheet("font-weight:600; color:%s;" % color)


# ============================================================
# 进度条（图纸 .bar —— 细长条）
# ============================================================
class MiniBar(QWidget):
    def __init__(self, pct, color_key="blue", parent=None):
        super().__init__(parent)
        self._pct = max(0.0, min(1.0, float(pct)))
        self._color_key = color_key
        self.setFixedHeight(5)
        self.setMinimumWidth(50)

    def paintEvent(self, e):
        from PySide6.QtGui import QPainter
        from . import theme
        t = theme.get(getattr(self, "_theme_name", "dark"))
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect()
        # 轨道
        p.setBrush(QColor(t["line"]))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(r, 2.5, 2.5)
        # 填充
        w = int(r.width() * self._pct)
        if w > 0:
            p.setBrush(QColor(t.get(self._color_key, t["blue"])))
            p.drawRoundedRect(0, 0, w, r.height(), 2.5, 2.5)

    def set_pct(self, v):
        self._pct = max(0.0, min(1.0, float(v)))
        self.update()

    def set_theme(self, name):
        self._theme_name = name
        self.update()
