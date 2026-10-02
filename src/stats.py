# -*- coding: utf-8 -*-
"""
Taku · 真实数据聚合（只读，第 33 轮新增）

★ 为什么要有这个文件：
    在此之前，界面上**所有数字都是写死的示例**（`pages_overview.py` 里
    直接写 "38 条"、"2/3"、"23 个人"），用户看到的第一反应是
    「这数字哪来的？」→ 发现是假的 → 觉得"这软件在骗我"。
    这一层把数字改成**从 data/tuoke.db 真算出来**。

★★★ 数据来源约束（规格书 5.5）—— 本文件必须守住 ★★★
    1. **每个数字都说清来源**（`SOURCES` 里写着呢）
    2. **"量出来的 0" 和 "没得量" 是两回事**，本文件严格区分：
         · 表在、量得出来 → **返回整数（0 也是真数，照实给）**
         · 表不在 / 库读不了 → **返回 None**，界面显示「—」
         · 全新装机（库里一行都没有）→ 数字虽然都是 0，
           但那是"还没开始用"，不是"今天真的没聊" →
           界面靠 `has_any_data=False` 统一显示「—」
       **绝不编示例值**（第 32 轮之前界面上那些 38 条 / 23 个人就是编的，已全撤）
    3. **估算值必须带「约」**
    4. **只读** —— 这个文件里不许出现 INSERT / UPDATE / DELETE

★ 三条红线（项目级）：
    - 不许删 data/tuoke.db 和 data/shots/
    - 不许改数据库已有字段名（只能加）
    - 本文件只读，不写库

用法：
    from stats import Stats
    s = Stats().summary()
    s["new_customers_today"]   # 数字 或 None
"""

import os
import sqlite3
import time
from datetime import datetime, timedelta

# ★ 复用 tt_db 的路径定位（开发态/打包态都对），保证**同一个库**
try:
    from tt_db import DEFAULT_DB
except Exception:                                    # 极端情况下的兜底
    def _root():
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DEFAULT_DB = os.path.join(_root(), "data", "tuoke.db")


# ============================================================
# 每个数字的"来源说明"（规格书 5.5：数字要说清来源）
# 界面上的「这些数字啥意思？」弹层直接念这个表
# ============================================================
SOURCES = {
    "new_customers_today": "来自 customers 表：今天新建的客户档案条数",
    "new_customers_yesterday": "来自 customers 表：昨天新建的客户档案条数（用来算「较昨日」）",
    "replied_today":       "来自 conversations 表：今天 send 方是 AI 的消息条数",
    "replied_yesterday":   "来自 conversations 表：昨天 AI 回的条数（用来算「较昨日」）",
    "goal_new_customers":  "今日新客户目标：读 settings，默认 3 位",
    "greet_left":          "今日打招呼配额 - 今天新开的口（配额读 settings，默认 20）",
    "signals_total":       "来自 customers 表：hit_signals 字段非空的客户数（累计）",
    "funnel":              "来自 customers 表：按 progress(1-5) 落到五级",
    "week_series":         "来自 conversations 表：按天分组统计每天的消息条数",
    "events":              "来自 notifications 表（今天的新通知）+ conversations 表（今天的往来）",
    "online_minutes":      "今天有消息往来的时间跨度（第一条到最后一条）",
}

# 打招呼默认配额（规格书 4.8.1：陌陌 20/天；settings 里可覆盖）
DEFAULT_GREET_QUOTA = 20
QUOTA_SETTING_KEYS = ("quota_greet_momo", "quota_greet", "greet_quota")

# 今日新客户默认目标（settings 里可覆盖）
DEFAULT_NEW_GOAL = 3
GOAL_SETTING_KEYS = ("goal_new_customers", "goal_new", "daily_new_goal")

# 漏斗五级 ← customers.progress 的映射（规格书 4.9 客户 6 级阶段）
FUNNEL_STAGES = [
    ("破冰",   1, "purple"),
    ("深聊",   2, "green"),
    ("加微信", 3, "gold"),
    ("信任",   4, "blue"),
    ("可见面", 5, "red"),
]

