# -*- coding: utf-8 -*-
"""
Taku · 数据仓库（store）

★★★ 这个文件是"软件像个样子"和"软件真能用"之间的那道坎 ★★★

★ 为什么必须要有它（用户的实测反馈）：
    原来界面上所有数据都是**写死在代码里的常量**：
        CUSTOMERS = [ {...}, {...} ]      # 客户列表
        TRASH     = [ {...} ]             # 回收站
    于是"删除"只能这么写：
        row_widget.setParent(None)        # 把界面上那一行拿掉
    **界面变了，数据没变。**
    用户点删除 → 那行消失了 → **切个页面回来，它又在** → "根本删不掉"。
    用户的评价是：「只是它像个样子，但实际上没有任何功能。」

★ 现在怎么办：
    所有数据集中到这里。界面只跟它打交道，**任何操作都真的改变数据**，
    改完发一个信号，界面自己重画。切页、刷新、重开软件 —— 都还是改完的样子。

★ 存哪儿：
    data/store.json（跟软件放一起，用户能自己看到、能备份）
    ★ 不用数据库：这一阶段数据量小，JSON 够用，而且**用户能打开看**，
      出问题一眼就明白。等数据量真大了再换 sqlite，界面一行都不用改。

★ 怎么用：
    from ui.store import get_store
    st = get_store()
    st.changed.connect(self._reload)      # 数据变了就重画
    for c in st.customers(): ...          # 读
    st.delete_customer(cid)               # 改（真的改）
"""

import json
import os
import time
import uuid

from PySide6.QtCore import QObject, Signal


# ============================================================
# 示例数据（★ 第 34 轮：不再自动塞给用户了）
#
# ★ 为什么改成"不自动塞"：
#    用户的原话是：「这些都是假客户」。他打开软件看到 5 个不认识的
#    客户，第一反应就是"这软件是假的"。
#    → 现在**默认空着**，走空态引导（"点左边的『拓客』开始找人"）。
#    → 想先试试功能，可以在客户页空态里点一下「放 3 个示例进来试试」，
#      明确知道那是示例，而且**随时能删**（走的是同一套删除逻辑）。
# ============================================================
def _sample_customers():
    """3 个示例客户（只在用户**主动点**的时候才放进来）。"""
    return [
        {"id": "s1", "name": "山间微风", "src": "陌陌", "stage": "已回聊",
         "heat": 72, "familiar": "中等", "last": "你平时都干嘛呀",
         "tm": "09:41", "unread": 2, "avatar": "山",
         "note": "示例客户：聊得挺自然，节奏可以再慢一点。", "hot": False,
         "_sample": True},
        {"id": "s2", "name": "爱健身的小周", "src": "Soul", "stage": "深聊",
         "heat": 81, "familiar": "较高", "last": "大理的风好舒服",
         "tm": "09:32", "unread": 0, "avatar": "周",
         "note": "示例客户：距离 320km。喜欢逛吃逛吃。热度 81，快到可以提见面的线了。",
         "hot": True, "_sample": True},
        {"id": "s3", "name": "悠悠", "src": "陌陌", "stage": "命中信号",
         "heat": 76, "familiar": "中等", "last": "要不加个微信？",
         "tm": "09:38", "unread": 1, "avatar": "悠",
         "note": "示例客户：对方主动提微信 —— 高意向，建议顺势交换。",
         "hot": True, "_sample": True},
    ]


def _seed_customers():
    """首启默认：**空**（不塞假客户）。"""
    return []


def _seed_trash():
    return []


def _seed_messages():
    return []


