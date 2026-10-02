# -*- coding: utf-8 -*-
"""
Taku 管理台 · 主窗口

★ 结构 1:1 对齐图纸 `管理台界面原型-v3.html`：

    ┌─────────────────────────────────────────────┐
    │ TopBar   品牌 | 状态黄条 | 目标药丸 图标×5    │  header.topbar
    ├──────┬──────────────────────────────────────┤
    │ Side │                                      │
    │ Nav  │              <页面容器>               │  div.shell
    │ 9 项 │                                      │
    ├──────┴──────────────────────────────────────┤
    │ StatusFooter  事件流 | 各项指标               │  footer.statusbar
    └─────────────────────────────────────────────┘

★ 9 页（图纸 nav-item 顺序）：
    总览 / 客户 / 消息 / 策略 / 技能库 / 拓客 / 统计 / 回收站 / 设置

★ 三条硬约束（规格书 17.4）：
    1. 9 页一个不少               → 本文件 NAV 表写死 9 条
    2. 深色浅色双主题             → apply_theme() 换 QSS
    3. 布局文案照抄图纸           → 每个页面模块里的文案直接抄 HTML
"""

import sys
import os

from PySide6.QtCore import Qt, QSize, QTimer     # ★ 第 33 轮补：QTimer 以前漏 import 了
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QFrame, QLabel, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QSizePolicy, QApplication, QPushButton,
)
from PySide6.QtGui import QFont, QShortcut, QKeySequence

# 允许直接 python main_window.py 跑（把 src 加进 path）
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.dirname(_HERE)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from ui import theme as TH            # noqa: E402
from ui import icons                  # noqa: E402
from ui.widgets import (              # noqa: E402
    IconBtn, NavItem, hline, toast, modal,
)
from ui.overlays import OverlayHost   # noqa: E402
from ui import device_hub             # noqa: E402
from ui import datasource as DS       # noqa: E402  ★ 第 33 轮：壳层也接真数据

APP_TITLE = "Taku · 拓客台"

# ============================================================
# ★ 左侧导航 9 项（照抄图纸第 1001~1040 行，顺序一字不改）
#   第 26 轮：第 2 列从 emoji 换成 **图纸原版 SVG 图标名**（见 icons.py）
# ============================================================
NAV = [
    ("overview",  "overview",  "总览",   0),
    ("customers", "customers", "客户",   0),
    ("messages",  "messages",  "消息",   3),   # 图纸 badge=3
    ("strategy",  "strategy",  "策略",   0),
    ("skills",    "skills",    "技能库", 0),
    ("tuoke",     "tuoke",     "拓客",   0),
    ("stats",     "stats",     "统计",   0),
    ("trash",     "trash",     "回收站", 0),
    ("__sep__",   "",          "",       0),   # 分隔线
    ("settings",  "settings",  "设置",   0),
]


