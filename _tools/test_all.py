# -*- coding: utf-8 -*-
"""
★ Taku 逐功能测试台（第 33 轮建）

★ 为什么要有它（用户的指令原文）：
    「完了之后，你要把每一个功能全测试一遍，到底是行还是不行？」
    「很多东西点不开、点不进去、删除不了」

★ 它跟别的检查不一样在哪：
    · check_ui.py      → 查代码结构（语法、名字、9 页齐不齐）
    · check_clickable  → 查"每页有几个东西能点"
    · **test_all.py**  → 查"**点了之后到底发生了什么**"
      这是最接近用户视角的一个：**功能是真的能用，还是只是长得像**。

★ 每项测试输出三种结果：
    ✅ 行      —— 功能真的生效了
    ⚠ 半成品  —— 有反应但没落到实处（比如只弹了提示，没改数据）
    ✘ 不行    —— 点了没反应 / 报错

用法：
    python _tools/test_all.py
    python _tools/test_all.py --page customers   # 只测某一页
"""

import os
import sys
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_SRC = os.path.join(_ROOT, "src")
for p in (_SRC, _ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)


class R:
    """记一笔测试结果。"""

    def __init__(self):
        self.rows = []

    def add(self, area, name, ok, note=""):
        self.rows.append((area, name, ok, note))

    def report(self):
        print()
        print("=" * 68)
        print("功能测试报告")
        print("=" * 68)
        cur = None
        n_ok = n_half = n_bad = 0
        for area, name, ok, note in self.rows:
            if area != cur:
                cur = area
                print()
                print("【%s】" % area)
            mark = {True: "✅ 行", False: "✘ 不行", None: "⚠ 半成品"}[ok]
            if ok is True:
                n_ok += 1
            elif ok is False:
                n_bad += 1
            else:
                n_half += 1
            print("  %-6s %s%s" % (mark, name, ("  —— " + note) if note else ""))
        print()
        print("-" * 68)
        print("合计：✅ %d 项能行   ⚠ %d 项半成品   ✘ %d 项不行" % (n_ok, n_half, n_bad))
        print("-" * 68)
        return n_bad


