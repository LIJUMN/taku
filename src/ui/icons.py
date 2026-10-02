# -*- coding: utf-8 -*-
"""
Taku 管理台 · 图标库（矢量线条图标）

★ 为什么要有这个文件（对标大厂）：
    工具型桌面应用（VS Code / Linear / 影刀 RPA / 飞书）全部使用
    **同一套 24×24 网格、同一档描边粗细、颜色跟随状态**的线条图标。
    这是"看起来像专业工具"和"看起来像玩具"之间最一眼的差距。

★ 图标数据来源：
    **1:1 抄自图纸 `管理台界面原型-v3.html`** 里内嵌的 SVG（nav 第 1002~1040 行、
    顶栏第 964~995 行）。只抽 `path/circle/rect` 部分，外层 `<svg>` 由本文件拼。

★ 用法：
    pm  = render("send", 16, "#4c8dff")          # 拿 QPixmap
    ico = make_icon("overview", 18, on="#4c8dff", off="#93a0b2")   # 拿会变色的 QIcon
"""

from PySide6.QtCore import QByteArray, Qt, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtSvg import QSvgRenderer


# ============================================================
# ★ 图标数据 —— 全部 1:1 抄自图纸（24×24 网格）
#   只存内层图形，stroke-only、无填充
# ============================================================
ICONS = {
    # ---------- 左侧导航 9 项（图纸第 1002~1040 行） ----------
    "overview": (
        '<rect x="4" y="4" width="7" height="7" rx="1.5"/>'
        '<rect x="13" y="4" width="7" height="7" rx="1.5"/>'
        '<rect x="4" y="13" width="7" height="7" rx="1.5"/>'
        '<rect x="13" y="13" width="7" height="7" rx="1.5"/>'
    ),
    "customers": (
        '<circle cx="9" cy="8" r="3.2"/>'
        '<path d="M3.5 19c.8-3 3-4.6 5.5-4.6s4.7 1.6 5.5 4.6'
        'M16 8.6a3 3 0 0 1 0 5.8M17.5 14.6c1.7.8 2.9 2.2 3.3 4"/>'
    ),
    "messages": (
        '<path d="M21 11.5a8 8 0 0 1-8 8 8.6 8.6 0 0 1-3.6-.8L3 20l1.2-6'
        'a8 8 0 0 1 16.8-2.5z"/>'
    ),
    "strategy": (
        '<circle cx="12" cy="12" r="8.4"/><circle cx="12" cy="12" r="2.6"/>'
        '<path d="M12 14.6 15.6 8.4"/>'
    ),
    "skills": (
        '<path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H11v16H5.5A1.5 1.5 0 0 1 4 18.5z"/>'
        '<path d="M20 5.5A1.5 1.5 0 0 0 18.5 4H13v16h5.5a1.5 1.5 0 0 0 1.5-1.5z"/>'
    ),
    "tuoke": (
        '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/>'
        '<path d="M11 8.4v5.2M8.4 11h5.2"/>'
    ),
    "stats": '<path d="M5 20V10M12 20V4M19 20v-7"/>',
    "trash": (
        '<path d="M4 7h16M9.5 7V5.2A1.2 1.2 0 0 1 10.7 4h2.6'
        'a1.2 1.2 0 0 1 1.2 1.2V7M18 7l-.8 12.1A1.9 1.9 0 0 1 15.3 21H8.7'
        'a1.9 1.9 0 0 1-1.9-1.9L6 7"/>'
    ),
    "settings": (
        '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9'
        'l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5'
        'V21a2 2 0 1 1-4 0v-.1A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.9.3l-.1.1'
        'a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3'
        'a2 2 0 1 1 0-4h.1A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.3-1.9l-.1-.1'
        'a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3'
        'a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1'
        'a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9v.1a1.7 1.7 0 0 0 1.5 1'
        'H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>'
    ),

    # ---------- 顶栏（图纸第 964~995 行） ----------
    "logo": '<path d="M13 2 4 14h6l-1 8 9-12h-6l1-8z"/>',          # 闪电
    "moon": '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "bell": ('<path d="M18 8a6 6 0 1 0-12 0c0 7-3 8-3 8h18s-3-1-3-8'
             'M13.7 21a2 2 0 0 1-3.4 0"/>'),
    "help": ('<circle cx="12" cy="12" r="9"/>'
             '<path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .8-1 1.5v.2"/>'
             '<circle cx="12" cy="17" r=".6" fill="CURCOLOR" stroke="none"/>'),

    # ---------- 通用操作（大厂工具必备的那几个） ----------
    "send": '<path d="m3 11 18-7-7 18-3.5-7.5L3 11z"/>',           # 纸飞机
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "check": '<path d="m4.5 12.5 5 5 10-11"/>',
    "close": '<path d="M6 6l12 12M18 6L6 18"/>',
    "refresh": ('<path d="M20.5 12a8.5 8.5 0 1 1-2.5-6"/>'
                '<path d="M20.5 4v5h-5"/>'),
    "chevron_right": '<path d="m9 5 7 7-7 7"/>',
    "chevron_down": '<path d="m5 9 7 7 7-7"/>',
    "warn": ('<path d="M12 3.6 2.5 20h19z"/>'
             '<path d="M12 9.5v4.5"/>'
             '<circle cx="12" cy="17" r=".7" fill="CURCOLOR" stroke="none"/>'),
    "info": ('<circle cx="12" cy="12" r="9"/>'
             '<path d="M12 11v5.5"/>'
             '<circle cx="12" cy="7.8" r=".7" fill="CURCOLOR" stroke="none"/>'),
    "play": '<path d="M6 3.8 20 12 6 20.2z"/>',
    "pause": '<path d="M8.5 4v16M15.5 4v16"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    "phone": ('<rect x="6.5" y="2.5" width="11" height="19" rx="2.5"/>'
              '<path d="M10.5 18.5h3"/>'),
    "robot": ('<rect x="3.5" y="7" width="17" height="12" rx="3"/>'
              '<circle cx="9" cy="13" r="1.4"/><circle cx="15" cy="13" r="1.4"/>'
              '<path d="M12 3.5v3.5M8 19v2M16 19v2"/>'),
    "user": ('<circle cx="12" cy="8" r="4"/>'
             '<path d="M4.5 20c1-4 4-6 7.5-6s6.5 2 7.5 6"/>'),
    "chat": ('<path d="M21 11.5a8 8 0 0 1-8 8 8.6 8.6 0 0 1-3.6-.8L3 20l1.2-6'
             'a8 8 0 0 1 16.8-2.5z"/>'),
    "clock": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    "flame": ('<path d="M12 21c4 0 6.5-2.6 6.5-6 0-4.5-4-6-4-9.5 0 0-3 1.5-4 5'
              '-1-1-1.5-2.5-1.5-4-2 2-3.5 4.5-3.5 8.5 0 3.4 2.5 6 6.5 6z"/>'),
    "shield": ('<path d="M12 3l7.5 3v6c0 4.5-3 7.8-7.5 9.5C7.5 19.8 4.5 16.5 4.5 12V6z"/>'
               '<path d="m9 12 2 2 4-4"/>'),
    "chart": '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    "folder": ('<path d="M3 7.5A2.5 2.5 0 0 1 5.5 5h3.2l2 2.5h8.8'
               'A2.5 2.5 0 0 1 22 10v7.5A2.5 2.5 0 0 1 19.5 20h-14'
               'A2.5 2.5 0 0 1 3 17.5z"/>'),
    "save": ('<path d="M4 5.5A1.5 1.5 0 0 1 5.5 4h10L20 8.5v10'
             'A1.5 1.5 0 0 1 18.5 20h-13A1.5 1.5 0 0 1 4 18.5z"/>'
             '<path d="M8 4v5h7V4M8 20v-6h8v6"/>'),
    "key": ('<circle cx="8" cy="13" r="4"/>'
            '<path d="M11.5 10.5 20 2M17 5l2.5 2.5M14.5 7.5 17 10"/>'),
    "palette": ('<circle cx="12" cy="12" r="9"/>'
                '<circle cx="9" cy="9.5" r="1.2" fill="CURCOLOR" stroke="none"/>'
                '<circle cx="15" cy="9.5" r="1.2" fill="CURCOLOR" stroke="none"/>'
                '<circle cx="9.5" cy="15" r="1.2" fill="CURCOLOR" stroke="none"/>'),
    "sun": ('<circle cx="12" cy="12" r="4.2"/>'
            '<path d="M12 2v3M12 19v3M2 12h3M19 12h3'
            'M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1"/>'),
    "dot": '<circle cx="12" cy="12" r="4" fill="CURCOLOR" stroke="none"/>',
    "more": ('<circle cx="5" cy="12" r="1.4" fill="CURCOLOR" stroke="none"/>'
             '<circle cx="12" cy="12" r="1.4" fill="CURCOLOR" stroke="none"/>'
             '<circle cx="19" cy="12" r="1.4" fill="CURCOLOR" stroke="none"/>'),

    # ---------- 遥控手机用的（第 28 轮） ----------
    "arrow_left": '<path d="M15 5 8 12l7 7"/><path d="M8 12h11"/>',
    "arrow_up": '<path d="M5 15l7-7 7 7"/><path d="M12 8v11"/>',
    "home": ('<path d="M4 10.6 12 4l8 6.6V20a1 1 0 0 1-1 1h-4.2v-6H9.2v6H5'
             'a1 1 0 0 1-1-1z"/>'),
    "lock": ('<rect x="5" y="10.5" width="14" height="9.5" rx="2.2"/>'
             '<path d="M8.6 10.5V7.2a3.4 3.4 0 0 1 6.8 0v3.3"/>'),
    "unlock": ('<rect x="5" y="10.5" width="14" height="9.5" rx="2.2"/>'
               '<path d="M8.6 10.5V7.2a3.4 3.4 0 0 1 6.5-1.3"/>'),
    "hand": ('<path d="M9 11V5.6a1.6 1.6 0 0 1 3.2 0V11"/>'
             '<path d="M12.2 11V4.6a1.6 1.6 0 0 1 3.2 0V11"/>'
             '<path d="M15.4 11.4V6.6a1.6 1.6 0 0 1 3.2 0v8.2'
             'A5.2 5.2 0 0 1 13.4 20h-1.2a5 5 0 0 1-4.3-2.4L5.3 13.3'
             'a1.6 1.6 0 0 1 1.9-2.4L9 11.7"/>'),
}