# 判定"这条消息是 AI 发的"：tt_db 自检用 'ai'，tt_loop_chat 落库用 'me'
# → 历史遗留不一致，这里两个都认（**不改库里的值**，只做读取兼容）
AI_SENDERS = ("ai", "me")


def _today():
    return time.strftime("%Y-%m-%d")


def _has_table(conn, name):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row is not None


def _pct(part, whole):
    """占比（0~100 的整数）。分母为 0 → None（不显示 0%，那是假的）。"""
    if not whole:
        return None
    return int(round(part * 100.0 / whole))


WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


class Stats:
    """只读聚合器。一次 new，多次 query；用完 close()。"""

    def __init__(self, db_path=None):
        self.db_path = db_path or DEFAULT_DB
        self.db_exists = os.path.exists(self.db_path)
        self.error = ""
        self._conn = None
        if self.db_exists:
            try:
                self._conn = sqlite3.connect("file:%s?mode=ro" % self.db_path.replace("\\", "/"),
                                             uri=True, timeout=5)
                self._conn.row_factory = sqlite3.Row
            except Exception as e:
                self.error = str(e)[:150]
                self._conn = None

    # --------------------------------------------------------
    def close(self):
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def _q(self, sql, args=()):
        """跑一条只读查询；出错返回 []（让上层显示「—」，绝不崩）。"""
        if self._conn is None:
            return []
        try:
            return self._conn.execute(sql, args).fetchall()
        except Exception as e:
            self.error = str(e)[:150]
            return []

    def _one(self, sql, args=()):
        rows = self._q(sql, args)
        return rows[0][0] if rows and rows[0][0] is not None else None

    # ========================================================
    # 总入口：一次把界面要的都算出来
    # ========================================================
    def summary(self, now=None):
        """
        返回一个 dict。**没有数据的项是 None**（界面显示「—」）。

        {
          "ok": True/False,              # 库能不能读
          "why": "",                     # 读不了的原因（人话）
          "db_path": "...", "db_exists": True,
          "generated_at": "2026-10-02 01:40:12",
          "has_any_data": True/False,    # 库里到底有没有"行"（跟"表在不在"是两回事）
          "new_customers_today": 2 / None,
          "replied_today": 38 / None,
          "signals_total": 3 / None,
          "greet_left": 17 / None, "greet_quota": 20, "greet_used": 3,
          "week_series": [..7 个 int..] / None,
          "week_total": 41 / None,
          "week_peak": (42, "周三") / None,
          "funnel": [{"name","num","rate","pct","color"}, ...] / None,
          "events": [{"t","tag","kind","text"}, ...],   # 空列表 = 今天没事发生
          "online_minutes": 372 / None,
        }
        """
        now = now or datetime.now()
        today = now.strftime("%Y-%m-%d")

        out = {
            "ok": self._conn is not None,
            "why": "",
            "db_path": self.db_path,
            "db_exists": self.db_exists,
            "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "has_any_data": False,
            "new_customers_today": None, "new_customers_yesterday": None,
            "replied_today": None, "replied_yesterday": None,
            "signals_total": None,
            "greet_left": None, "greet_quota": DEFAULT_GREET_QUOTA, "greet_used": None,
            "goal_new_customers": DEFAULT_NEW_GOAL,
            "week_series": None, "week_total": None, "week_peak": None,
            "funnel": None,
            "events": [],
            "online_minutes": None,
        }

        if self._conn is None:
            out["why"] = ("读不到数据库（%s）%s"
                          % ("文件不存在" if not self.db_exists else "打开失败",
                             ("：" + self.error) if self.error else ""))
            return out

        has_customers = _has_table(self._conn, "customers")
        has_conv = _has_table(self._conn, "conversations")
        has_notif = _has_table(self._conn, "notifications")

        # ★ "库里有行" 才算真开始用了 —— 表在但一行没有 = 全新装机
        #   （这时数字虽然都是 0，但那是"还没开始用"，界面统一显示「—」）
        rows_n = 0
        for t in ("customers", "conversations", "notifications"):
            if _has_table(self._conn, t):
                n = self._one("SELECT COUNT(*) FROM %s" % t)
                rows_n += int(n or 0)
        out["has_any_data"] = rows_n > 0

        ai_ph = ",".join("?" * len(AI_SENDERS))
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")

        # ---------- ① 今日新客户（附昨日，好算「较昨日」）----------
        if has_customers:
            out["new_customers_today"] = self._one(
                "SELECT COUNT(*) FROM customers WHERE date(created_at)=?", (today,))
            out["new_customers_yesterday"] = self._one(
                "SELECT COUNT(*) FROM customers WHERE date(created_at)=?", (yesterday,))
            out["goal_new_customers"] = self._goal()

        # ---------- ② 今日已回消息 ----------
        if has_conv:
            out["replied_today"] = self._one(
                "SELECT COUNT(*) FROM conversations "
                "WHERE date(sent_at)=? AND sender IN (%s)" % ai_ph,
                (today,) + AI_SENDERS)
            out["replied_yesterday"] = self._one(
                "SELECT COUNT(*) FROM conversations "
                "WHERE date(sent_at)=? AND sender IN (%s)" % ai_ph,
                (yesterday,) + AI_SENDERS)

        # ---------- ③ 命中信号（累计，不是今天） ----------
        if has_customers:
            out["signals_total"] = self._one(
                "SELECT COUNT(*) FROM customers "
                "WHERE COALESCE(hit_signals,'')<>''")

        # ---------- ④ 打招呼剩余 ----------
        if has_conv:
            quota = self._greet_quota()
            out["greet_quota"] = quota
            # "今天新开的口" = 今天第一次给某客户发消息的客户数
            used = self._one(
                "SELECT COUNT(DISTINCT customer_id) FROM conversations "
                "WHERE date(sent_at)=? AND sender IN (%s) AND customer_id NOT IN ("
                "  SELECT DISTINCT customer_id FROM conversations "
                "  WHERE date(sent_at)<? AND sender IN (%s))" % (ai_ph, ai_ph),
                (today,) + AI_SENDERS + (today,) + AI_SENDERS)
            out["greet_used"] = used if used is not None else None
            if used is not None:
                out["greet_left"] = max(0, quota - used)

        # ---------- ⑤ 近 7 天消息量 ----------
        if has_conv:
            days = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
            series = []
            for d in days:
                n = self._one(
                    "SELECT COUNT(*) FROM conversations WHERE date(sent_at)=?", (d,))
                series.append(int(n or 0))
            # ★ 表在就照实给（全 0 也是真读数）；"要不要显示"由界面按 has_any_data 决定
            out["week_series"] = series
            out["week_total"] = sum(series)
            mx = max(series)
            if mx > 0:
                idx = series.index(mx)
                out["week_peak"] = (
                    mx, WEEKDAY_CN[datetime.strptime(days[idx], "%Y-%m-%d").weekday()])

        # ---------- ⑥ 转化漏斗（按 progress 落五级） ----------
        if has_customers:
            rows = self._q("SELECT progress, COUNT(*) n FROM customers "
                           "GROUP BY COALESCE(progress,1)")
            bucket = {}
            for r in rows:
                try:
                    bucket[int(r["progress"] or 1)] = int(r["n"])
                except Exception:
                    pass
            total = sum(bucket.values())
            if total:
                funnel = []
                for i, (name, lvl, color) in enumerate(FUNNEL_STAGES):
                    num = sum(n for p, n in bucket.items() if p >= lvl)
                    pct = _pct(num, total)
                    funnel.append({
                        "name": name, "num": num,
                        "pct": pct if pct is not None else 0,
                        "rate": ("%d%%" % pct) if pct is not None else "—",
                        "color": color,
                    })
                out["funnel"] = funnel

        # ---------- ⑦ 今日事件流 ----------
        out["events"] = self._events(today, has_conv, has_notif, ai_ph)

        # ---------- ⑧ 今日在线时长（有往来的时间跨度） ----------
        if has_conv:
            span = self._q(
                "SELECT MIN(sent_at) a, MAX(sent_at) b FROM conversations "
                "WHERE date(sent_at)=?", (today,))
            if span and span[0]["a"] and span[0]["b"]:
                try:
                    a = datetime.strptime(span[0]["a"][:19], "%Y-%m-%d %H:%M:%S")
                    b = datetime.strptime(span[0]["b"][:19], "%Y-%m-%d %H:%M:%S")
                    out["online_minutes"] = int((b - a).total_seconds() // 60)
                except Exception:
                    pass

        return out

    # --------------------------------------------------------
    def _greet_quota(self):
        if not _has_table(self._conn, "settings"):
            return DEFAULT_GREET_QUOTA
        for k in QUOTA_SETTING_KEYS:
            v = self._one("SELECT value FROM settings WHERE key=?", (k,))
            if v:
                try:
                    return int(float(v))
                except Exception:
                    pass
        return DEFAULT_GREET_QUOTA

    def _goal(self):
        """今日新客户目标（settings 可覆盖，默认 3）。"""
        if not _has_table(self._conn, "settings"):
            return DEFAULT_NEW_GOAL
        for k in GOAL_SETTING_KEYS:
            v = self._one("SELECT value FROM settings WHERE key=?", (k,))
            if v:
                try:
                    return int(float(v))
                except Exception:
                    pass
        return DEFAULT_NEW_GOAL

    def _events(self, today, has_conv, has_notif, ai_ph, limit=12):
        """今天发生的事：往来的消息 + 平台通知。时间倒序。"""
        items = []

        if has_conv:
            rows = self._q(
                "SELECT c.sent_at t, c.sender, c.content, c.verified, "
                "       COALESCE(cu.nickname, cu.account_id, '未知') who "
                "FROM conversations c LEFT JOIN customers cu ON cu.id=c.customer_id "
                "WHERE date(c.sent_at)=? ORDER BY c.id DESC LIMIT ?", (today, limit))
            for r in rows:
                who = r["who"]
                is_ai = (r["sender"] in AI_SENDERS)
                content = (r["content"] or "").strip().replace("\n", " ")
                if len(content) > 34:
                    content = content[:34] + "…"
                if is_ai:
                    tag = "已回复" if r["verified"] else "发过"
                    kind = "ok" if r["verified"] else "warn"
                    text = "回复「%s」——%s" % (who, content or "（空）")
                else:
                    tag, kind = "收到", "info"
                    text = "「%s」说：%s" % (who, content or "（空）")
                items.append({"t": (r["t"] or "")[11:16], "tag": tag,
                              "kind": kind, "text": text})

        if has_notif:
            rows = self._q(
                "SELECT created_at t, platform, title, text FROM notifications "
                "WHERE date(created_at)=? ORDER BY id DESC LIMIT ?", (today, limit))
            for r in rows:
                pkg = (r["platform"] or "").split(".")[-1] or "手机"
                txt = (r["text"] or "").strip() or ("%s 来了新通知" % pkg)
                items.append({"t": (r["t"] or "")[11:16], "tag": "系统",
                              "kind": "info", "text": txt})

        items.sort(key=lambda x: x["t"], reverse=True)
        return items[:limit]

    # ========================================================
    # ⑧ 客户列表 / 往来记录（第 34 轮：客户页接真库）
    # ========================================================
    def customers(self, include_closed=False):
        """
        客户列表。**按最近动静倒序**（聊天工具的习惯：有动静的排前面）。

        返回 list[dict]（每个字段照 customers 表来，另加两列算出来的）：
            id / platform / nickname / account_id / distance / progress /
            summary / personal_info / hit_signals / next_topic / status /
            last_msg_time / created_at
            + last_content（最后一句说了啥，列表预览用）
            + last_at    （最后一次动静的时间，排序/显示时间用）

        ★ 返回 None 表示**读不到**（表不在 / 库打不开）→ 界面要说"读不到"；
          返回 [] 表示**真的一个客户都没有** → 界面要显示空态引导语。
          这两个在界面上长得不一样，别混。
        """
        if self._conn is None or not _has_table(self._conn, "customers"):
            return None
        sql = "SELECT * FROM customers"
        if not include_closed:
            sql += " WHERE COALESCE(status,'active')<>'closed'"
        sql += " ORDER BY COALESCE(last_msg_time, created_at) DESC, id DESC"
        out = []
        for r in self._q(sql):
            out.append({k: r[k] for k in r.keys()})

        # 每条挂上"最后一句" —— 一次查完，别在循环里查（N+1）
        last = {}
        if _has_table(self._conn, "conversations"):
            # ★ 第 42 轮：把最后一句的**说话人**也带上（last_sender）——
            #   消息页要靠它判断"谁最后开口"：他最后说的 = 待处理；
            #   我这边最后回的 = 已回复。
            for r in self._q("SELECT customer_id, content, sent_at, sender FROM conversations "
                             "WHERE id IN (SELECT MAX(id) FROM conversations "
                             "             GROUP BY customer_id)"):
                last[int(r["customer_id"])] = r
        for d in out:
            lr = last.get(int(d["id"]))
            d["last_content"] = (lr["content"] if lr else "") or ""
            d["last_at"] = ((lr["sent_at"] if lr else "") or d.get("last_msg_time") or "")
            d["last_sender"] = ((lr["sender"] if lr else "") or "")

        # ★ 顺手标一句"这个客户有没有对话记录" —— 界面据此决定中栏显示聊天还是空态
        d_has = {}
        if _has_table(self._conn, "conversations"):
            for r in self._q("SELECT customer_id, COUNT(*) n FROM conversations "
                             "GROUP BY customer_id"):
                d_has[int(r["customer_id"])] = int(r["n"] or 0)
        for d in out:
            d["msg_count"] = d_has.get(int(d["id"]), 0)
        return out

    # ---- 某个客户的往来 ----
    def platform_new(self, days=7):
        """
        近 N 天各平台的**新客户数**（第 42 轮新增）。

        返回 dict：{'momo': 3, 'wechat': 1}（没客人的平台不出现）；
        读不到库 → None。
        ★ 为什么要有它：统计页原来那个"陌陌 14 / Soul 6 / 微信 3"
          是**写死的假数字** —— 真库里只有微信 1 位。假数字比没数字更毒。
        """
        if self._conn is None or not _has_table(self._conn, "customers"):
            return None
        rows = self._q(
            "SELECT platform, COUNT(*) n FROM customers "
            "WHERE date(created_at) >= date('now','-%d days') GROUP BY platform"
            % max(0, days - 1))
        return {r["platform"]: int(r["n"] or 0) for r in rows}

    def hourly_activity(self, days=30):
        """
        近 N 天的往来消息，按每 2 小时一档分成 12 档（第 42 轮新增）。

        返回 list[int]（12 个数），读不到库 → None。
        ★ 统计页那张热力图原来是用一行"模拟强度"硬画的 —— 全亮全是假的。
          现在喂真的：没数据就是全暗 + 空态说明。
        """
        if self._conn is None or not _has_table(self._conn, "conversations"):
            return None
        out = [0] * 12
        rows = self._q(
            "SELECT strftime('%%H', sent_at) hh, COUNT(*) n FROM conversations "
            "WHERE date(sent_at) >= date('now','-%d days') "
            "GROUP BY hh" % max(0, days - 1))
        for r in rows:
            try:
                out[int(r["hh"]) // 2] += int(r["n"] or 0)
            except Exception:
                pass
        return out

    def today_counts(self):
        """
        今天一天的真实往来：{'his': 2, 'mine': 1}（第 42 轮新增）。
        周报复盘要用真话 —— 数据不够就说不够，不编 41%。
        """
        if self._conn is None or not _has_table(self._conn, "conversations"):
            return None
        his = self._one(
            "SELECT COUNT(*) n FROM conversations "
            "WHERE date(sent_at)=? AND sender='other'", (_today(),))
        mine = self._one(
            "SELECT COUNT(*) n FROM conversations "
            "WHERE date(sent_at)=? AND sender IN ('ai','me','user')", (_today(),))
        return {"his": int(his or 0), "mine": int(mine or 0)}

    def messages(self, customer_id, limit=200):
        """
        某个客户的往来，**按时间正序**（聊天区是从上往下读的，正序才顺手）。

        返回 list[dict]：id / customer_id / sender / content /
                        strategy_note / sent_at / verified
        sender 取值：ai（我这边发的）/ other（对方）/ user（人工接管时发的）
        ★ 返回 None = 读不到；[] = 这个客户确实还没聊过。
        """
        if self._conn is None or not _has_table(self._conn, "conversations"):
            return None
        rows = self._q("SELECT id, customer_id, sender, content, strategy_note, "
                       "       sent_at, verified FROM conversations "
                       "WHERE customer_id=? ORDER BY id DESC LIMIT ?",
                       (customer_id, limit))
        return [{k: r[k] for k in r.keys()} for r in reversed(rows)]

    # ---- 同名的会不会是同一个人（跨平台同人识别的第一级线索）----
    def customers_same_nickname(self, nickname):
        """同名客户（跨平台）。返回 list[dict]；没有 → []。

        ★ 这**不是**判定"就是同一个人"，只是把线索摆出来给人看。
          真正的合并要三级证据（规格书 4.11），别在这里替人下结论。
        """
        if self._conn is None or not _has_table(self._conn, "customers") or not nickname:
            return []
        rows = self._q("SELECT id, platform, nickname, account_id FROM customers "
                       "WHERE nickname=? ORDER BY id", (nickname,))
        return [{k: r[k] for k in r.keys()} for r in rows]


def summary(db_path=None):
    """便捷函数：算一次就关。"""
    s = Stats(db_path)
    try:
        return s.summary()
    finally:
        s.close()


# ============================================================
# 自检（python src/stats.py）
# ============================================================
def self_test():
    import tempfile
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from tt_db import TuokeDB

    tmp = os.path.join(tempfile.gettempdir(), "tt_stats_selftest.db")
    if os.path.exists(tmp):
        os.remove(tmp)

    # ---- ① 空库（连表都没有）→ 一律 None，不许伪造 ----
    sqlite3.connect(tmp).close()
    s = Stats(tmp).summary()
    assert s["ok"] is True, s
    assert s["has_any_data"] is False
    assert s["new_customers_today"] is None, s["new_customers_today"]
    assert s["replied_today"] is None, s["replied_today"]
    assert s["signals_total"] is None
    assert s["greet_left"] is None
    assert s["week_series"] is None
    assert s["funnel"] is None
    assert s["events"] == []
    #   ★ 连接要显式关：Windows 上只要还有一个句柄开着，后面 os.remove 就会报 WinError 32
    _s0 = Stats(tmp)
    assert _s0.customers() is None, "表都没有 → 必须返回 None（界面说『读不到』），不是 []"
    _s0.close()
    print("① 空库 → 全部「—」  ✓")

    # ---- ①b 全新装机（表在、一行没有）→ 数字是 0 但 has_any_data=False ----
    db0 = TuokeDB(tmp)
    _s1 = Stats(tmp)
    s = _s1.summary()
    assert _s1.customers() == [], "表在、一行没有 → 空列表（界面显示空态引导语），不是 None"
    _s1.close()
    assert s["has_any_data"] is False, s["has_any_data"]
    assert s["new_customers_today"] == 0, s["new_customers_today"]
    assert s["week_series"] == [0] * 7, s["week_series"]
    assert s["funnel"] is None, s["funnel"]
    print("①b 全新装机 → 量得到 0，但 has_any_data=False（界面显示「—」）  ✓")
    # 后面要在同一个库里造数据
    #   ★ 必须**显式 close**：`del` 只是减引用，而 sqlite3 连接带引用环，
    #     要等一次 GC 才真正放手 —— Windows 上句柄不放，最后就删不掉临时库
    #     （症状是 `PermissionError: [WinError 32] 另一个程序正在使用此文件`）。
    db0.conn.close()
    del db0

    # ---- ② 造真数据（走正式的数据层，不手写 SQL）----
    db = TuokeDB(tmp)
    today = _today()
    c1 = db.upsert_customer("momo", "小鹿", summary="破冰期", hit_signals="聊到健身",
                            progress=3)
    c2 = db.upsert_customer("soul", "测试用户A", progress=5)
    c3 = db.upsert_customer("momo", "测试用户B", progress=2)
    db.add_message(c1, "other", "在吗 你是哪里人啊", verified=1)
    db.add_message(c1, "ai", "我大理的，你呢？", verified=1)
    db.add_message(c1, "me", "周末去健身了吗", verified=1)   # 历史遗留写法
    db.add_message(c2, "other", "照片拍得真好")
    db.dedupe_notification("com.immomo.momo", "n1", "", "")
    db.conn.commit()

    st = Stats(tmp)
    s = st.summary()
    assert s["ok"] and s["has_any_data"], s
    assert s["new_customers_today"] == 3, s["new_customers_today"]
    assert s["replied_today"] == 2, s["replied_today"]         # ai + me 都算
    assert s["signals_total"] == 1, s["signals_total"]
    assert s["greet_used"] == 1 and s["greet_left"] == 19, (s["greet_used"], s["greet_left"])
    assert s["week_series"][-1] == 4, s["week_series"]
    assert s["week_total"] == 4 and s["week_peak"][0] == 4, s["week_peak"]
    f = s["funnel"]
    # c1=3级 / c2=5级 / c3=2级 → 破冰3 深聊3 加微信2 信任1 可见面1
    assert [x["num"] for x in f] == [3, 3, 2, 1, 1], [x["num"] for x in f]
    assert f[0]["rate"] == "100%" and f[4]["rate"] == "33%", [x["rate"] for x in f]
    assert len(s["events"]) == 5, len(s["events"])           # 4 条消息 + 1 条通知
    print("② 造数据 → 数字全对  ✓  ", {
        k: s[k] for k in ("new_customers_today", "replied_today",
                          "signals_total", "greet_left", "week_total")})

    # ---- ②b 客户列表 / 往来（客户页接真库要用的两个查询）----
    cl = st.customers()
    assert cl is not None and len(cl) == 3, cl
    assert {d["id"] for d in cl} == {c1, c2, c3}, [d["id"] for d in cl]
    by_id = {d["id"]: d for d in cl}
    assert by_id[c1]["msg_count"] == 3, by_id[c1]["msg_count"]
    assert by_id[c1]["last_content"] == "周末去健身了吗", by_id[c1]["last_content"]
    assert by_id[c2]["last_content"] == "照片拍得真好", by_id[c2]["last_content"]
    assert by_id[c3]["msg_count"] == 0 and by_id[c3]["last_content"] == ""
    # ★ 排序只验"契约"，不验"谁排第一"：时间戳是**秒级**的，
    #   自检里这几步全在同一秒内跑完 → 谁第一纯看运气，硬断言等于在测运气。
    keys = [(d["last_at"] or d["created_at"] or "", int(d["id"])) for d in cl]
    assert keys == sorted(keys, reverse=True), "客户列表没按『最近动静』倒序：%s" % keys
    ms = st.messages(c1)
    assert [m["content"] for m in ms] == ["在吗 你是哪里人啊", "我大理的，你呢？",
                                          "周末去健身了吗"], ms
    assert [m["sender"] for m in ms] == ["other", "ai", "me"], ms
    assert st.messages(999999) == []                    # 没聊过的客户 → 空，不是 None
    assert [d["id"] for d in st.customers_same_nickname("小鹿")] == [c1]
    assert st.customers_same_nickname("") == []
    print("②b 客户列表 / 往来只读查询  ✓  ",
          {d["id"]: d["msg_count"] for d in cl})

    # ---- ③ 只读性：这个模块**只允许读库** ----
    #   只看 self_test 之前的正文（自检代码自己要写临时库造数据，不算）
    raw = open(os.path.abspath(__file__), encoding="utf-8").read()
    body = raw.split("def self_test")[0].upper()
    # 把文档里那句"不许出现 A/B/C"本身摘掉，免得检查到自己
    body = body.replace("不许出现 INSERT / UPDATE / DELETE", "")
    for bad in ("INSERT", "UPDATE", "DELETE", "DROP", "REPLACE INTO"):
        assert bad not in body, "正文里出现了写库语句：%s" % bad
    print("③ 只读性（正文无写入语句）  ✓")

    st.close()
    db.conn.close()
    import gc
    gc.collect()          # 兜一层：万一还有连接环没散，删文件前先催一次
    os.remove(tmp)
    print("SELF_TEST_OK  全部通过")


if __name__ == "__main__":
    self_test()
