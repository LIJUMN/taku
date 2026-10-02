# -*- coding: utf-8 -*-
"""
拓客台 · 数据层（M2 起点）
按《AI社交运营管理台需求文档 v1.0》§22 建表规格实现。
- 版本化迁移：schema_version 表 + 迁移脚本链（启动时按版本顺序执行）
- v1: customers / conversations / settings（V1.0 三张核心表）
- v2: notifications（M2 事件闭环必需：通知去重，PRD 定义为"事件驱动的基础"）
  产品决策（2026-10-02）：通知去重表提前到 M2，其余 operation_log / goals /
  platform_quota / risk_events 仍按 PRD 留待 V1.1 迁移加入。
字段名与 PRD §22 完全一致。
"""
import sqlite3, time, os, sys


def _project_root() -> str:
    """项目根：开发模式=仓库根；打包模式=exe 所在目录（保证 DB 外置）"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _default_db() -> str:
    """
    默认库路径。

    ★ 第 34 轮加了一个开关：环境变量 `TAKU_DB`。
      为什么需要它：客户页"接真库"必须能**在副本上做端到端验证**
      （造几个客户 + 几条对话，看界面是不是真读出来了）。
      在用户真库上造测试数据 = 污染用户资产；所以测试时把库指到临时副本上。
      平时这个变量是空的 → 行为跟以前**完全一样**（外置 data/tuoke.db）。
    """
    env = os.environ.get("TAKU_DB")
    if env:
        return env
    return os.path.join(_project_root(), "data", "tuoke.db")


DEFAULT_DB = _default_db()

MIGRATIONS = {
    1: """
    CREATE TABLE customers (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        platform      TEXT NOT NULL,
        nickname      TEXT,
        account_id    TEXT,
        distance      TEXT,
        progress      INTEGER DEFAULT 1,          -- 1-5 五级进度
        summary       TEXT,
        personal_info TEXT,
        hit_signals   TEXT,
        next_topic    TEXT,
        status        TEXT DEFAULT 'active',      -- active/handover/closed
        last_msg_time TEXT,
        created_at    TEXT NOT NULL
    );
    CREATE TABLE conversations (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id   INTEGER NOT NULL REFERENCES customers(id),
        sender        TEXT NOT NULL,              -- ai / other / user
        content       TEXT NOT NULL,
        strategy_note TEXT,
        sent_at       TEXT NOT NULL,
        verified      INTEGER DEFAULT 0           -- 0/1 是否验证发送成功
    );
    CREATE INDEX idx_conv_customer ON conversations(customer_id, sent_at);
    CREATE TABLE settings (
        key        TEXT PRIMARY KEY,
        value      TEXT,
        updated_at TEXT
    );
    """,
    2: """
    CREATE TABLE notifications (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        platform   TEXT,
        notif_id   TEXT NOT NULL,
        title      TEXT,
        text       TEXT,
        processed  INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        UNIQUE(platform, notif_id)
    );
    """,
}


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


class TuokeDB:
    def __init__(self, path=DEFAULT_DB):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self._migrate()

    def _migrate(self):
        c = self.conn
        c.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
        row = c.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1").fetchone()
        cur = row[0] if row else 0
        for v in sorted(MIGRATIONS):
            if v > cur:
                c.executescript(MIGRATIONS[v])
                c.execute("INSERT INTO schema_version (version) VALUES (?)", (v,))
        c.commit()

    @property
    def version(self):
        return self.conn.execute("SELECT MAX(version) v FROM schema_version").fetchone()["v"]

    # ---- customers ----
    def upsert_customer(self, platform, nickname, account_id=None, distance=None,
                        summary=None, personal_info=None, hit_signals=None,
                        next_topic=None, progress=1, status="active"):
        c = self.conn
        ts = now()
        if account_id:
            row = c.execute("SELECT id FROM customers WHERE platform=? AND account_id=?",
                            (platform, account_id)).fetchone()
        else:
            row = c.execute("SELECT id FROM customers WHERE platform=? AND nickname=?",
                            (platform, nickname)).fetchone()
        if row:
            c.execute("""UPDATE customers SET nickname=?, distance=?, summary=?, personal_info=?,
                         hit_signals=?, next_topic=?, status=?, last_msg_time=?
                         WHERE id=?""",
                      (nickname, distance, summary, personal_info, hit_signals, next_topic,
                       status, ts, row["id"]))
            cid = row["id"]
        else:
            cur = c.execute("""INSERT INTO customers (platform, nickname, account_id, distance,
                               progress, summary, personal_info, hit_signals, next_topic,
                               status, last_msg_time, created_at)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (platform, nickname, account_id, distance, progress, summary,
                             personal_info, hit_signals, next_topic, status, ts, ts))
            cid = cur.lastrowid
        c.commit()
        return cid

    def get_customer(self, cid):
        return self.conn.execute("SELECT * FROM customers WHERE id=?", (cid,)).fetchone()

    def list_customers(self, platform=None, status=None):
        sql, args = "SELECT * FROM customers", []
        conds = []
        if platform:
            conds.append("platform=?"); args.append(platform)
        if status:
            conds.append("status=?"); args.append(status)
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY last_msg_time DESC"
        return self.conn.execute(sql, args).fetchall()

    # ---- 客户档案：备注 / 线索（第 34 轮新增）----
    def save_customer_notes(self, cid, summary=None, hit_signals=None,
                            next_topic=None, personal_info=None):
        """
        只更新**传进来的那几列**，其余一律不动。

        ★ 为什么不用 upsert_customer 存备注（第 34 轮的决定）：
          upsert_customer 是按 `platform + nickname`（或 account_id）找行的，
          界面上保存备注时如果走它，**两个同名客户会被写串**；
          而且它会把没传的字段（distance/status/personal_info…）覆盖成 NULL。
          → 保存备注是"改一行的一部分"，就老老实实按主键 id 改这几列。
        ★ 字段名照抄既有表结构，**没有改任何字段名**（红线 3）。
        """
        fields, args = [], []
        for col, val in (("summary", summary), ("hit_signals", hit_signals),
                         ("next_topic", next_topic), ("personal_info", personal_info)):
            if val is not None:
                fields.append("%s=?" % col)
                args.append(val)
        if not fields:
            return False
        args.append(cid)
        self.conn.execute("UPDATE customers SET %s WHERE id=?" % ", ".join(fields), args)
        self.conn.commit()
        return True

    def save_customer_stage(self, cid, progress):
        """
        改客户的阶段（customers.progress，1-5）。

        ★ 第 35 轮新增（用户一直点不动的「阶段」就靠它）：
          只更新 progress 这一列，**别的一概不动**（红线 3：不改字段名，只改值）。
          第 6 级「已见面」没有对应字段（只能用户手动标，见规格书 4.9.1），
          所以这里只收 1-5。
        """
        try:
            p = int(progress)
        except Exception:
            return False
        if not 1 <= p <= 5:
            return False
        self.conn.execute("UPDATE customers SET progress=? WHERE id=?", (p, cid))
        self.conn.commit()
        return True

    # ---- conversations ----
    def add_message(self, customer_id, sender, content, strategy_note=None, verified=0):
        ts = now()
        cur = self.conn.execute(
            "INSERT INTO conversations (customer_id, sender, content, strategy_note, sent_at, verified) VALUES (?,?,?,?,?,?)",
            (customer_id, sender, content, strategy_note, ts, verified))
        self.conn.execute("UPDATE customers SET last_msg_time=? WHERE id=?", (ts, customer_id))
        self.conn.commit()
        return cur.lastrowid

    def history(self, customer_id, limit=50):
        return self.conn.execute(
            "SELECT * FROM conversations WHERE customer_id=? ORDER BY id DESC LIMIT ?",
            (customer_id, limit)).fetchall()

    # ---- settings ----
    def set_setting(self, key, value):
        self.conn.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, now()))
        self.conn.commit()

    def get_setting(self, key, default=None):
        row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    # ---- notifications（M2 事件闭环）----
    def dedupe_notification(self, platform, notif_id, title, text):
        """返回 True 表示新通知（首次入库）；False 表示重复。"""
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO notifications (platform, notif_id, title, text, created_at) VALUES (?,?,?,?,?)",
            (platform, notif_id, title, text, now()))
        self.conn.commit()
        return cur.rowcount > 0