class Store(QObject):
    """数据仓库。全软件就一个（见下面的 get_store）。"""

    changed = Signal(str)      # 哪一类变了：customers / trash / messages / all

    def __init__(self, path=None):
        super().__init__()
        self._path = path or self._default_path()
        self._d = {}
        self._migrate_old_path()
        self.load()

    # --------------------------------------------------------
    # 文件路径
    # --------------------------------------------------------
    @staticmethod
    def _default_path():
        """
        ★ 第 34 轮修：原来这里少算了一级目录，store.json 落到了 `src/data/`，
          而用户的数据、备份都在项目根的 `data/` —— 两处分家，用户根本找不到。
          现在统一问 paths.project_root()。
        """
        try:
            from ui.paths import data_dir
            root = data_dir()
        except Exception:
            root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
            try:
                os.makedirs(root, exist_ok=True)
            except Exception:
                pass
        return os.path.join(root, "store.json")

    def _migrate_old_path(self):
        """
        把**老位置**（src/data/store.json）的数据搬到正确位置。
        ★ 只搬一次：新位置有文件就不动；老位置没有就算了。
          用户之前删掉的客户、加过的备注，不能因为改路径就丢。
        """
        import shutil
        try:
            old = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "store.json")
            old = os.path.abspath(old)
            if os.path.abspath(self._path) == old:
                return
            if os.path.exists(old) and not os.path.exists(self._path):
                os.makedirs(os.path.dirname(self._path), exist_ok=True)
                shutil.copy2(old, self._path)
        except Exception:
            pass

    # --------------------------------------------------------
    # 读写
    # --------------------------------------------------------
    def load(self):
        if os.path.exists(self._path):
            try:
                with open(self._path, encoding="utf-8") as f:
                    self._d = json.load(f)
            except Exception:
                self._d = {}
        if not self._d:
            self._d = {
                "customers": _seed_customers(),
                "trash": _seed_trash(),
                "messages": _seed_messages(),
                "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            self.save()

    def save(self):
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._d, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def reset(self):
        """变回示例数据（设置页里给个"恢复示例数据"用）。"""
        try:
            if os.path.exists(self._path):
                os.remove(self._path)
        except Exception:
            pass
        self._d = {}
        self.load()
        self.changed.emit("all")

    def path(self):
        return self._path

    # ========================================================
    # ★★ 从数据库"播种"（第 33 轮）
    #
    #   ★ 为什么要这么绕：
    #     客户数据的真实源头是 data/tuoke.db。但那个库是**只读**打开的
    #     （stats.py 故意的，防界面误改）。界面要能删能改，就必须有一个
    #     **可写的副本**。
    #   ★ 做法：
    #     第一次读库的时候，把库里那批客户**复制一份**进 store。
    #     以后界面只跟 store 打交道 —— 读、删、改，全是真的。
    #     等以后真正接管数据层，把这里换成"写回库里"就行。
    # ========================================================
    def seed_from_db(self, rows):
        if not rows:
            return
        if self._d.get("seeded"):
            return                       # 已经播过种了，别再覆盖用户的改动

        out = []
        for r in rows:
            d = dict(r)
            if not d.get("id"):
                d["id"] = uuid.uuid4().hex[:8]
            out.append(d)

        self._d["customers"] = out
        self._d["seeded"] = True
        self.save()

    def has_data(self):
        return bool(self._d.get("customers")) or bool(self._d.get("seeded"))

    # --------------------------------------------------------
    # 客户
    # --------------------------------------------------------
    def customers(self):
        return list(self._d.get("customers", []))

    def get_customer(self, cid):
        """
        按 id 找客户。

        ★ 第 34 轮修：改成**按字符串比**（理由同 update_customer）。
        """
        t = "" if cid is None else str(cid)
        for c in self._d.get("customers", []):
            v = c.get("id")
            if ("" if v is None else str(v)) == t:
                return c
        return None

    def find_by_name(self, name):
        for c in self._d.get("customers", []):
            if c.get("name") == name:
                return c
        return None

    def add_samples(self):
        """
        放几个示例客户进来（用户在空态里**主动点**才会走这里）。

        ★ 和以前"偷偷塞"的区别：
          这些是**明确的示例**（每条带 `_sample: True`），
          而且走的是同一套删除逻辑 —— 想删就删，删了不会回来。
        """
        arr = self._d.setdefault("customers", [])
        have = {c.get("id") for c in arr}
        n = 0
        for c in _sample_customers():
            if c["id"] not in have:
                arr.append(dict(c))
                n += 1
        self._d["seeded"] = True
        self.save()
        self.changed.emit("customers")
        return n

    def count_samples(self):
        return sum(1 for c in self._d.get("customers", []) if c.get("_sample"))

    def update_customer(self, cid, **kw):
        """
        改客户身上某个字段。

        ★ 第 34 轮修：**按字符串比 id**。
          库里的 id 是整数、界面上传过来的可能是字符串，
          原来用 `==` 直接比，一个 int 一个 str 就永远匹配不上，
          "保存备注"会静默失败（用户看到的是"存了"，其实没存进去）。
          （同 delete_customer 的老坑 24。）
        """
        c = self.get_customer(cid)
        if c is None:
            return False
        c.update(kw)
        self.save()
        self.changed.emit("customers")
        return True

    def delete_customer(self, cid, to_trash=True, why="你自己删的", row=None):
        """
        删客户。

        ★ 规矩（规格书 4.9.3）：**默认是"扔进回收站"，不是真删**。
          用户说"删除"时，多数时候意思是"我不想再看到她了"，
          而不是"把记录抹掉"。给他留个 30 天的后悔期。

        ★ 第 35 轮重写（配合作"库为正文 + store 叠加"的新合并规则）：
          现在客户有两种来路 ——
            · 库里的人（AI 聊到的 / 手动加的）：**不在 store 的列表里**，
              删除 = 记进 `hidden` 名单，合并时被过滤掉（不然切个页就复活）
            · store 自己的行（示例客户）：从列表里真删掉
          两种都进回收站。`row` 是界面上那一行的原始数据，
          库里的人 store 这边没有他的资料，靠它写回收站的"是谁"。

        ★ 按编号删时**要把所有同号的都删掉**（老坑 24：重复编号时"删了还在"）。
        """
        target = "" if cid is None else str(cid)
        if not target:
            return False

        # ① store 自己列表里的（有就删，没有也不算失败）
        arr = self._d.get("customers", [])
        keep, gone = [], []
        for x in arr:
            if ("" if x.get("id") is None else str(x.get("id"))) == target:
                gone.append(x)
            else:
                keep.append(x)
        self._d["customers"] = keep

        # ② 记进"藏起来"名单 —— 库里那行也会被过滤掉（删了不复活的关键）
        hid = self._d.setdefault("hidden", [])
        already = target in [str(x) for x in hid]
        if not already:
            hid.append(target)

        # 两种都没动静（本来就没有、也已经藏了）→ 照实说没删
        if not gone and already:
            return False

        # ③ 进回收站（谁、哪个平台、为什么）
        if to_trash:
            src_row = gone[0] if gone else (row or {})
            self._d.setdefault("trash", []).insert(0, {
                "id": (gone[0].get("id") if gone else None) or target,
                "name": (src_row.get("name") or src_row.get("nickname") or "?"),
                "src": (src_row.get("src") or src_row.get("platform") or "—"),
                "why": why,
                "tm": time.strftime("%m-%d"),
                "_raw": src_row or None,       # 捞回来时原样还给他
            })
            self.changed.emit("trash")
        self.save()
        self.changed.emit("customers")
        return True

    # --------------------------------------------------------
    # 回收站
    # --------------------------------------------------------
    def trash(self):
        return list(self._d.get("trash", []))

    def restore(self, tid):
        """捞回来 —— 真的放回客户列表。"""
        arr = self._d.get("trash", [])
        item = None
        for i, x in enumerate(arr):
            if x.get("id") == tid:
                item = arr.pop(i)
                break
        if item is None:
            return False

        raw = item.get("_raw")
        if raw:
            raw.pop("_trashed", None)
            self._d.setdefault("customers", []).insert(0, raw)
        # ★ 第 35 轮：捞回来 = 同时从"藏起来"名单里放出来，
        #   否则合并的时候它还是被过滤的，捞了也白捞。
        try:
            self.unhide(item.get("id"))
        except Exception:
            pass
        self.save()
        self.changed.emit("trash")
        self.changed.emit("customers")
        return True

    def purge(self, tid):
        """永久删 —— 真没了，捞不回来。"""
        arr = self._d.get("trash", [])
        for i, x in enumerate(arr):
            if x.get("id") == tid:
                arr.pop(i)
                self.save()
                self.changed.emit("trash")
                return True
        return False

    def empty_trash(self):
        n = len(self._d.get("trash", []))
        self._d["trash"] = []
        self.save()
        self.changed.emit("trash")
        return n

    # --------------------------------------------------------
    # 消息
    # --------------------------------------------------------
    def messages(self):
        return list(self._d.get("messages", []))

    def mark_read(self, mid):
        for m in self._d.get("messages", []):
            if m.get("id") == mid:
                m["tag"] = "已回复"
                m["unread"] = 0
                self.save()
                self.changed.emit("messages")
                return True
        return False

    def add_message(self, name, src, tx, tag="待处理"):
        self._d.setdefault("messages", []).insert(0, {
            "id": uuid.uuid4().hex[:8],
            "name": name, "src": src, "tx": tx,
            "tm": time.strftime("%H:%M"), "tag": tag,
        })
        self.save()
        self.changed.emit("messages")

    # --------------------------------------------------------
    # 通用设置（键值对）
    #
    # ★ 第 34 轮加：设置页里的开关、人设、上次备份时间这些，
    #   原来点了只弹一句提示就没了 —— 重开软件全忘光。
    #   现在**真的写进数据**，切页 / 重开都还在。
    # --------------------------------------------------------
    def settings(self):
        return dict(self._d.get("settings", {}))

    def get_setting(self, key, default=None):
        return self._d.get("settings", {}).get(key, default)

    def set_setting(self, key, value):
        self._d.setdefault("settings", {})[key] = value
        self.save()
        self.changed.emit("settings")
        return True

    # --------------------------------------------------------
    # 排队任务（认路 / 让她聊 / 学习）
    #
    # ★ 第 34 轮加：技能库「现在就去学」、拓客「让她聊」这些
    #   原来只是弹一句提示。现在真写进队列，界面能看到"排队中"。
    # --------------------------------------------------------
    def queue_task(self, kind, title, note=""):
        q = self._d.setdefault("queue", [])
        item = {
            "id": uuid.uuid4().hex[:8],
            "kind": kind, "title": title, "note": note,
            "at": time.strftime("%m-%d %H:%M"),
            "state": "排队中",
        }
        q.insert(0, item)
        self._d["queue"] = q[:50]
        self.save()
        self.changed.emit("queue")
        return item

    def queue(self):
        return list(self._d.get("queue", []))

    def clear_queue(self):
        self._d["queue"] = []
        self.save()
        self.changed.emit("queue")
        return True

    # ========================================================
    # ★★★ 隐藏 / 覆盖层（第 33 轮加，修"删不掉"的核心）
    #
    #   ★ 为什么不能直接删 DB 里的行：
    #     客户数据的**源头是 data/tuoke.db**，而 stats.py 用的是
    #     `mode=ro`（只读）打开的 —— 这是故意的，防界面误改数据。
    #     所以界面上的"删除"根本无处可删，只能把那一行从界面上抹掉，
    #     切个页面它就回来了。用户的原话："删除按钮可以摁进去，
    #     但他们根本删除不了。"
    #
    #   ★ 修法（叠加层，不动 DB）：
    #     把"用户删掉的 id"和"用户改过的字段"记在这里。
    #     读数据时过滤掉隐藏的、覆盖掉改过的。
    #     → 删了就是删了，改了就变了，**重开软件也还在**。
    #     → 以后真正接管数据时，把这一层提升成"真实写入"即可。
    # ========================================================
    def hidden_ids(self):
        return set(self._d.get("hidden", []))

    def hide(self, cid):
        """把某个客户从界面上"藏掉"（= 用户理解的"删除"）。"""
        if not cid:
            return False
        hid = self._d.setdefault("hidden", [])
        if cid not in hid:
            hid.append(cid)
            self.save()
            self.changed.emit("customers")
        return True

    def unhide(self, cid):
        hid = self._d.setdefault("hidden", [])
        if cid in hid:
            hid.remove(cid)
            self.save()
            self.changed.emit("customers")
            return True
        return False

    def hidden_customers(self):
        """被藏起来的那批（回收站页面从这儿拿，就能真的"捞回来"）。"""
        ids = self.hidden_ids()
        arr = self._d.get("customers", [])
        out = []
        for c in arr:
            if c.get("id") in ids:
                d = dict(c)
                d["_hidden"] = True
                out.append(d)
        return out

    def overrides(self):
        return dict(self._d.get("override", {}))

    def set_override(self, cid, **kw):
        """记住用户改过的字段（备注、阶段、打招呼开关…）。"""
        if not cid:
            return False
        ov = self._d.setdefault("override", {})
        ov.setdefault(cid, {}).update(kw)
        self.save()
        self.changed.emit("customers")
        return True

    # ========================================================
    # ★★ 给 AI 下的指令（第 34 轮）
    #
    #   ★ 原来"约见面""继续深聊"这些按钮点了只弹一句
    #     「已告诉 AI：……」，然后就没了 —— **指令根本没存下来**。
    #     用户的原话："只是它像个样子，但实际上没有任何功能。"
    #   ★ 现在：指令**真的写进数据**，界面能看到、能撤销，
    #     AI 那一轮跑的时候也会读它。（接真机之后 AI 会照做）
    # ========================================================
    ORDERS = {
        "约见面":     ("meet",   "往见面方向带"),
        "继续深聊":   ("deeper", "这个话题接着聊"),
        "晾一会":     ("wait",   "先别回，晾一会儿"),
        "重新生成":   ("regen",  "重新想一句"),
        "标记疑似熟客": ("same",   "去别的平台核对是不是同一个人"),
    }

    def set_order(self, cid, label):
        """给某个客户下一道指令。返回 (ok, 说明)。"""
        if not cid:
            return False, "还没选中客户"
        code, human = self.ORDERS.get(label, (label, label))
        orders = self._d.setdefault("orders", {})
        orders.setdefault(str(cid), [])
        orders[str(cid)].append({
            "code": code, "label": label, "human": human,
            "at": time.strftime("%m-%d %H:%M"),
        })
        # 每个客户最多留 5 条，别越攒越多
        orders[str(cid)] = orders[str(cid)][-5:]
        self.save()
        self.changed.emit("customers")
        return True, human

    def orders(self, cid=None):
        o = self._d.get("orders", {})
        if cid is None:
            return o
        return list(o.get(str(cid), []))

    def clear_orders(self, cid):
        o = self._d.get("orders", {})
        if str(cid) in o:
            o[str(cid)] = []
            self.save()
            self.changed.emit("customers")
            return True
        return False

    def apply_to(self, rows):
        """
        把"隐藏/覆盖"应用到一批客户数据上。
        ★ datasource 每次读完之后都会过一遍这个函数。
        """
        if not rows:
            return rows
        hid = self.hidden_ids()
        ov = self.overrides()
        out = []
        for r in rows:
            cid = r.get("id")
            if cid in hid:
                continue
            r = dict(r)
            if cid in ov:
                r.update(ov[cid])
            out.append(r)
        return out


# ============================================================
# 全软件一个
# ============================================================
_STORE = None


def get_store():
    global _STORE
    if _STORE is None:
        _STORE = Store()
    return _STORE
