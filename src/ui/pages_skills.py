# -*- coding: utf-8 -*-
"""
页面 ⑤ 技能库（图纸 view-skills，第 1324~1417 行）

★ 这一页是第 20 轮新加的第 8 页（原定 6 页 → 扩到 9 页）。
★ 定位：记的是「AI 会不会用这个 App」（认路），不是「聊天用哪几招」。

★ 图纸页头原文：
    技能库 / AI 在每个 App 里学会的"路怎么走"。第一次用到某个 App，它会自己去认一次路。
    右上两个按钮：[↻ 刷新状态] [＋ 让 AI 现在去学一个 App]
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea, QGridLayout,
)
from ui import theme as TH
from ui.widgets import Card, Btn, page_title, page_sub, toast, modal, ask


# ★ 图纸三张卡（陌陌 可用 / Soul 可用 / 微信 未认路），字段照抄
APPS = [
    {
        "logo": "M", "name": "陌陌", "state": "ok",
        "line": "已学会 · 认路时间 2026-09-28 14:20",
        "tag": "✔ 可用",
        "entries": "5 个", "cost": "3 分 12 秒", "last": "10 分钟前",
        "chips": ["发消息", "看新消息", "翻聊天记录", "搜索用户", "进个人主页"],
    },
    {
        "logo": "S", "name": "Soul", "state": "ok",
        "line": "已学会 · 认路时间 2026-09-29 09:05",
        "tag": "✔ 可用",
        "entries": "4 个", "cost": "4 分 40 秒", "last": "2 小时前",
        "chips": ["发消息", "看新消息", "翻聊天记录", "进个人主页"],
    },
    {
        "logo": "微", "name": "微信", "state": "pending",
        "line": "还没学过 · 第一次用到会自动排到队首",
        "tag": "⏳ 未认路",
        "entries": "—", "cost": "—", "last": "还没用过",
        "chips": [],
        "note": "用到它的时候，AI 会先花几分钟自己认一遍路，认完才开始干活。",
    },
]


class AppCard(QFrame):
    def __init__(self, d, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")

        ok = (d["state"] == "ok")
        accent = TH.cur()["green"] if ok else TH.cur()["gold"]
        self._name = d["name"]
        self._ok = ok

        lay = QVBoxLayout(self)
        lay.setContentsMargins(15, 13, 15, 13)
        lay.setSpacing(9)

        # 头
        h = QHBoxLayout()
        h.setSpacing(11)

        logo = QLabel(d["logo"])
        logo.setFixedSize(38, 38)
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet("background:%s; color:#fff; border-radius:9px;"
                           "font-size:16px; font-weight:700;" % TH.cur()["blue"])
        h.addWidget(logo)

        meta = QVBoxLayout()
        meta.setSpacing(2)
        nm = QLabel(d["name"]); nm.setStyleSheet("font-weight:700; font-size:13.5px;")
        li = QLabel(d["line"]); li.setObjectName("Faint"); li.setStyleSheet("font-size:11px;")
        meta.addWidget(nm); meta.addWidget(li)
        h.addLayout(meta, 1)

        tag = QLabel(d["tag"])
        tag.setStyleSheet("font-size:10.5px; padding:3px 9px; border-radius:9px;"
                          "color:%s; background:%s;" % (accent, _bg(accent)))
        h.addWidget(tag)
        lay.addLayout(h)

        sep = QFrame(); sep.setFixedHeight(1)
        sep.setStyleSheet("background:%s;" % TH.cur()["line"])
        lay.addWidget(sep)

        # 三行 KV
        for k, v in (("学会的入口", d["entries"]),
                     ("上次认路耗时", d["cost"]),
                     ("最近一次使用", d["last"])):
            r = QHBoxLayout()
            a = QLabel(k); a.setObjectName("Sub"); a.setStyleSheet("font-size:11.5px;")
            b = QLabel(v); b.setStyleSheet("font-weight:600; font-size:11.5px;")
            r.addWidget(a); r.addStretch(1); r.addWidget(b)
            lay.addLayout(r)

        # 入口小标签
        if d["chips"]:
            wrap = QHBoxLayout()
            wrap.setSpacing(5)
            for c in d["chips"]:
                t = QLabel(c)
                t.setStyleSheet("font-size:10.5px; padding:2px 8px; border-radius:8px;"
                                "background:%s; color:%s;"
                                % (TH.cur()["card3"], TH.cur()["sub"]))
                wrap.addWidget(t)
            wrap.addStretch(1)
            lay.addLayout(wrap)
        else:
            n = QLabel(d.get("note", ""))
            n.setObjectName("Faint")
            n.setWordWrap(True)
            n.setStyleSheet("font-size:11px;")
            lay.addWidget(n)

        lay.addStretch(1)

        # 底部按钮
        f = QHBoxLayout()
        f.setSpacing(7)
        if ok:
            b1 = Btn("重新认一次路", "ghost")
            b1.clicked.connect(self._relearn)
            b2 = Btn("看它记住了啥", "ghost")
            b2.clicked.connect(self._show_memory)
            f.addWidget(b1)
            f.addWidget(b2)
        else:
            b = Btn("现在就去学", "primary", icon_name="play")
            b.clicked.connect(self._learn_now)
            f.addWidget(b)
        f.addStretch(1)
        lay.addLayout(f)

    # --------------------------------------------------------
    def _relearn(self):
        ask(self, "让 AI 重新认一遍 %s 的路？" % self._name,
            "它会自己走一遍这个 App 的主要页面，记下路怎么走。\n"
            "大概要 3~5 分钟，这段时间它不干别的活。",
            self._queue_done,
            yes_text="开始认路")

    def _queue_done(self):
        """★ 第 34 轮：真排进队列（不再是弹一句就完了）。"""
        from ui.store import get_store
        get_store().queue_task("认路", "重新认一遍 %s 的路" % self._name,
                               "排队等手机——接上就自己跑")
        toast(self, "已排队 —— AI 会重新认一遍 %s 的路" % self._name, "ok", 3600)

    def _show_memory(self):
        from ui.store import get_store
        q = [x for x in get_store().queue()
             if ("%s" % self._name) in x.get("title", "")]
        extra = ""
        if q:
            extra = "\n\n★ 已排的活：\n" + "\n".join(
                "· %s（%s，%s）" % (x["title"], x["at"], x["state"]) for x in q[:5])
        modal(self, "%s 记住了什么" % self._name,
              "它记的是「路怎么走」，比如：\n\n"
              "· 点哪儿能发消息\n"
              "· 消息列表怎么翻\n"
              "· 怎么进某个人的主页\n"
              "· 发完消息会停在哪个页面\n\n"
              "记的是位置和顺序，不读别人的聊天内容。" + extra,
              [("知道了", None, "primary")])

    def _learn_now(self):
        from ui.store import get_store
        get_store().queue_task("认路", "现在就去学 %s" % self._name,
                               "排队等手机——接上就自己跑")
        toast(self, "已排队 —— AI 现在就去学 %s（接上手机就跑）" % self._name, "ok", 3600)


def _bg(h):
    h = h.lstrip("#")
    return "rgba(%d,%d,%d,0.13)" % (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


class SkillsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(18, 16, 18, 18)
        lay.setSpacing(14)

        # 页头
        head = QHBoxLayout()
        hl = QVBoxLayout()
        hl.setSpacing(3)
        hl.addWidget(page_title("技能库"))
        hl.addWidget(page_sub("AI 在每个 App 里学会的「路怎么走」。第一次用到某个 App，它会自己去认一次路。"))
        head.addLayout(hl)
        head.addStretch(1)

        b1 = Btn("刷新状态", "ghost", icon_name="refresh")
        b1.clicked.connect(self._refresh)
        b2 = Btn("让 AI 现在去学一个 App", "primary", icon_name="plus")
        b2.clicked.connect(self._learn_new)
        head.addWidget(b1)
        head.addWidget(b2)
        lay.addLayout(head)

        # ★ 第 34 轮：真状态行 + 真队列卡片（点了"去学"之后有东西留下来）
        self._status = QLabel("点「刷新状态」看看现在什么情况。")
        self._status.setObjectName("Sub")
        self._status.setStyleSheet("font-size:11.5px;")
        lay.addWidget(self._status)

        self._queue_card = Card()
        lay.addWidget(self._queue_card)
        self._paint_queue()

        # 三张卡
        grid = QGridLayout()
        grid.setSpacing(12)
        for i, d in enumerate(APPS):
            grid.addWidget(AppCard(d), i // 2, i % 2)
        lay.addLayout(grid)

        # 说人话
        tip = QFrame()
        tip.setObjectName("TipBox")
        tl = QVBoxLayout(tip)
        tl.setContentsMargins(14, 11, 14, 11)
        t = QLabel("<b>说人话：</b>这里记的是「AI 会不会用这个 App」。"
                   "学会了才敢让它去干活，没学会它会先自己去学一遍。")
        t.setObjectName("Sub")
        t.setWordWrap(True)
        tl.addWidget(t)
        lay.addWidget(tip)

        lay.addStretch(1)
        scroll.setWidget(inner)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

        # 队列一变就重画
        try:
            from ui.store import get_store
            get_store().changed.connect(self._on_store)
        except Exception:
            pass

    def _on_store(self, kind):
        if kind == "queue":
            self._paint_queue()

    def _paint_queue(self):
        from ui.store import get_store
        card = self._queue_card
        body = card.body()
        while body.count():
            it = body.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
        q = get_store().queue()
        title = QLabel("待办队列（%d 条）" % len(q))
        title.setStyleSheet("font-weight:700; font-size:13px;")
        body.addWidget(title)
        if not q:
            e = QLabel("空。点上面的「让 AI 现在去学一个 App」，或者卡片上的按钮，"
                       "排进来的活会在这显示。")
            e.setObjectName("Faint")
            e.setWordWrap(True)
            e.setStyleSheet("font-size:11.5px;")
            body.addWidget(e)
            return
        for x in q[:6]:
            r = QWidget()
            rl = QHBoxLayout(r)
            rl.setContentsMargins(0, 2, 0, 2)
            a = QLabel("%s · %s" % (x.get("kind", ""), x.get("title", "")))
            a.setStyleSheet("font-size:11.5px;")
            b = QLabel("%s ｜ %s" % (x.get("at", ""), x.get("state", "")))
            b.setObjectName("Faint")
            b.setStyleSheet("font-size:11px;")
            rl.addWidget(a, 1)
            rl.addWidget(b)
            body.addWidget(r)

    def _refresh(self):
        """
        ★ 第 34 轮：真去读本机 —— 技能目录里有几个技能、库里有几条认路记录。
          原来只弹一句"3 个 App：2 个会用了"，那是我编的。
        """
        import os
        import time
        from ui.store import get_store

        from ui.paths import project_root, data_dir
        root = project_root()
        sk = os.path.join(root, "skills")
        skills = []
        if os.path.isdir(sk):
            for fn in sorted(os.listdir(sk)):
                if os.path.isdir(os.path.join(sk, fn)):
                    skills.append(fn)

        known = 0
        try:
            import sqlite3
            db = os.path.join(data_dir(), "tuoke.db")
            c = sqlite3.connect("file:%s?mode=ro" % db.replace("\\", "/"), uri=True)
            try:
                known = c.execute("select count(*) from app_skills").fetchone()[0]
            except Exception:
                known = 0
            finally:
                c.close()
        except Exception:
            known = 0

        ts = time.strftime("%H:%M")
        get_store().set_setting("skills_refreshed_at", ts)
        self._status.setText(
            "上次刷新 %s ｜ 技能目录：%d 个（%s）｜ App 认路记录：%d 条 %s"
            % (ts, len(skills), "、".join(skills) if skills else "空",
               known, "（还没真学过，第一次用得先认路）" if not known else ""))
        self._status.setStyleSheet("font-size:11.5px; color:%s;" % TH.cur()["green"])
        self._paint_queue()
        toast(self, "刷新好了：技能目录 %d 个，认路记录 %d 条"
              % (len(skills), known), "ok", 3200)

    def _learn_new(self):
        modal(self, "让 AI 去学哪个 App？",
              "它会自己打开这个 App、走一遍主要页面、把路记下来。\n"
              "认路期间不干别的活，大概 3~5 分钟。",
              [("陌陌", lambda: self._queued("陌陌"), "ghost"),
               ("Soul", lambda: self._queued("Soul"), "ghost"),
               ("微信", lambda: self._queued("微信"), "primary")])

    def _queued(self, name):
        from ui.store import get_store
        get_store().queue_task("认路", "现在就去学 %s" % name,
                               "排队等手机——接上就自己跑")
        toast(self, "已排队 —— AI 现在就去学 %s（接上手机就跑）" % name, "ok", 3600)

    def on_show(self):
        pass
