# -*- coding: utf-8 -*-
"""
★ 检查"每一页里到底有几个东西能点"（第 32 轮加）

★ 为什么要有这个检查（这是个教训）：
    第 31 轮我跑过"74 个按钮全点一遍，0 崩溃" —— 看起来很充分。
    结果用户一上手就说：「点进去根本动不了，太智障了」。

    因为那两页（消息 / 统计）**压根没有可点的东西**，
    而我的检查只测了"已有的按钮能不能点通"——
    **问错了问题。**

★ 这个脚本换一个问法：
    不以"按钮"为单位，以"**一页**"为单位：
    这一页里，用户到底能点几个地方？
    少于门槛（默认 4 个）就报警。

★ 数什么算"能点"：
    · QPushButton（按钮）
    · QCheckBox（开关）
    · QComboBox（下拉）
    · QLineEdit / QTextEdit（能打字的）
    · 任何设了"手型光标"的控件（= 界面在暗示"我能点"）

用法：
    python _tools/check_clickable.py           # 只看有没有问题
    python _tools/check_clickable.py --detail  # 顺便列出每页都是些什么
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_SRC = os.path.join(_ROOT, "src")
for p in (_SRC, _ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

# 每页至少要有这么多个"能点的地方"
MIN_CLICKABLE = 4

# 页面里这些"不算"独立可点（它们本身就是导航/容器）
SKIP_NAMES = {"NavItem", "IconBtn"}


def main():
    detail = "--detail" in sys.argv

    from PySide6.QtWidgets import (
        QApplication, QPushButton, QCheckBox, QComboBox, QLineEdit,
        QTextEdit, QPlainTextEdit, QWidget,
    )
    from PySide6.QtCore import Qt

    app = QApplication(sys.argv)
    from ui.main_window import MainWindow

    win = MainWindow()
    win.show()
    app.processEvents()

    print("=" * 60)
    print("每页可点元素检查（门槛：至少 %d 个）" % MIN_CLICKABLE)
    print("=" * 60)
    print()

    bad = []
    for key, label in win.PAGE_LABELS:
        win.goto(key)
        for _ in range(3):
            app.processEvents()
        page = win._pages.get(key)
        if page is None:
            print("  %-8s 页面没建起来！" % label)
            bad.append(label)
            continue

        found = []

        def add(kind, txt):
            txt = (txt or "").strip().replace("\n", " ")[:18]
            found.append("%s(%s)" % (kind, txt) if txt else kind)

        for b in page.findChildren(QPushButton):
            if b.objectName() in SKIP_NAMES:
                continue
            add("按钮", b.text() or b.toolTip())
        for c in page.findChildren(QCheckBox):
            add("开关", c.text())
        for c in page.findChildren(QComboBox):
            add("下拉", c.currentText())
        for e in page.findChildren(QLineEdit):
            add("输入框", e.placeholderText())
        for e in page.findChildren(QTextEdit) + page.findChildren(QPlainTextEdit):
            add("文本框", e.placeholderText())
        # 手型光标的（= 界面在说"我能点"）
        for w in page.findChildren(QWidget):
            if w.cursor().shape() == Qt.PointingHandCursor:
                add("可点块", w.objectName())

        n = len(found)
        flag = "  ⚠ 太少！" if n < MIN_CLICKABLE else ""
        print("  %-8s %2d 个%s" % (label, n, flag))

        if detail or n < MIN_CLICKABLE:
            for f in found:
                print("        · %s" % f)
        if n < MIN_CLICKABLE:
            bad.append(label)

    print()
    print("=" * 60)
    if bad:
        print("⚠ 有 %d 页可点元素太少：%s" % (len(bad), "、".join(bad)))
        print("  → 用户点进去会觉得'动不了'，必须补交互")
        return 1
    print("全部通过 —— 每一页都有足够多的地方可以点。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