def self_test():
    import tempfile
    tmp = os.path.join(tempfile.gettempdir(), "tt_db_selftest.db")
    if os.path.exists(tmp):
        os.remove(tmp)
    db = TuokeDB(tmp)
    assert db.version == 2, db.version
    cid = db.upsert_customer("momo", "测试客户A", account_id="acc_1", distance="3km",
                             summary="破冰期", hit_signals="聊到工作")
    assert cid is not None
    cid2 = db.upsert_customer("momo", "测试客户A", account_id="acc_1")  # 同账号 → 更新
    assert cid == cid2
    db.add_message(cid, "other", "你好，你是哪里人？")
    db.add_message(cid, "ai", "我大理的，你呢？", strategy_note="拉近距离")
    h = db.history(cid)
    assert len(h) == 2 and h[0]["content"] == "我大理的，你呢？"
    db.set_setting("active_hours", "19:00-23:00")
    assert db.get_setting("active_hours") == "19:00-23:00"
    assert db.dedupe_notification("momo", "n1", "陌陌", "新消息") is True
    assert db.dedupe_notification("momo", "n1", "陌陌", "新消息") is False
    assert len(db.list_customers()) == 1
    # ---- 备注保存：只动传进来的列，别的列不许被覆盖 ----
    #   ★ 断言写成"跟改之前比"，而不是"跟猜的值比" ——
    #     猜的值会随上面几步 upsert 的前提变化而变，比的是别的东西。
    before = dict(db.get_customer(cid))
    db.save_customer_notes(cid, summary="改过的备注", hit_signals="聊到工作")
    row = db.get_customer(cid)
    assert row["summary"] == "改过的备注", row["summary"]
    assert row["hit_signals"] == "聊到工作"
    for col in ("nickname", "distance", "personal_info", "progress",
                "status", "created_at"):
        assert row[col] == before[col], (col, row[col], before[col])
    assert db.save_customer_notes(999999) is False          # 什么都没传 → 不动手
    print("SELF_TEST_OK version=%d customers=%d conv=%d" % (
        db.version, len(db.list_customers()), len(h)))
    db.conn.close()
    os.remove(tmp)


if __name__ == "__main__":
    self_test()
