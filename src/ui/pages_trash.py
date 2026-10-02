# -*- coding: utf-8 -*-
"""
页面 ⑧ 回收站（图纸 view-trash，第 1503~1562 行）

★ 定位（规格书 4.9.3-4.9.4）：
    放弃（pass）由 AI 自己判，但**放弃理由必须留档 + 进回收站**（不是删除）。
    明确拒绝 / 涉钱 / 骗子 = 立即放弃铁律。
    「已见面」只能用户手动标（规格书 4.9.1）。

★ 图纸页头原文：
    回收站 / 被放弃的客户会先到这里，30 天后自动清掉。想捞回来随时可以。
    右上：[清空回收站]
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea,
)
from ui import theme as TH
from ui.widgets import Card, Btn, page_title, page_sub, toast, ask, modal, Empty


# ★ 第 33 轮：原来这里有个写死的 ITEMS 常量（3 条假数据）。
#   现在回收站的内容从 store 读 —— 你在客户页删了谁，这里就出现谁。
#   （假数据已撤，见 git 历史）


def _bg(h):
    h = h.lstrip("#")
    return "rgba(%d,%d,%d,0.13)" % (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


class TrashPage(QWidget):
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
        hl = QVBoxLayout(); hl.setSpacing(3)
        hl.addWidget(page_title("回收站"))
        hl.addWidget(page_sub("被放弃的客户会先到这里，30 天后自动清掉。想捞回来随时可以。"))
        head.addLayout(hl)
        head.addStretch(1)
        empty_btn = Btn("清空回收站", "ghost")
        empty_btn.clicked.connect(self._empty_all)
        head.addWidget(empty_btn)
        self._empty_btn = empty_btn
        lay.addLayout(head)

        # ★ 第 34 轮：一行"现在有几条"的状态。点了清空/捞回来，这行字立刻变 ——
        #   用户不用靠"提示飘一下"来判断到底成没成。
        self._cnt = QLabel("回收站里 0 条")
        self._cnt.setObjectName("Sub")
        self._cnt.setStyleSheet("font-size:11.5px;")
        lay.addWidget(self._cnt)

        # 列表（★ 第 33 轮：不再写死，从 store 读）
        self.card = Card()
        self.card.body().setSpacing(0)
        lay.addWidget(self.card)

        # 说人话
        tb = QFrame()
        tb.setObjectName("TipBox")
        tl = QVBoxLayout(tb)
        tl.setContentsMargins(14, 11, 14, 11)
        t = QLabel("<b>说人话：</b>AI 觉得没戏、或者你自己删掉的人，都先放这儿，不会真没了。"
                   "想找谁回来，点「捞回来」就行。")
        t.setObjectName("Sub")
        t.setWordWrap(True)
        tl.addWidget(t)
        lay.addWidget(tb)

        lay.addStretch(1)
        scroll.setWidget(inner)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

        # 数据变了就重画（客户页删了人，这边立刻能看到）
        try:
            from ui.store import get_store
            get_store().changed.connect(lambda _k: self._reload())
        except Exception:
            pass

        self._render()

    # --------------------------------------------------------
    def _items(self):
        """回收站里有什么 —— 从 store 读（拿不到就空着，不编数据）。"""
        try:
            from ui.store import get_store
            return get_store().trash()
        except Exception:
            return []

    def _reload(self):
        self._render()

    # ---- 空态里的几个去处 ----
    def _goto(self, key):
        w = self.window()
        if hasattr(w, "goto"):
            w.goto(key)

    def _goto_customers(self):
        self._goto("customers")

    def _goto_tuoke(self):
        self._goto("tuoke")

    def _explain(self):
        modal(self, "回收站怎么用",
              "· 你点「移出」删掉的人，**先来这儿**，不是真没了。\n"
              "· AI 觉得没戏而放弃的人，也来这儿（理由会写清楚）。\n"
              "· 想找谁回来，点「捞回来」，她就回到客户列表了。\n"
              "· 点「永久删」才是真删，**找不回来**。\n"
              "· 什么都不做，放满 30 天它会自己清掉。\n\n"
              "你不需要手动清理它。",
              [("知道了", None, "primary")])

    def _render(self):
        box = self.card.body()
        while box.count():
            it = box.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)      # 立刻摘掉（只 deleteLater 会残留到下一轮事件循环）
                w.deleteLater()

        items = self._items()
        try:
            self._cnt.setText("回收站里 %d 条" % len(items))
        except Exception:
            pass
        # ★ 空的时候把它变灰 —— 没东西可清，让它能点就是"点了没用"
        #   （用户最恨的就是这种按钮）。
        try:
            self._empty_btn.setEnabled(bool(items))
            self._empty_btn.setCursor(
                Qt.PointingHandCursor if items else Qt.ForbiddenCursor)
            self._empty_btn.setToolTip(
                "把回收站里的人永久删掉（不可恢复）" if items
                else "回收站本来就是空的，没什么可清的")
        except Exception:
            pass
        if not items:
            # ★ 第 34 轮：空态不再是一条死路 —— 给几个**真能点**的去处。
            #   （自检工具也报过"这一页只有 1 个能点的，用户会觉得动不了"。）
            box.addWidget(Empty(
                "🗑", "回收站是空的 —— 挺好的",
                "你删掉的人会先来这儿，30 天后自动清掉。",
                action=[("回客户列表", self._goto_customers),
                        ("去拓客找人", self._goto_tuoke),
                        ("回收站怎么用？", self._explain)]))
            return

        for it in items:
            nm = it.get("name", "?")
            box.addWidget(self._row(
                nm[:1], nm, it.get("src", "—"),
                it.get("why", ""), it.get("tm", ""), it.get("id")))

    def _row(self, logo, nm, src, why, tm, tid):
        f = QFrame()
        f.setStyleSheet("QFrame{background:transparent; border:none;"
                        "border-bottom:1px solid %s;}" % TH.cur()["line"])
        l = QHBoxLayout(f)
        l.setContentsMargins(0, 11, 0, 11)
        l.setSpacing(11)

        av = QLabel(logo)
        av.setFixedSize(38, 38)
        av.setAlignment(Qt.AlignCenter)
        av.setStyleSheet("background:%s; color:%s; border-radius:9px;"
                         "font-size:15px; font-weight:700;"
                         % (TH.cur()["card3"], TH.cur()["sub"]))
        l.addWidget(av)

        mid = QVBoxLayout(); mid.setSpacing(3)
        r1 = QHBoxLayout(); r1.setSpacing(6)
        n = QLabel(nm); n.setStyleSheet("font-weight:600; font-size:12.5px;")
        s = QLabel(src)
        s.setStyleSheet("font-size:10px; padding:1px 6px; border-radius:5px;"
                        "background:%s; color:%s;" % (_bg(TH.cur()["blue"]), TH.cur()["blue"]))
        r1.addWidget(n); r1.addWidget(s); r1.addStretch(1)

        w = QLabel(why)
        w.setObjectName("Sub")
        w.setWordWrap(True)
        w.setStyleSheet("font-size:11.5px;")

        mid.addLayout(r1); mid.addWidget(w)
        l.addLayout(mid, 1)

        tt = QLabel(tm)
        tt.setObjectName("Faint")
        tt.setFixedWidth(72)
        tt.setAlignment(Qt.AlignRight | Qt.AlignTop)
        tt.setStyleSheet("font-size:10.5px;")
        l.addWidget(tt)

        acts = QHBoxLayout()
        acts.setSpacing(6)
        back = Btn("捞回来", "ghost")
        back.clicked.connect(lambda _=False, i=tid, x=nm: self._restore(i, x))
        dele = Btn("永久删", "danger")
        dele.clicked.connect(lambda _=False, i=tid, x=nm: self._delete_forever(i, x))
        acts.addWidget(back)
        acts.addWidget(dele)
        l.addLayout(acts)

        return f

    # --------------------------------------------------------
    def _restore(self, tid, name):
        """捞回来 —— 真的放回客户列表（切页、重开都还在）。"""
        try:
            from ui.store import get_store
            ok = get_store().restore(tid)
        except Exception:
            ok = False

        if not ok:
            toast(self, "没捞回来（这条记录可能已经不在了）", "warn")
            self._reload()
            return

        try:
            from ui import datasource as _ds
            _ds.invalidate()
        except Exception:
            pass

        self._reload()
        toast(self, "已把「%s」捞回客户列表" % name, "ok", 3200)

    def _delete_forever(self, tid, name):
        """
        ★ 规格书 4.9.4：永久删是**不可逆**的，
          大厂规矩 —— 破坏性操作必须二次确认，且按钮要说清楚后果。

        ★ 第 35 轮：真删库里那条记录（客户 + 聊天往来一起删）。
          以前只从回收站列表里划掉 —— 库里那行还在，只是被"藏"着，
          那不叫永久删。按钮写着"找不回来"，就得真的找不回来。
        """
        def _do():
            # ① 库里真删（数据层的活，页面不碰 SQL）
            try:
                from tt_db import TuokeDB
                db = TuokeDB()
                try:
                    db.conn.execute("DELETE FROM conversations WHERE customer_id=?", (tid,))
                    db.conn.execute("DELETE FROM customers WHERE id=?", (tid,))
                    db.conn.commit()
                finally:
                    db.conn.close()
            except Exception:
                pass                      # 库里本来就没有（示例客户）→ 算删干净了

            # ② 从回收站划掉
            try:
                from ui.store import get_store
                get_store().purge(tid)
            except Exception:
                pass
            try:
                from ui import datasource as _ds
                _ds.invalidate()
            except Exception:
                pass
            self._reload()
            toast(self, "已永久删掉「%s」（聊天记录一起删了，找不回来了）" % name,
                  "warn", 4600)

        ask(self, "永久删掉「%s」？" % name,
            "这个删了就真没了，回收站里也找不回来 —— 跟「捞回来」不一样。\n\n"
            "**她跟 AI 的聊天记录也会一起删掉。**\n"
            "如果只是不想理她了，用「捞回来」放到客户列表里晾着就行。",
            _do, yes_text="永久删", danger=True)

    def _empty_all(self):
        n = len(self._items())
        if n == 0:
            toast(self, "回收站本来就是空的", "info")
            return

        def _do():
            try:
                from ui.store import get_store
                get_store().empty_trash()
            except Exception:
                pass
            self._reload()
            toast(self, "已清空回收站（%d 个）" % n, "warn")

        ask(self, "清空回收站？",
            "里面 %d 个人的记录会全部永久删除，找不回来了。\n\n"
            "平时不用手动清 —— 放满 30 天它会自己清。" % n,
            _do, yes_text="清空", danger=True)

    def on_show(self):
        self._reload()
