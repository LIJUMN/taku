# -*- coding: utf-8 -*-
"""
Taku 管理台 · 主题色板（深色 / 浅色两套）

★ 数据来源：1:1 抄自图纸 `管理台界面原型-v3.html` 的 CSS 变量（第 26~58 行）。
  - 深色 = `html[data-theme="dark"], :root`
  - 浅色 = `html[data-theme="light"]`

★ 规矩（规格书 17.4 三条硬约束）：
  1. 9 页一个不少
  2. 深色浅色双主题
  3. 布局文案照抄图纸，不许自己发挥
"""

# ============================================================
# 深色（默认）
# ============================================================
DARK = {
    "name": "dark",

    # 圆角 / 间距
    "r_sm": "7px",  "r_md": "10px", "r_lg": "13px", "r_xl": "16px",
    "sp": "8px",

    # 强调色（两套主题共用同一批语义色）
    "blue":   "#4c8dff", "blue2": "#2f6fed",
    "green":  "#3ecf8e",
    "gold":   "#e8b34b",
    "purple": "#a479f5",
    "red":    "#ff5c5c",
    "pink":   "#e06ab0",
    "cyan":   "#3ec9cf",

    # 背景 / 面板 / 卡片
    "bg":     "#0d1117",
    "panel":  "#121820",
    "card":   "#18202b",
    "card2":  "#1e2836",
    "card3":  "#232e3d",

    # 线条
    "line":   "#27303e",
    "line2":  "#33405a",

    # 文字
    "ink":    "#e8edf4",   # 主文字
    "sub":    "#93a0b2",   # 次级文字
    "faint":  "#64707f",   # 最弱文字

    # 语义底色（半透明）
    "blue_bg":   "rgba(76,141,255,.12)",
    "green_bg":  "rgba(62,207,142,.12)",
    "gold_bg":   "rgba(232,179,75,.12)",
    "purple_bg": "rgba(164,121,245,.14)",
    "red_bg":    "rgba(255,92,92,.12)",
    "pink_bg":   "rgba(224,106,176,.12)",
    "cyan_bg":   "rgba(62,201,207,.12)",

    # 其它
    "scroll_hover": "#4a5b78",
    "shadow":  "0 8px 30px rgba(0,0,0,.45)",
    "overlay": "rgba(4,7,12,.62)",
}

# ============================================================
# 浅色
# ============================================================
LIGHT = {
    "name": "light",

    "r_sm": "7px",  "r_md": "10px", "r_lg": "13px", "r_xl": "16px",
    "sp": "8px",

    # ★ 浅色下强调色也会压暗一档（图纸第 57~58 行）
    "blue":   "#2f6fed", "blue2": "#2f6fed",
    "green":  "#17a069",
    "gold":   "#c8871a",
    "purple": "#8250dc",
    "red":    "#e03232",
    "pink":   "#c83c96",
    "cyan":   "#1496a0",

    "bg":     "#f4f6fa",
    "panel":  "#ffffff",
    "card":   "#ffffff",
    "card2":  "#f7f9fc",
    "card3":  "#eef2f8",

    "line":   "#e2e8f0",
    "line2":  "#cbd5e1",

    "ink":    "#1a2231",
    "sub":    "#5b6b82",
    "faint":  "#93a0b2",

    # ★ 浅色下底色是加一层浅色，而不是减一层暗色
    "blue_bg":   "rgba(47,111,237,.10)",
    "green_bg":  "rgba(23,160,105,.12)",
    "gold_bg":   "rgba(200,140,20,.13)",
    "purple_bg": "rgba(130,80,220,.11)",
    "red_bg":    "rgba(224,50,50,.10)",
    "pink_bg":   "rgba(200,60,150,.10)",
    "cyan_bg":   "rgba(20,150,160,.11)",

    "scroll_hover": "#94a3b8",
    "shadow":  "0 6px 24px rgba(30,45,80,.10)",
    "overlay": "rgba(20,30,50,.42)",
}

THEMES = {"dark": DARK, "light": LIGHT}


def get(name="dark"):
    """按名字取主题色板；不认识的名字一律回退深色。"""
    return THEMES.get(name, DARK)


# ============================================================
# ★ 当前主题（第 26 轮新增，修一个系统性缺陷）
#
#   问题：页面代码里以前到处写 `TH.DARK["blue"]`，等于把深色的颜色
#         写死进了控件的样式字符串。切浅色时，这些地方不会跟着变。
#         一共 75 处 —— 浅色主题看着就"花"了。
#
#   做法：页面一律写 `TH.cur()["blue"]`，它拿的是**当前**主题的色值。
#         切主题时主窗口调 set_current()，再重建页面，
#         所有颜色一次性跟着走。
# ============================================================
_CURRENT = {"name": "dark"}


