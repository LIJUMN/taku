# -*- coding: utf-8 -*-
"""
页面 ① 总览（图纸 view-overview，第 1044~1142 行）

★ 结构（照抄图纸）：
    1. 诚实说明条        —— 这批数字现在从哪来
    2. 运行条 runbar      —— 运行状态 + 今日已运行/处理事件/最近活动 + 暂停运行
    3. 四格大数字 stat-grid —— 今日新客户 / 已回消息 / 打招呼剩余 / 命中信号
    4. 两栏 two-col       —— 转化漏斗 | 近 7 天消息量（折线图）
    5. 今天 AI 干了什么   —— runlist
    6. 今日事件流         —— evt

★★★ 第 33 轮（本轮）把这一页从「示例数字」改成「真数据」★★★
    改之前：卡片上写死 "2 / 3"、"38 条"、"17/20"、"3 个"，漏斗写死 23/12/5/3/1，
            折线是图纸 SVG 里那 8 个点 → 用户第一反应「这数字哪来的？假的吧」。
    改之后：全部来自 `stats.py` 对 `data/tuoke.db` 的只读聚合；
            库里没有 → 显示「—」，**不显示 0、不显示示例**（规格书 5.5）。

★ 数据来源约束（规格书 5.5）：
    数字说清来源；无数据显示「—」；点「这些数字啥意思？」能看每一条的来源。
"""

from PySide6.QtCore import Qt, QPointF, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QFrame, QSizePolicy, QComboBox, QScrollArea,
)
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath

from ui import theme as TH
from ui import icons
from ui import datasource as DS
from ui.widgets import (
    Card, Btn, MiniBar, hline, toast, modal, LinkLabel,
)

DASH = DS.DASH


def _clear_layout(lay):
    """把布局里的东西全清掉（刷新数据时重建用）。"""
    while lay.count():
        it = lay.takeAt(0)
        w = it.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()
            continue
        sub = it.layout()
        if sub is not None:
            _clear_layout(sub)
            sub.deleteLater()


def _empty_row(text="还没有数据 —— 等 AI 真聊过之后这里就有了"):
    lb = QLabel(text)
    lb.setObjectName("Faint")
    lb.setWordWrap(True)
    lb.setStyleSheet("font-size:11.5px; padding:8px 2px;")
    return lb


# ============================================================
# 折线图（图纸是内嵌 SVG，Qt 里改成自绘 —— 数据改成真的）
# ============================================================
class AreaChart(QWidget):
    """
    ★ 图纸 SVG 的形态（第 1115~1128 行）：viewBox 400x170，网格在 y=34/76/118/160
    ★ 第 33 轮：不再画死数据，改由 set_series() 喂 7 天的真消息量。
    """

    VB_W, VB_H = 400.0, 170.0
    GRID_Y = [34, 76, 118, 160]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._theme = "dark"
        self._series = None          # list[int] × 7 或 None

    def set_theme(self, name):
        self._theme = name
        self.update()

    def set_series(self, series):
        self._series = list(series) if series else None
        self.update()

    def paintEvent(self, e):
        t = TH.get(self._theme)
        w, h = self.width(), self.height()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # 网格线（照抄图纸）
        p.setPen(QPen(QColor(t["line"]), 1))
        for gy in self.GRID_Y:
            y = gy * (h / self.VB_H)
            p.drawLine(0, int(y), w, int(y))

        series = self._series
        if not series or max(series) <= 0:
            p.setPen(QPen(QColor(t["faint"]), 1))
            p.drawText(self.rect(), Qt.AlignCenter, "还没有数据")
            return

        # 7 个点铺满宽度，高度按最大值归一
        pad = 16.0
        n = len(series)
        mx = float(max(series))
        sx = w / float(max(1, n - 1))
        avail = max(1.0, h - 2 * pad)

        pts = [QPointF(i * sx, pad + (1.0 - (v / mx)) * avail)
               for i, v in enumerate(series)]

        path = QPainterPath()
        path.moveTo(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)

        # 面积填充（渐变：上蓝下透明）
        area = QPainterPath(path)
        area.lineTo(pts[-1].x(), h)
        area.lineTo(0, h)
        area.closeSubpath()

        from PySide6.QtGui import QLinearGradient
        g = QLinearGradient(0, 0, 0, h)
        c1 = QColor(t["blue"]); c1.setAlpha(88)
        c2 = QColor(t["blue"]); c2.setAlpha(0)
        g.setColorAt(0.0, c1)
        g.setColorAt(1.0, c2)
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawPath(area)

        # 折线本体
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(t["blue"]), 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(path)

        # 峰值圆点
        idx = series.index(max(series))
        p.setPen(QPen(QColor(t["panel"]), 2))
        p.setBrush(QColor(t["blue"]))
        p.drawEllipse(pts[idx], 3.6, 3.6)


