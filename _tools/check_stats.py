# -*- coding: utf-8 -*-
"""
Taku · 第 33 轮自检 —— 「界面上的数字是不是真的」

跑法（不需要手机）：
    python _tools/check_stats.py

★ 这个脚本查什么（每条都对应一个真踩过的坑）：

    ① **数据层算得对**        —— 造数据 → 断言每个数字（stats.py 自检）
    ② **显示规则对**          —— 没数据必须是「—」，**不许出现 0 冒充**
    ③ **界面真的接上了**      —— 离屏开窗口，断言卡片上的字 == 数据层算出来的字
                                （**不是**看代码"看起来"接上了）
    ④ **假数据防线**          —— pages_overview.py 里不许再出现那批写死的示例数字
                                （"38 条"、"23/12/5/3/1"…），防止哪天改回去
    ⑤ **只读防线**            —— stats.py 正文不许有写库语句

★ 为什么要写④这种"防回归"检查：
    第 32 轮的教训是「按钮都点得通 ≠ 用户点哪都有反应」。
    同一个道理：今天把假数据换成真数据，**下一轮很容易又写回去**
    （改样式、加卡片时顺手写死一个数最省事）。要有机器盯着。
"""

import os
import re
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_SRC = os.path.join(_ROOT, "src")
sys.path.insert(0, _SRC)

PY = sys.executable

OK = "  ✔ "
BAD = "  ✘ "

_fails = []


def _check(name, fn):
    try:
        fn()
        print(OK + name)
    except Exception as e:
        _fails.append((name, e))
        print(BAD + name + "  → " + repr(e))


# ============================================================
# ① 数据层自检
# ============================================================
def t_data_layer():
    r = subprocess.run([PY, os.path.join(_SRC, "stats.py")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    assert "SELF_TEST_OK" in (r.stdout or ""), r.stdout


# ============================================================
# ② 显示规则（规格书 5.5）
# ============================================================
def t_display_rules():
    from ui import datasource as DS

    empty = DS._empty("测试用空壳")
    assert empty["has_any_data"] is False
    # 全新装机：数字量出来是 0，但 must 显示「—」
    assert DS.num(0, empty, " 条") == DS.DASH, DS.num(0, empty, " 条")
    assert DS.num(None, empty, " 条") == DS.DASH
    assert DS.ratio(0, 20, False) is None
    assert DS.delta(0, 0) is None, DS.delta(0, 0)          # 两个 0 不写"持平"

    good = dict(empty); good["ok"] = True; good["has_any_data"] = True
    assert DS.num(38, good, " 条") == "38 条"
    assert DS.num(0, good, " 条") == "0 条"                  # 真读数：0 就是 0
    assert DS.ratio(5, 20, True, good) == 25
    assert DS.delta(12, 0, "条").startswith("较昨日 +12")

    # 来源说明：必须能说出"每个数字哪来的"
    note = DS.source_note(good)
    assert "customers 表" in note and "conversations 表" in note, note[:80]


# ============================================================
# ③ 界面真的接上了（离屏开窗，比字）
# ============================================================
def t_ui_wired():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])

    from ui import theme as TH
    from ui import datasource as DS
    from ui.pages_overview import OverviewPage

    TH.set_current("dark")
    page = OverviewPage()

    # on_show 之前：必须是「—」（**不许**一开始就摆一屏假数字）
    for k, c in page._cards.items():
        assert c._lv.text() == DS.DASH, "开页前 %s 就不是「—」：%s" % (k, c._lv.text())

    page.on_show()
    s = DS.snapshot()
    expect = {
        "new":     DS.num(s.get("new_customers_today"), s, " 位"),
        "replied": DS.num(s.get("replied_today"), s, " 条"),
        "signals": DS.num(s.get("signals_total"), s, " 个"),
    }
    for k, want in expect.items():
        got = page._cards[k]._lv.text()
        assert got == want, "卡片 %s 显示 %r，数据层给的是 %r" % (k, got, want)

    # 漏斗必须等于数据层算的
    f = s.get("funnel") or []
    rows = [page._funnel_box.itemAt(i).widget() for i in range(page._funnel_box.count())]
    rows = [r for r in rows if r is not None and hasattr(r, "_info")]
    assert len(rows) == len(f), "漏斗行数 %d ≠ 数据 %d" % (len(rows), len(f))
    for r, st in zip(rows, f):
        assert r._info[0] == st["name"] and r._info[1] == str(st["num"]), (r._info, st)

    # 折线：数据层没数据时，图上不许有线
    if not s.get("has_any_data") or not s.get("week_peak"):
        assert page.chart._series is None, page.chart._series


# ============================================================
# ④ 假数据防线（防回归）
# ============================================================
#   这批数字是第 32 轮之前写在 pages_overview.py / pages_stats.py 里的
#   "图纸示例值"。它们一旦又出现在代码里，说明有人把真数据改回假数据了。
FAKE_PATTERNS = [
    r'"2"\s*,\s*" / 3 目标"',            # 今日新客户 2/3
    r'"38"',                              # 已回消息 38 条
    r'"17"',                              # 打招呼剩余 17/20
    r'23,\s*"100%"',                      # 漏斗 破冰 23
    r'12,\s*"52%"',                       # 漏斗 深聊 12
    r'5,\s*"22%"',                        # 漏斗 加微信 5
    r'3,\s*"13%"',                        # 漏斗 信任 3
    r'"6h 12m"',                          # 今日已运行 6h12m
    r'"41 条"',                           # 处理事件 41 条
]

#   注意：pages_stats.py 这一轮**故意没动**（统计页是下一轮的活），
#   所以只扫总览页 + 主窗口（这两个这轮改了）。
SCAN_FILES = ["ui/pages_overview.py", "ui/main_window.py"]


def t_no_fake_numbers():
    bad = []
    for rel in SCAN_FILES:
        path = os.path.join(_SRC, rel)
        text = open(path, encoding="utf-8").read()
        for pat in FAKE_PATTERNS:
            for m in re.finditer(pat, text):
                line = text[:m.start()].count("\n") + 1
                bad.append("%s:%d  %s" % (rel, line, m.group(0)))
    assert not bad, "又出现写死的示例数字了：\n      " + "\n      ".join(bad)


# ============================================================
# ⑤ 只读防线
# ============================================================
def t_stats_readonly():
    text = open(os.path.join(_SRC, "stats.py"), encoding="utf-8").read()
    body = text.split("def self_test")[0].upper()
    body = body.replace("不许出现 INSERT / UPDATE / DELETE", "")
    for kw in ("INSERT", "UPDATE", "DELETE", "DROP"):
        assert kw not in body, "stats.py 正文里出现了 %s" % kw


# ============================================================
def main():
    print("=" * 60)
    print("Taku · 第 33 轮自检 —— 界面上的数字是不是真的")
    print("=" * 60)

    _check("① 数据层算得对（stats.py 自检）", t_data_layer)
    _check("② 显示规则对（无数据=「—」，不拿 0 冒充）", t_display_rules)
    _check("③ 界面真的接上了（离屏开窗，比字）", t_ui_wired)
    _check("④ 假数据防线（总览页不许再有写死的示例数字）", t_no_fake_numbers)
    _check("⑤ 只读防线（stats.py 不写库）", t_stats_readonly)

    print("-" * 60)
    if _fails:
        print("❌ 有 %d 项没过：" % len(_fails))
        for n, e in _fails:
            print("   ·", n, "→", e)
        return 1
    print("✅ 全过 —— 总览页/底栏的数字确实是从 data/tuoke.db 算出来的")
    return 0


if __name__ == "__main__":
    sys.exit(main())
