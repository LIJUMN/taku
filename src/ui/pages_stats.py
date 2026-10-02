# -*- coding: utf-8 -*-
"""
页面 ⑦ 统计（图纸 view-stats，第 1252~1299 行）

★ 结构：
    1. 两栏：平台产出对比（近7天） | 回复时段热力（近30天）
    2. 转化漏斗（近7天）
    3. 周报复盘（10 月第 1 周）

★ 数据来源约束（规格书 5.5）：每个数字说清来源；估算值带「约」；无数据显示「—」。
"""

from PySide6.QtCore import Qt, QRectF
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea, QGridLayout,
)
from PySide6.QtGui import QPainter, QColor, QPen

from ui import theme as TH
from ui.widgets import Card, MiniBar, hline, Btn, toast, modal
from ui.pages_overview import FunnelRow, _run_row, _alpha_bg


# ============================================================
# 热力图（图纸 .heat —— 24 小时 × 若干天的小方块）
# ============================================================
class HeatGrid(QWidget):
    """
    ★ 说明（规格书 5.5）：这里的数值是**示例形态**，接真数据后由
      数据库按「每 2 小时一档、近 30 天」聚合出来。
    """

    COLS = 12   # 12 档（0/2/4/…/22 时）
    ROWS = 7

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        self._theme = "dark"
        self._data = None          # ★ 第 42 轮：真实的小时分布（12 个数）

    def set_theme(self, n):
        self._theme = n
        self.update()

    def set_data(self, counts):
        """喂真实的"每 2 小时消息量"。None/全 0 = 还没数据（画暗格 + 说明）。"""
        self._data = counts
        self.update()

    def paintEvent(self, e):
        t = TH.get(self._theme)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        gap = 3
        cw = (w - gap * (self.COLS - 1)) / self.COLS
        ch = (h - gap * (self.ROWS - 1)) / self.ROWS

        # ★ 第 42 轮：原来这里是一行"模拟强度"硬编码 —— 全亮全是假的。
        #   现在画**真的**小时分布；没数据就全暗 + 一句说明，不装。
        data = self._data or []
        mx = max(data) if data else 0

        for r in range(self.ROWS):
            for c in range(self.COLS):
                v = 0.0
                if mx > 0:
                    # 每一档的量按行堆叠显示：量越大、亮的行越多（简单直观）
                    v = min(1.0, (data[c] if c < len(data) else 0) / float(mx))
                    v = max(0.0, v - r * (1.0 / self.ROWS)) * self.ROWS / 2.0
                    v = min(1.0, v)
                col = QColor(t["blue"])
                col.setAlphaF(0.10 + 0.80 * v)
                p.setPen(Qt.NoPen)
                p.setBrush(col)
                p.drawRoundedRect(
                    QRectF(c * (cw + gap), r * (ch + gap), cw, ch), 3, 3)

        if mx <= 0:
            p.setPen(QColor(t["faint"]))
            f = p.font(); f.setPointSize(9); p.setFont(f)
            p.drawText(self.rect(), Qt.AlignCenter,
                       "还没有往来数据 —— AI 干起活来，这里会按小时亮起来")

    def sizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(300, 150)


WEEK = []   # ★ 第 42 轮：假周报撤了，见 _rebuild_week()（真数据，不够就照实说）


class StatsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(18, 16, 18, 18)
        lay.setSpacing(14)

        # ---------- ① 两栏 ----------
        two = QHBoxLayout()
        two.setSpacing(12)

        # 平台产出对比
        c1 = Card()
        head1 = QHBoxLayout()
        head1.addWidget(_h3("平台产出对比（近 7 天）"))
        head1.addStretch(1)
        b_exp = Btn("导出", "ghost", icon_name="save")
        b_exp.setToolTip("把这一页的数据导成一份表格（真的写文件）")
        b_exp.clicked.connect(lambda: self._export_stats())
        head1.addWidget(b_exp)
        # ★ 第 34 轮：导出完**在页面上留一行字**（最近导到哪儿了）。
        #   原来只弹一下提示，提示一飘走就什么痕迹都没有 ——
        #   用户会怀疑"到底导没导"。
        self._exp_lb = QLabel("还没导出过")
        self._exp_lb.setObjectName("Faint")
        self._exp_lb.setStyleSheet("font-size:10.5px;")
        head1.addWidget(self._exp_lb)
        c1.body().addLayout(head1)
        # ★ 第 42 轮：原来这三行是写死的"陌陌 14 / Soul 6 / 微信 3"——
        #   真库里只有微信 1 位。假数字比没数字更毒。现在放容器，真数据重画。
        self._plat_box = QVBoxLayout()
        self._plat_box.setSpacing(0)
        c1.body().addLayout(self._plat_box)

        self._plat_tip = QFrame()
        self._plat_tip.setStyleSheet("background:%s; border-radius:%s;"
                          % (_alpha_bg(TH.cur()["green"]), TH.cur()["r_md"]))
        tl = QVBoxLayout(self._plat_tip)
        tl.setContentsMargins(12, 9, 12, 9)
        self._plat_tip_label = QLabel("<b>结论</b>  （等真数据攒出来再下结论）")
        self._plat_tip_label.setObjectName("Sub")
        self._plat_tip_label.setWordWrap(True)
        tl.addWidget(self._plat_tip_label)
        c1.body().addWidget(self._plat_tip)
        two.addWidget(c1, 1)

        # 热力图
        c2 = Card()
        c2.body().addWidget(_h3("回复时段热力（近 30 天 · 真实统计）"))
        self.heat = HeatGrid()
        c2.body().addWidget(self.heat)

        lb = QHBoxLayout()
        for i, t in enumerate(["0时", "2", "4", "6", "8", "10", "12", "14", "16", "18", "20", "22"]):
            x = QLabel(t)
            x.setObjectName("Faint")
            x.setStyleSheet("font-size:10px;")
            x.setAlignment(Qt.AlignCenter)
            lb.addWidget(x, 1)
        c2.body().addLayout(lb)

        lg = QLabel("越亮 = 那个时段的消息越多。")
        lg.setObjectName("Faint")
        lg.setStyleSheet("font-size:11px;")
        c2.body().addWidget(lg)
        two.addWidget(c2, 1)

        lay.addLayout(two)

        # ---------- ② 转化漏斗 ----------
        c3 = Card()
        head3 = QHBoxLayout()
        head3.addWidget(_h3("转化漏斗（近 7 天）"))
        head3.addStretch(1)
        b_ask = Btn("这些数字啥意思？", "ghost", icon_name="help")
        b_ask.clicked.connect(lambda: modal(
            self, "漏斗怎么看",
            "从上往下就是一个人从「刚认识」到「能见面」要走的五步。\n\n"
            "· 破冰 —— 说上话了\n"
            "· 深聊 —— 聊起来了\n"
            "· 加微信 —— 换联系方式了\n"
            "· 信任 —— 开始聊私事\n"
            "· 可见面 —— AI 觉得可以约了\n\n"
            "（这些数字从库里现算 —— 有多少显示多少）",
            [("知道了", None, "primary")]))
        head3.addWidget(b_ask)
        c3.body().addLayout(head3)
        # ★ 第 42 轮：漏斗也改真数据（总览页早就是真的了，这页居然还是编的）
        self._funnel_box = QVBoxLayout()
        self._funnel_box.setSpacing(0)
        c3.body().addLayout(self._funnel_box)
        lay.addWidget(c3)

        # ---------- ③ 周报 ----------
        c4 = Card()
        self._week_title = _h3("周报复盘")
        c4.body().addWidget(self._week_title)
        c4.body().addWidget(hline())
        self._week_box = QVBoxLayout()
        c4.body().addLayout(self._week_box)
        lay.addWidget(c4)

        lay.addStretch(1)
        scroll.setWidget(inner)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

        # 首次灌真数据（on_show 里还会再灌）
        self._fill_real()

    def apply_theme(self, n):
        if hasattr(self, "heat"):
            self.heat.set_theme(n)

    # --------------------------------------------------------
    # ★ 第 42 轮：这一页全部改吃真数据（原来三块全是编的）
    # --------------------------------------------------------
    def _fill_real(self):
        try:
            self._rebuild_platform()
        except Exception:
            pass
        try:
            self._rebuild_funnel()
        except Exception:
            pass
        try:
            self._rebuild_heat()
        except Exception:
            pass
        try:
            self._rebuild_week()
        except Exception:
            pass

    def _rebuild_platform(self):
        """平台产出 = 近 7 天各平台**真实**新客户数（stats.platform_new）。"""
        try:
            from stats import Stats
            st = Stats()
            try:
                brk = st.platform_new(7) or {}
            finally:
                st.close()
        except Exception:
            brk = {}

        order = [("momo", "陌陌", "green"), ("soul", "Soul", "purple"),
                 ("wechat", "微信", "gold")]
        rows = []
        for key, cn, col in order:
            n = int(brk.get(key, 0) or 0)
            rows.append((cn, n, col, key))
        total = sum(r[1] for r in rows)

        # 重画
        while self._plat_box.count():
            it = self._plat_box.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None); w.deleteLater()
        mx = max((r[1] for r in rows), default=0)
        for cn, n, col, key in rows:
            pct = int(n * 100 / mx) if mx else 0
            row = FunnelRow(cn, pct, n, ("%d%%" % round(n * 100 / total)) if total else "—", col)
            row.clicked.connect(
                lambda _=False, x=cn, v=n, r=("%d%%" % round(n * 100 / total)) if total else "—":
                self._platform_detail(x, v, r))
            self._plat_box.addWidget(row)

        # 结论条：有什么说什么，没数据不下结论
        named = [(r[0], r[1]) for r in rows if r[1] > 0]
        if total == 0:
            txt = "近 7 天还没有新客户 —— 开始用起来，这里就是各平台的真实产出。"
        elif len(named) == 1:
            txt = "目前只有 <b>%s</b> 有新客户（%d 位）。别家还没开张，不下结论。" % named[0]
        else:
            best = max(named, key=lambda x: x[1])
            txt = "近 7 天 <b>%s</b> 产出最多（%d 位）。数据再攒攒，结论会更靠谱。" % best
        self._plat_tip_label.setText("<b>结论</b>  " + txt)

    def _rebuild_funnel(self):
        """漏斗 = 库里 progress 的真实分布（和总览页同一份）。"""
        try:
            from ui import datasource as DS
            funnel = (DS.snapshot(force=True) or {}).get("funnel") or []
        except Exception:
            funnel = []

        while self._funnel_box.count():
            it = self._funnel_box.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None); w.deleteLater()
        if not funnel:
            e = QLabel("还没有客户，漏斗暂时是空的。")
            e.setObjectName("Faint")
            e.setStyleSheet("font-size:11.5px; padding:8px 0;")
            self._funnel_box.addWidget(e)
            return
        for f in funnel:
            row = FunnelRow(f["name"], int(f.get("pct") or 0), int(f.get("num") or 0),
                            f.get("rate", "—"), f.get("color", "blue"))
            row.clicked.connect(
                lambda _=False, x=f["name"], v=int(f.get("num") or 0), r=f.get("rate", "—"):
                self._stage_detail(x, v, r))
            self._funnel_box.addWidget(row)

    def _rebuild_heat(self):
        try:
            from stats import Stats
            st = Stats()
            try:
                counts = st.hourly_activity(30)
            finally:
                st.close()
        except Exception:
            counts = None
        self.heat.set_data(counts)

    def _rebuild_week(self):
        """周报只说真话：数据不够就明说不够，绝不编"高于平均 30%"。"""
        try:
            from stats import Stats
            st = Stats()
            try:
                cnt = st.today_counts() or {}
                s = st.summary() or {}
            finally:
                st.close()
        except Exception:
            cnt, s = {}, {}

        his, mine = cnt.get("his", 0), cnt.get("mine", 0)
        rows = []
        rows.append(("往来", "今天共 <b>%d</b> 条消息（对方 %d 条，我方回 %d 条）"
                     % (his + mine, his, mine)))
        nc = s.get("new_customers_today")
        rows.append(("新客", "今天新客户 <b>%s</b> 位；在聊 %s 人"
                     % (nc if nc is not None else "—",
                        s.get("customers_active") or "—")))
        rows.append(("风控", "风控事件记录这块还没接 —— 接上后，有没有被平台限制都摆在这。"))
        if his + mine < 20:
            rows.append(("建议", "数据还太少（今天 %d 条），看不出规律。攒一周，"
                         "这里会给真建议，不编数。" % (his + mine)))

        import time as _tm
        self._week_title.setText("周报复盘（今天 · %s）—— 只说真话" % _tm.strftime("%m-%d"))
        while self._week_box.count():
            it = self._week_box.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None); w.deleteLater()
        t = TH.cur()
        for tag, text in rows:
            r = QWidget()
            rl = QHBoxLayout(r)
            rl.setContentsMargins(0, 6, 0, 6)
            rl.setSpacing(10)
            a = QLabel(tag)
            a.setFixedWidth(48)
            a.setStyleSheet("font-size:11px; color:%s; font-weight:600;" % t["gold"])
            b = QLabel(text)
            b.setObjectName("Sub")
            b.setWordWrap(True)
            b.setStyleSheet("font-size:11.5px;")
            rl.addWidget(a); rl.addWidget(b, 1)
            self._week_box.addWidget(r)

    # --------------------------------------------------------
    # 点图表给反馈（第 32 轮补：原来这些全是死的）
    # --------------------------------------------------------
    def _platform_detail(self, name, num, rate):
        modal(self, "%s：%d 个新客户（占 %s）" % (name, num, rate),
              {
                  "陌陌": "现在的主攻平台 —— 产出最高、风控最低。\n"
                          "打招呼配额也最宽（每天 20 次）。",
                  "Soul": "出人质量还行，但节奏要慢一点。\n"
                          "人偏年轻，聊天口味跟陌陌不太一样。",
                  "微信": "**只承接不拓客** —— 微信上不做主动打招呼，\n"
                          "只在别处聊热了、换了联系方式之后接过来。",
              }.get(name, "") + "\n\n（数字是库里现算的）",
              [("知道了", None, "primary")])

    def _stage_detail(self, name, num, rate):
        who = {
            "破冰": "说上话的人。AI 主动开口、或者回了别人的招呼。",
            "深聊": "聊超过 5 轮的。这一步最能看出 AI 会不会聊天。",
            "加微信": "换了联系方式的。到这一步就踏实了。",
            "信任": "开始聊私事的。AI 会记住这些（但只记能记住的，不编）。",
            "可见面": "AI 判断可以提见面的 —— 这种会给你弹「接力卡」，"
                      "见面由你本人来约。",
        }.get(name, "")
        modal(self, "「%s」：%d 个人（%s）" % (name, num, rate),
              who + "\n\n（数字是库里现算的）",
              [("知道了", None, "primary")])

    # --------------------------------------------------------
    def _export_stats(self):
        """
        真的导出一份 CSV。

        ★ 第 34 轮改：原来只弹一句"已导出（示例数据）"，**根本没写文件**。
          用户骂的"装样子"就是这种。现在真写，而且写完把文件夹打开给他看。
        """
        import csv
        import os
        import sys
        import time

        try:
            from ui.paths import sub_dir
            d = sub_dir("exports")
            fn = os.path.join(d, "统计_%s.csv" % time.strftime("%Y%m%d_%H%M%S"))

            from ui import datasource as ds
            s = {}
            try:
                from stats import Stats
                st_ = Stats()
                try:
                    s = st_.summary() or {}
                finally:
                    st_.close()
            except Exception:
                s = {}

            with open(fn, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["项目", "数值", "说明"])
                w.writerow(["导出时间", time.strftime("%Y-%m-%d %H:%M:%S"), ""])
                for k, label in (("new_customers_today", "今日新客户"),
                                 ("replied_today", "今日已回消息"),
                                 ("greet_left", "打招呼剩余"),
                                 ("signals_total", "命中信号")):
                    v = s.get(k)
                    w.writerow([label,
                                "—" if v is None else v,
                                "库里没有这项数据" if v is None else ""])
                w.writerow([])
                w.writerow(["客户数", len(ds.customers(force=True) or []), ""])

            # 写完把文件夹打开，让用户**看见**文件真在那儿
            try:
                if sys.platform.startswith("win"):
                    os.startfile(d)              # noqa: S606
            except Exception:
                pass

            toast(self, "已导出：%s（顺手把文件夹打开了）" % os.path.basename(fn),
                  "ok", 4200)
            try:
                self._exp_lb.setText("上次导出 %s" % time.strftime("%m-%d %H:%M"))
                self._exp_lb.setStyleSheet("font-size:10.5px; color:%s;"
                                           % TH.cur()["green"])
            except Exception:
                pass
        except Exception as e:
            toast(self, "导出没成功：%s" % str(e)[:50], "error", 4200)

    def on_show(self):
        """每次进这页都重算（第 42 轮：全页改吃真数据）。"""
        self._fill_real()


def _h3(t):
    lb = QLabel(t)
    lb.setStyleSheet("font-size:13px; font-weight:700;")
    return lb