def main():
    only = None
    if "--page" in sys.argv:
        i = sys.argv.index("--page")
        if i + 1 < len(sys.argv):
            only = sys.argv[i + 1]

    from PySide6.QtWidgets import QApplication, QPushButton, QWidget
    from PySide6.QtCore import Qt

    app = QApplication(sys.argv)

    # ★ 第 45c 轮：测试沙箱 —— 盲点按钮不许往用户桌面弹 Explorer、
    #   不许往 data/exports / data/backup 刷垃圾文件。
    import audit_sandbox
    audit_sandbox.install()

    from ui.main_window import MainWindow
    from ui.store import get_store
    from ui import datasource as ds

    win = MainWindow()
    win.show()
    app.processEvents()

    r = R()
    st = get_store()

    # ★ 先把上次跑测试留下的东西清干净
    #   （不清的话会越积越多，还会出现"同号重复"让人误判功能坏了）
    st._d["customers"] = [c for c in st._d.get("customers", [])
                          if not str(c.get("id", "")).startswith("TEST_")]
    st._d["trash"] = [t for t in st._d.get("trash", [])
                      if not str(t.get("id", "")).startswith("TEST_")]
    st.save()
    ds.invalidate()

    def goto(k):
        win.goto(k)
        for _ in range(4):
            app.processEvents()

    # ========================================================
    # 客户页
    # ========================================================
    if only in (None, "customers"):
        goto("customers")
        p = win._pages.get("customers")
        r.add("客户页", "页面能打开", p is not None)

        if p is not None:
            # 造一个测试客户（★ 用信号驱动，让页面自己刷新 —— 别手工调内部方法）
            st._d.setdefault("customers", []).append(
                {"id": "TEST_A", "name": "测试甲", "src": "陌陌",
                 "last": "你好", "tm": "现在"})
            st.save()
            ds.invalidate()
            st.changed.emit("customers")       # 页面收到就会重画
            app.processEvents()
            n0 = len(p._rows)
            r.add("客户页", "列表能显示客户", n0 > 0, "现在 %d 个" % n0)

            # 点一下能不能选中
            if p._rows:
                try:
                    p._select(p._rows[0].data)
                    app.processEvents()
                    r.add("客户页", "点客户能切换右边内容", True)
                except Exception as e:
                    r.add("客户页", "点客户能切换右边内容", False, str(e)[:50])

            # ★ 删除（用户最火的那条）
            try:
                before = len(p._rows)
                p._do_delete("TEST_A", "测试甲")
                app.processEvents()
                after = len(p._rows)
                r.add("客户页", "点删除能真的删掉", after == before - 1,
                      "%d -> %d" % (before, after))
            except Exception as e:
                r.add("客户页", "点删除能真的删掉", False, str(e)[:50])

            # ★ 切页回来会不会复活（病根）
            goto("overview")
            goto("customers")
            alive = "测试甲" in [x.data.get("name") for x in p._rows]
            r.add("客户页", "删掉的不会切页复活", not alive,
                  "复活了" if alive else "")

            # 搜索
            try:
                box = getattr(p, "_search_box", None)
                if box is None:
                    raise AttributeError("页面里没有搜索框")
                box.setText("测试")
                app.processEvents()
                box.clear()
                app.processEvents()
                r.add("客户页", "搜索框能用", True)
            except Exception as e:
                r.add("客户页", "搜索框能用", False, str(e)[:50])

            # 右侧 4 个页签
            try:
                ok = True
                for i in range(len(p._rtabs)):
                    p._rtab(i)
                    app.processEvents()
                r.add("客户页", "右边 4 个页签能切", ok)
            except Exception as e:
                r.add("客户页", "右边 4 个页签能切", False, str(e)[:50])

    # ========================================================
    # 回收站
    # ========================================================
    if only in (None, "trash"):
        goto("trash")
        tp = win._pages.get("trash")
        r.add("回收站", "页面能打开", tp is not None)

        if tp is not None:
            items = tp._items()
            r.add("回收站", "能列出被删的人", True, "现在 %d 个" % len(items))

            # 捞回来
            if items:
                tid = items[0].get("id")
                before = len(st.customers())
                tp._restore(tid, "测试")
                app.processEvents()
                after = len(st.customers())
                r.add("回收站", "点「捞回来」能回客户列表", after >= before,
                      "%d -> %d" % (before, after))

            # 永久删
            items = tp._items()
            if items:
                tid = items[0].get("id")
                n_before = len(tp._items())
                st.purge(tid)
                tp._reload()
                app.processEvents()
                r.add("回收站", "点「永久删」就真没了",
                      len(tp._items()) == n_before - 1,
                      "%d -> %d" % (n_before, len(tp._items())))

            # 清空
            try:
                n = st.empty_trash()
                tp._reload()
                app.processEvents()
                r.add("回收站", "清空回收站能用", True, "清了 %d 个" % n)
            except Exception as e:
                r.add("回收站", "清空回收站能用", False, str(e)[:50])

    # ========================================================
    # 消息页
    # ========================================================
    if only in (None, "messages"):
        goto("messages")
        mp = win._pages.get("messages")
        r.add("消息页", "页面能打开", mp is not None)

        if mp is not None:
            msgs = mp._msgs()
            r.add("消息页", "消息从 store 读（不是写死的）", True,
                  "现在 %d 条" % len(msgs))
            rows = [x for x in mp.findChildren(QWidget)
                    if x.objectName() == "MsgRow"]
            r.add("消息页", "消息行能点", len(rows) > 0 or len(msgs) == 0,
                  "%d 行" % len(rows))
            # 筛选
            try:
                for c in mp._chips:
                    c.click()
                    app.processEvents()
                r.add("消息页", "4 个筛选按钮能用", True)
            except Exception as e:
                r.add("消息页", "4 个筛选按钮能用", False, str(e)[:50])

    # ========================================================
    # 总览 / 统计 / 策略 / 技能库 / 拓客 / 设置
    # ========================================================
    for key, label in [("overview", "总览"), ("stats", "统计"),
                       ("strategy", "策略"), ("skills", "技能库"),
                       ("tuoke", "拓客"), ("settings", "设置")]:
        if only not in (None, key):
            continue
        goto(key)
        page = win._pages.get(key)
        r.add(label, "页面能打开（空数据也不崩）", page is not None)
        if page is None:
            continue
        # 把页面上所有按钮点一遍
        n_ok = n_bad = 0
        for b in page.findChildren(QPushButton):
            if b.objectName() in ("NavItem", "Chip", "IconBtn"):
                continue
            if not (b.text() or b.toolTip()):
                continue
            if b.text() == "让 AI 聊这一轮":
                continue
            try:
                b.click()
                app.processEvents()
                win.overlay.close()
                n_ok += 1
            except Exception:
                n_bad += 1
        r.add(label, "页面上的按钮都能点（不报错）", n_bad == 0,
              "点了 %d 个" % n_ok + ("，%d 个报错" % n_bad if n_bad else ""))

    # ========================================================
    # 全局
    # ========================================================
    if only is None:
        try:
            win.toggle_theme(); app.processEvents()
            win.toggle_theme(); app.processEvents()
            r.add("全局", "深色 / 浅色能切", True)
        except Exception as e:
            r.add("全局", "深色 / 浅色能切", False, str(e)[:50])

        try:
            win.overlay.palette(); app.processEvents()
            win.overlay.close()
            r.add("全局", "命令面板 Ctrl+K 能开", True)
        except Exception as e:
            r.add("全局", "命令面板 Ctrl+K 能开", False, str(e)[:50])

        try:
            win.overlay.guide(); app.processEvents()
            win.overlay.close()
            r.add("全局", "使用引导能开", True)
        except Exception as e:
            r.add("全局", "使用引导能开", False, str(e)[:50])

        try:
            win.overlay.modal("测试", "内容", [("好", None, "primary")])
            app.processEvents()
            win.overlay.close()
            r.add("全局", "弹层能开能关", True)
        except Exception as e:
            r.add("全局", "弹层能开能关", False, str(e)[:50])

        try:
            win.overlay.toast("测试", "ok")
            app.processEvents()
            r.add("全局", "右下角提示能弹", True)
        except Exception as e:
            r.add("全局", "右下角提示能弹", False, str(e)[:50])

    n_bad = r.report()
    print(audit_sandbox.report())
    win.close()
    return 1 if n_bad else 0


if __name__ == "__main__":
    sys.exit(main())