# 需要更粗描边的图标（顶栏 / logo 那种小的）
BOLD = {"logo"}

_cache = {}


# ============================================================
# 渲染
# ============================================================
def _svg_text(name, color, stroke):
    body = ICONS.get(name)
    if body is None:
        body = ICONS["dot"]
    body = body.replace("CURCOLOR", color)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        'fill="none" stroke="%s" stroke-width="%s" '
        'stroke-linecap="round" stroke-linejoin="round">%s</svg>'
        % (color, stroke, body)
    )


def render(name, size=18, color="#e8edf4", stroke=None, dpr=2.0):
    """
    渲染成 QPixmap（按 dpr 超采样，保证高分屏不糊）。

    ★ 为什么要 dpr：Qt 在高分屏下会把图放大，如果只画 18px 的图，
      放大后就糊了。按 2 倍画再交给 Qt 缩，边缘是锐的。
    """
    if stroke is None:
        stroke = 2.0 if name in BOLD else 1.8

    ck = (name, size, color, stroke, dpr)
    if ck in _cache:
        return _cache[ck]

    px = int(size * dpr)
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)

    r = QSvgRenderer(QByteArray(_svg_text(name, color, stroke).encode("utf-8")))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    r.render(p)
    p.end()

    pm.setDevicePixelRatio(dpr)
    _cache[ck] = pm
    return pm


def make_icon(name, size=18, on="#4c8dff", off="#93a0b2",
              stroke=None, disabled=None):
    """
    造一个"会跟着选中状态变色"的 QIcon。

    ★ 大厂做法：同一个图标，未选中是灰的、选中是主色、禁用更浅。
      Qt 里用 QIcon 的 On/Off 状态就能自动切，不用自己监听状态。
    """
    ico = QIcon()
    ico.addPixmap(render(name, size, off, stroke), QIcon.Normal, QIcon.Off)
    ico.addPixmap(render(name, size, on, stroke), QIcon.Normal, QIcon.On)
    ico.addPixmap(render(name, size, on, stroke), QIcon.Active, QIcon.On)
    ico.addPixmap(render(name, size, on, stroke), QIcon.Selected, QIcon.On)
    ico.addPixmap(render(name, size, disabled or "#4a5568", stroke),
                  QIcon.Disabled, QIcon.Off)
    return ico


def make_icon_simple(name, size=16, color="#93a0b2"):
    """单色图标（按钮上的、不随状态变色的那种）。"""
    return QIcon(render(name, size, color))


def pixmap(name, size=16, color="#93a0b2", stroke=None):
    return render(name, size, color, stroke)