class MainWindow(QMainWindow):
    # ★ 给命令面板用的页面名表（顺序 = 导航顺序）
    PAGE_LABELS = [
        ("overview", "总览"), ("customers", "客户"), ("messages", "消息"),
        ("strategy", "策略"), ("skills", "技能库"), ("tuoke", "拓客"),
        ("stats", "统计"), ("trash", "回收站"), ("settings", "设置"),
    ]

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(1180, 720)
        # ★ 按屏幕大小开窗、并且居中（第 32 轮）
        #   原来写死 1440×900 —— 但用户是 2560×1440 的屏，
        #   开出来只占中间一小块，显得局促，也浪费地方。
        self._size_to_screen()

        self._theme_name = "dark"
        self._pages = {}          # key -> widget

        root = QWidget()
        self.setCentralWidget(root)

        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---------- ① 顶部全局栏 ----------
        outer.addWidget(self._build_topbar())

        # ---------- ② 主体：左导航 + 页面 ----------
        shell = QWidget()
        sh = QHBoxLayout(shell)
        sh.setContentsMargins(0, 0, 0, 0)
        sh.setSpacing(0)

        self.sidenav = self._build_sidenav()
        sh.addWidget(self.sidenav)

        self.stack = QStackedWidget()
        sh.addWidget(self.stack, 1)

        outer.addWidget(shell, 1)

        # ---------- ③ 底部状态栏 ----------
        outer.addWidget(self._build_footer())

        # ---------- ④ 装页面 ----------
        self._install_pages()

        # ---------- ⑤ 弹层总管 ----------
        # ★ 必须在装完页面之后建，因为遮罩要盖在整个窗口上
        self.overlay = OverlayHost(self)

        # ---------- ⑥ 快捷键（大厂必备：Ctrl+K 命令面板 / Ctrl+1~9 直达） ----------
        self._bind_shortcuts()

        # ---------- ⑦ 上色（主题在 __init__ 开头已定为 dark） ----------
        TH.set_current(self._theme_name)
        self._apply_qss()

        # ---------- ⑧ 设备管家：把手机画面接到界面上 ----------
        #    ★ 这一条是"软件从漂亮变成能用"的分界线 —— 界面开始有真数据了
        self._device_frame = None
        self._device_st = dict(device_hub.NOT_CONNECTED)
        self.hub = device_hub.start_hub()
        self.hub.frame.connect(self._on_device_frame)
        self.hub.status.connect(self._on_device_status)
        self._update_device_ui(self._device_st)

        # 默认停在「客户」页（图纸 view on 给的是 customers）
        self.goto("customers")

        # ---------- ⑧b 壳层的真数据（★ 第 33 轮）----------
        #   顶栏「今日新客 N/目标」+ 底部状态栏，都改成读 data/tuoke.db
        self.refresh_stats()
        self._stats_timer = QTimer(self)
        self._stats_timer.setInterval(15000)          # 15 秒自己刷一次
        self._stats_timer.timeout.connect(self.refresh_stats)
        self._stats_timer.start()

        # ---------- ⑧c 挂机守护（★ 第 38 轮）----------
        #   它在哪一页都得能弹"等你点头"的卡片，所以信号接在主窗口上。
        try:
            from watcher import get_watcher
            _w = get_watcher()
            if not getattr(self, "_watch_connected", False):
                _w.evt.connect(self._on_watch_evt)
                self._watch_connected = True
        except Exception:
            pass

        # ---------- ⑨ 第一次打开：自动弹一下引导 ----------
        #   ★ 第 32 轮加：用户第一次打开，看到 9 个页面 + 一堆陌生词，
        #     很容易直接关掉。大厂做法：首次自动弹一次引导，之后就靠 ? 按钮。
        QTimer.singleShot(900, self._maybe_first_run)

    # ========================================================
    def _size_to_screen(self):
        """按屏幕大小定窗口尺寸（并且居中），别在大屏上开个小窗。"""
        try:
            scr = QApplication.primaryScreen()
            g = scr.availableGeometry()
            w = max(1180, min(1680, int(g.width() * 0.78)))
            h = max(760, min(1020, int(g.height() * 0.88)))
            self.resize(w, h)
            self.move(g.x() + (g.width() - w) // 2,
                      g.y() + max(0, (g.height() - h) // 2 - 20))
        except Exception:
            self.resize(1440, 900)

    # ========================================================
    # 挂机守护的事件（★ 第 38 轮）
    # ========================================================
    def _on_watch_evt(self, kind, d):
        """
        挂机线程的播报：
          · 一般消息 → 右下角提示
          · 试跑打好字 → 弹卡片等用户点头（哪一页都得能弹，所以放这）
        """
        try:
            if kind == "typed" and not d.get("auto"):
                self._ask_send_reply(d)
            elif kind == "replied":
                toast(self, "挂机替你回了：%s" % (d.get("text") or ""), "ok", 4200)
            elif kind == "incoming":
                toast(self, "来新消息了：%s" % (d.get("text") or "")[:20], "info", 3200)
            elif kind == "blocked":
                toast(self, "停手叫人：%s" % (d.get("why") or ""), "warn", 6000)
            elif kind == "error":
                toast(self, "挂机出错：%s" % (d.get("why") or ""), "error", 5200)
        except Exception:
            pass

    def _ask_send_reply(self, d):
        """
        试跑闸门（P35）：AI 把话打进了输入框但没发 —— 这是**收不回的社交行为**，
        必须你点头。卡片上写清楚那句话，点「发出去」才发，「不发了」就清掉。
        """
        try:
            from watcher import get_watcher
            w = get_watcher()
            modal(self, "AI 想好了，等你点头",
                  "它把这句话打进了输入框（**还没发**）：\n\n"
                  "「%s」\n\n"
                  "发不发你说了算。不想让它再问，去设置里开「挂机自动发」。"
                  % (d.get("text") or ""),
                  [("不发了", lambda: w.resolve(False), "ghost"),
                   ("发出去", lambda: w.resolve(True), "primary")], width=380)
        except Exception:
            pass

    def _maybe_first_run(self):
        """
        第一次打开才弹引导（之后靠顶栏的 ? 或 F1）。

        ★ 判断依据：data/ 目录下有没有 first_run_done 这个文件。
          不要用注册表 —— 用户卸载软件时希望一切随文件夹走。
        """
        try:
            from ui.paths import data_dir
            d = data_dir()
            flag = os.path.join(d, "first_run_done")
            if os.path.exists(flag):
                return
            with open(flag, "w", encoding="utf-8") as f:
                f.write("1")
        except Exception:
            return
        try:
            self.overlay.guide()
        except Exception:
            pass

    # ========================================================
    # 设备（手机画面）—— 收设备管家的信号，再分给当前页
    # ========================================================
    def _on_device_frame(self, png):
        self._device_frame = png
        w = self.stack.currentWidget()
        fn = getattr(w, "on_device_frame", None)
        if callable(fn):
            fn(png)

    def _on_device_status(self, st):
        self._device_st = dict(st)
        self._update_device_ui(st)
        w = self.stack.currentWidget()
        fn = getattr(w, "on_device_status", None)
        if callable(fn):
            fn(st)

    def _update_device_ui(self, st):
        """顶栏：连接就亮绿点、收起黄条；没连就把原因写在黄条上。"""
        t = TH.cur()
        ok = bool(st.get("connected"))

        self.dev_dot.setStyleSheet(
            "background:%s; border-radius:4px;" % (t["green"] if ok else t["line2"]))
        if ok:
            self.dev_dot.setToolTip("手机已连上：%s" % st.get("model", ""))

        if ok:
            self.status_box.hide()
            self.btn_more_status.hide()
        else:
            self.status_box.show()
            self.btn_more_status.show()
            self.status_lb.setText(st.get("why") or "手机还没连上")

    def device_state(self):
        """给页面用：任何时候都能问"手机连上没有"。"""
        return dict(self._device_st)

    def device_frame(self):
        return self._device_frame

    # ========================================================
    # 快捷键
    # ========================================================
    def _bind_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+K"), self, self.overlay.palette)
        QShortcut(QKeySequence("Ctrl+P"), self, self.overlay.palette)
        QShortcut(QKeySequence("F1"), self, self.overlay.guide)
        QShortcut(QKeySequence("Esc"), self, self.overlay.close)
        QShortcut(QKeySequence("Ctrl+T"), self, self.toggle_theme)
        # Ctrl+1~9 直达 9 页
        keys = ["Ctrl+1", "Ctrl+2", "Ctrl+3", "Ctrl+4", "Ctrl+5",
                "Ctrl+6", "Ctrl+7", "Ctrl+8", "Ctrl+9"]
        for i, (key, _label) in enumerate(self.PAGE_LABELS):
            QShortcut(QKeySequence(keys[i]), self,
                      lambda k=key: self.goto(k))

    # ========================================================
    # 顶部栏
    # ========================================================
    def _build_topbar(self):
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(52)

        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 14, 0)
        lay.setSpacing(10)

        # 品牌（第 26 轮：⚡ emoji → 图纸原版闪电线条图标）
        logo = QLabel()
        logo.setPixmap(icons.render("logo", 19, TH.cur()["blue"], stroke=2.0))
        logo.setFixedSize(21, 21)

        brand = QLabel("Taku")
        brand.setObjectName("Brand")
        ver = QLabel("· v3.0")
        ver.setObjectName("BrandVer")

        lay.addWidget(logo)
        lay.addWidget(brand)
        lay.addWidget(ver)

        # ★ 设备连接绿点（新手引导里说"顶栏左上角出现绿点，就说明电脑认出手机了"）
        self.dev_dot = QLabel()
        self.dev_dot.setFixedSize(8, 8)
        self.dev_dot.setToolTip("手机连接状态")
        lay.addSpacing(5)
        lay.addWidget(self.dev_dot)

        lay.addSpacing(14)

        # ★ 状态黄条：规格书第 16 章 —— 只显示最高优先级一条
        sbox = QFrame()
        sbox.setObjectName("StatusBar")
        sl = QHBoxLayout(sbox)
        sl.setContentsMargins(10, 4, 8, 4)
        sl.setSpacing(7)

        self.s_ico = QLabel()
        self.s_ico.setPixmap(icons.render("warn", 14, TH.cur()["gold"]))
        self.s_ico.setFixedSize(15, 15)

        self.status_lb = QLabel("正在查手机…")
        self.status_lb.setObjectName("StatusText")

        sl.addWidget(self.s_ico)
        sl.addWidget(self.status_lb)
        lay.addWidget(sbox)
        self.status_box = sbox

        # ★ 图纸 sbarMore：还有 N 条状态，点开看全部
        self.btn_more_status = QPushButton("+1")
        self.btn_more_status.setObjectName("SbarMore")
        self.btn_more_status.setCursor(Qt.PointingHandCursor)
        self.btn_more_status.setToolTip("还有 1 条状态")
        self.btn_more_status.clicked.connect(self._on_more_status)
        lay.addWidget(self.btn_more_status)

        lay.addStretch(1)

        # 今日目标药丸（★ 第 33 轮：数字改成真数据，refresh_stats() 里刷）
        pill = QFrame()
        pill.setObjectName("GoalPill")
        pl = QHBoxLayout(pill)
        pl.setContentsMargins(11, 5, 11, 5)
        pl.setSpacing(7)

        gl = QLabel("今日新客")
        gl.setObjectName("GoalLabel")
        self.goal_num = QLabel("%s / 3" % DS.DASH)
        self.goal_num.setObjectName("GoalNum")

        from PySide6.QtWidgets import QProgressBar
        gb = QProgressBar()
        gb.setObjectName("GoalBar")
        gb.setRange(0, 100)
        gb.setValue(0)
        gb.setTextVisible(False)
        gb.setFixedSize(56, 6)
        self.goal_bar = gb

        pl.addWidget(gl)
        pl.addWidget(self.goal_num)
        pl.addWidget(gb)
        lay.addWidget(pill)

        # 图标组（图纸 5 个：主题 / 命令面板 / 通知 / 引导 / 设置）
        b_theme = IconBtn("moon", "切换深色 / 浅色  (Ctrl+T)")
        b_theme.clicked.connect(self.toggle_theme)

        b_pal = IconBtn("search", "命令面板  (Ctrl+K)")
        b_pal.clicked.connect(lambda: self.overlay.palette())

        b_notify = IconBtn("bell", "通知")
        b_notify.clicked.connect(self._on_notify)

        b_guide = IconBtn("help", "使用引导  (F1)")
        b_guide.clicked.connect(lambda: self.overlay.guide())

        b_set = IconBtn("settings", "设置")
        b_set.clicked.connect(lambda: self.goto("settings"))

        for b in (b_theme, b_pal, b_notify, b_guide, b_set):
            lay.addWidget(b)

        self._b_theme = b_theme
        self._b_pal = b_pal
        self._b_notify = b_notify
        self._b_guide = b_guide
        return bar

    def _on_notify(self):
        """★ 通知：暂时给个弹层说明（以后接真通知列表）。"""
        self.overlay.modal(
            "通知",
            "今天还没有新通知。\n\n"
            "以后这里会显示：有人在等你回话、AI 拿不准要不要发、"
            "平台额度快用完了这类要你拿主意的事。",
            [("知道了", None, "primary")],
        )

    def _on_more_status(self):
        """★ 图纸 sbarMore：把被压在下面的几条状态展开看。"""
        self.overlay.modal(
            "还有这些情况",
            "① 输入法降级中：换成了 ADB 键盘，打字会慢一点\n\n"
            "② 今天还没设置今日目标，先按 3 位算",
            [("知道了", None, "primary")],
        )

    # ========================================================
    # 左侧导航
    # ========================================================
    def _build_sidenav(self):
        nav = QFrame()
        nav.setObjectName("SideNav")
        nav.setFixedWidth(178)

        lay = QVBoxLayout(nav)
        lay.setContentsMargins(10, 12, 10, 12)
        lay.setSpacing(3)

        self._nav_btns = {}
        for key, icon_name, text, badge in NAV:
            if key == "__sep__":
                sp = QWidget()
                sp.setFixedHeight(9)
                lay.addWidget(sp)
                lay.addWidget(hline())
                sp2 = QWidget()
                sp2.setFixedHeight(6)
                lay.addWidget(sp2)
                continue
            b = NavItem(icon_name, text)
            b.set_badge(badge)
            b.clicked.connect(lambda _=False, k=key: self.goto(k))
            lay.addWidget(b)
            self._nav_btns[key] = b

        lay.addStretch(1)

        # 底部小字（图纸里没有，但留一个版本号位置，方便用户对版本）
        v = QLabel("底子已真机打通\n界面重写中")
        v.setObjectName("Faint")
        v.setAlignment(Qt.AlignCenter)
        v.setStyleSheet("font-size:10px; line-height:15px;")
        lay.addWidget(v)

        return nav

    # ========================================================
    # 底部状态栏
    # ========================================================
    def _build_footer(self):
        f = QFrame()
        f.setObjectName("StatusFooter")
        f.setFixedHeight(30)

        lay = QHBoxLayout(f)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(16)

        # ★ 第 33 轮：底部这一排原来写死 "0/20"、"0/50"，改成真数据
        #   （refresh_stats() 里刷；没数据显示「—」，不显示 0 —— 规格书 5.5）
        self.foot_event = QLabel("事件流：正在读数据…")
        self.foot_event.setObjectName("FootEvent")
        lay.addWidget(self.foot_event)
        lay.addStretch(1)

        self.foot_items = {}
        for key, obj in (
            ("greet",   "FootItemWarn"),
            ("follow",  "FootItem"),
            ("new",     "FootItemOk"),
            ("replied", "FootItem"),
            ("goal",    "FootItemWarn"),
        ):
            lb = QLabel("%s %s" % (key, DS.DASH))
            lb.setObjectName(obj)
            self.foot_items[key] = lb
            lay.addWidget(lb)

        return f

    # ========================================================
    # ★ 第 33 轮：壳层（顶栏目标 + 底部状态栏）接真数据
    # ========================================================
    def refresh_stats(self):
        """
        把统计数字刷到顶栏药丸和底部状态栏。

        ★ 只读：数据全来自 `ui.datasource` → `stats.py` → data/tuoke.db
        ★ 任何异常都不许让窗口崩（自动化/挂机时更不许）
        """
        try:
            s = DS.snapshot()
            D = DS.DASH
            has = bool(s.get("has_any_data"))

            def show(v, unit=""):
                return DS.num(v, s, unit)

            # ---- 顶栏「今日新客 N / 目标」----
            goal = s.get("goal_new_customers") or 3
            v = s.get("new_customers_today")
            if has and v is not None:
                self.goal_num.setText("%d / %d" % (v, goal))
                self.goal_bar.setValue(int(min(100, v * 100.0 / goal)) if goal else 0)
            else:
                self.goal_num.setText("%s / %d" % (D, goal))
                self.goal_bar.setValue(0)
            self.goal_num.setToolTip("来源：customers 表，今天新建的档案数（目标读 settings，默认 3）")

            # ---- 底部：事件流 ----
            evs = s.get("events") or []
            if not s.get("ok"):
                self.foot_event.setText("事件流：读不到数据库")
            elif not has:
                self.foot_event.setText("事件流：还没有数据")
            elif not evs:
                self.foot_event.setText("事件流：今天还没有事件")
            else:
                self.foot_event.setText("事件流：%s  %s" % (evs[0]["t"], evs[0]["text"][:26]))

            # ---- 底部：各项指标 ----
            left, quota = s.get("greet_left"), s.get("greet_quota") or 20
            self.foot_items["greet"].setText(
                "陌陌 招呼 %s" % (("%s/%d" % (left, quota)) if (has and left is not None) else D))
            # 「关注」这一项还没有数据源（关注功能没做），**不许编 0/50**
            self.foot_items["follow"].setText("关注 %s" % D)
            self.foot_items["follow"].setToolTip("关注/粉丝数还没接数据源（那是拓客模块的活）")
            self.foot_items["new"].setText("今日新客 %s" % (show(v) if has else D))
            self.foot_items["replied"].setText("已回 %s" % (show(s.get("replied_today")) if has else D))
            self.foot_items["goal"].setText(
                "目标 %s/%d" % ((v if (has and v is not None) else D), goal))
        except Exception:
            import traceback
            traceback.print_exc()

    # ========================================================
    # 页面装配
    # ========================================================
    def _install_pages(self):
        """
        ★ 图纸 9 页，一页不少。
        ★ 每页单独一个模块（ui/pages_*.py），互不干扰 —— 这样改一页不会碰坏别页。
        """
        try:
            from ui.pages_overview import OverviewPage
            from ui.pages_customers import CustomersPage
            from ui.pages_messages import MessagesPage
            from ui.pages_strategy import StrategyPage
            from ui.pages_skills import SkillsPage
            from ui.pages_tuoke import TuokePage
            from ui.pages_stats import StatsPage
            from ui.pages_trash import TrashPage
            from ui.pages_settings import SettingsPage
        except Exception as e:
            # 页面模块还没写全时，不要整窗崩掉 —— 缺哪页就放个占位
            import traceback
            traceback.print_exc()
            self._install_placeholder(str(e))
            return

        pages = [
            ("overview",  OverviewPage()),
            ("customers", CustomersPage()),
            ("messages",  MessagesPage()),
            ("strategy",  StrategyPage()),
            ("skills",    SkillsPage()),
            ("tuoke",     TuokePage()),
            ("stats",     StatsPage()),
            ("trash",     TrashPage()),
            ("settings",  SettingsPage()),
        ]
        for key, w in pages:
            self._pages[key] = w
            self.stack.addWidget(w)

    def _install_placeholder(self, err):
        from ui.widgets import Empty
        w = Empty("🚧", "界面正在重写中", "这一版先搭骨架，页面模块随后逐个补齐。\n%s" % err)
        self._pages["overview"] = w
        self.stack.addWidget(w)

    # ========================================================
    # 切页
    # ========================================================
    def goto(self, key):
        w = self._pages.get(key)
        if w is None:
            return
        self.stack.setCurrentWidget(w)
        for k, b in self._nav_btns.items():
            b.setChecked(k == key)

        # ★ 补发一次设备状态 + 最新一帧
        #   页面可能是刚建的（或切主题后重建的），还没收到过信号。
        #   不补发的话，切过去会是"还没连上手机"的假象。
        fn_st = getattr(w, "on_device_status", None)
        if callable(fn_st):
            try:
                fn_st(self._device_st)
            except Exception:
                pass
        if self._device_frame is not None:
            fn_fr = getattr(w, "on_device_frame", None)
            if callable(fn_fr):
                try:
                    fn_fr(self._device_frame)
                except Exception:
                    pass

        # 页面若有 on_show 钩子（用来刷新数据），调一下
        if hasattr(w, "on_show"):
            try:
                w.on_show()
            except Exception:
                pass

        # ★ 壳层数字也跟着刷（切页往往意味着"刚干完活"）
        if hasattr(self, "foot_items"):
            self.refresh_stats()

    def _goto_settings_panel(self, panel_key):
        """跳到「设置」页的指定面板（命令面板和引导会用到）。"""
        self.goto("settings")
        w = self._pages.get("settings")
        if w is not None and hasattr(w, "goto_panel"):
            try:
                w.goto_panel(panel_key)
            except Exception:
                pass

    # ========================================================
    # 主题
    # ========================================================
    def _apply_qss(self):
        """把当前主题渲染成 QSS 铺上去，并通知所有自绘控件。"""
        name = self._theme_name
        t = TH.get(name)
        self.setStyleSheet(TH.to_qss(t))

        # 自绘控件（MiniBar / AreaChart / HeatGrid / NavItem / IconBtn…）
        for w in self.findChildren(QWidget):
            if hasattr(w, "set_theme"):
                try:
                    w.set_theme(name)
                except Exception:
                    pass
            if hasattr(w, "apply_theme"):
                try:
                    w.apply_theme(name)
                except Exception:
                    pass

        if hasattr(self, "_b_theme"):
            # ★ 显示"当前是哪种"（对齐图纸默认态：深色时显示月亮）
            self._b_theme.set_icon("moon" if name == "dark" else "sun")

    def _rebuild_pages(self):
        """
        切主题后重建页面。

        ★ 为什么要重建：页面里的颜色（背景、边框、文字色）是**创建时**
          写进样式字符串的。不重建的话，一页里深色浅色混着，看着"花"。
          （这是把 109 处硬编码换成 TH.cur() 之后的配套动作。）
        """
        cur_key = None
        cur_w = self.stack.currentWidget()
        for k, w in self._pages.items():
            if w is cur_w:
                cur_key = k

        for w in list(self._pages.values()):
            self.stack.removeWidget(w)
            w.setParent(None)
            w.deleteLater()
        self._pages.clear()

        self._install_pages()
        self.goto(cur_key or "customers")

    def apply_theme(self, name):
        self._theme_name = name
        TH.set_current(name)          # ★ 页面里的 TH.cur() 从此取新色
        self._apply_qss()
        self._rebuild_pages()         # ★ 重建，让写死的颜色跟着换

    def toggle_theme(self):
        self.apply_theme("light" if self._theme_name == "dark" else "dark")

    # ========================================================
    # 关窗：把设备管家的后台线程收拾干净
    # ========================================================
    def closeEvent(self, e):
        try:
            device_hub.stop_hub()
        except Exception:
            pass
        # ★ 关窗时把 scrcpy 投屏进程也收掉（别留一个孤儿窗口在桌面上）
        try:
            from ui.scrcpy_mirror import stop_mirror
            stop_mirror()
        except Exception:
            pass
        super().closeEvent(e)


# ============================================================
# 单独跑（调试用）：python src/ui/main_window.py
# ============================================================
def main():
    app = QApplication(sys.argv)
    # 高 DPI 下别让字体糊
    try:
        app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    except Exception:
        pass
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
