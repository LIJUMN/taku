# -*- coding: utf-8 -*-
"""
★ 界面截图脚本 —— 把 9 页 + 双主题逐张拍下来，存到 _shots_ui/

为什么要它：
    用户"只会点点点"，我更要把 9 页都先拍成图给他看一遍，
    他一眼就知道对不对，不用自己一个个点。
    同时这也是"1:1 抄图纸"的验收证据。

用法：
    python _tools/shot_ui.py            # 深色 + 浅色，9 页
    python _tools/shot_ui.py dark       # 只拍深色
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_SRC = os.path.join(_ROOT, "src")
for p in (_SRC, _ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

OUT = os.path.join(_ROOT, "_shots_ui")

PAGES = [
    ("overview",  "1-总览"),
    ("customers", "2-客户"),
    ("messages",  "3-消息"),
    ("strategy",  "4-策略"),
    ("skills",    "5-技能库"),
    ("tuoke",     "6-拓客"),
    ("stats",     "7-统计"),
    ("trash",     "8-回收站"),
    ("settings",  "9-设置"),
]


def main():
    themes = [a for a in sys.argv[1:] if a in ("dark", "light")] or ["dark", "light"]

    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt

    app = QApplication(sys.argv)

    from ui.main_window import MainWindow

    os.makedirs(OUT, exist_ok=True)

    win = MainWindow()
    win.resize(1440, 900)
    win.show()

    # 等窗口画完
    for _ in range(6):
        app.processEvents()

    n = 0
    for th in themes:
        win.apply_theme(th)
        for _ in range(3):
            app.processEvents()

        for key, label in PAGES:
            win.goto(key)
            for _ in range(5):
                app.processEvents()
            fn = os.path.join(OUT, "%s_%s.png" % (th, label))
            win.grab().save(fn)
            n += 1
            print("  %s" % fn)

    print("\n拍了 %d 张 → %s" % (n, OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
