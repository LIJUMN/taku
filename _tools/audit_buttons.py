# -*- coding: utf-8 -*-
"""
★★★ Taku 逐按钮审计器（第 34 轮建）

★ 用户的指令原文：
    「你去把那个软件的每一个按钮点开，测试它的功能然后逻辑对不对？每一个按钮。」

★ 它跟前面几个检查的区别：
    check_ui.py        → 查代码结构（语法、名字、9 页齐不齐）
    check_clickable.py → 查"每页有几个东西能点"
    test_all.py        → 查"关键功能能不能用"
    **本脚本**         → 查"**每一个按钮点下去，到底发生了什么**"，一个不落

★ "逻辑对不对"怎么判断：
    点击前记一份状态（弹层有没有、在哪个页、数据变了没、toast 弹了没），
    点击后再记一份，对比：

      · 弹了层        → ✅ 有反应（打开了确认框/详情/面板）
      · 切了页        → ✅ 有反应（跳转了）
      · 数据变了      → ✅ 有反应（真的改了东西）
      · 只弹了个提示  → ⚠ 半成品（只是嘴上说说，没落到实处）
      · 什么都没发生  → ✘ **装了样子没功能**（这就是用户骂的）

用法：
    python _tools/audit_buttons.py              # 全部
    python _tools/audit_buttons.py --page tuoke # 只看某一页
    python _tools/audit_buttons.py --csv out.csv  # 顺便导出一份表格
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_SRC = os.path.join(_ROOT, "src")
for p in (_SRC, _ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)


def _snapshot(win, st):
    """
    抓一份当前状态（用来跟点击后对比）。

    ★ 第 34 轮补两项，否则会**误判**：
      原来只看了"弹层/跳页/数据"，结果像「接管」这种按钮 ——
      它点了会把徽章文字从"AI 托管中"改成"你在聊"，
      明明有反应，却被判成"什么都没发生"。
      现在加上：
        · text —— 抓当前页所有文字（改文字也算有反应）
        · toast —— 右下角轻提示（弹一下也算有反应）
    """
    from PySide6.QtWidgets import QLabel

    try:
        has_layer = win.overlay._layer is not None
    except Exception:
        has_layer = False
    try:
        page = win.stack.currentWidget().__class__.__name__
        texts = tuple(sorted(lb.text() for lb in
                             win.stack.currentWidget().findChildren(QLabel)
                             if lb.text()))
    except Exception:
        page = "?"
        texts = ()

    try:
        n_cust = len(st.customers())
        n_trash = len(st.trash())
        n_msg = len(st.messages())
    except Exception:
        n_cust = n_trash = n_msg = -1

    # ★ 第 34 轮：待办队列 / 给 AI 下的指令，也都是"真数据"。
    #   点了"让她聊""约见面"如果只写进数据、界面文字没变，
    #   这两个数会变 —— 那就说明它**真干活了**，不该被判成"没落到实处"。
    try:
        n_queue = len(st.queue())
    except Exception:
        n_queue = -1
    try:
        n_orders = sum(len(v) for v in (st.orders() or {}).values())
    except Exception:
        n_orders = -1

    try:
        n_toast = len([t for t in win.overlay._toasts if t.isVisible()])
    except Exception:
        n_toast = 0

    # ★ 第 34 轮：**只增不减**的 toast 计数器 + 文案历史。
    #   原来只数"当前可见的条数"，而 toast 会自己过期消失 ——
    #   旧的刚消失、新的刚出现，条数正好抵消，就会被误判成"什么都没发生"。
    try:
        toast_seq = int(getattr(win.overlay, "_toast_seq", 0))
    except Exception:
        toast_seq = -1
    try:
        toast_log = tuple(getattr(win.overlay, "_toast_log", [])[-6:])
    except Exception:
        toast_log = ()

    # ★ 再补两项（否则会误判）：
    #   · 页签切换 —— 内容区换了个 widget，但**页面上所有文字集合没变**
    #     （因为各个页签的内容都在，只是显示/隐藏）
    #   · 胶囊/开关的选中态 —— 点了会切高亮，但文字不变
    #   → 抓"可见性 + 选中态"就都能看见
    from PySide6.QtWidgets import QWidget
    vis = []
    try:
        for w in win.stack.currentWidget().findChildren(QWidget):
            try:
                vis.append((w.objectName(),
                            bool(w.isVisible()),
                            bool(w.isChecked()) if hasattr(w, "isChecked") else None))
            except Exception:
                pass
    except Exception:
        pass

    # ★ 第 34 轮再补一项：页面**内部**的堆叠页（设置页左边那排导航就是）。
    #   点它切的是"里层"的页 —— 外层的 win.stack 没动，文字集合也没变
    #   （各面板都在，只是显示/隐藏），以前会误判成"什么都没发生"。
    inner = []
    try:
        from PySide6.QtWidgets import QStackedWidget
        for s in win.stack.currentWidget().findChildren(QStackedWidget):
            inner.append(s.currentIndex())
    except Exception:
        pass

    return {
        "layer": has_layer,
        "page": page,
        "texts": texts,
        "vis": tuple(vis),
        "inner": tuple(inner),
        "cust": n_cust,
        "trash": n_trash,
        "msg": n_msg,
        "queue": n_queue,
        "orders": n_orders,
        "toast": n_toast,
        "toast_seq": toast_seq,
        "toast_log": toast_log,
    }


def _diff(a, b):
    """对比两份状态，返回"发生了什么"。"""
    what = []
    if not a["layer"] and b["layer"]:
        what.append("弹了层")
    if a["layer"] and not b["layer"]:
        what.append("关了层")
    if a["page"] != b["page"]:
        what.append("跳了页(%s→%s)" % (a["page"], b["page"]))
    if a["cust"] != b["cust"]:
        what.append("客户数变了(%d→%d)" % (a["cust"], b["cust"]))
    if a["trash"] != b["trash"]:
        what.append("回收站变了(%d→%d)" % (a["trash"], b["trash"]))
    if a["msg"] != b["msg"]:
        what.append("消息数变了(%d→%d)" % (a["msg"], b["msg"]))
    if a.get("queue") != b.get("queue"):
        what.append("待办队列变了(%s→%s)" % (a.get("queue"), b.get("queue")))
    if a.get("orders") != b.get("orders"):
        what.append("给AI的指令变了(%s→%s)" % (a.get("orders"), b.get("orders")))
    if b["toast"] > a["toast"]:
        what.append("弹了提示")
    # ★ 只增不减的计数器（比"数可见条数"可靠：不会被过期抵消）
    if b.get("toast_seq", -1) > a.get("toast_seq", -1):
        if "弹了提示" not in what:
            what.append("弹了提示")
        new_txt = [x for x in b.get("toast_log", ()) if x not in a.get("toast_log", ())]
        if new_txt:
            what.append("提示内容:%s" % new_txt[-1][:18])
    if a["texts"] != b["texts"]:
        what.append("界面文字变了")
    # ★ 页面内部的堆叠页切了（设置页左导航）—— 也算真跳转
    if a.get("inner") != b.get("inner"):
        what.append("内容区切了")
    # ★ 可见性 / 选中态（页签切换、胶囊高亮都在这儿）
    if a.get("vis") != b.get("vis"):
        try:
            av, bv = a["vis"], b["vis"]
            n_vis = sum(1 for x, y in zip(av, bv) if x[1] != y[1])
            n_chk = sum(1 for x, y in zip(av, bv) if x[2] != y[2])
            if n_vis:
                what.append("内容区切了")
            if n_chk:
                what.append("选中态变了")
            if not n_vis and not n_chk:
                what.append("控件状态变了")
        except Exception:
            what.append("控件状态变了")
    return what


def main():
    only = None
    if "--page" in sys.argv:
        i = sys.argv.index("--page")
        if i + 1 < len(sys.argv):
            only = sys.argv[i + 1]

    csv_path = None
    if "--csv" in sys.argv:
        i = sys.argv.index("--csv")
        if i + 1 < len(sys.argv):
            csv_path = sys.argv[i + 1]

    from PySide6.QtWidgets import QApplication, QPushButton, QCheckBox, QComboBox
    app = QApplication(sys.argv)

    # ★ 第 45c 轮：审计沙箱 —— 点按钮验证逻辑可以，
    #   但不许往用户桌面弹 Explorer、不许往 data/exports 刷垃圾文件。
    import audit_sandbox
    audit_sandbox.install()

    from ui.main_window import MainWindow
    from ui.store import get_store

    win = MainWindow()
    win.show()
    app.processEvents()

    st = get_store()

    results = []          # (页面, 按钮名, 结论, 说明)

    print()
    print("=" * 74)
    print("逐按钮审计 —— 每一个按钮点下去，到底发生了什么")
    print("=" * 74)

    # 有些按钮点了会真的动手机 / 跑 AI / 弹系统窗口，审计时跳过（避免误操作）
    #   ★ 第 45c 轮补「高清投屏」：它会真启动 scrcpy 在桌面弹一个投屏窗。
    SKIP_TEXT = {"让 AI 聊这一轮", "检测连接", "看一眼手机现在什么样", "高清投屏"}

    for key, label in win.PAGE_LABELS:
        if only and key != only:
            continue

        # ★ 第 34 轮：客户页得**先有数据 + 选中一个人**，否则
        #   "保存备注 / 撤销修改"这些是灰的（没挑人本来就该灰），测出来全是假问题。
        #   所以这里先放 3 个示例客户进来，再挑中第一个。
        if key == "customers":
            try:
                if not st.customers():
                    st.add_samples()
                    try:
                        from ui import datasource as _ds
                        _ds.invalidate()
                    except Exception:
                        pass
            except Exception:
                pass

        win.goto(key)
        for _ in range(4):
            app.processEvents()

        page = win._pages.get(key)
        if page is None:
            results.append((label, "(整页)", "✘ 不行", "页面没建起来"))
            continue

        if key == "customers":
            try:
                rows = getattr(page, "_rows", []) or []
                if rows and getattr(page, "customer_id", None) is None:
                    data = getattr(rows[0], "data", None)
                    if data is not None:
                        page._select(data)
                        for _ in range(3):
                            app.processEvents()
            except Exception:
                pass

        # 收集这一页所有"可点的东西"
        targets = []
        for b in page.findChildren(QPushButton):
            if b.objectName() in ("NavItem", "IconBtn"):
                continue
            txt = (b.text() or b.toolTip() or "").strip()
            if not txt:
                continue
            targets.append(("按钮", txt, b))
        for c in page.findChildren(QCheckBox):
            targets.append(("开关", c.text().strip(), c))
        for c in page.findChildren(QComboBox):
            targets.append(("下拉", "(排序/筛选菜单)", c))

        print()
        print("【%s】 共 %d 个可点项" % (label, len(targets)))

        if not targets:
            print("    ✘ 这一页一个能点的都没有")
            results.append((label, "(整页)", "✘ 不行", "一个能点的都没有"))
            continue

        for kind, txt, w in targets:
            # ★ 点之前先确认"还在测这一页"。
            #   有些按钮点了会**跳页**（比如策略页的「去技能库看看」），
            #   跳走之后当前页就不是它了 —— 后面再点这一页的按钮，
            #   观察的是**另一个页面**的文字，当然看不出变化，全被误判成"没干活"。
            try:
                if win.stack.currentWidget() is not page:
                    win.goto(key)
                    for _ in range(3):
                        app.processEvents()
            except Exception:
                pass

            if txt in SKIP_TEXT:
                print("    ⏭  %-22s (会真动手机，审计时跳过)" % txt[:22])
                results.append((label, txt, "⏭ 跳过", "会真动手机"))
                continue

            before = _snapshot(win, st)
            # ★ 点之前先记一下"它是不是本来就选中的"。
            #   页签/导航这种可选中按钮，点"已经选中的那一个"**本来就不会有变化**，
            #   工具要是照旧判"什么都没发生"，就冤枉它了。
            was_checked = None
            try:
                if hasattr(w, "isCheckable") and w.isCheckable():
                    was_checked = bool(w.isChecked())
            except Exception:
                was_checked = None
            # ★ 灰不灰要**点之前**看！点之后再问就晚了 ——
            #   有些按钮点完会把自己变灰（比如拓客的「让她聊」点完变「已安排」），
            #   点完再问就全成了"灰的"，把真结果盖掉了。
            was_enabled = True
            try:
                was_enabled = bool(w.isEnabled())
            except Exception:
                was_enabled = True
            err = None
            try:
                if kind == "开关":
                    w.click()          # 开关：点一下看状态有没有翻
                elif kind == "下拉":
                    w.showPopup()
                    app.processEvents()
                    w.hidePopup()
                else:
                    w.click()
                for _ in range(3):
                    app.processEvents()
            except Exception as e:
                err = str(e)[:60]

            after = _snapshot(win, st)
            what = _diff(before, after)

            # ---- 判定（★ 分三档，别把"嘴上说说"当成"真功能"）----
            hard = any(x.startswith(("弹了层", "跳了页", "客户数变",
                                     "回收站变", "消息数变",
                                     "待办队列变", "给AI的指令变")) for x in what)
            soft_text = any(x == "界面文字变了" for x in what)
            soft_ui = any(x.startswith(("内容区切了", "选中态变了", "控件状态变了"))
                          for x in what)
            soft_toast = any(x == "弹了提示" for x in what)

            if err:
                verdict, note = "✘ 不行", "报错：" + err
            elif not was_enabled:
                # ★ 灰的按钮：程序本来就让它点不了（比如"没挑客户就不能存备注"）。
                #   这**不算坏** —— 但也不该混进"✅ 行"里装作没问题，
                #   所以单开一档，让人一眼看见"哦，这个现在是灰的，为什么灰"。
                verdict, note = "⏸ 灰的", "现在点不了（" + (w.toolTip() or "没说明原因").replace("\n", " ")[:40] + "）"
            elif hard:
                if any(x.startswith("弹了层") for x in what):
                    verdict, note = "✅ 行", "弹出了东西"
                else:
                    verdict, note = "✅ 行", "、".join(what)
            elif soft_text or soft_ui:
                # 界面跟着变了（页签切换 / 徽章文字改 / 胶囊高亮）
                verdict, note = "✅ 行", "、".join([x for x in what if x])
            elif soft_toast:
                # 只弹了个提示 —— 嘴上说说，没落到实处
                verdict, note = "⚠ 半成品", "只弹了个提示，没真干活"
            elif kind == "开关":
                verdict, note = "⚠ 半成品", "开关没翻（可能是故意锁定的）"
            elif kind == "下拉":
                verdict, note = "✅ 行", "下拉能展开"
            elif was_checked:
                # 可选中按钮，而且**点之前就已经是选中态**
                # → 它本来就是"当前这一页"，点它没变化是对的，不算坏
                verdict, note = "✅ 行", "本来就是选中的那一项（无需变化）"
            else:
                verdict, note = "✘ 不行", "**点了什么都没发生**"

            mark = verdict.split()[0]
            print("    %-4s %-22s %s" % (mark, txt[:22], note))
            results.append((label, txt, verdict, note))

            # 点完关掉可能弹出来的层，别影响下一个
            try:
                if win.overlay._layer is not None:
                    win.overlay.close()
                    app.processEvents()
            except Exception:
                pass

    # ========================================================
    print()
    print("=" * 74)
    print("汇总")
    print("=" * 74)

    n_ok = sum(1 for r in results if r[2].startswith("✅"))
    n_half = sum(1 for r in results if r[2].startswith("⚠"))
    n_bad = sum(1 for r in results if r[2].startswith("✘"))
    n_skip = sum(1 for r in results if r[2].startswith("⏭"))
    n_grey = sum(1 for r in results if r[2].startswith("⏸"))

    print()
    print("  共审计 %d 个可点项" % len(results))
    print("  ✅ 行        %3d" % n_ok)
    print("  ⚠ 半成品    %3d" % n_half)
    print("  ✘ 不行      %3d" % n_bad)
    print("  ⏸ 灰的      %3d" % n_grey)
    print("  ⏭ 跳过      %3d" % n_skip)

    if n_bad:
        print()
        print("  ✘ 这些是「装了样子但没功能」的（用户骂的就是这种）：")
        for area, name, v, note in results:
            if v.startswith("✘"):
                print("     [%s] %s  —— %s" % (area, name, note))

    if n_grey:
        print()
        print("  ⏸ 这些现在是灰的（点不了）—— 逐个确认「该灰才灰」：")
        for area, name, v, note in results:
            if v.startswith("⏸"):
                print("     [%s] %s  —— %s" % (area, name, note))

    if n_half:
        print()
        print("  ⚠ 这些是「有反应但没落到实处」的：")
        for area, name, v, note in results:
            if v.startswith("⚠"):
                print("     [%s] %s  —— %s" % (area, name, note))

    if csv_path:
        try:
            with open(csv_path, "w", encoding="utf-8-sig") as f:
                f.write("页面,按钮,结论,说明\n")
                for area, name, v, note in results:
                    f.write("%s,%s,%s,%s\n" % (area, name.replace(",", "，"),
                                               v, note.replace(",", "，")))
            print()
            print("  已导出：%s" % csv_path)
        except Exception as e:
            print("  导出失败：", e)

    # ★ 第 45c 轮：把沙箱接住的副作用打出来 ——
    #   证明"备份/导出/打开文件夹"这些按钮**逻辑真跑了**（有记账），
    #   只是不再溅到用户桌面上。
    print()
    print(audit_sandbox.report())

    win.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
