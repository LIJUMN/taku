# -*- coding: utf-8 -*-
"""
Taku · 界面 ← 数据（唯一入口，第 33 轮新增）

★ 为什么要有这一层（而不是让每个页面自己去 new 一个 Stats）：
    1. **一处缓存**：切主题会把 9 个页面**全部重建**（第 26 轮定的规矩），
       要是每页都去连库，切一次主题就是 9 次连库。这里加个 3 秒缓存兜住。
    2. **一处兜底**：库读不了 / 模块没装上 —— 页面不该崩，只该显示「—」。
    3. **一处显示规则**：规格书 5.5「无数据显示『—』」这种规矩，
       散在 9 个页面里迟早各写各的 → 统一收在这里。

★ 这个文件**只读**，不许写库。
"""

import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.dirname(_HERE)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# 缓存：切主题重建页面 / 来回切页时，别每次都去连库
TTL = 3.0
_cache = {"t": 0.0, "data": None}
# 客户列表单独一份缓存（它比总览那份重，而且客户页切进切出很频繁）
_ccache = {"t": 0.0, "list": None}


# 读不到数据时的兜底（**不是**示例数据，是空壳 —— 页面会显示「—」）
def _empty(why="还没有数据"):
    return {
        "ok": False, "why": why, "db_path": "", "db_exists": False,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "has_any_data": False,
        "new_customers_today": None, "new_customers_yesterday": None,
        "replied_today": None, "replied_yesterday": None,
        "signals_total": None,
        "greet_left": None, "greet_quota": 20, "greet_used": None,
        "goal_new_customers": 3,
        "week_series": None, "week_total": None, "week_peak": None,
        "funnel": None, "events": [], "online_minutes": None,
    }


def invalidate():
    """让下一次 snapshot() 一定重算（AI 刚干完活时调一下）。"""
    _cache["t"] = 0.0
    _cache["data"] = None
    _ccache["t"] = 0.0
    _ccache["list"] = None


def snapshot(force=False):
    """拿一份数据快照（3 秒内复用）。任何情况都不抛异常。"""
    now = time.time()
    if (not force) and _cache["data"] is not None and (now - _cache["t"]) < TTL:
        return _cache["data"]
    try:
        from stats import summary
        data = summary()
    except Exception as e:                 # 模块缺失 / 库坏了 → 兜底，不崩
        data = _empty("读不到数据模块：%s" % str(e)[:120])
    _cache["t"] = now
    _cache["data"] = data
    return data


# ============================================================
# 客户列表 / 聊天往来（第 34 轮：客户页接真库）
# ------------------------------------------------------------
# ★ 客户页**不许自己连库**（这是第 33 轮定的"唯一入口"），
#   所以客户列表和聊天记录也从这里走。
# ★ 这两个函数**只读**。保存备注是"写"，走 tt_db（数据层），不从这里走 ——
#   一个模块又能读又能写，早晚会有人顺手在这里写库，那一层的边界就没了。
# ============================================================
def customers(force=False):
    """
    客户列表。返回：
        list[dict]  —— 库读得到（可能是空的 []，那就是"真没有客户"）
        None        —— 读不到（库不在 / 表不在 / 模块炸了）

    ★ 为什么要把 [] 和 None 分开：界面上的话不一样 ——
        []   → 空态引导语「还没有客户。点左边的『拓客』开始找人聊天。」
        None → 「读不到数据库」（那是故障，不是"还没开始用"）
    """
    now = time.time()
    if (not force) and _ccache["list"] is not None and (now - _ccache["t"]) < TTL:
        return _ccache["list"]
    data = None
    try:
        from stats import Stats
        st = Stats()
        try:
            data = st.customers()
        finally:
            st.close()
    except Exception:
        data = None

    # ★★★ 让用户的"删/改"真的生效（第 33 轮加，第 35 轮重写合并规则）
    #
    #   ★ 第 35 轮为什么必须重写：
    #     原来的规则是"store 有数据就只读 store"。这有个致命后果——
    #     **一旦 store 播过种，数据库里新出现的客户就再也看不见了**
    #     （AI 在手机上聊到新的人、写进库，界面上也不会出现）。
    #     更糟的是：AI 干完活更新了库里这个人的"最后一句"，界面上还是旧的。
    #
    #   ★ 新规则（谁说了算）：
    #     · **数据库是正文** —— 库里有的行，以库为准（AI 更新了就跟着变）
    #     · **store 只管三件事**：
    #         ① 用户藏掉的人（hidden）→ 过滤掉
    #         ② 用户改过的字段（override：备注/阶段）→ 按字段盖上去
    #         ③ 库里没有的行（示例客户 / 手动加的）→ 补进来
    #     → 这样：删了不复活、改了不丢、AI 写库界面立刻看得见。
    try:
        from ui.store import get_store
        _st = get_store()
        if data:
            _st.seed_from_db(data)             # 播种（只播一次）
        merged = {}
        for r in (data or []):
            merged[str(r.get("id"))] = dict(r)          # 库为正文
        for r in _st.customers():                        # store 独有的行补进来
            k = str(r.get("id"))
            if k not in merged:
                merged[k] = r
        for cid, ov in (_st.overrides() or {}).items():  # 用户改过的字段盖上去
            if cid in merged and isinstance(ov, dict):
                merged[cid].update(ov)
        hid = _st.hidden_ids()
        data = [r for k, r in merged.items() if k not in hid]
    except Exception:
        pass

    _ccache["t"] = now
    _ccache["list"] = data
    return data