# ============================================================
# 大数字卡（图纸 .stat）—— **可点** + **可刷新**
# ============================================================
class StatCard(QFrame):
    """
    总览页的四格大数字卡片。

    ★ 第 32 轮：原来纯展示，点了没反应 → 现在移上去亮边框、点一下跳页。
    ★ 第 33 轮：加 set_data()，数字由真数据刷新（不再靠构造参数写死）。
    """

    clicked = Signal(str)

    def __init__(self, k, unit="", color="blue", goto="", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self._goto = goto
        self._unit = unit
        if goto:
            self.setCursor(Qt.PointingHandCursor)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(7)

        lk = QLabel(k)
        lk.setObjectName("Sub")
        lk.setStyleSheet("font-size:11.5px;")

        row = QHBoxLayout()
        row.setSpacing(3)
        self._lv = QLabel(DASH)
        self._lv.setStyleSheet("font-size:25px; font-weight:700; line-height:1;")
        self._lu = QLabel(unit)
        self._lu.setObjectName("Faint")
        self._lu.setStyleSheet("font-size:11.5px;")
        row.addWidget(self._lv)
        row.addWidget(self._lu, 0, Qt.AlignBottom)
        row.addStretch(1)

        self._bar = MiniBar(0.0, color)
        self._bar.set_theme(TH.cur().get("name", "dark"))

        self._ld = QLabel(DASH)
        self._ld.setObjectName("Faint")
        self._ld.setStyleSheet("font-size:11px;")

        lay.addWidget(lk)
        lay.addLayout(row)
        lay.addWidget(self._bar)
        lay.addWidget(self._ld)

        self._paint_border(False)

    def set_data(self, value_text, pct, delta_text, source_tip=""):
        """喂真数据：value_text 已经是字符串（可能是「—」）。"""
        self._lv.setText(value_text)
        self._bar.set_pct((pct or 0) / 100.0)
        self._ld.setText(delta_text or DASH)
        if source_tip:
            self.setToolTip("来源：%s" % source_tip)

    def _paint_border(self, on):
        t = TH.cur()
        self.setStyleSheet(
            "QFrame#Card{background:%s; border:1px solid %s; border-radius:%s;}"
            % (t["card"], t["blue"] if on else t["line"], t["r_lg"]))

    def enterEvent(self, e):
        if self._goto:
            self._paint_border(True)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._paint_border(False)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if self._goto and e.button() == Qt.LeftButton:
            self.clicked.emit(self._goto)


# ============================================================
# 漏斗行（图纸 .funnel-row）—— 也可点
# ============================================================
class FunnelRow(QFrame):
    """漏斗的一行 —— 移上去高亮，点一下弹这一级的详情。"""

    clicked = Signal(str, str, str)      # (名字, 数量文本, 比率)

    def __init__(self, label, pct, num, rate, color_key, parent=None):
        super().__init__(parent)
        self.setObjectName("FunnelRow")
        self._info = (label, str(num), str(rate))
        self.setCursor(Qt.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(10)

        lb = QLabel(label)
        lb.setFixedWidth(52)
        lb.setObjectName("Sub")

        bar = MiniBar((pct or 0) / 100.0, color_key)
        bar.set_theme(TH.cur().get("name", "dark"))
        bar.setFixedHeight(8)

        n = QLabel(str(num))
        n.setFixedWidth(40)
        n.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        n.setStyleSheet("font-weight:600;")

        r = QLabel(str(rate))
        r.setFixedWidth(46)
        r.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        r.setObjectName("Faint")

        lay.addWidget(lb)
        lay.addWidget(bar, 1)
        lay.addWidget(n)
        lay.addWidget(r)

        self._paint(False)

    def _paint(self, on):
        t = TH.cur()
        self.setStyleSheet(
            "QFrame#FunnelRow{background:%s; border-radius:%s;}"
            % (t["card"] if on else "transparent", t["r_sm"]))

    def enterEvent(self, e):
        self._paint(True)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._paint(False)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(*self._info)


# ============================================================
# 行（AI 活动 / 事件流 共用）
# ============================================================
def _run_row(tm, badge, badge_color, text):
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 5, 0, 5)
    lay.setSpacing(9)

    l_tm = QLabel(tm or "--:--")
    l_tm.setObjectName("Faint")
    l_tm.setFixedWidth(40)
    l_tm.setStyleSheet("font-size:11px;")

    l_bd = QLabel(badge)
    l_bd.setFixedWidth(56)
    l_bd.setAlignment(Qt.AlignCenter)
    l_bd.setStyleSheet(
        "font-size:10.5px; padding:1px 0; border-radius:6px;"
        "color:%s; background:%s;" % (badge_color, _alpha_bg(badge_color)))

    l_tx = QLabel(text)
    l_tx.setObjectName("Sub")
    l_tx.setWordWrap(True)

    lay.addWidget(l_tm)
    lay.addWidget(l_bd)
    lay.addWidget(l_tx, 1)
    return w


def _alpha_bg(hex_color):
    """把强调色转成 13% 透明底色（跟图纸 --xx-bg 一个意思）。"""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return "rgba(%d,%d,%d,0.13)" % (r, g, b)


KIND_COLOR = {"ok": "green", "warn": "gold", "info": "blue", "fail": "red"}


class OverviewPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(18, 16, 18, 18)
        lay.setSpacing(14)

        # ---------- ⓿ 诚实说明（内容由 refresh() 按真实情况填） ----------
        note = QFrame()
        note.setObjectName("SampleNote")
        nl = QHBoxLayout(note)
        nl.setContentsMargins(12, 8, 14, 8)
        nl.setSpacing(9)

        self._note_ico = QLabel()
        self._note_ico.setPixmap(icons.render("info", 14, TH.cur()["gold"]))
        self._note_ico.setFixedSize(15, 15)

        self._note_lb = QLabel("正在读数据…")
        self._note_lb.setWordWrap(True)
        self._note_lb.setStyleSheet("font-size:11.5px; color:%s;" % TH.cur()["gold"])

        self._note_more = LinkLabel("这些数字啥意思？")
        self._note_more.setStyleSheet("font-size:11.5px;")
        self._note_more.clicked.connect(self._show_sources)

        nl.addWidget(self._note_ico)
        nl.addWidget(self._note_lb, 1)
        nl.addWidget(self._note_more)
        lay.addWidget(note)

        # ---------- ① 运行条 ----------
        lay.addWidget(self._build_runbar())

        # ---------- ② 四格大数字 ----------
        grid = QGridLayout()
        grid.setSpacing(12)
        self._cards = {}
        spec = [
            ("new",     "今日新客户", " 位", "blue",  "customers"),
            ("replied", "已回消息",   " 条", "blue",  "messages"),
            ("greet",   "打招呼剩余", "",    "green", "tuoke"),
            ("signals", "命中信号",   " 个", "gold",  "messages"),
        ]
        for i, (key, title, unit, color, go) in enumerate(spec):
            c = StatCard(title, unit, color, goto=go)
            c.clicked.connect(self._goto)
            self._cards[key] = c
            grid.addWidget(c, 0, i)
        lay.addLayout(grid)

        # ---------- ③ 两栏：漏斗 + 折线 ----------
        two = QHBoxLayout()
        two.setSpacing(12)

        c1 = Card()
        head = QHBoxLayout()
        head.addWidget(QLabel("转化漏斗（按客户进度）"))
        head.addStretch(1)
        cb = QComboBox()
        cb.addItems(["近 7 天", "近 30 天", "本月"])
        cb.setFixedWidth(96)
        cb.currentTextChanged.connect(
            lambda _t: toast(self, "漏斗目前按「客户档案累计进度」算，时间筛选还没接", "info"))
        head.addWidget(cb)
        c1.body().addLayout(head)
        self._funnel_box = QVBoxLayout()
        self._funnel_box.setSpacing(2)
        c1.body().addLayout(self._funnel_box)
        two.addWidget(c1, 1)

        c2 = Card()
        c2.body().addWidget(QLabel("近 7 天消息量"))
        self.chart = AreaChart()
        c2.body().addWidget(self.chart)
        leg = QHBoxLayout()
        dot = QLabel("●")
        dot.setStyleSheet("color:%s;" % TH.cur()["blue"])
        lg = QLabel("消息总量")
        lg.setObjectName("Sub")
        self._peak_lb = QLabel(DASH)
        self._peak_lb.setObjectName("Faint")
        leg.addWidget(dot); leg.addWidget(lg); leg.addStretch(1); leg.addWidget(self._peak_lb)
        c2.body().addLayout(leg)
        two.addWidget(c2, 1)

        lay.addLayout(two)

        # ---------- ④ 今天 AI 干了什么 ----------
        c3 = Card()
        h3 = QHBoxLayout()
        h3.addWidget(QLabel("今天 AI 干了什么"))
        h3.addStretch(1)
        fl = LinkLabel("仅看失败 →")
        fl.setObjectName("Sub")
        fl.setStyleSheet("font-size:11.5px;")
        fl.clicked.connect(self._show_fails)
        h3.addWidget(fl)
        c3.body().addLayout(h3)
        c3.body().addWidget(hline())
        self._runs_box = QVBoxLayout()
        self._runs_box.setSpacing(0)
        c3.body().addLayout(self._runs_box)
        lay.addWidget(c3)

        # ---------- ⑤ 今日事件流 ----------
        c4 = Card()
        h4 = QHBoxLayout()
        h4.addWidget(QLabel("今日事件流"))
        h4.addStretch(1)
        more2 = LinkLabel("查看全部 →")
        more2.setObjectName("Sub")
        more2.setStyleSheet("font-size:11.5px;")
        more2.clicked.connect(self._show_all_events)
        h4.addWidget(more2)
        c4.body().addLayout(h4)
        c4.body().addWidget(hline())
        self._evt_box = QVBoxLayout()
        self._evt_box.setSpacing(0)
        c4.body().addLayout(self._evt_box)
        lay.addWidget(c4)

        lay.addStretch(1)
        scroll.setWidget(inner)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

        # ★ 不在 __init__ 里读库（切主题会重建页面，见 ui/README.md 规矩②）
        #   骨架先摆好，on_show() 时再灌真数据
        self._fill_static_placeholders()

    # ========================================================
    # 运行条
    # ========================================================
    def _build_runbar(self):
        bar = QFrame()
        bar.setObjectName("Card")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 9, 12, 9)
        lay.setSpacing(14)

        self.run_dot = QLabel("●")
        self.run_txt = QLabel("手动模式 · AI 未挂机")
        self.run_txt.setStyleSheet("font-weight:600;")
        lay.addWidget(self.run_dot)
        lay.addWidget(self.run_txt)

        self._run_items = {}
        for key, lb in (("online", "今日已运行"), ("events", "处理事件"),
                        ("last", "最近活动"), ("next", "下次检查")):
            sep = QFrame()
            sep.setFixedWidth(1)
            sep.setFixedHeight(14)
            sep.setStyleSheet("background:%s;" % TH.cur()["line"])
            lay.addWidget(sep)

            item = QLabel("%s <b>%s</b>" % (lb, DASH))
            item.setObjectName("Sub")
            item.setStyleSheet("font-size:11.5px;")
            self._run_items[key] = item
            lay.addWidget(item)

        lay.addStretch(1)

        # ★ 第 38 轮：挂机开关（真开关，不再只是个摆设）
        #   「暂停运行」是总闸（急刹），「开始挂机」是油门 —— 两回事，都要有。
        self.btn_watch = Btn("开始挂机", "primary")
        self.btn_watch.clicked.connect(self._toggle_watch)
        lay.addWidget(self.btn_watch)

        self.btn_pause = Btn("暂停运行", "ghost")
        self.btn_pause.clicked.connect(self._toggle_pause)
        lay.addWidget(self.btn_pause)
        self._paused = False

        # 挂机线程的事件 → 刷新这条运行条
        try:
            from watcher import get_watcher
            w = get_watcher()
            if not getattr(self, "_watch_connected", False):
                w.evt.connect(self._on_watch_evt)
                w.stopped.connect(self._on_watch_stopped)
                self._watch_connected = True
        except Exception:
            pass
        return bar

    # --------------------------------------------------------
    # 挂机（第 38 轮）
    # --------------------------------------------------------
    def _toggle_watch(self):
        """点一下开始盯，再点一下停。手机要停在聊天页它才有得盯。"""
        try:
            from watcher import get_watcher, watcher_running
        except Exception as e:
            toast(self, "挂机组件没起来：%s" % str(e)[:60], "error")
            return

        if watcher_running():
            get_watcher().stop()
            self.btn_watch.setText("停止中…")
            self.btn_watch.setEnabled(False)
            return

        # 开工前的三道检查（有话直说，别让它开起来空转）
        try:
            from ui.store import get_store
            if get_store().get_setting("paused", False):
                toast(self, "你按了暂停 —— 先点「继续运行」再挂机", "warn", 4200)
                return
        except Exception:
            pass
        try:
            from ui import device_hub as _dh
            if not _dh.get_hub().is_connected():
                toast(self, "手机没连上 —— 插上数据线再挂机", "warn", 4600)
                return
        except Exception:
            pass

        get_watcher().start()
        self.btn_watch.setText("停止挂机")
        self.run_dot.setStyleSheet("color:%s; font-size:11px;" % TH.cur()["green"])
        self.run_txt.setText("挂机中 · 刚开始盯")
        toast(self, "挂机开始 —— 把手机停在聊天页，有新消息它替你回"
                    "（默认试跑：打好字等你点头）", "ok", 5200)

    def _on_watch_evt(self, kind, d):
        """挂机线程的播报 → 运行条上的字。"""
        t = TH.cur()
        if kind == "watch":
            self.run_dot.setStyleSheet("color:%s; font-size:11px;" % t["green"])
            self.run_txt.setText("挂机中 · %s" % (d.get("why") or ""))
        elif kind == "skipped":
            self.run_txt.setText("挂机中 · %s" % (d.get("why") or "")[:24])
        elif kind == "incoming":
            self.run_dot.setStyleSheet("color:%s; font-size:11px;" % t["gold"])
            self.run_txt.setText("来消息了 · 正在想怎么回")
        elif kind == "typed":
            self.run_txt.setText("等你点头 · 已打好字在输入框" if not d.get("auto")
                                 else "挂机中 · 自动发模式")
        elif kind == "replied":
            w = None
            try:
                from watcher import get_watcher
                w = get_watcher()
            except Exception:
                pass
            n = w.replies_sent if w else 0
            self.run_dot.setStyleSheet("color:%s; font-size:11px;" % t["green"])
            self.run_txt.setText("挂机中 · 已替你回 %d 条" % n)
        elif kind == "blocked":
            self.run_dot.setStyleSheet("color:%s; font-size:11px;" % t["red"])
            self.run_txt.setText("停手叫人 · %s" % (d.get("why") or "")[:24])
        elif kind == "error":
            self.run_txt.setText("挂机出错 · 看右下角提示")

    def _on_watch_stopped(self):
        self.btn_watch.setText("开始挂机")
        self.btn_watch.setEnabled(True)
        self.run_dot.setStyleSheet("color:%s; font-size:11px;" % TH.cur()["line2"])
        self.run_txt.setText("手动模式 · AI 未挂机")
        toast(self, "挂机已停", "info", 2600)

    def _set_run_item(self, key, label, value):
        self._run_items[key].setText("%s <b>%s</b>" % (label, value))

    # ========================================================
    def _fill_static_placeholders(self):
        self.chart.set_series(None)
        _clear_layout(self._funnel_box)
        self._funnel_box.addWidget(_empty_row("正在读数据…"))

    # ========================================================
    # ★ 刷新：把真数据灌进界面（on_show 时调）
    # ========================================================
    def refresh(self):
        s = DS.snapshot()
        try:
            self._fill_note(s)
            self._fill_runbar(s)
            self._fill_cards(s)
            self._fill_funnel(s)
            self._fill_chart(s)
            self._fill_runs(s)
            self._fill_events(s)
        except Exception:
            import traceback
            traceback.print_exc()

    def on_show(self):
        """★ 每次切到这一页都会走这儿 —— 数据就在这刷。"""
        self.refresh()

    # --------------------------------------------------------
    def _fill_note(self, s):
        """诚实说明条：按「真实情况」说，不按套路说。"""
        t = TH.cur()
        if not s.get("ok"):
            self._note_lb.setText("**读不到数据库**：%s（数字先显示「—」）"
                                  % (s.get("why") or "原因不明"))
            self._note_ico.setPixmap(icons.render("warn", 14, t["red"]))
            self._note_lb.setStyleSheet("font-size:11.5px; color:%s;" % t["red"])
        elif not s.get("has_any_data"):
            self._note_lb.setText(
                "**数据库还是空的**（一行数据都没有）。这里的数字先显示「—」—— "
                "不是 0，是「还没有东西可量」。等 AI 真聊过几轮，这里就是真的了。")
            self._note_ico.setPixmap(icons.render("info", 14, t["gold"]))
            self._note_lb.setStyleSheet("font-size:11.5px; color:%s;" % t["gold"])
        else:
            self._note_lb.setText(
                "这些数字**是真的** —— 来自 data/tuoke.db（只读统计）。最后一次算：%s。"
                % s.get("generated_at", "")[11:])
            self._note_ico.setPixmap(icons.render("check", 14, t["green"]))
            self._note_lb.setStyleSheet("font-size:11.5px; color:%s;" % t["green"])

    # --------------------------------------------------------
    def _fill_runbar(self, s):
        """
        ★ 老实说：**现在还没有「挂机」这回事**。
          新界面里 AI 是你点一下才跑一轮（客户页那个按钮），
          后台常驻的事件闭环（P11）还没接。
          → 所以这里不许写「运行中 · AI 托管 / 今日已运行 6h12m」，那是骗人的。

        ★ 第 38 轮补一条：挂机跑着的时候这条**归挂机说了算**，
          别用定时刷新把它刷回"手动模式"。
        """
        try:
            from watcher import watcher_running
            if watcher_running():
                return
        except Exception:
            pass

        t = TH.cur()
        self.run_dot.setStyleSheet("color:%s; font-size:11px;" % t["line2"])
        self.run_txt.setText("手动模式 · AI 未挂机")
        self.run_txt.setToolTip(
            "现在是「你点一下，AI 跑一轮」。\n"
            "全自动挂机（自己盯着消息、到点就回）还没接 —— 那是下一步。")

        self._set_run_item("online", "今日已运行",
                           ("%d 分钟" % s["online_minutes"]) if s.get("online_minutes")
                           else DASH)
        self._set_run_item("events", "处理事件",
                           DS.num(len(s.get("events") or []), s, " 条"))
        evs = s.get("events") or []
        self._set_run_item("last", "最近活动", (evs[0]["t"] if evs else DASH))
        self._set_run_item("next", "下次检查", "未挂机")

        # ★ 第 34 轮：这个按钮**一直可用**了。
        #   原来它在手动模式下是灰的 —— 用户点了没反应，又是一处"坏了"。
        #   现在它是个真的总闸：按下去，AI 这一轮就别想开工（规格书 1.10.1）。
        from ui.store import get_store
        paused = bool(get_store().get_setting("paused", False))
        self._paused = paused
        self.btn_pause.setEnabled(True)
        if paused:
            self.run_dot.setStyleSheet("color:%s; font-size:11px;" % t["gold"])
            self.run_txt.setText("已暂停 · AI 不许开工")
            self.btn_pause.setText("继续运行")
            self.btn_pause.setToolTip("现在 AI 不会动手机。点一下恢复。")
        else:
            self.btn_pause.setText("暂停运行")
            self.btn_pause.setToolTip(
                "按下去 = 让 AI 立刻停手，别再碰手机。\n"
                "（规格书 1.10.1：这是你的最高优先级动作）")

    # --------------------------------------------------------
    def _fill_cards(self, s):
        has = s.get("has_any_data")

        # ① 今日新客户
        v = s.get("new_customers_today")
        goal = s.get("goal_new_customers") or 3
        self._cards["new"].set_data(
            DS.num(v, s, " 位"),
            DS.ratio(v, goal, has, s),
            (DS.delta(v, s.get("new_customers_yesterday"), "位")
             + ("（目标 %d 位）" % goal)) if has and v is not None else DASH,
            "customers 表：今天新建的客户档案")

        # ② 已回消息
        v = s.get("replied_today")
        self._cards["replied"].set_data(
            DS.num(v, s, " 条"),
            None if not (has and v) else min(100, v * 5),
            DS.delta(v, s.get("replied_yesterday"), "条") or DASH,
            "conversations 表：今天 AI 发出去的消息")

        # ③ 打招呼剩余
        left, quota = s.get("greet_left"), (s.get("greet_quota") or 20)
        self._cards["greet"].set_data(
            DS.num(left, s, "") + ((" / %d" % quota) if (has and left is not None) else ""),
            DS.ratio(left, quota, has, s),
            ("今天已开口 %s 个" % s["greet_used"])
            if (has and s.get("greet_used") is not None) else DASH,
            "配额读 settings（默认 20），减去今天新开的口")

        # ④ 命中信号
        v = s.get("signals_total")
        self._cards["signals"].set_data(
            DS.num(v, s, " 个"),
            None if not (has and v) else min(100, v * 20),
            ("累计命中，待你接管" if (has and v) else DASH),
            "customers 表：hit_signals 非空的客户数（累计）")

    # --------------------------------------------------------
    def _fill_funnel(self, s):
        _clear_layout(self._funnel_box)
        f = s.get("funnel")
        if not f:
            self._funnel_box.addWidget(_empty_row("还没有客户档案，所以漏斗是空的。"))
            return
        for st in f:
            row = FunnelRow(st["name"], st["pct"], st["num"], st["rate"], st["color"])
            row.clicked.connect(self._funnel_detail)
            self._funnel_box.addWidget(row)

    # --------------------------------------------------------
    def _fill_chart(self, s):
        """
        折线：7 天消息量。

        ★ 只有「有数据 且 有非零的一天」才画线 —— 否则画一条贴着 0 的平线，
          看着像"这周真的一条都没聊"，其实可能只是**还没接过数据**。
        """
        peak = s.get("week_peak")
        series = s.get("week_series") if (s.get("has_any_data") and peak) else None
        self.chart.set_series(series)
        self._peak_lb.setText("峰值 %d 条 / %s" % (peak[0], peak[1]) if (series and peak)
                              else DASH)

    # --------------------------------------------------------
    def _fill_runs(self, s):
        """「今天 AI 干了什么」—— 只挑 AI 干的事（从事件流里筛）。"""
        _clear_layout(self._runs_box)
        evs = [e for e in (s.get("events") or [])
               if e["tag"] in ("已回复", "发过", "没做成", "已跳过")]
        if not evs:
            self._runs_box.addWidget(_empty_row(
                "今天 AI 还没干过活。（去「客户」页点「让 AI 聊这一轮」试试）"))
            return
        for e in evs[:8]:
            self._runs_box.addWidget(_run_row(
                e["t"], e["tag"], TH.cur()[KIND_COLOR.get(e["kind"], "blue")], e["text"]))

    # --------------------------------------------------------
    def _fill_events(self, s):
        _clear_layout(self._evt_box)
        evs = s.get("events") or []
        if not evs:
            self._evt_box.addWidget(_empty_row("今天还没有事件。"))
            return
        for e in evs:
            self._evt_box.addWidget(_run_row(
                e["t"], e["tag"], TH.cur()[KIND_COLOR.get(e["kind"], "blue")], e["text"]))

    # ========================================================
    # 交互
    # ========================================================
    def _goto(self, key):
        w = self.window()
        if hasattr(w, "goto"):
            w.goto(key)

    def _show_sources(self):
        modal(self, "这些数字哪来的？（规格书 5.5：数字要说清来源）",
              DS.source_note(DS.snapshot()), [("知道了", None, "primary")])

    def _show_fails(self):
        s = DS.snapshot()
        fails = [e for e in (s.get("events") or []) if e["kind"] in ("warn", "fail")]
        if not fails:
            toast(self, "今天没有失败的动作", "ok")
            return
        modal(self, "今天没做成的 %d 条" % len(fails),
              "\n".join("· %s %s" % (e["t"], e["text"]) for e in fails),
              [("知道了", None, "primary")])

    def _show_all_events(self):
        s = DS.snapshot()
        evs = s.get("events") or []
        if not evs:
            toast(self, "今天还没有事件", "info")
            return
        modal(self, "今天的事件（共 %d 条）" % len(evs),
              "\n".join("· %s [%s] %s" % (e["t"], e["tag"], e["text"]) for e in evs),
              [("知道了", None, "primary")])

    def _funnel_detail(self, name, num, rate):
        s = DS.snapshot()
        who = {
            "破冰": "说上话的人。",
            "深聊": "聊起来的。",
            "加微信": "换了联系方式的。",
            "信任": "开始聊私事的。",
            "可见面": "AI 判断可以提见面的 —— 这种会给你弹「接力卡」，见面由你本人来约。",
        }.get(name, "")
        src = ("来源：customers 表，按 progress 字段（1-5）落级。"
               if s.get("has_any_data") else DS.source_note(s))
        modal(self, "「%s」这一级：%s 个人（%s）" % (name, num, rate),
              who + "\n\n" + src, [("知道了", None, "primary")])

    def _toggle_pause(self):
        """
        ★ 规格书 1.10.1：暂停是用户的最高优先级动作（1 秒内停手）。

        ★ 第 34 轮把它做成**真闸门**：
          按下去 → 往数据里写 paused=True → AI 想开工的那条路会先看这个标记，
          看到就不许动手机。所以这是一个**真的能拦住 AI 的开关**，
          而不是一个"挂机之后才有用"的灰按钮。
        """
        from ui.store import get_store
        st = get_store()
        self._paused = not bool(self._paused)
        st.set_setting("paused", self._paused)
        if self._paused:
            self.run_dot.setStyleSheet("color:%s; font-size:11px;" % TH.cur()["gold"])
            self.run_txt.setText("已暂停 · AI 不许开工")
            self.btn_pause.setText("继续运行")
            toast(self, "已叫停 —— AI 把手收回来了，你可以自己动手机", "warn", 4200)
        else:
            self.run_dot.setStyleSheet("color:%s; font-size:11px;" % TH.cur()["line2"])
            self.run_txt.setText("手动模式 · AI 未挂机")
            self.btn_pause.setText("暂停运行")
            toast(self, "已继续，AI 接着干", "ok")

    # --------------------------------------------------------
    def apply_theme(self, name):
        if hasattr(self, "chart"):
            self.chart.set_theme(name)
        for w in self.findChildren(QWidget):
            if hasattr(w, "set_theme") and w is not getattr(self, "chart", None):
                try:
                    w.set_theme(name)
                except Exception:
                    pass
