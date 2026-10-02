# -*- coding: utf-8 -*-
"""
临时冒烟测试：真开窗 → 切 9 页 → 切主题 → 客户页选中真客户 → 看消息区。
只读，不写库、不碰真机。跑完可删。
"""
import sys, os, traceback
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from PySide6.QtWidgets import QApplication


def step(n, msg):
    print("[%02d] %s" % (n, msg), flush=True)


def main():
    step(1, "QApplication")
    app = QApplication(sys.argv)
    from ui.main_window import MainWindow
    step(2, "MainWindow 构造")
    w = MainWindow()
    w.resize(1440, 900)
    w.show()
    app.processEvents()

    keys = ["overview", "customers", "messages", "strategy", "skills",
            "tuoke", "stats", "trash", "settings"]
    step(3, "切 9 页")
    for i, k in enumerate(keys, 1):
        try:
            w.goto(k)
            app.processEvents()
            print("     OK  %-10s" % k, flush=True)
        except Exception:
            print("     FAIL %-10s" % k, flush=True)
            traceback.print_exc()

    step(4, "客户页：真库读取")
    pg = w._pages.get("customers")
    rows = getattr(pg, "_data", None)
    print("     pg.customer_id =", getattr(pg, "customer_id", "?"), flush=True)
    try:
        from ui import datasource as DS
        cs = DS.customers()
        print("     DS.customers() ->", None if cs is None else ("%d 位" % len(cs)), flush=True)
        for c in (cs or []):
            print("        id=%s %s [%s] progress=%s msgs=%s"
                  % (c.get("id"), c.get("nickname"), c.get("platform"),
                     c.get("progress"), c.get("msg_count")), flush=True)
    except Exception:
        traceback.print_exc()

    step(5, "客户页：选中第一位真客户")
    try:
        if cs:
            pg.select_by_id(cs[0]["id"])
            app.processEvents()
            print("     选中后 customer_id =", getattr(pg, "customer_id", "?"), flush=True)
            print("     聊天区气泡数 =", pg.msgs_box.count(), flush=True)
        else:
            print("     库里 0 位客户 —— 应该走空态", flush=True)
    except Exception:
        traceback.print_exc()

    step(6, "切主题 dark -> light -> dark")
    for name in ("light", "dark"):
        try:
            w.apply_theme(name)
            app.processEvents()
            print("     切到 %-5s OK" % name, flush=True)
        except Exception:
            print("     切到 %-5s FAIL" % name, flush=True)
            traceback.print_exc()

    step(7, "切主题后 9 页再走一遍")
    for k in keys:
        try:
            w.goto(k)
            app.processEvents()
        except Exception:
            print("     FAIL %s" % k, flush=True)
            traceback.print_exc()
    print("     9 页在重建后再切换：完成", flush=True)

    step(8, "关窗")
    try:
        w.close()
    except Exception:
        traceback.print_exc()

    print("SMOKE_DONE", flush=True)


if __name__ == "__main__":
    main()
