# -*- coding: utf-8 -*-
"""
Taku · AI 干活的过程面板

★ 干什么：
    把 AgentRunner 报上来的 8 步显示出来 —— 用户能看着 AI 一步步干活，
    而不是对着一个转圈的加载图标干等。

★ 为什么这件事重要（产品的核心体验）：
    这软件的目的是"AI 替你聊，你看着就行"。
    **"你看着"**这四个字就是这个面板 —— 它是"托管感"的来源。
    AI 要是默默在后台干，用户会不放心（"它到底在干嘛？发错话没有？"）。

★ 试跑模式的落点：
    跑到第 7 步（发送）时**停下来**，把"AI 打算说的话"摆给用户看，
    下面两个按钮：**让它发出去** / **不发了**。用户点一下才算完。
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout, QScrollArea,
)
from PySide6.QtGui import QPixmap

from . import theme as TH
from . import icons as IC
from .widgets import Btn, add_shadow


STATE_ICON = {
    "running": ("dot",   "blue"),
    "ok":      ("check", "green"),
    "fail":    ("close", "red"),
    "wait":    ("pause", "gold"),
    "idle":    ("dot",   "faint"),
}

STATE_TEXT = {
    "running": "正在做",
    "ok":      "成了",
    "fail":    "没成",
    "wait":    "等你定",
    "idle":    "还没到",
}


class _StepRow(QWidget):
    """一步一行：序号 + 状态 + 名字 + 说明。"""

    def __init__(self, no, name, parent=None):
        super().__init__(parent)
        t = TH.cur()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 5, 0, 5)
        lay.setSpacing(9)

        # 序号圆点
        self.num = QLabel(str(no))
        self.num.setFixedSize(20, 20)
        self.num.setAlignment(Qt.AlignCenter)

        # 状态图标
        self.ico = QLabel()
        self.ico.setFixedSize(16, 16)

        # 名字
        self.name = QLabel(name)
        self.name.setFixedWidth(112)

        # 说明
        self.detail = QLabel("")
        self.detail.setWordWrap(True)

        lay.addWidget(self.num)
        lay.addWidget(self.ico)
        lay.addWidget(self.name)
        lay.addWidget(self.detail, 1)

        self.set_state("idle", "")

    def set_state(self, state, detail):
        t = TH.cur()
        icon_name, color_key = STATE_ICON.get(state, STATE_ICON["idle"])
        col = t[color_key]

        self.ico.setPixmap(IC.render(icon_name, 13, col))

        if state == "idle":
            self.num.setStyleSheet(
                "background:%s; color:%s; border-radius:10px; font-size:10.5px;"
                % (t["card3"], t["faint"]))
            self.name.setStyleSheet("font-size:12px; color:%s;" % t["faint"])
            self.detail.setStyleSheet("font-size:11.5px; color:%s;" % t["faint"])
        elif state == "running":
            self.num.setStyleSheet(
                "background:%s; color:#ffffff; border-radius:10px;"
                "font-size:10.5px; font-weight:700;" % t["blue"])
            self.name.setStyleSheet("font-size:12px; color:%s; font-weight:600;" % t["ink"])
            self.detail.setStyleSheet("font-size:11.5px; color:%s;" % t["blue"])
        else:
            self.num.setStyleSheet(
                "background:%s; color:%s; border-radius:10px; font-size:10.5px;"
                % (t["card3"], t["sub"]))
            self.name.setStyleSheet("font-size:12px; color:%s;" % t["ink"])
            self.detail.setStyleSheet("font-size:11.5px; color:%s;" % t["sub"])

        if detail:
            self.detail.setText(detail)


class AiPanel(QFrame):
    """
    AI 干活的过程面板（弹层内容）。

    用法：
        panel = AiPanel(parent, on_stop=..., on_send=..., on_close=...)
        runner.step.connect(panel.set_step)
        runner.done.connect(panel.finish)
    """

    send_it = Signal()      # 用户点了"让它发出去"
    stop_it = Signal()      # 用户点了"停下"

    def __init__(self, parent=None, on_close=None, dry_run=True, parent_page=None):
        super().__init__(parent)
        self.setObjectName("AiPanel")
        self._on_close = on_close
        self._dry_run = dry_run
        self._page = parent_page
        self._rows = {}
        self._reply = ""
        self._finished = False

        t = TH.cur()
        self.setStyleSheet(
            "QFrame#AiPanel{background:%s; border:1px solid %s;"
            "border-radius:%s;}" % (t["card"], t["line2"], t["r_xl"]))
        add_shadow(self, blur=44, dy=16, alpha=180)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ---------- 头 ----------
        head = QWidget()
        hl = QHBoxLayout(head)
        hl.setContentsMargins(20, 15, 16, 13)
        hl.setSpacing(9)

        self.title = QLabel("AI 正在替你聊这一轮")
        self.title.setStyleSheet("font-size:14px; font-weight:700;")

        self.prog = QLabel("0 / 8")
        self.prog.setStyleSheet(
            "font-size:11px; color:%s; background:%s; border-radius:9px;"
            "padding:2px 9px;" % (t["blue"], t["blue_bg"]))

        hl.addWidget(self.title)
        hl.addStretch(1)
        hl.addWidget(self.prog)
        lay.addWidget(head)

        sep = QFrame(); sep.setFixedHeight(1)
        sep.setStyleSheet("background:%s;" % t["line"])
        lay.addWidget(sep)

        # ---------- 步骤列表 ----------
        box = QWidget()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(20, 10, 20, 10)
        bl.setSpacing(0)

        from .agent_runner import STEPS
        for i, name in enumerate(STEPS, 1):
            row = _StepRow(i, name)
            self._rows[i] = row
            bl.addWidget(row)
        bl.addStretch(1)

        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setWidget(box)
        lay.addWidget(sc, 1)

        # ---------- 试跑提示（第 7 步停下时显示） ----------
        self.tipbox = QFrame()
        self.tipbox.setStyleSheet(
            "background:%s; border-top:1px solid %s;"
            % (t["gold_bg"], t["line"]))
        tl = QVBoxLayout(self.tipbox)
        tl.setContentsMargins(20, 12, 20, 12)
        tl.setSpacing(6)

        self.ask = QLabel("")
        self.ask.setWordWrap(True)
        self.ask.setStyleSheet("font-size:12.5px;")
        tl.addWidget(self.ask)

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setFixedHeight(150)
        self.preview.hide()
        tl.addWidget(self.preview)

        lay.addWidget(self.tipbox)
        self.tipbox.hide()

        # ---------- 底部按钮 ----------
        foot = QWidget()
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(20, 12, 20, 16)
        fl.setSpacing(9)
        fl.addStretch(1)

        self.btn_stop = Btn("停下", "ghost", icon_name="stop")
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_send = Btn("让它发出去", "primary", icon_name="send")
        self.btn_send.clicked.connect(self._on_send)
        self.btn_close = Btn("关闭", "ghost")
        self.btn_close.clicked.connect(lambda: self._on_close and self._on_close())

        fl.addWidget(self.btn_stop)
        fl.addWidget(self.btn_close)
        fl.addWidget(self.btn_send)
        lay.addWidget(foot)
        self.btn_send.hide()

        self._btn_row = (self.btn_stop, self.btn_close, self.btn_send)

    # --------------------------------------------------------
    # 收进度
    # --------------------------------------------------------
    def set_step(self, d):
        no = d.get("no", 0)
        state = d.get("state", "idle")
        detail = d.get("detail", "")
        total = d.get("total", 8)

        row = self._rows.get(no)
        if row is not None:
            row.set_state(state, detail)

        # 还没到的步骤保持"还没到"
        for i in range(no + 1, total + 1):
            r = self._rows.get(i)
            if r is not None:
                r.set_state("idle", "")

        done = no if state in ("ok",) else max(0, no - 1)
        self.prog.setText("%d / %d" % (done, total))

    def finish(self, d):
        self._finished = True
        self._reply = d.get("reply", "")

        ok = d.get("ok")
        self.title.setText(d.get("title", "做完了"))

        if ok and d.get("dry_run") and self._reply:
            # ★ 试跑：把 AI 打算发的话摆出来，问用户发不发
            self.prog.setText("8 / 8 · 等你定")
            self.tipbox.show()
            self.ask.setText(
                "AI 把这句话打进你手机的输入框了：\n\n"
                "「%s」\n\n还没点发送 —— 你说发，它才发。"
                % self._reply)

            shot = d.get("shot")
            if shot:
                pm = QPixmap()
                if pm.loadFromData(shot):
                    self.preview.setPixmap(pm.scaled(
                        280, 145, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                    self.preview.show()

            self.btn_stop.hide()
            self.btn_close.setText("不发了")
            self.btn_send.show()
        else:
            self.prog.setText("已结束")
            self.btn_stop.hide()
            self.btn_close.setText("知道了")
            self.btn_send.hide()
            self.tipbox.show()
            self.ask.setText(d.get("summary", ""))

    # --------------------------------------------------------
    def _on_stop(self):
        self.stop_it.emit()

    def _on_send(self):
        """
        ★ 用户点头了，真发。
          这里不自己发 —— 交给页面去调（发完要清输入框、刷新画面）。
        """
        self.btn_send.setEnabled(False)
        self.btn_send.setText("正在发…")
        self.send_it.emit()

    def mark_sent(self, ok, why=""):
        self.btn_send.setEnabled(True)
        self.btn_send.setText("让它发出去")
        if ok:
            self.tipbox.hide()
            self.btn_send.hide()
            self.btn_close.setText("好的")
            self.title.setText("发出去了")
            if self._page is not None:
                try:
                    from .widgets import toast
                    toast(self._page, "发出去了 —— 回读确认气泡已出现", "ok", 3200)
                except Exception:
                    pass
        else:
            self.ask.setText("发失败了：%s" % (why or "原因不明"))
