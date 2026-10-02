# -*- coding: utf-8 -*-
"""
★★★ 闭环测试（第 35 轮建）—— "芯在壳里"到底通没通 ★★★

★ 它验证的是最初想法里最要紧的一段链路（**不需要手机**）：

    加一个人 → AI 替他聊了一轮（写进库）
              → 总览页的"今日已回"数字真的动了
              → 客户列表里这个人真的出现、最后一句就是 AI 说的那句
              → 聊天区真的能读出这两句往来
              → 用户删掉他 → 不会复活 → 捞回来 → 又在

★ 为什么要有它：以前"AI 落库"这条线是**断的**（customer_id 传不下去），
  界面再漂亮数字也是死的。这个测试就是给这条线装的"心跳监测仪"。

用法：
    python _tools/test_db_loop.py
★ 会往库里写几条测试数据，跑完**自己清干净**，不留垃圾。
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_SRC = os.path.join(_ROOT, "src")
for p in (_SRC, _ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append((name, detail))
    print("  %s %s%s" % ("✅" if ok else "✘", name,
                         ("　—— " + detail) if detail and not ok else ""))


def main():
    print("=" * 70)
    print("闭环测试：加人 → AI 聊 → 落库 → 数字动 → 看得见 → 删掉不复活")
    print("=" * 70)

    from tt_db import TuokeDB
    from stats import Stats

    # --------------------------------------------------------
    # 0. 记下之前的数字（待会儿对比"动了没"）
    # --------------------------------------------------------
    st0 = Stats()
    try:
        s0 = st0.summary() or {}
    finally:
        st0.close()
    before_replied = s0.get("replied_today") or 0

    # --------------------------------------------------------
    # 1. 加一个人（真写库 —— 界面上「+ 加一个人」走的就是这一条）
    # --------------------------------------------------------
    print("\n【1】加一个人")
    db = TuokeDB()
    try:
        cid = db.upsert_customer("soul", "闭环测试-勿删")
        check("能写进库（拿到编号 %s）" % cid, bool(cid))
    except Exception as e:
        db.conn.close()
        check("能写进库", False, str(e)[:80])
        return _done()

    # --------------------------------------------------------
    # 2. AI 替他聊一轮（写进 conversations —— tt_loop_chat 落库走的就是这个）
    # --------------------------------------------------------
    print("\n【2】AI 聊了一轮（她问一句，AI 答一句）")
    try:
        db.add_message(cid, "other", "在吗？")
        db.add_message(cid, "ai", "在的呀，刚看到你主页", verified=1)
        check("两条都写进库了", True)
    except Exception as e:
        check("写库", False, str(e)[:80])

    # --------------------------------------------------------
    # 3. 总览页的数字动了没（这是用户最先看的那个）
    # --------------------------------------------------------
    print("\n【3】总览页的数字动了吗")
    st1 = Stats()
    try:
        s1 = st1.summary() or {}
    finally:
        st1.close()
    after_replied = s1.get("replied_today") or 0
    check("今日已回：%s → %s（AI 回的那条算进去了）" % (before_replied, after_replied),
          after_replied >= before_replied + 1)

    # --------------------------------------------------------
    # 4. 客户列表里看得见吗（datasource 是界面唯一的数据入口）
    # --------------------------------------------------------
    print("\n【4】客户列表 / 聊天区看得见吗")
    from ui import datasource as DS
    DS.invalidate()
    rows = DS.customers() or []
    mine = [r for r in rows if str(r.get("id")) == str(cid)]
    check("列表里有这个人", bool(mine))
    if mine:
        last = (mine[0].get("last_content") or "").strip()
        check("最后一句就是 AI 说的那句（%s）" % last[:20],
              last == "在的呀，刚看到你主页")

    msgs = DS.messages(cid) or []
    check("聊天区能读出 %d 条往来（应为 2）" % len(msgs), len(msgs) == 2)

    # --------------------------------------------------------
    # 5. 用户删掉他 → 不许复活 → 捞回来 → 又在
    # --------------------------------------------------------
    print("\n【5】删掉 → 不复活 → 捞回来")
    from ui.store import get_store
    sto = get_store()
    ok = sto.delete_customer(cid)
    check("删除成功", ok)
    DS.invalidate()
    gone = [r for r in (DS.customers() or []) if str(r.get("id")) == str(cid)]
    check("删了之后列表里**没有**他（不复活）", not gone)

    tid = None
    for t in sto.trash():
        if str(t.get("id")) == str(cid):
            tid = t.get("id")
            break
    check("回收站里找得到他", tid is not None)

    if tid:
        sto.restore(tid)
        DS.invalidate()
        back = [r for r in (DS.customers() or []) if str(r.get("id")) == str(cid)]
        check("捞回来之后又在了", bool(back))

    # --------------------------------------------------------
    # 6. 清理测试数据（不留垃圾在用户的库里）
    # --------------------------------------------------------
    print("\n【6】清理测试数据")
    try:
        db.conn.execute("DELETE FROM conversations WHERE customer_id=?", (cid,))
        db.conn.execute("DELETE FROM customers WHERE id=?", (cid,))
        db.conn.commit()
        check("库里那条测试客户和聊天记录删干净了", True)
    except Exception as e:
        check("清理", False, str(e)[:80])
    finally:
        db.conn.close()

    # 把 store 里为这条测试留的痕迹（隐藏标记/回收站）也清掉
    try:
        from ui.store import get_store
        s2 = get_store()
        s2.unhide(cid)
        s2._d["trash"] = [t for t in s2.trash() if str(t.get("id")) != str(cid)]
        s2.save()
        s2.changed.emit("all")
    except Exception:
        pass

    DS.invalidate()
    return _done()


def _done():
    print()
    print("=" * 70)
    print("通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
    if FAIL:
        print("没过的：")
        for n, d in FAIL:
            print("   ✘", n, d)
    print("=" * 70)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
