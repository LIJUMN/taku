# -*- coding: utf-8 -*-
"""
页面 ② 客户 —— 三栏工作区（图纸 view-customers，第 1143~1221 行）

★ 三栏布局（照抄图纸 div.col-list / div.col-chat / div.col-right）：

    左 col-list   客户列表：标题+计数 / 平台筛选胶囊 / 搜索框 / 排序 / 列表
    中 col-chat   聊天区： 头像+昵称+模式徽章+接管 / 策略条 / 消息区 /
                          快捷指令行 / 输入框+发送
    右 col-right  右侧页签 4 个：手机画面 / 客户档案 / AI 聊天计划 / 关联账号
                   ★ 第 20 轮拍板：页签由 2 个扩到 4 个

★ 这一页是全项目信息密度最高的地方，也是用户看着干活的地方。
"""

import time

from PySide6.QtCore import Qt, Signal, QSize, QTimer, QPointF
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QLineEdit,
    QComboBox, QScrollArea, QPushButton, QSizePolicy, QTextEdit,
    QStackedWidget, QGridLayout, QListWidget, QListWidgetItem, QMenu,
)
from PySide6.QtGui import QColor, QPainter, QPixmap, QFont, QPen, QAction

from ui import theme as TH
from ui import icons
from ui import datasource as DS
from ui.widgets import Card, Btn, Chip, sub, faint, toast, modal, ask, Empty


# ============================================================
# 头像（图纸 .avatar —— 圆角方块 + 首字）
# ============================================================
class Avatar(QLabel):
    PALETTE = ["#4c8dff", "#a479f5", "#3ecf8e", "#e8b34b", "#e06ab0", "#3ec9cf"]

    def __init__(self, text, size=38, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._text = (text or "?")[:1]
        # 按名字挑一个稳定的颜色（同一人每次都是同色）
        idx = sum(ord(c) for c in (text or "?")) % len(self.PALETTE)
        self._color = self.PALETTE[idx]
        self._size = size

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self._color))
        p.drawRoundedRect(self.rect(), 9, 9)

        p.setPen(QColor("#ffffff"))
        f = QFont()
        f.setPointSize(self._size // 4)
        f.setBold(True)
        p.setFont(f)
        p.drawText(self.rect(), Qt.AlignCenter, self._text)


# ============================================================
# 客户列表行（图纸客户列表项 —— 头像 + 名 + 平台 + 预览 + 未读）
# ============================================================
class CustRow(QFrame):
    """
    客户列表的一行：头像 + 名字 + 平台 + 最后一句 + 时间。

    ★★ 第 40 轮整行重写（用户骂对了，这行之前是坏的）★★
      ① 之前这行代码被我改坏了：名字/平台/最后一句那段代码断在了
         错误的位置 —— **整行只剩一个头像**，别的全没画出来；
         鼠标扫过还弹出「移出」按钮。
         用户看到的就是"点开头像蹦出个删除"，能不炸吗。
      ② 现在的规矩（写死，别再改回去）：
         · **悬停永远不弹危险按钮** —— 破坏性操作不许靠"鼠标扫过"露出，
           误碰一下就是一场虚惊，这是大厂铁律；
         · 删除挪进**右键菜单**（微信桌面版同款交互），点完仍要二次确认。
    """

    clicked = Signal(dict)
    deleted = Signal(dict)      # 用户从右键菜单选了"移出"

    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.data = data
        self.setObjectName("CustRow")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(62)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(11, 9, 11, 9)
        lay.setSpacing(10)

        av = Avatar(data["name"], 38)
        lay.addWidget(av)

        mid = QVBoxLayout()
        mid.setSpacing(3)

        top = QHBoxLayout()
        top.setSpacing(6)
        nm = QLabel(data["name"])
        nm.setStyleSheet("font-weight:600; font-size:12.5px;")
        top.addWidget(nm)

        src = QLabel(data["src"])
        src.setStyleSheet(
            "font-size:10px; padding:1px 6px; border-radius:5px;"
            "background:%s; color:%s;" % (_bg(TH.cur()["blue"]), TH.cur()["blue"])
        )
        top.addWidget(src)
        top.addStretch(1)

        if data.get("unread"):
            n = QLabel(str(data["unread"]))
            n.setStyleSheet(
                "background:%s; color:#fff; border-radius:8px;"
                "padding:1px 6px; font-size:10px; font-weight:700;" % TH.cur()["red"]
            )
            top.addWidget(n)

        tm = QLabel(data.get("time", ""))
        tm.setObjectName("Faint")
        tm.setStyleSheet("font-size:10.5px;")
        top.addWidget(tm)

        pv = QLabel(data.get("preview", ""))
        pv.setObjectName("Sub")
        pv.setStyleSheet("font-size:11.5px;")
        pv.setMaximumWidth(210)
        txt = data.get("preview", "") or ""
        pv.setText(txt[:22] + ("…" if len(txt) > 22 else ""))

        mid.addLayout(top)
        mid.addWidget(pv)
        lay.addLayout(mid, 1)

    def set_selected(self, on):
        self.setStyleSheet(
            "QFrame#CustRow{background:%s;}" % TH.cur()["blue_bg"] if on else ""
        )
        self.setProperty("sel", on)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, e):
        """左键 = 选中这个人。右键交给 contextMenuEvent。"""
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.data)
        super().mousePressEvent(e)

    def contextMenuEvent(self, e):
        """右键菜单：删除只住在这里，悬停永不弹。"""
        m = QMenu(self)
        a_del = m.addAction("移出到回收站")
        a_del.setToolTip("30 天内随时能捞回来")
        act = m.exec(e.globalPos())
        if act is None:
            return
        if act is a_del:
            self.deleted.emit(self.data)


def _sid(v):
    """
    把客户编号**统一成字符串**来比较。

    ★ 第 33 轮修的一个会崩页面的坑：
      原来代码里到处都是 `int(d["id"])`。而编号不一定是数字 ——
      库里是 1/2/3，但临时数据、以后的 UUID 都可能是文字。
      只要出现一个非数字的编号，`int()` 就抛 ValueError，
      **整个客户页连带切主题全崩**。用户看到的就是"点进去动不了"。
      → 统一转字符串来比，谁都不挑。
    """
    return "" if v is None else str(v)


def _bg(hex_color):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return "rgba(%d,%d,%d,0.13)" % (r, g, b)


# ============================================================
# 聊天气泡（图纸 .msgs 里的气泡）
# ============================================================
class Bubble(QWidget):
    """★ 对方 = 浅色靠左；我 = 彩色靠右（跟真机实测一致）"""

    def __init__(self, who, text, time_text="", parent=None):
        super().__init__(parent)
        # ★ 第 49 轮：竖向 Fixed —— 高度只听内容。
        #   实测布局中间态会把气泡竖向拉伸成"巨型色块"（撑满整个消息区），
        #   Fixed 之后布局永远不许拉它，治本。
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 3, 0, 3)

        mine = (who == "我")
        b = QLabel(text)
        b.setWordWrap(True)
        b.setMaximumWidth(330)
        b.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        b.setStyleSheet(
            "padding:8px 11px; border-radius:11px; font-size:12.5px;"
            + ("background:%s; color:#fff;" % TH.cur()["blue"] if mine
               else "background:%s; color:%s;" % (TH.cur()["card3"], TH.cur()["ink"]))
        )

        if mine:
            lay.addStretch(1)
            lay.addWidget(b)
        else:
            lay.addWidget(b)
            lay.addStretch(1)


# ============================================================
# 右侧四个页签的内容
# ============================================================
class _ScreenCanvas(QWidget):
    """
    画面区：画手机画面 + 画点击痕迹 + 收鼠标点击。

    ★ 为什么不用 QLabel 放图片：QLabel 只显示图，画不了"刚点了这里"的圈，
      也拿不到"点在图上哪个位置"（那要自己算缩放和居中偏移）。
      自己画一遍，这些全有了。
    """

    tapped = Signal(int, int)      # 点了画面上的某点（传显示坐标）
    swiped = Signal(int, int, int, int)   # ★ 在画面上划了一下（起点、终点）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pm = None
        self._real = None           # 手机真实分辨率，如 (1080, 2400)
        self._disp = (0, 0, 0, 0)   # 图在本控件里的实际位置 (x, y, w, h)
        self._marks = []            # 点击痕迹 [(x, y, 时间)]
        self._placeholder = "还没连上手机\n\n插上数据线，画面就出来了"
        self._press = None          # ★ 按下的起点（松手时再决定是"点"还是"拉"）
        self._drag = None           # ★ 拖动中的当前位置（画轨迹用）
        self.setMinimumHeight(300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.PointingHandCursor)

    # ---- 数据 ----
    def set_pixmap(self, pm):
        self._pm = pm
        self.update()

    def set_placeholder(self, text):
        self._pm = None
        self._placeholder = text
        self.update()

    def set_real_size(self, w, h):
        try:
            self._real = (int(w), int(h))
        except Exception:
            self._real = None

    def flash(self, x, y):
        """点完留个圈，让用户看见"点在这儿了"。"""
        self._marks.append((x, y, time.time()))
        self.update()
        QTimer.singleShot(430, self._expire)

    def _expire(self):
        now = time.time()
        self._marks = [m for m in self._marks if now - m[2] < 0.42]
        self.update()

    # ---- 坐标换算 ----
    def to_phone(self, dx, dy):
        """
        显示坐标 → **手机真实像素坐标**。

        ★ 这一步算错就会"点偏"。要点：
          图是按 KeepAspectRatio 缩放并**居中**摆的，所以先减掉两侧留白，
          再按"显示宽 : 手机宽"的比例放大回去。
        """
        if self._pm is None or self._real is None:
            return None
        ox, oy, dw, dh = self._disp
        if dw <= 1 or dh <= 1:
            return None
        rx, ry = self._real
        x = (dx - ox) / float(dw) * rx
        y = (dy - oy) / float(dh) * ry
        if x < 0 or y < 0 or x > rx or y > ry:
            return None
        return int(x), int(y)

    # ---- 画 ----
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = TH.cur()
        r = self.rect()

        p.setPen(QPen(QColor(t["line"]), 1))
        p.setBrush(QColor(t["bg"]))
        p.drawRoundedRect(r.adjusted(0, 0, -1, -1), 8, 8)

        if self._pm is None:
            p.setPen(QColor(t["faint"]))
            p.drawText(r, Qt.AlignCenter | Qt.TextWordWrap, self._placeholder)
            self._disp = (0, 0, 0, 0)
            return

        aw, ah = max(1, r.width() - 2), max(1, r.height() - 2)
        sw, sh = float(self._pm.width()), float(self._pm.height())
        scale = min(aw / sw, ah / sh)
        dw, dh = sw * scale, sh * scale
        ox, oy = 1 + (aw - dw) / 2.0, 1 + (ah - dh) / 2.0
        self._disp = (ox, oy, dw, dh)

        p.drawPixmap(int(round(ox)), int(round(oy)),
                     int(round(dw)), int(round(dh)), self._pm)

        # 刚点过的位置留个圈
        for (mx, my, _ts) in self._marks:
            p.setPen(QPen(QColor(t["blue"]), 2))
            p.setBrush(QColor(t["blue_bg"]))
            p.drawEllipse(QPointF(mx, my), 15, 15)

        # ★ 拖动中的轨迹线（让人看见"正在往哪儿拉"）
        if self._press is not None and self._drag is not None:
            p.setPen(QPen(QColor(t["blue"]), 2, Qt.DashLine))
            p.drawLine(QPointF(*self._press), QPointF(*self._drag))

    # ---- 鼠标：点 / 拉（2026-10-02 用户拍板：只能点不能拉太鸡肋）----
    def mousePressEvent(self, e):
        if self._pm is None:
            return
        pos = e.position().toPoint()
        ox, oy, dw, dh = self._disp
        if not (ox <= pos.x() <= ox + dw and oy <= pos.y() <= oy + dh):
            return          # 点在留白上，不算
        self._press = (pos.x(), pos.y())
        self._drag = None

    def mouseMoveEvent(self, e):
        if self._press is None:
            return
        self._drag = (e.position().x(), e.position().y())
        self.update()

    def mouseReleaseEvent(self, e):
        if self._press is None:
            return
        a = self._press
        b = (e.position().x(), e.position().y())
        self._press = None
        self._drag = None
        dist = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
        if dist < 18:
            # 基本没动 → 当"点"
            self.flash(a[0], a[1])
            self.tapped.emit(a[0], a[1])
        else:
            # 拖出去一段距离 → 当"划"（下拉状态栏、翻页、滚列表都靠它）
            self.flash(b[0], b[1])
            self.swiped.emit(a[0], a[1], b[0], b[1])