def messages(customer_id, limit=200):
    """某个客户的往来（时间正序）。返回 list[dict]；读不到 → None；没聊过 → []。"""
    if not customer_id:
        return None
    try:
        from stats import Stats
        st = Stats()
        try:
            return st.messages(customer_id, limit=limit)
        finally:
            st.close()
    except Exception:
        return None


def same_nickname(nickname):
    """同名客户（跨平台同人识别的线索）。读不到 → []。"""
    if not nickname:
        return []
    try:
        from stats import Stats
        st = Stats()
        try:
            return st.customers_same_nickname(nickname)
        finally:
            st.close()
    except Exception:
        return []


# ============================================================
# 显示规则（第 34 轮新增）—— 全站唯一一份
# ------------------------------------------------------------
# ★ 为什么要把"英文值 → 中文"收在这里：库里的 platform 存的是
#   `momo` / `soul`（当年建表就这规矩，**不许改**），界面上必须显示
#   「陌陌」/「Soul」。要是每个页面各写一份映射，早晚有一页漏了，
#   用户就会在界面上看到 `momo` —— 一眼就是"这软件没做完"。
# ============================================================
PLATFORM_CN = {
    "momo": "陌陌", "momo2": "陌陌",
    "soul": "Soul",
    "wechat": "微信", "weixin": "微信", "wechat_mp": "微信",
}
# 反过来：界面选的平台 → 库里存的值（筛选时要按库里的值查）
PLATFORM_DB = {"陌陌": ("momo",), "Soul": ("soul",), "微信": ("wechat", "weixin")}

# 客户的进度阶段（customers.progress，1-5。规格书 4.9 的六级阶段里第 6 级"已见面"
# 由用户手动标，库里没有对应字段 → 这里只映射 1-5，别自己编）
STAGE_CN = {1: "破冰", 2: "深聊", 3: "加微信", 4: "信任", 5: "可见面"}


def platform_cn(raw):
    """`momo` → 「陌陌」。认不出来的原样显示（不猜，也不写成"未知"）。"""
    if not raw:
        return DASH
    return PLATFORM_CN.get(str(raw).lower(), str(raw))


def stage_cn(progress):
    """progress → 阶段中文。读不出来 → 「—」（不写"破冰"糊弄）。"""
    try:
        return STAGE_CN.get(int(progress), DASH)
    except Exception:
        return DASH


def when(ts):
    """
    消息时间 → 列表上看的短写法（聊天工具的习惯）。

        今天   → 09:41
        昨天   → 昨天
        更早   → 09-28
        空/读不出 → ""
    """
    if not ts:
        return ""
    try:
        d = time.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)[:16]
    n = time.localtime()
    if d[:3] == n[:3]:
        return "%02d:%02d" % (d[3], d[4])
    yd = time.localtime(time.time() - 86400)
    if d[:3] == yd[:3]:
        return "昨天"
    return "%02d-%02d" % (d[1], d[2])


# ============================================================
# 显示规则（规格书 5.5）—— 全站唯一一份
# ============================================================
DASH = "—"


def num(value, s, unit="", has_any_data=None):
    """
    把统计值变成界面上的字符串。

    · 值为 None      → 「—」
    · 库是全新装机    → 「—」（数字虽然是 0，但那是"还没开始用"，
                        写 0 会让人以为"今天真的一条都没聊"）
    · 正常           → "38 条"
    """
    if has_any_data is None:
        has_any_data = bool(s.get("has_any_data"))
    if value is None or not has_any_data:
        return DASH
    return "%s%s" % (value, unit)


def ratio(value, total, has_any_data=None, s=None):
    """百分比（0~100）。算不出来 → None（界面不画进度条）。"""
    if s is not None and has_any_data is None:
        has_any_data = bool(s.get("has_any_data"))
    if has_any_data is False:
        return None
    try:
        if not total:
            return None
        return max(0, min(100, int(round(float(value) * 100.0 / float(total)))))
    except Exception:
        return None


def delta(today, yesterday, unit="条"):
    """
    「较昨日 +12 条」。

    ★ 第 33 轮修了一个会**崩页面**的坑：
      原来"量不到"的时候返回 None。结果总览页这么用：
          delta(...) + ("（目标 3 位）")      # None + str → 直接抛异常
      数据一空，整页就报错 —— 用户看到的就是"点进去动不了"。
      → 现在**永远返回字符串**（量不到就返回空串）。
        空串是 falsy，外面 `delta(...) or DASH` 照样出「—」，行为不变，
        但再也不会崩了。
    """
    if today is None or yesterday is None:
        return ""
    if today == 0 and yesterday == 0:
        return ""
    d = today - yesterday
    if d == 0:
        return "与昨日持平"
    return "较昨日 %s%d %s" % ("+" if d > 0 else "", d, unit)


def source_note(s):
    """给「这些数字啥意思？」弹层用：把来源一条条列出来（规格书 5.5）。"""
    from stats import SOURCES
    lines = []
    if not s.get("ok"):
        return "现在**读不到数据库**：%s" % (s.get("why") or "原因不明")
    if not s.get("has_any_data"):
        return ("数据库是**空的**（一行数据都没有）。\n\n"
                "所以这一页的数字**全部显示「—」** —— "
                "不是 0，是「还没有东西可量」。\n\n"
                "等 AI 真的聊过几轮之后，这里就是真的了。")
    for k in ("new_customers_today", "replied_today", "greet_left",
              "signals_total", "funnel", "week_series", "events"):
        if k in SOURCES:
            lines.append("· **%s** —— %s" % (k, SOURCES[k]))
    lines.append("")
    lines.append("最后更新：%s" % s.get("generated_at", ""))
    return "\n".join(lines)