def set_current(name):
    _CURRENT["name"] = name if name in THEMES else "dark"


def cur():
    """取当前主题色板。★ 页面里一律用它，不要写 TH.DARK。"""
    return THEMES.get(_CURRENT["name"], DARK)


def cur_name():
    return _CURRENT["name"]


def to_qss(t, extra=""):
    """
    把色板渲染成 Qt 样式表（QSS）。

    ★ 为什么用 QSS 而不是给每个控件写 palette：
      Qt 的 palette 机制对"圆角/边框/悬停/选中"这类东西控制力很弱，
      而图纸是 CSS 画出来的，QSS 的语法跟 CSS 最像 —— 抄起来最省事。
      这就是选 PySide6 的原因之一（规格书 11.1：必须 Windows 落地）。
    """
    return (_BASE_QSS.format(t=t) + extra)


# ============================================================
# 全局样式表骨架
#   ★ 每个占位符都对应色板里一个键，改主题 = 换色板，不动这个模板
# ============================================================
_BASE_QSS = """
/* ---------- 全局 ---------- */
* {{
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 12px;
    outline: none;
}}
QWidget {{
    background: {t[bg]};
    color: {t[ink]};
}}
QToolTip {{
    background: {t[card3]};
    color: {t[ink]};
    border: 1px solid {t[line]};
    border-radius: {t[r_sm]};
    padding: 6px 9px;
}}

/* ---------- 滚动条 ---------- */
QScrollBar:vertical {{
    background: transparent; width: 9px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {t[line2]}; border-radius: 4px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {t[scroll_hover]}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

QScrollBar:horizontal {{
    background: transparent; height: 9px; margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {t[line2]}; border-radius: 4px; min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{ background: {t[scroll_hover]}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}

/* ---------- 顶部全局栏 ---------- */
QFrame#TopBar {{
    background: {t[panel]};
    border-bottom: 1px solid {t[line]};
}}
QLabel#Brand {{
    font-size: 15px; font-weight: 700; letter-spacing: .4px; color: {t[ink]};
}}
QLabel#BrandVer {{ font-size: 10.5px; color: {t[faint]}; font-weight: 500; }}

/* 「这一页的数字是示例」的诚实声明条（第 32 轮加） */
QFrame#SampleNote {{
    background: {t[gold_bg]};
    border: 1px solid {t[line]};
    border-radius: {t[r_md]};
}}

/* 顶部状态条（黄条）—— 只显示最高优先级一条（规格书第 16 章） */
QFrame#StatusBar {{
    background: {t[gold_bg]};
    border-radius: {t[r_sm]};
}}
QLabel#StatusText {{
    color: {t[gold]};
    font-size: 11.5px;
}}
/* 「还有 N 条」小按钮（图纸 .sbar-more） */
QPushButton#SbarMore {{
    background: {t[gold_bg]};
    color: {t[gold]};
    border: 1px solid transparent;
    border-radius: {t[r_sm]};
    padding: 3px 9px;
    font-size: 10.5px;
}}
QPushButton#SbarMore:hover {{
    border-color: {t[gold]};
}}

/* 今日目标小药丸 */
QFrame#GoalPill {{
    background: {t[card]};
    border: 1px solid {t[line]};
    border-radius: {t[r_lg]};
}}
QLabel#GoalLabel {{ color: {t[sub]}; font-size: 11px; }}
QLabel#GoalNum   {{ color: {t[ink]}; font-weight: 700; font-size: 12.5px; }}
QProgressBar#GoalBar {{
    background: {t[line]}; border: none; border-radius: 3px; height: 6px;
}}
QProgressBar#GoalBar::chunk {{ background: {t[blue]}; border-radius: 3px; }}

/* 顶栏图标按钮 */
QPushButton#IconBtn {{
    background: transparent; border: 1px solid transparent;
    border-radius: {t[r_sm]}; color: {t[sub]};
    font-size: 15px; padding: 0;
}}
QPushButton#IconBtn:hover  {{ background: {t[card]}; color: {t[ink]}; }}
QPushButton#IconBtn:checked{{ background: {t[blue_bg]}; color: {t[blue]}; }}

/* ---------- 左侧导航 ---------- */
QFrame#SideNav {{
    background: {t[panel]};
    border-right: 1px solid {t[line]};
}}
QPushButton#NavItem {{
    background: transparent; border: none; border-left: 2px solid transparent;
    border-radius: {t[r_md]};
    color: {t[sub]}; text-align: left; padding: 9px 10px 9px 10px;
    font-size: 12.5px;
}}
QPushButton#NavItem:hover {{ background: {t[card]}; color: {t[ink]}; }}
QPushButton#NavItem:checked {{
    background: {t[blue_bg]}; color: {t[blue]}; font-weight: 600;
    border-left: 2px solid {t[blue]};
}}
QFrame#NavSep {{ background: {t[line]}; max-height: 1px; }}

/* 导航角标 */
QLabel#NavBadge {{
    background: {t[red]}; color: #ffffff;
    border-radius: 8px; padding: 1px 6px;
    font-size: 10px; font-weight: 700;
}}

/* ---------- 底部状态栏 ---------- */
QFrame#StatusFooter {{
    background: {t[panel]};
    border-top: 1px solid {t[line]};
}}
QLabel#FootEvent {{ color: {t[sub]}; font-size: 11.5px; }}
QLabel#FootItem  {{ color: {t[sub]}; font-size: 11.5px; }}
QLabel#FootItemOk   {{ color: {t[green]}; font-size: 11.5px; }}
QLabel#FootItemWarn {{ color: {t[gold]} ; font-size: 11.5px; }}

/* ---------- 通用卡片 / 按钮 ---------- */
QFrame#Card {{
    background: {t[card]};
    border: 1px solid {t[line]};
    border-radius: {t[r_lg]};
}}
QLabel#CardTitle {{ font-size: 13px; font-weight: 700; color: {t[ink]}; }}
QLabel#Sub  {{ color: {t[sub]};   font-size: 11.5px; }}
QLabel#Faint{{ color: {t[faint]}; font-size: 11px; }}

QPushButton#Btn {{
    background: {t[card2]}; border: 1px solid {t[line]};
    border-radius: {t[r_sm]}; color: {t[ink]}; padding: 6px 13px;
}}
QPushButton#Btn:hover {{ border-color: {t[line2]}; background: {t[card3]}; }}

QPushButton#BtnPrimary {{
    background: {t[blue]}; border: 1px solid {t[blue]};
    border-radius: {t[r_sm]}; color: #ffffff;
    padding: 6px 13px; font-weight: 600;
}}
QPushButton#BtnPrimary:hover {{ background: {t[blue2]}; border-color: {t[blue2]}; }}

QPushButton#BtnGhost {{
    background: transparent; border: 1px solid {t[line]};
    border-radius: {t[r_sm]}; color: {t[sub]}; padding: 6px 13px;
}}
QPushButton#BtnGhost:hover {{ color: {t[ink]}; border-color: {t[line2]}; }}

QPushButton#BtnDanger {{
    background: transparent; border: 1px solid {t[line]};
    border-radius: {t[r_sm]}; color: {t[red]}; padding: 6px 13px;
}}
QPushButton#BtnDanger:hover {{ background: {t[red_bg]}; border-color: {t[red]}; }}

/* 平台筛选小胶囊 */
QPushButton#Chip {{
    background: transparent; border: 1px solid {t[line]};
    border-radius: 11px; color: {t[sub]}; padding: 3px 11px; font-size: 11.5px;
}}
QPushButton#Chip:hover {{ color: {t[ink]}; border-color: {t[line2]}; }}
QPushButton#Chip:checked {{
    background: {t[blue_bg]}; border-color: {t[blue]};
    color: {t[blue]}; font-weight: 600;
}}

/* ---------- 输入框 ---------- */
QLineEdit, QPlainTextEdit, QTextEdit {{
    background: {t[card]}; border: 1px solid {t[line]};
    border-radius: {t[r_sm]}; color: {t[ink]};
    padding: 6px 9px;
    selection-background-color: {t[blue]};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border-color: {t[blue]};
}}
QComboBox {{
    background: {t[card]}; border: 1px solid {t[line]};
    border-radius: {t[r_sm]}; color: {t[ink]}; padding: 5px 9px;
}}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    background: {t[card2]}; border: 1px solid {t[line]};
    color: {t[ink]}; selection-background-color: {t[blue_bg]};
    selection-color: {t[blue]};
}}

/* ---------- 页面标题 ---------- */
QLabel#PageTitle {{ font-size: 17px; font-weight: 700; color: {t[ink]}; }}
QLabel#PageSub   {{ font-size: 11.5px; color: {t[faint]}; }}

/* ---------- 提示框 ---------- */
QFrame#TipBox {{
    background: {t[blue_bg]};
    border: 1px solid {t[line]};
    border-left: 3px solid {t[blue]};
    border-radius: {t[r_md]};
}}
QLabel#TipText {{ color: {t[sub]}; font-size: 11.5px; }}
"""