class PhoneView(QWidget):
    """
    手机画面（实时投屏 **+ 遥控**）。

    ★ 规格书 1.10.6：**投屏只管给人看，AI 另拍照**。
      这里显示的画面是给用户看的（2 秒一帧、糊点没关系、可以丢帧）；
      AI 看图走的是另一条通道（要高清、不能被投屏抢 adb）。

    ★ 第 28 轮加了遥控：点画面上哪，手机上就真的点哪。
      动作交给设备管家排队执行（见 device_hub.tap 的注释）——
      这样点击和截图永远排在同一队里，不会互相抢数据线。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._locked = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        self.tip = QLabel("点画面 = 点手机；按住拖动 = 滑动（下拉状态栏就往下拖）")
        self.tip.setObjectName("Faint")
        self.tip.setWordWrap(True)
        lay.addWidget(self.tip)

        # 画面区（可点、可划）
        self.canvas = _ScreenCanvas()
        self.canvas.tapped.connect(self._on_tap)
        self.canvas.swiped.connect(self._on_swipe)
        lay.addWidget(self.canvas, 1)

        # 遥控按钮行
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.btn_back = Btn("返回", "ghost", icon_name="arrow_left")
        self.btn_back.clicked.connect(lambda: self._remote("back"))
        self.btn_home = Btn("桌面", "ghost", icon_name="home")
        self.btn_home.clicked.connect(lambda: self._remote("home"))
        self.btn_wake = Btn("点亮", "ghost", icon_name="sun")
        self.btn_wake.clicked.connect(lambda: self._remote("wake"))
        self.btn_hd = Btn("高清投屏", "ghost", icon_name="play")
        self.btn_hd.setToolTip(
            "scrcpy 高清投屏：画面流畅、手机声音从电脑出、操作更跟手。\n"
            "（不是 AI 干活用的 —— AI 自己有自己的截图通道）")
        self.btn_hd.clicked.connect(self._toggle_hd)
        self.btn_lock = Btn("锁住", "ghost", icon_name="lock")
        self.btn_lock.setToolTip("锁住后点画面不会碰到手机（只看不碰，防误触）")
        self.btn_lock.clicked.connect(self._toggle_lock)
        for b in (self.btn_back, self.btn_home, self.btn_wake, self.btn_hd,
                  self.btn_lock):
            b.setStyleSheet(b.styleSheet() + "font-size:11px; padding:4px 9px;")
            bar.addWidget(b)
        bar.addStretch(1)
        lay.addLayout(bar)

        # 状态行
        self.foot = QLabel("—")
        self.foot.setObjectName("Faint")
        self.foot.setWordWrap(True)
        self.foot.setStyleSheet("font-size:10.5px;")
        lay.addWidget(self.foot)

        # ★ 高清投屏的状态播报接进来（镜像单例比界面活得长，
        #   界面重建后新 PhoneView 重新接一次，旧连接随旧控件销毁自动断）
        try:
            from ui import scrcpy_mirror
            scrcpy_mirror.get_mirror().state.connect(self._on_mirror_state)
            if scrcpy_mirror.get_mirror().running():
                self.btn_hd.setText("关闭投屏")
        except Exception:
            pass

        self._n = 0

    # --------------------------------------------------------
    # 设备信号
    # --------------------------------------------------------
    def on_device_status(self, st):
        if st.get("connected"):
            try:
                self.canvas.set_real_size(st.get("width"), st.get("height"))
            except Exception:
                pass
            self.foot.setText("%s · %s×%s · 安卓%s" % (
                st.get("model", "—"), st.get("width", "—"),
                st.get("height", "—"), st.get("android", "—")))
        else:
            why = st.get("why") or "插上数据线，画面就出来了"
            self.canvas.set_placeholder("还没连上手机\n\n" + why)
            self.foot.setText(why)

    def on_device_frame(self, png_bytes):
        pm = QPixmap()
        if not pm.loadFromData(png_bytes or b""):
            return
        self.canvas.set_pixmap(pm)
        self._n += 1
        if self._n % 8 == 1:
            self.foot.setText("实时画面 · 已刷新 %d 次" % self._n)

    # --------------------------------------------------------
    # 遥控
    # --------------------------------------------------------
    def _on_tap(self, dx, dy):
        if self._locked:
            toast(self, "遥控锁着呢 —— 先解锁再点画面", "warn", 2400)
            return
        xy = self.canvas.to_phone(dx, dy)
        if xy is None:
            return
        self.canvas.flash(dx, dy)
        self._hub().tap(xy[0], xy[1])
        self.foot.setText("点了手机上的 %d, %d" % xy)

    def _on_swipe(self, x1, y1, x2, y2):
        """★ 按住拖动 = 在手机上划（2026-10-02 用户拍板补的）"""
        if self._locked:
            toast(self, "遥控锁着呢 —— 先解锁再划", "warn", 2400)
            return
        p1 = self.canvas.to_phone(x1, y1)
        p2 = self.canvas.to_phone(x2, y2)
        if p1 is None or p2 is None:
            return
        self._hub().swipe(p1[0], p1[1], p2[0], p2[1], 300)
        self.foot.setText("在手机上划了一下：（%d, %d）→（%d, %d）" % (p1 + p2))

    # --------------------------------------------------------
    # 高清投屏（scrcpy）—— 点拉滑动 + 手机声音转发到电脑
    # --------------------------------------------------------
    def _toggle_hd(self):
        from ui import scrcpy_mirror
        m = scrcpy_mirror.get_mirror()
        if m.running():
            m.stop()
            self.btn_hd.setText("高清投屏")
            self.tip.setText("点画面 = 点手机；按住拖动 = 滑动（下拉状态栏就往下拖）")
            self.foot.setText("已关掉高清投屏（回到普通投屏）")
            return
        try:
            st = self.window().device_state()
        except Exception:
            st = {}
        serial = (st or {}).get("serial")
        if not st.get("connected") or not serial or serial == "—":
            toast(self, "手机没连上 —— 插上数据线再开高清投屏", "warn", 3600)
            return
        self.btn_hd.setText("关闭投屏")
        self.tip.setText("高清投屏启动中…（首次要几秒钟）")
        m.start(serial, self.canvas)

    def _on_mirror_state(self, s):
        try:
            if s == "starting":
                self.foot.setText("正在启动高清投屏…")
            elif s == "embedded":
                self.tip.setText("高清投屏中：画面上直接点 / 拉 / 滑，手机声音从电脑出")
                self.foot.setText("高清投屏已嵌入界面（scrcpy）—— 操作直接在画面上进行")
            elif s == "standalone":
                self.tip.setText("高清投屏在独立的小窗口里（嵌不进面板，功能一样全）")
                self.foot.setText("高清投屏开好了（独立置顶窗口）—— 点/拉/滑/声音都在那窗口里")
            elif s == "stopped":
                self.btn_hd.setText("高清投屏")
                self.tip.setText("点画面 = 点手机；按住拖动 = 滑动（下拉状态栏就往下拖）")
                self.foot.setText("高清投屏已结束（手机拔了或窗口被关了）")
            elif s.startswith("failed:"):
                self.btn_hd.setText("高清投屏")
                self.tip.setText("点画面 = 点手机；按住拖动 = 滑动（下拉状态栏就往下拖）")
                self.foot.setText(s[7:])
                toast(self, (s[7:] or "高清投屏没开起来")[:60], "error", 5200)
        except Exception:
            pass

    def _remote(self, what):
        """
        ★ 第 34 轮：状态行也跟着变 —— 没连手机时原来只弹一句提示，
          用户点完不知道"到底动没动"。现在不管成没成，都在下面写明白。
        """
        names = {"back": "返回", "home": "回桌面", "wake": "点亮屏幕"}
        label = names.get(what, what)

        if self._locked and what != "wake":
            self.foot.setText("遥控锁着呢 —— 先点「解锁」")
            toast(self, "遥控锁着呢 —— 先解锁", "warn", 2200)
            return
        hub = self._hub()
        try:
            connected = hub.is_connected()
        except Exception:
            connected = False
        if not connected:
            self.foot.setText("按了「%s」，但手机没连上 —— 插上数据线再试" % label)
            toast(self, "手机没连上，没按成", "warn")
            return
        try:
            getattr(hub, what)()
        except Exception as e:
            self.foot.setText("按「%s」出错：%s" % (label, str(e)[:40]))
            toast(self, "没按成：%s" % str(e)[:50], "error")
            return
        self.foot.setText("已经替你按了「%s」" % label)

    def _toggle_lock(self):
        self._locked = not self._locked
        if self._locked:
            self.btn_lock.setText("解锁")
            self.btn_lock.set_icon("unlock")
            self.canvas.setCursor(Qt.ForbiddenCursor)
            self.tip.setText("已锁住 —— 点画面不会碰到手机")
            toast(self, "锁住了，光看不碰不怕误触", "info", 2400)
        else:
            self.btn_lock.setText("锁住")
            self.btn_lock.set_icon("lock")
            self.canvas.setCursor(Qt.PointingHandCursor)
            self.tip.setText("点画面 = 点手机（不能打字）")
            toast(self, "解锁了，现在可以点手机了", "ok", 2400)

    @staticmethod
    def _hub():
        from ui import device_hub
        return device_hub.get_hub()


def _rt_phone():
    """手机画面（★ 规格书 1.10.6：投屏只管给人看，AI 另拍照）"""
    return PhoneView()


def _kv_row(k, v, color=None):
    """档案里的一行「键 …… 值」。值取不到就写「—」（不写 0，也不写"暂无"）。"""
    r = QHBoxLayout()
    a = QLabel(k); a.setObjectName("Sub")
    b = QLabel(v if v not in (None, "") else DS.DASH)
    b.setStyleSheet("font-weight:600;"
                    + ("color:%s;" % color if color else ""))
    r.addWidget(a); r.addStretch(1); r.addWidget(b)
    return r


class ArchiveView(QWidget):
    """
    客户档案（★ 规格书 4.9：阶段 + 备注 + 命中信号）。

    ★ 第 34 轮改造：从"图纸上的死数据"改成**真读这个客户的档案**，而且能改能存。

      · 可改：备注（summary）/ 下一步聊啥（next_topic）
      · 只读：命中信号（hit_signals）—— 那是 AI 从对话里读出来的，不该人工编
      · 保存：右键档案区「保存备注」，或点下面的「保存」按钮
      · 写库走 `tt_db.save_customer_notes`（数据层），页面里**一行 SQL 都没有**
      · **没有改任何字段名**（红线 3）

    ★ 为什么不显示"热度分 / 熟悉度"了：库里没有这两列。
      写死一个 "72 / 100" 比不显示更糟 —— 用户会拿它做判断。
      真要有，得先加字段（那是另一轮的活），所以这里显示「—」。
    """
    saved = Signal(int)          # 存好了（客户 id）→ 外面拿去刷列表和数字

    def __init__(self, parent=None):
        super().__init__(parent)
        self.customer = None
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(9)

        self.head = QLabel("还没选客户")
        self.head.setStyleSheet("font-weight:600;")
        lay.addWidget(self.head)

        self.kv_box = QVBoxLayout()
        self.kv_box.setSpacing(7)
        lay.addLayout(self.kv_box)

        sep = QFrame(); sep.setFixedHeight(1)
        sep.setStyleSheet("background:%s;" % TH.cur()["line"])
        lay.addWidget(sep)

        # ---- 命中信号（只读）----
        t1 = QLabel("AI 记得的事")
        t1.setStyleSheet("font-weight:600;")
        lay.addWidget(t1)
        self.sig = QLabel(DS.DASH)
        self.sig.setObjectName("Sub")
        self.sig.setWordWrap(True)
        lay.addWidget(self.sig)

        # ---- 备注（可改）----
        t2 = QLabel("备注（你自己写的）")
        t2.setStyleSheet("font-weight:600;")
        lay.addWidget(t2)
        self.note_edit = QTextEdit()
        self.note_edit.setPlaceholderText("这个人什么情况？随便写两句，AI 会参考…")
        self.note_edit.setFixedHeight(66)
        lay.addWidget(self.note_edit)

        # ---- 下一步聊啥（可改）----
        t3 = QLabel("下一步聊啥")
        t3.setStyleSheet("font-weight:600;")
        lay.addWidget(t3)
        self.topic_edit = QLineEdit()
        self.topic_edit.setPlaceholderText("比如：问问她周末去哪玩")
        lay.addWidget(self.topic_edit)

        # ---- 阶段（可改，第 35 轮加）----
        # ★ 之前"阶段"只能看不能改 —— 用户问"都聊到这份上了怎么还是破冰"。
        #   库里有 progress 这一列（1-5），第 6 级「已见面」没有字段、
        #   按规格书 4.9.1 只能用户手动标，所以这里只给 1-5。
        t4 = QLabel("阶段（到哪一步了，你自己改）")
        t4.setStyleSheet("font-weight:600;")
        lay.addWidget(t4)
        self.stage_cb = QComboBox()
        self.stage_cb.addItems(["1 · 破冰", "2 · 深聊", "3 · 加微信", "4 · 信任", "5 · 可见面"])
        self.stage_cb.currentIndexChanged.connect(self._on_stage)
        lay.addWidget(self.stage_cb)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.btn_save = Btn("保存备注", "primary")
        self.btn_save.setStyleSheet(self.btn_save.styleSheet() + "font-size:11.5px;")
        self.btn_save.clicked.connect(self._save)
        self.btn_revert = Btn("撤销修改", "ghost")
        self.btn_revert.setStyleSheet(self.btn_revert.styleSheet() + "font-size:11.5px;")
        self.btn_revert.clicked.connect(lambda: self.set_customer(self.customer))
        row.addWidget(self.btn_save)
        row.addWidget(self.btn_revert)
        row.addStretch(1)
        lay.addLayout(row)

        tip = QLabel("在这个框里点右键，也能存。")
        tip.setObjectName("Faint")
        tip.setStyleSheet("font-size:10.5px;")
        lay.addWidget(tip)

        lay.addStretch(1)

    # --------------------------------------------------------
    def set_customer(self, d):
        """把某个客户的档案摊开。d = None → 回到"还没选客户"。"""
        self.customer = d
        while self.kv_box.count():
            it = self.kv_box.takeAt(0)
            lay = it.layout()
            if lay is not None:
                while lay.count():
                    sub_it = lay.takeAt(0)
                    w = sub_it.widget()
                    if w:
                        w.deleteLater()
                lay.deleteLater()

        if not d:
            self.head.setText("还没选客户")
            self.sig.setText(DS.DASH)
            self.note_edit.clear()
            self.topic_edit.clear()
            self.setEnabled_edits(False)
            return

        self.setEnabled_edits(True)
        self.head.setText(d.get("nickname") or "（没名字）")
        for k, v, color in (
            ("平台",   DS.platform_cn(d.get("platform")), None),
            ("阶段",   DS.stage_cn(d.get("progress")), TH.cur()["blue"]),
            ("进度",   ("%s / 5" % d.get("progress")) if d.get("progress") else DS.DASH, None),
            ("距离",   d.get("distance"), None),
            ("状态",   {"active": "在聊", "handover": "人工接管", "closed": "已放弃"}
                        .get(d.get("status"), d.get("status")), None),
            ("建档",   (d.get("created_at") or "")[:16] or DS.DASH, None),
            # ★ 库里没有这两列 → 老实写「—」，不编一个好看的分数骗人
            ("热度分", DS.DASH, TH.cur()["gold"]),
            ("熟悉度", DS.DASH, None),
        ):
            self.kv_box.addLayout(_kv_row(k, v, color))

        self.sig.setText(((d.get("hit_signals") or "") or (d.get("note") or "")).strip() or DS.DASH)
        self.note_edit.setPlainText(d.get("summary") or d.get("note") or "")
        self.topic_edit.setText(d.get("next_topic") or "")

        # 阶段下拉：先挡住信号再设值，别让"显示"误触发"保存"
        try:
            self.stage_cb.blockSignals(True)
            try:
                p = int(d.get("progress") or 0)
            except Exception:
                p = 0
            self.stage_cb.setCurrentIndex(p - 1 if 1 <= p <= 5 else -1)
            self.stage_cb.blockSignals(False)
        except Exception:
            pass

    def setEnabled_edits(self, on):
        for w in (self.note_edit, self.topic_edit, self.btn_save, self.btn_revert,
                  getattr(self, "stage_cb", None)):
            if w is not None:
                w.setEnabled(on)

    # --------------------------------------------------------
    # 改阶段（第 35 轮：原来只能看，改不了）
    # --------------------------------------------------------
    def _on_stage(self, idx):
        d = self.customer
        if not d or idx < 0:
            return
        cid = _sid(d.get("id"))
        p = idx + 1

        ok_db = False
        try:
            from tt_db import TuokeDB
            db = TuokeDB()
            try:
                ok_db = db.save_customer_stage(cid, p)
            finally:
                db.conn.close()
        except Exception:
            ok_db = False

        ok_store = False
        try:
            from ui.store import get_store
            st = get_store()
            ok_store = st.update_customer(cid, progress=p)   # 界面自己加的行
            st.set_override(cid, progress=p)                 # 库里的人（合并时盖上去）
            ok_store = True
        except Exception:
            ok_store = False

        if not (ok_db or ok_store):
            toast(self, "阶段没改成功", "error", 3800)
            return

        d["progress"] = p
        DS.invalidate()
        toast(self, "阶段改成「%s」了" % DS.stage_cn(p), "ok", 2800)

    # --------------------------------------------------------
    # 存（唯一写库入口）
    # --------------------------------------------------------
    def _dirty(self):
        d = self.customer
        if not d:
            return False
        return (self.note_edit.toPlainText().strip() != (d.get("summary") or "").strip()
                or self.topic_edit.text().strip() != (d.get("next_topic") or "").strip())

    def _save(self):
        d = self.customer
        if not d:
            toast(self, "先挑一个客户，再存备注", "warn", 2400)
            return False
        if not self._dirty():
            toast(self, "没改动，不用存", "info", 2000)
            return True

        cid = _sid(d.get("id"))
        summary = self.note_edit.toPlainText().strip()
        topic = self.topic_edit.text().strip()

        # ★ 第 34 轮：先写**数据仓库**（store）。
        #   ★ 第 35 轮改成"双写"：update_customer（界面自己加的行，如示例客户）
        #     + set_override（库里的人 —— 合并时**按字段**盖上去）。
        #     只 update_customer 的话，库里的人会被"库为正文"盖回去，备注白写。
        saved_to_store = False
        try:
            from ui.store import get_store
            st = get_store()
            st.update_customer(cid, summary=summary, next_topic=topic)
            st.set_override(cid, summary=summary, next_topic=topic)
            saved_to_store = True
        except Exception:
            saved_to_store = False

        # 库里真有这个人（整数 id）→ 顺手也写进库，保持两边一致
        wrote_db = False
        try:
            from tt_db import TuokeDB
            db = TuokeDB()
            try:
                db.save_customer_notes(cid, summary=summary, next_topic=topic)
                wrote_db = True
            finally:
                db.conn.close()          # ★ 显式关：Windows 上句柄不放会锁住库文件
        except Exception:
            wrote_db = False

        if not saved_to_store and not wrote_db:
            toast(self, "没存上（数据和数据库都没写进去）", "error", 4200)
            return False

        d["summary"] = summary
        d["next_topic"] = topic
        DS.invalidate()                  # 让列表预览/统计下次重算
        self.saved.emit(cid)
        toast(self, "存好了 —— 备注已经写进去", "ok", 2600)
        return True

    # ---- 右键菜单（需求点名要的：右键档案区保存备注）----
    def contextMenuEvent(self, ev):
        m = QMenu(self)
        a1 = QAction("保存备注", self)
        a1.triggered.connect(self._save)
        a2 = QAction("撤销修改", self)
        a2.triggered.connect(lambda: self.set_customer(self.customer))
        a3 = QAction("刷新档案", self)
        a3.triggered.connect(self._reload)
        m.addAction(a1)
        m.addAction(a2)
        m.addSeparator()
        m.addAction(a3)
        for a in (a1, a2, a3):
            if not self.customer:
                a.setEnabled(False)
        a3.setEnabled(True)
        m.exec(ev.globalPos())

    def _reload(self):
        """重新读一遍这个客户（别人改了 / 别处改了，这里跟上）。"""
        d = self.customer
        if not d:
            return
        DS.invalidate()
        for row in (DS.customers(force=True) or []):
            if _sid(row.get("id")) == _sid(d.get("id")):
                self.set_customer(row)
                return
        toast(self, "这个客户已经不在了（可能被删了）", "warn", 3200)


class PlanView(QWidget):
    """
    AI 聊天计划。

    ★ 第 34 轮：图纸上写的三行"未来 3~5 轮打算这么聊"是**编的**。
      现在库里能装这个的只有 `customers.next_topic`（下一步聊啥）这一列，
      所以：有就显示真的，没有就**照规格书 5.1 的空态文案**说人话。
      编一份漂亮的计划书，只会让用户以为 AI 已经想好了。
    """
    EMPTY = "AI 还没给这个客户做计划。聊起来之后就有了。"

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(9)

        self.t = QLabel("下一步聊啥")
        self.t.setStyleSheet("font-weight:600;")
        lay.addWidget(self.t)

        self.box = QVBoxLayout()
        self.box.setSpacing(7)
        lay.addLayout(self.box)

        self.empty = QLabel(self.EMPTY)
        self.empty.setObjectName("Faint")
        self.empty.setWordWrap(True)
        lay.addWidget(self.empty)

        lay.addStretch(1)
        self.set_customer(None)

    def set_customer(self, d):
        while self.box.count():
            it = self.box.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        topic = ((d or {}).get("next_topic") or "").strip()
        self.empty.setVisible(not topic)
        if not topic:
            return
        c = QFrame()
        c.setObjectName("Card")
        cl = QVBoxLayout(c)
        cl.setContentsMargins(11, 9, 11, 9)
        cl.setSpacing(3)
        a = QLabel("备忘的话题")
        a.setStyleSheet("font-size:10.5px; color:%s; font-weight:600;" % TH.cur()["blue"])
        b = QLabel(topic)
        b.setObjectName("Sub")
        b.setWordWrap(True)
        cl.addWidget(a); cl.addWidget(b)
        self.box.addWidget(c)


class AcctView(QWidget):
    """
    关联账号（★ 规格书 4.11：跨平台同人识别）。

    ★ 第 34 轮：原来这里摆着"测试用户A / 测试用户B"两条**假数据**。
      现在改成**真查**：库里有没有同名的客户出现在不同平台。
      这只是**线索**，不是结论 —— 真要合并得走三级证据（4.11），
      所以这里只把线索摆出来，不替用户下判断。
    """
    EMPTY = "还没发现同一个人出现在多个平台。"

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        self.t = QLabel("同一个人，在几个 App 里出现过")
        self.t.setStyleSheet("font-weight:600;")
        self.t.setWordWrap(True)
        lay.addWidget(self.t)

        tip = QLabel("发现是同一个人，进度和聊天记录会打通 —— "
                     "免得在微信里又当新人聊一次，穿帮。")
        tip.setObjectName("Faint")
        tip.setWordWrap(True)
        lay.addWidget(tip)

        self.box = QVBoxLayout()
        self.box.setSpacing(7)
        lay.addLayout(self.box)

        self.empty = QLabel(self.EMPTY)
        self.empty.setObjectName("Faint")
        self.empty.setWordWrap(True)
        lay.addWidget(self.empty)

        lay.addStretch(1)
        self.set_customer(None)

    def set_customer(self, d):
        while self.box.count():
            it = self.box.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        rows = DS.same_nickname((d or {}).get("nickname")) if d else []
        self.empty.setVisible(len(rows) < 2)
        if len(rows) < 2:
            return
        for r in rows:
            c = QFrame()
            c.setObjectName("Card")
            cl = QHBoxLayout(c)
            cl.setContentsMargins(11, 9, 11, 9)
            cl.setSpacing(9)
            av = Avatar(r.get("nickname") or "?", 30)
            cl.addWidget(av)
            box = QVBoxLayout()
            box.setSpacing(2)
            a = QLabel(r.get("nickname") or "（没名字）"); a.setStyleSheet("font-weight:600;")
            b = QLabel(DS.platform_cn(r.get("platform")))
            b.setObjectName("Faint"); b.setStyleSheet("font-size:10.5px;")
            box.addWidget(a); box.addWidget(b)
            cl.addLayout(box, 1)
            self.box.addWidget(c)


# ============================================================
# 客户页主体
# ============================================================
# ★ 第 34 轮：这里原来写着一份**图纸上的假客户名单**（小鹿 / 若若 / 安然…）。
#   它的坏处不只是"假"——是**它没有真 id**，所以选中一个人之后传下去的是 None，
#   AI 跑完那一轮**根本不知道算在谁头上**，于是不落库，总览页的数字永远不动。
#   现在整份名单改成从 data/tuoke.db 的 customers 表读（走 ui/datasource.py）。
#   `_tools/check_stats.py` 里有"假数据防线"，那批名字再出现就会红灯。

def _plat_key(d):
    """
    这一行客户是哪个平台的（返回小写英文键，去 DS.PLATFORM_DB 里比对）。

    ★ 第 35 轮加：要兼容两种行 ——
      库里的行有 `platform`（momo/soul/wechat），
      界面自己加的行（示例客户）只有 `src`（陌陌/Soul/微信）。
    """
    p = (d.get("platform") or "").strip().lower()
    if p:
        return p
    return {"陌陌": "momo", "Soul": "soul", "微信": "wechat"}.get(d.get("src") or "", "")


class CustomersPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []
        self._cur = None
        # ★ 这一轮真正的"钥匙"：选中客户的**真 id**。
        #   AgentRunner 拿它去落库（没有它，AI 干完活等于白干）。
        self.customer_id = None
        self._customers = None       # None = 还没读；[] = 真没有客户
        self._filter_name = "全部"

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_left())
        root.addWidget(self._build_chat(), 1)
        root.addWidget(self._build_right())

        # 建好就把真库读一遍（读不到 → 空态，不是崩）
        self.reload()

        # ★★ 订阅"数据变了"（第 33 轮补）
        #   不订这个信号会出大问题：
        #     回收站点了「捞回来」→ 数据回到客户表了 → 但客户页还在显示旧样子，
        #     用户得手动切页才看得到。他会觉得"这功能没生效"。
        #   订上之后：**任何地方改了数据，这边自己会重画**。
        try:
            from ui.store import get_store
            get_store().changed.connect(self._on_store_changed)
        except Exception:
            pass

    def _on_store_changed(self, kind):
        """别处改了数据 —— 把缓存丢掉，重画列表。"""
        if kind not in ("customers", "all"):
            return
        try:
            from ui import datasource as _ds
            _ds.invalidate()
        except Exception:
            pass
        try:
            self.reload()
        except Exception:
            pass

    # --------------------------------------------------------
    # 读真库（页面唯一入口：ui/datasource.py，页面里不连库）
    # --------------------------------------------------------
    def reload(self, keep_selection=True):
        """
        把客户列表从库里重新读一遍。

        ★ keep_selection：AI 干完一轮回来刷新时，用户选中的那个人不该跳走。
        """
        old_id = self.customer_id
        self._customers = DS.customers()
        self._rebuild_list()

        if not self._customers:
            self._select(None)
            return

        # 尽量把选中的人留住（还在的话）
        if keep_selection and old_id is not None:
            for d in self._customers:
                if _sid(d.get("id")) == _sid(old_id):
                    self._select(d, keep_scroll=True)
                    return
        self._select(self._visible()[0] if self._visible() else None)

    def _visible(self):
        """当前筛选 + 搜索条件下的客户（列表里真正显示的这些）。"""
        kw = (self._search_box.text() or "").strip().lower() if hasattr(self, "_search_box") else ""
        out = []
        for d in (self._customers or []):
            if not self._match_platform(d):
                continue
            if kw:
                hay = "%s %s %s" % (d.get("nickname") or "", d.get("account_id") or "",
                                    d.get("id"))
                if kw not in hay.lower():
                    continue
            out.append(d)
        return self._sort(out)

    def _match_platform(self, d):
        name = getattr(self, "_filter_name", "全部")
        if name == "全部":
            return True
        return _plat_key(d) in DS.PLATFORM_DB.get(name, ())

    def _sort(self, rows):
        """排序。★ 库里可用的列只有这些，所以选项要能真做到，做不到就说清。"""
        mode = self.sort_cb.currentText() if hasattr(self, "sort_cb") else "最近活跃"
        if mode == "进度最高":
            return sorted(rows, key=lambda d: (-(d.get("progress") or 0), d.get("id") or 0))
        if mode == "命中信号":
            return sorted(rows, key=lambda d: (0 if (d.get("hit_signals") or "").strip()
                                               else 1, -(d.get("id") or 0)))
        # 最近活跃 / 未读优先（未读目前没有真数据，见 _on_sort_changed）
        return sorted(rows, key=lambda d: (d.get("last_at") or d.get("created_at") or "",
                                           _sid(d.get("id"))), reverse=True)

    # --------------------------------------------------------
    # 左栏：客户列表
    # --------------------------------------------------------
    def _build_left(self):
        col = QFrame()
        col.setFixedWidth(258)
        col.setStyleSheet("background:%s; border-right:1px solid %s;"
                          % (TH.cur()["panel"], TH.cur()["line"]))

        lay = QVBoxLayout(col)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # 头部
        head = QWidget()
        hl = QVBoxLayout(head)
        hl.setContentsMargins(12, 12, 12, 10)
        hl.setSpacing(9)

        r1 = QHBoxLayout()
        t = QLabel("客户")
        t.setStyleSheet("font-size:14px; font-weight:700;")
        self.cnt = QLabel(DS.DASH)                 # ★ 个数：真数，算不出就「—」
        self.cnt.setObjectName("Faint")
        self.cnt.setStyleSheet("font-size:11px;")
        r1.addWidget(t); r1.addSpacing(6); r1.addWidget(self.cnt); r1.addStretch(1)
        hl.addLayout(r1)

        # 平台筛选
        chips = QHBoxLayout()
        chips.setSpacing(6)
        self._chips = []
        for i, name in enumerate(["全部", "陌陌", "Soul", "微信"]):
            c = Chip(name)
            c.setChecked(i == 0)
            c.clicked.connect(lambda _=False, n=name: self._filter(n))
            chips.addWidget(c)
            self._chips.append(c)
        chips.addStretch(1)
        hl.addLayout(chips)

        # 搜索
        se = QLineEdit()
        se.setPlaceholderText("搜索客户名 / ID")
        se.textChanged.connect(self._search)
        hl.addWidget(se)
        self._search_box = se

        # 排序
        sr = QHBoxLayout()
        sl = QLabel("排序"); sl.setObjectName("Sub"); sl.setStyleSheet("font-size:11.5px;")
        self.sort_cb = QComboBox()
        self.sort_cb.addItems(["最近活跃", "进度最高", "命中信号", "未读优先"])
        self.sort_cb.setFixedWidth(112)
        self.sort_cb.currentTextChanged.connect(self._on_sort_changed)
        sr.addWidget(sl); sr.addWidget(self.sort_cb)
        sr.addStretch(1)
        # ★ 原来是写死的「未读 2」—— 那是**编的**。
        #   库里没有"未读"这一列（得等通知同步那一块做出来才有）→ 老实写「—」。
        self.unread = QLabel("未读 %s" % DS.DASH)
        self.unread.setObjectName("Sub"); self.unread.setStyleSheet("font-size:11.5px;")
        self.unread.setToolTip("还没有「未读」这个数据 —— 它要靠手机通知同步，那一块还没做。"
                               "这里的数字不会瞎编。")
        sr.addWidget(self.unread)

        # ★ 第 35 轮：手动加一个人（真写库）。
        #   为什么必须有它：拓客还没接（AI 还不会自己找人），
        #   而 AI 跑一轮要挂在"某个人"头上才落得了库。
        #   没这个入口，库里永远 0 个人 → AI 干完活没地方记 → 数字永远不动。
        add = Btn("+ 加一个人", "ghost", icon_name="plus")
        add.setToolTip("把你正在聊的人记进来（真写进数据库），"
                       "AI 之后每一轮都会挂在这个人头上")
        add.clicked.connect(self._add_customer)
        sr.addWidget(add)
        hl.addLayout(sr)

        lay.addWidget(head)

        sep = QFrame(); sep.setFixedHeight(1)
        sep.setStyleSheet("background:%s;" % TH.cur()["line"])
        lay.addWidget(sep)

        # 列表
        self.list_box = QVBoxLayout()
        self.list_box.setContentsMargins(0, 4, 0, 4)
        self.list_box.setSpacing(0)

        holder = QWidget()
        holder.setLayout(self.list_box)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setWidget(holder)
        sc.setStyleSheet("background:transparent;")
        lay.addWidget(sc, 1)

        return col

    def _rebuild_list(self):
        """
        重建左边那一列。

        ★ 第 34 轮修：删旧控件时**同时 `setParent(None)`**。
          只 `deleteLater()` 的话，旧控件要等事件循环跑到才真正消失，
          这中间它**还挂在父控件上** —— 自检工具 `findChildren()` 会把它们
          一起数进来（空态那个"放示例进来"按钮被数出 3 个），
          看着像"界面里重复了一堆按钮"。
        """
        while self.list_box.count():
            it = self.list_box.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)      # 立刻从父控件摘掉（别等事件循环）
                w.deleteLater()
        self._rows = []

        n_all = len(self._customers or [])
        rows = self._visible()
        # 计数：算得出就给真数（含"库读不到"和"真没有"两种空态的区别）
        if self._customers is None:
            self.cnt.setText(DS.DASH)
            self.cnt.setToolTip("读不到数据库")
        elif n_all == 0:
            self.cnt.setText(DS.DASH)
            self.cnt.setToolTip("库里还没有客户")
        else:
            self.cnt.setText("%d 位" % n_all)
            self.cnt.setToolTip("来自 customers 表（在聊的客户数，不含已放弃）")

        if not rows:
            if self._customers is None:
                self.list_box.addWidget(Empty("🔌", "读不到客户数据",
                                              "打不开 data/tuoke.db。\n数据文件在的话，重启一下程序试试。"))
            elif n_all == 0:
                # ★ 规格书 5.1 空态文案表（客户列表那句）
                # ★ 第 34 轮：不再偷偷塞假客户 —— 空着，但给一个**明确的入口**。
                self.list_box.addWidget(Empty(
                    "👤", "还没有客户",
                    "点左边的『拓客』开始找人聊天。\n"
                    "想先试试功能，也可以放 3 个示例客户进来（随时能删）。",
                    action=("放 3 个示例客户进来试试", self._load_samples)))
            else:
                self.list_box.addWidget(Empty("🔍", "这条件下没找到人",
                                              "换个平台，或把搜索词删掉试试。"))
            self.list_box.addStretch(1)
            return

        for d in rows:
            row = CustRow(self._row_data(d))
            row.clicked.connect(lambda _=False, dd=d: self._select(dd))
            row.deleted.connect(self._delete_one)      # ★ 移出按钮
            self.list_box.addWidget(row)
            self._rows.append(row)
        self.list_box.addStretch(1)

    # ========================================================
    # ★ 删除客户（第 33 轮：这次是真的删得掉）
    # ========================================================
    def _delete_one(self, d):
        """点了「移出」——先问一句，再真的移出去。"""
        cid = d.get("id")
        name = d.get("name", "这个人")
        if not cid:
            toast(self, "这条记录没有编号，删不了（数据可能不完整）", "warn")
            return

        ask(self, "把「%s」移出去？" % name,
            "她会进**回收站**，30 天内随时能捞回来 —— 不是真的抹掉。\n\n"
            "如果只是暂时不想理她，放着也行，AI 会自己判断该不该继续聊。",
            lambda: self._do_delete(cid, name, d),
            yes_text="移出去")

    def _do_delete(self, cid, name, row=None):
        """
        真的执行删除。

        ★ 关键：不是把界面那一行拿掉（那是假的，切页就回来）。
        ★ 第 35 轮：把**这一行的资料**一起递过去 ——
          库里的人 store 这边没有他的资料，回收站里"是谁"全靠它写。
        """
        try:
            from ui.store import get_store
            get_store().delete_customer(cid, to_trash=True,
                                        why="你自己在客户列表里移出的",
                                        row=row)
        except Exception as e:
            toast(self, "没删掉：%s" % str(e)[:50], "error", 4000)
            return

        # 让 datasource 的缓存失效，然后重画列表
        try:
            from ui import datasource as _ds
            _ds.invalidate()
        except Exception:
            pass

        self._rebuild_list()
        toast(self, "已把「%s」移进回收站 —— 想找她随时能捞回来" % name, "ok", 3400)

    @staticmethod
    def _row_data(d):
        """
        把库里的行，变成列表行看得懂的样子（**只翻译，不编**）。

        ★ 第 35 轮：兼容两种行 ——
          · 数据库的行：nickname / platform / summary / last_msg_time
          · 界面自己加的行（示例客户）：name / src / note / tm
          原来只认库里的字段名，示例客户进来会全显示成「（没名字）」。
        """
        name = (d.get("nickname") or d.get("name") or "").strip() or "（没名字）"
        raw_plat = (d.get("platform") or "").strip()
        if raw_plat:
            src = DS.platform_cn(raw_plat)
        else:
            src = d.get("src") or "—"
        return {
            "id": d.get("id"),
            "name": name,
            "src": src,
            "preview": ((d.get("last_content") or "").strip()
                        or (d.get("summary") or "").strip()
                        or (d.get("note") or "").strip()),
            "time": DS.when(d.get("last_at") or d.get("last_msg_time")
                            or d.get("tm") or ""),
            "unread": 0,          # 没有未读数据 → 0 → 角标不显示（不编一个数字上去）
        }

    def _filter(self, name):
        self._filter_name = name
        for c in self._chips:
            c.setChecked(c.text() == name)
        self._rebuild_list()

    def _search(self, kw):
        self._filter_name = next((c.text() for c in self._chips if c.isChecked()), "全部")
        self._rebuild_list()

    # --------------------------------------------------------
    def _load_samples(self):
        """
        空态里那个「放 3 个示例客户进来试试」。

        ★ 为什么要有它：软件刚装上时一个客户都没有（真客户得等 AI 聊过才有），
          用户想试"删除/回收站/备注"这些功能就没东西可点。
          → 给个**明确写着"示例"**的入口，点进来的都是可删的真数据。
        """
        try:
            from ui.store import get_store
            n = get_store().add_samples()
        except Exception as e:
            toast(self, "放不进来：%s" % str(e)[:50], "error")
            return
        try:
            from ui import datasource as _ds
            _ds.invalidate()
        except Exception:
            pass
        if hasattr(self, "reload"):
            self.reload()
        else:
            self._rebuild_list()
        toast(self, "放进来了 %d 个示例客户 —— 随时可以删掉" % n, "ok", 3600)

    # --------------------------------------------------------
    def _add_customer(self):
        """
        手动加一个人（**真写进数据库**）。

        ★ 为什么要它（第 35 轮）：AI 跑一轮要挂在"某个人"头上才落得了库。
          拓客还没接（AI 还不会自己找人），所以这是唯一的人头来源。
          没有它 → 库里永远 0 个人 → AI 干完活没地方记 → 数字永远不动。
        """
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        v.addWidget(QLabel("昵称（手机上怎么显示就怎么写）"))
        name = QLineEdit()
        name.setPlaceholderText("比如：爱健身的小周")
        v.addWidget(name)

        v.addWidget(QLabel("在哪个 App 上"))
        plat = QComboBox()
        plat.addItems(["Soul", "陌陌", "微信"])
        v.addWidget(plat)

        tip = QLabel("★ 真写进数据库。之后 AI 每一轮聊了什么，都记在这个人头上，"
                     "总览页的数字才会动。")
        tip.setObjectName("Faint")
        tip.setWordWrap(True)
        tip.setStyleSheet("font-size:11px;")
        v.addWidget(tip)

        def _do():
            nm = name.text().strip()
            if not nm:
                toast(self, "先写个昵称再点「加进来」", "warn", 3000)
                return
            pmap = {"Soul": "soul", "陌陌": "momo", "微信": "wechat"}
            try:
                from tt_db import TuokeDB
                db = TuokeDB()
                try:
                    cid = db.upsert_customer(pmap[plat.currentText()], nm)
                finally:
                    db.conn.close()          # 不关会把库文件锁住
            except Exception as e:
                toast(self, "没加成：%s" % str(e)[:60], "error", 4600)
                return
            try:
                from ui import datasource as _ds
                _ds.invalidate()
            except Exception:
                pass
            try:
                from ui.store import get_store
                get_store().changed.emit("customers")
            except Exception:
                pass
            self.reload()
            toast(self, "加进来了：%s（编号 %s）—— 点他一下，就能让 AI 聊这一轮"
                  % (nm, cid), "ok", 4600)

        modal(self, "加一个人", box,
              [("取消", None, "ghost"), ("加进来", _do, "primary")], width=360)

    def _on_sort_changed(self, mode):
        """
        换排序方式。

        ★ 「未读优先」这一项**做不到**：库里没有"未读"这一列
          （它要靠手机通知同步，那块还没做）。
          按它排 = 偷偷按别的规则排 → 用户以为"未读的排前面了"，其实没有。
          所以：照实说一句，然后按「最近活跃」排。
        """
        if mode == "未读优先":
            toast(self, "还没有「未读」这个数据 —— 它要等手机通知同步做完。"
                        "先按「最近活跃」给你排。", "warn", 4200)
        self._rebuild_list()

    # --------------------------------------------------------
    # 中栏：聊天
    # --------------------------------------------------------
    def _build_chat(self):
        col = QWidget()
        lay = QVBoxLayout(col)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ---- 聊天头 ----
        head = QWidget()
        hl = QHBoxLayout(head)
        hl.setContentsMargins(14, 10, 14, 10)
        hl.setSpacing(11)

        self.ch_av = Avatar("?", 40)
        hl.addWidget(self.ch_av)

        box = QVBoxLayout()
        box.setSpacing(2)
        self.ch_name = QLabel("")
        self.ch_name.setStyleSheet("font-size:14px; font-weight:700;")
        self.ch_meta = QLabel("")
        self.ch_meta.setObjectName("Faint")
        self.ch_meta.setStyleSheet("font-size:11px;")
        box.addWidget(self.ch_name)
        box.addWidget(self.ch_meta)
        hl.addLayout(box)

        self.mode_badge = QLabel("AI 托管中")
        self.mode_badge.setStyleSheet(
            "background:%s; color:%s; border-radius:10px;"
            "padding:3px 10px; font-size:11px; font-weight:600;"
            % (_bg(TH.cur()["blue"]), TH.cur()["blue"]))
        hl.addWidget(self.mode_badge)

        hl.addStretch(1)

        # ★ 「让 AI 聊一轮」—— 点开就能**看着它干活**（第 29 轮）
        self.btn_ai = Btn("让 AI 聊这一轮", "ghost", icon_name="robot")
        self.btn_ai.setToolTip("AI 会自己看消息、想回复、打字；试跑模式打完不发送，等你点头")
        self.btn_ai.clicked.connect(self._run_ai)
        hl.addWidget(self.btn_ai)

        self.btn_take = Btn("接管", "primary")
        self.btn_take.setIconSize(QSize(14, 14))
        self.btn_take.setToolTip("点一下 AI 立刻停手，你自己聊")
        self.btn_take.clicked.connect(self._toggle_takeover)
        hl.addWidget(self.btn_take)

        head.setStyleSheet("border-bottom:1px solid %s;" % TH.cur()["line"])
        lay.addWidget(head)

        # ---- 策略条 ----
        sb = QFrame()
        sb.setStyleSheet("background:%s; border-bottom:1px solid %s;"
                         % (_bg(TH.cur()["gold"]), TH.cur()["line"]))
        sl = QHBoxLayout(sb)
        sl.setContentsMargins(14, 7, 14, 7)
        sl.setSpacing(8)
        lb = QLabel("策略")
        lb.setStyleSheet("font-size:10.5px; color:%s; font-weight:700;" % TH.cur()["gold"])
        st = QLabel("")
        st.setObjectName("Sub")
        st.setStyleSheet("font-size:11.5px;")
        st.setWordWrap(True)
        sl.addWidget(lb); sl.addWidget(st, 1)
        lay.addWidget(sb)
        self.strategy_bar = sb
        self._strategy_text = st

        # ---- 消息区 ----
        self.msgs_box = QVBoxLayout()
        self.msgs_box.setContentsMargins(16, 14, 16, 14)
        self.msgs_box.setSpacing(3)

        holder = QWidget()
        holder.setLayout(self.msgs_box)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setWidget(holder)
        lay.addWidget(sc, 1)
        self.msgs_scroll = sc

        # ---- 快捷指令行 ----
        cr = QWidget()
        cl = QHBoxLayout(cr)
        cl.setContentsMargins(14, 4, 14, 6)
        cl.setSpacing(7)
        for cmd in ["约见面", "继续深聊", "晾一会", "标记疑似熟客", "重新生成"]:
            b = Btn(cmd, "ghost")
            b.setStyleSheet(b.styleSheet() + "font-size:11.5px; padding:4px 11px;")
            b.clicked.connect(lambda _=False, c=cmd: self._on_cmd(c))
            cl.addWidget(b)
        cl.addStretch(1)
        lay.addWidget(cr)

        # ★ 已下达的指令（第 34 轮）—— 让用户**看得见**指令真的存住了
        #   原来点了只弹一句提示就没了，用户没法确认"它到底记住没有"。
        self._orders_lb = QLabel("")
        self._orders_lb.setWordWrap(True)
        self._orders_lb.setStyleSheet(
            "font-size:11px; color:%s; background:%s; border-radius:6px;"
            "padding:4px 10px;" % (TH.cur()["blue"], _bg(TH.cur()["blue"])))
        self._orders_lb.hide()
        wrap = QWidget()
        wl = QHBoxLayout(wrap)
        wl.setContentsMargins(14, 0, 14, 5)
        wl.addWidget(self._orders_lb)
        wl.addStretch(1)
        lay.addWidget(wrap)

        # ---- 输入行 ----
        ir = QWidget()
        il = QHBoxLayout(ir)
        il.setContentsMargins(14, 0, 14, 12)
        il.setSpacing(9)

        wrap = QVBoxLayout()
        wrap.setSpacing(4)
        self.input = QTextEdit()
        self.input.setPlaceholderText("给 AI 下指令（如：回复她），或切换到接管后亲自回复…")
        self.input.setFixedHeight(56)
        hint = QLabel("Enter 发送 · Shift+Enter 换行          当前：AI 托管")
        hint.setObjectName("Faint")
        hint.setStyleSheet("font-size:10.5px;")
        wrap.addWidget(self.input)
        wrap.addWidget(hint)
        il.addLayout(wrap, 1)

        send = Btn("", "primary", icon_name="send")
        send.setFixedSize(44, 44)
        send.setIconSize(QSize(19, 19))
        send.setToolTip("发送  (Enter)")
        send.clicked.connect(self._on_send)
        il.addWidget(send, 0, Qt.AlignBottom)
        self.btn_send = send
        lay.addWidget(ir)

        # 输入框里按 Enter 直接发（大厂习惯）
        self.input.installEventFilter(self)

        return col

    # --------------------------------------------------------
    # 右栏：4 个页签
    # --------------------------------------------------------
    def _build_right(self):
        col = QFrame()
        col.setFixedWidth(322)
        col.setStyleSheet("background:%s; border-left:1px solid %s;"
                          % (TH.cur()["panel"], TH.cur()["line"]))

        lay = QVBoxLayout(col)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # 页签条
        tabs = QWidget()
        tl = QHBoxLayout(tabs)
        tl.setContentsMargins(10, 9, 10, 0)
        tl.setSpacing(4)

        self.rstack = QStackedWidget()
        self._rtabs = []
        for i, name in enumerate(["手机画面", "客户档案", "AI 聊天计划", "关联账号"]):
            b = QPushButton(name)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setChecked(i == 0)
            b.clicked.connect(lambda _=False, n=i: self._rtab(n))
            tl.addWidget(b)
            self._rtabs.append(b)
        tl.addStretch(1)
        lay.addWidget(tabs)

        # 页签样式
        for b in self._rtabs:
            b.setStyleSheet("""
                QPushButton {{
                    background:transparent; border:none; color:{sub};
                    font-size:11.5px; padding:6px 9px; border-bottom:2px solid transparent;
                }}
                QPushButton:hover  {{ color:{ink}; }}
                QPushButton:checked {{
                    color:{blue}; font-weight:600; border-bottom:2px solid {blue};
                }}
            """.format(sub=TH.cur()["sub"], ink=TH.cur()["ink"], blue=TH.cur()["blue"]))

        sep = QFrame(); sep.setFixedHeight(1)
        sep.setStyleSheet("background:%s;" % TH.cur()["line"])
        lay.addWidget(sep)

        # ★ 顺序就是页签顺序：先手机画面，再客户档案 / AI 聊天计划 / 关联账号。
        #   注意：别用 insertWidget 往回插 —— Qt 会**自动把当前索引后移**
        #   （它要保证"原来显示的那一项"不变），结果就是按钮选中和内容对不上。
        self.phone_view = PhoneView()
        self.rstack.addWidget(self.phone_view)

        # ★ 第 34 轮：这三个从"函数返回死数据"改成"有状态的真页面"，
        #   因为选中客户时要把这个人的档案塞进去（以前没有"人"可塞）。
        self.arc_view = ArchiveView()
        self.arc_view.saved.connect(self._on_notes_saved)
        self.plan_view = PlanView()
        self.acct_view = AcctView()
        for w in (self.arc_view, self.plan_view, self.acct_view):
            self.rstack.addWidget(w)
        lay.addWidget(self.rstack, 1)

        return col

    # --------------------------------------------------------
    # 设备画面转发（主窗口收到设备管家的帧后调这两个）
    # --------------------------------------------------------
    def on_device_frame(self, png_bytes):
        v = getattr(self, "phone_view", None)
        if v is not None:
            v.on_device_frame(png_bytes)

    def on_device_status(self, st):
        v = getattr(self, "phone_view", None)
        if v is not None:
            v.on_device_status(st)

    def _rtab(self, i):
        for j, b in enumerate(self._rtabs):
            b.setChecked(j == i)
        self.rstack.setCurrentIndex(i)

    # ========================================================
    # 交互（第 26 轮：把死按钮接活）
    # ========================================================
    def _toggle_takeover(self):
        """
        接管 / 还给 AI。

        ★ 规格书 4.3：人工接管是**随时可用的最高优先级动作**。
          点一下 AI 立刻停手（最坏一个步边界，1.8 秒）。
        """
        self._taken = not getattr(self, "_taken", False)
        if self._taken:
            self.mode_badge.setText("你在聊")
            self.mode_badge.setStyleSheet(
                "background:%s; color:%s; border-radius:10px;"
                "padding:3px 10px; font-size:11px; font-weight:600;"
                % (_bg(TH.cur()["gold"]), TH.cur()["gold"]))
            self.btn_take.setText("还给 AI")
            toast(self, "已接管 —— AI 停手了，你自己打字。聊完点「还给 AI」",
                  "warn", 4200)
        else:
            self.mode_badge.setText("AI 托管中")
            self.mode_badge.setStyleSheet(
                "background:%s; color:%s; border-radius:10px;"
                "padding:3px 10px; font-size:11px; font-weight:600;"
                % (_bg(TH.cur()["blue"]), TH.cur()["blue"]))
            self.btn_take.setText("接管")
            toast(self, "已还给 AI，它可以接着聊了", "ok")

    def _on_cmd(self, cmd):
        """
        快捷指令：给 AI 定个方向。

        ★ 第 34 轮改（用户骂的"装样子"就是这个）：
          原来点了只弹一句「已告诉 AI：……」，**指令根本没存下来**，
          关掉重开就没了，AI 也不知道。
          现在：指令**真的写进数据**（store.orders），
          界面能看到、AI 那一轮也能读到。
        """
        cid = getattr(self, "customer_id", None)
        if not cid:
            toast(self, "先在左边选一个人，再说要她怎么聊", "warn", 2800)
            return

        try:
            from ui.store import get_store
            ok, human = get_store().set_order(cid, cmd)
        except Exception as e:
            toast(self, "没下成：%s" % str(e)[:44], "error", 3600)
            return

        if not ok:
            toast(self, human, "warn", 2600)
            return

        # 让"待办指令"那条提示跟着更新
        self._refresh_orders_tip()
        toast(self, "已下达：%s —— AI 下一轮就照这个来" % human, "ok", 3400)

    def _refresh_orders_tip(self):
        """把"已下达的指令"显示在聊天页上（让用户看得见真的存住了）。"""
        lb = getattr(self, "_orders_lb", None)
        if lb is None:
            return
        try:
            from ui.store import get_store
            os_ = get_store().orders(getattr(self, "customer_id", None))
        except Exception:
            os_ = []
        if not os_:
            lb.hide()
            return
        txt = " · ".join("%s" % o.get("label", "?") for o in os_[-3:])
        lb.setText("已给 AI 下的指令：%s" % txt)
        lb.show()

    def _on_send(self):
        """
        人工接管后，自己在输入框里打的那句话。

        ★ 第 34 轮改了：以前不管手机连没连，都先往聊天区插一个气泡，
          再补一句"这句只落在界面上"——**等于在界面上造了一条假聊天记录**。
          现在：
            · 暂停了 → 不许发
            · 手机没连 → 直接说发不出去，**不插那个气泡**（不造假记录）
            · 手机连着 → 真交给发送通道（打字 + 点发送 + 回读验证），
                        发成功了才把气泡记上
        """
        txt = self.input.toPlainText().strip()
        if not txt:
            toast(self, "还没打字呢", "warn")
            return

        try:
            from ui.store import get_store
            if get_store().get_setting("paused", False):
                toast(self, "你按了暂停 —— 先回总览页点「继续运行」再发", "warn", 4200)
                return
        except Exception:
            pass

        try:
            from ui import device_hub
            connected = device_hub.get_hub().is_connected()
        except Exception:
            connected = False

        if not connected:
            toast(self, "这句发不出去 —— 手机没连上（插上数据线再试）", "warn", 4600)
            return

        try:
            from ui.agent_runner import SendWorker
            w = SendWorker(txt, self)
            w.done.connect(lambda ok, how, t=txt: self._on_send_done(ok, how, t))
            w.finished.connect(w.deleteLater)
            self._sender = w
            self.input.clear()
            toast(self, "正在替你发出去…（打字 + 点发送 + 回读验证）", "info", 2400)
            w.start()
        except Exception as e:
            toast(self, "发不出去：%s" % str(e)[:60], "error", 4200)

    def _on_send_done(self, ok, how, txt=""):
        """发送通道回来了：真发上了才把这条记进聊天区。"""
        if ok:
            self.msgs_box.insertWidget(self.msgs_box.count() - 1, Bubble("我", txt))
            QTimer.singleShot(30, self._scroll_bottom)
            toast(self, "发出去了 ✔" + ("（%s）" % how if how else ""), "ok", 4200)
        else:
            toast(self, "没发成" + ("：%s" % how if how else ""), "error", 4600)

    # ========================================================
    # ★ 让 AI 聊一轮（第 29 轮）—— 全程看得见
    # ========================================================
    def _run_ai(self):
        """
        点一下，AI 走一轮：看消息 → 想回复 → 打字 → （等你点头才发）。

        ★ 默认**试跑**：AI 会把字真打进你手机的输入框，但**不点发送**。
          你能亲眼看见它打算说什么，你点头了才真发出去。
        ★ AI 干活期间投屏自动让路（AgentRunner 里管的）。
        """
        win = self.window()
        r0 = getattr(self, "_runner", None)
        if r0 is not None and r0.isRunning():
            toast(self, "上一轮还没跑完，等它做完", "warn", 2600)
            return

        # ★ 第 35 轮：先看手机在不在，别让它跑到一半才失败。
        #   AI 干活 = 截图 + 点屏，没手机什么都干不了。
        #   与其让它报一串看不懂的错，不如一开始就说人话。
        try:
            from ui import device_hub as _dh
            if not _dh.get_hub().is_connected():
                toast(self, "手机没连上 —— 插上数据线、解锁屏幕，再点这一下", "warn", 5200)
                return
        except Exception:
            pass

        # ★ 暂停总闸（规格书 1.10.1）：按了暂停，AI 不许开工。
        try:
            from ui.store import get_store as _gs
            if _gs().get_setting("paused", False):
                toast(self, "你按了暂停 —— 先回总览页点「继续运行」", "warn", 4200)
                return
        except Exception:
            pass

        try:
            from ui.agent_runner import AgentRunner
            from ui.ai_panel import AiPanel
        except Exception as e:
            toast(self, "组件没起来：%s" % str(e)[:60], "error")
            return

        holder = {}

        def make(mask):
            p = AiPanel(mask, on_close=lambda: win.overlay.close(),
                        dry_run=True, parent_page=self)
            p.stop_it.connect(self._stop_ai)
            p.send_it.connect(self._send_ai)
            holder["panel"] = p
            return p

        panel = win.overlay.custom(make, width=640, height=610, y_ratio=0.5)
        self._panel = panel

        # ★ 第 34 轮：这里现在传的是**真 customer_id**（客户页已经接真库了）。
        #   有了它，ChatLoop 才会把这一轮写进 conversations 表；
        #   总览页/底栏的数字也才会跟着动。
        #   注意：光有 id 还不够 —— ChatLoop 还得拿到 db 连接才行，
        #   所以 AgentRunner 里也补上了 `db=TuokeDB()`（第 34 轮修的第二个根因）。
        if self.customer_id is None:
            toast(self, "先在左边挑一个客户，AI 才知道这轮算什么头上", "warn", 3600)
            win.overlay.close()
            return
        runner = AgentRunner(dry_run=True, customer_id=self.customer_id)
        runner.step.connect(panel.set_step)
        runner.done.connect(panel.finish)
        runner.done.connect(self._ai_done_note)
        runner.start()
        self._runner = runner

    def _ai_done_note(self, d):
        """
        一轮跑完，把界面和数字都跟上。

        ★ 第 34 轮的要点：AI 这一轮**已经落库了**（它会往 conversations 里
          写一条"对方说了啥"），所以这里要把聊天区重读一遍 ——
          否则用户会觉得"AI 跑完了，可聊天记录里啥也没多"。
        """
        try:
            reply = d.get("reply") or ""
            if d.get("ok") and reply:
                self.ch_meta.setText("AI 刚想好一句，等你点头")
            # 干完活 → 统计缓存作废（不然要等 3 秒缓存过期，用户以为"没反应"）
            DS.invalidate()
            win = self.window()
            if hasattr(win, "refresh_stats"):
                win.refresh_stats()
            # 聊天区重读真库 + 列表预览跟上（选中的那个人留住）
            if self.customer_id is not None:
                self._fill_messages(self._cur)
            self.reload(keep_selection=True)
            QTimer.singleShot(30, self._scroll_bottom)
        except Exception:
            pass

    def _stop_ai(self):
        r = getattr(self, "_runner", None)
        if r is not None:
            r.stop()
        self.window().overlay.close()
        toast(self, "停了 —— AI 把手收回来了", "warn", 2600)

    def _send_ai(self):
        """
        ★ 用户点了「让它发出去」—— 这才是**唯一**会真发消息的入口。
          前面所有步骤都是试跑，只有这个按钮会动真格。
        """
        panel = getattr(self, "_panel", None)
        reply = getattr(panel, "_reply", "") if panel else ""
        if not reply:
            toast(self, "没有要发的内容", "warn")
            return

        try:
            from ui.agent_runner import SendWorker
        except Exception as e:
            toast(self, "发送组件没起来：%s" % str(e)[:50], "error")
            return

        w = SendWorker(reply)

        def _on_done(ok, why):
            if panel is not None:
                try:
                    panel.mark_sent(ok, why)
                except Exception:
                    pass
            if ok:
                self.msgs_box.insertWidget(self.msgs_box.count() - 1,
                                           Bubble("我", reply))
            else:
                toast(self, "没发出去：%s" % (why or "原因不明"), "error", 4200)

        w.done.connect(_on_done)
        w.start()
        self._send_worker = w

    def eventFilter(self, obj, ev):
        """输入框里按 Enter 直接发（Shift+Enter 换行）。"""
        from PySide6.QtCore import QEvent
        if obj is getattr(self, "input", None) and ev.type() == QEvent.KeyPress:
            if ev.key() in (Qt.Key_Return, Qt.Key_Enter):
                if not (ev.modifiers() & Qt.ShiftModifier):
                    self._on_send()
                    return True
        return super().eventFilter(obj, ev)

    # --------------------------------------------------------
    def _select(self, d, keep_scroll=False):
        """
        选中一个客户 —— 这是这一页的**枢纽**。

        ★ 干三件要紧事：
          1. 把真 id 记进 `self.customer_id` → AgentRunner 拿它去落库
             （没有它，AI 跑完那一轮等于白干，总览页的数字永远不动）
          2. 中栏去库里读**这个人的**往来（不再是那 6 行示例对话）
          3. 右侧三个页签各自换成"这个人"的内容
        """
        self._cur = d
        # 换人了 → 待办指令条跟着换
        # （用 singleShot(0) 是因为此刻 customer_id 还没设好，等这一轮事件走完再刷）
        QTimer.singleShot(0, lambda: self._refresh_orders_tip())

        # ---- 空态：没人可选（库里没客户，或筛选没筛出来）----
        if not d:
            self.customer_id = None
            self.ch_av._text = "?"; self.ch_av.update()
            self.ch_name.setText("还没挑客户")
            self.ch_meta.setText("左边点一个人，这里就是他跟你的聊天")
            self.strategy_bar.setVisible(False)
            self._run_enabled(False)
            self._fill_messages(None)
            for v in (self.arc_view, self.plan_view, self.acct_view):
                v.set_customer(None)
            for r in self._rows:
                r.set_selected(False)
            return

        # ---- ① 真 id ----
        try:
            self.customer_id = d.get("id")
        except Exception:
            self.customer_id = None

        self.strategy_bar.setVisible(True)
        self._run_enabled(self.customer_id is not None)

        # ---- 中栏头 ----
        self.ch_av.setFixedSize(40, 40)
        self.ch_av._text = (d.get("nickname") or "?")[:1]
        self.ch_av.update()
        self.ch_name.setText(d.get("nickname") or "（没名字）")
        self.ch_meta.setText("%s · %s · 阶段：%s" % (
            DS.platform_cn(d.get("platform")),
            (d.get("distance") or DS.DASH),
            DS.stage_cn(d.get("progress"))))

        # ---- ② 真往来 ----
        self._fill_messages(d)

        # ---- ③ 右侧三页签 ----
        self.arc_view.set_customer(d)
        self.plan_view.set_customer(d)
        self.acct_view.set_customer(d)

        # 策略条：有真备忘就说真备忘，没有就照实说"还没定"
        self._set_strategy(d)

        # 列表高亮
        for r in self._rows:
            r.set_selected(r.data.get("id") == d.get("id"))

        if not keep_scroll:
            QTimer.singleShot(30, self._scroll_bottom)

    def _scroll_bottom(self):
        self.msgs_scroll.verticalScrollBar().setValue(
            self.msgs_scroll.verticalScrollBar().maximum())

    def _run_enabled(self, on):
        """没选中真客户就别让 AI 跑 —— 不然它跑完不知道算在谁头上。"""
        self.btn_ai.setEnabled(on)
        self.btn_ai.setToolTip(
            "AI 会自己看消息、想回复、打字；试跑模式打完不发送，等你点头"
            if on else "先在左边挑一个客户，再让 AI 聊")

    def _set_strategy(self, d):
        """策略条：读 `next_topic`（下一步聊啥）；没有就照实说还没定。"""
        topic = (d.get("next_topic") or "").strip()
        note = (d.get("summary") or "").strip()
        # ★ 第 49 轮：备注里可能本来就写着"备注：xxx"（用户/示例数据手打的），
        #   下面又补一个"备注："前缀 → 界面出现"备注：备注：xxx"叠词
        while note.startswith("备注：") or note.startswith("备注:"):
            note = note[3:].strip()
        if topic:
            txt = "下一步：%s" % topic
        elif note:
            txt = "备注：%s" % note
        else:
            txt = "AI 还没给这个人定策略 —— 聊起来之后就有了。"
        self._strategy_text.setText(txt)

    # --------------------------------------------------------
    # 中栏消息区（真读 conversations）
    # --------------------------------------------------------
    def _fill_messages(self, d):
        while self.msgs_box.count():
            it = self.msgs_box.takeAt(0)
            w = it.widget()
            if w:
                # ★ 第 49 轮：deleteLater 是异步的 —— 旧气泡在删除落地前
                #   还挂在树上**继续画**（实测页面上叠了 3 代气泡，
                #   其中第一代还是 640×480 的默认巨块 = 界面上那个"巨型蓝泡"）。
                #   先藏起来 + 摘出树，当场消失，删除什么时候落地都无所谓。
                w.hide()
                w.setParent(None)
                w.deleteLater()

        if not d:
            self.msgs_box.addWidget(Empty("💬", "还没挑客户",
                                          "在左边点一个人，这里就显示你俩聊过什么。"))
            self.msgs_box.addStretch(1)
            return

        rows = DS.messages(d.get("id"))
        if rows is None:
            self.msgs_box.addWidget(Empty("🔌", "读不到聊天记录",
                                          "打不开 data/tuoke.db。"))
            self.msgs_box.addStretch(1)
            return
        if not rows:
            self.msgs_box.addWidget(Empty("💬", "还没跟这个人聊过",
                                          "点右上角「让 AI 聊这一轮」，它先试跑给你看。"))
            self.msgs_box.addStretch(1)
            return

        for m in rows:
            who = "我" if (m.get("sender") in ("ai", "me", "user")) else "对方"
            self.msgs_box.addWidget(Bubble(who, m.get("content") or DS.DASH,
                                           DS.when(m.get("sent_at"))))
        self.msgs_box.addStretch(1)

    # --------------------------------------------------------
    # 外部跳转进来用（消息页点一条 → 跳过来选中这个人）
    # --------------------------------------------------------
    def select_by_name(self, name):
        """按名字选中客户。找不到就静默算了（别弹错吓用户）。"""
        for d in (self._customers or []):
            if (d.get("nickname") or "") == name:
                self._select(d)
                return True
        return False

    def select_by_id(self, cid):
        """按真 id 选中（外面拿到的就是 id，比名字可靠）。"""
        for d in (self._customers or []):
            if _sid(d.get("id")) == _sid(cid):
                self._select(d)
                return True
        return False

    # --------------------------------------------------------
    # 备注存好了（档案区发出来的）
    # --------------------------------------------------------
    def _on_notes_saved(self, cid):
        """备注写进库了 → 列表预览可能变了，重读一遍（选中的那个人留住）。"""
        self.reload(keep_selection=True)

    def on_show(self):
        """切到这一页时重读一次（AI 可能刚干完活，库里的东西变了）。"""
        if getattr(self, "_customers", None) is None:
            self.reload()
            return
        # ★ 用 3 秒缓存挡一下：来回切页不要每次都连库
        self._customers = DS.customers()
        self._rebuild_list()
        if self.customer_id is not None:
            self.select_by_id(self.customer_id)
