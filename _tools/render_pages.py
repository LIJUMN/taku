# -*- coding: utf-8 -*-
"""
★ UI 审视工具（第 49 轮建）：把 9 个页面真实渲染成图，逐页看设计
   —— "界面好不好看"不能靠读代码想象，必须亲眼看渲染结果。

用法：
    python _tools/render_pages.py            # 深色主题 → _shots_ui/审视-深色-*.png
    python _tools/render_pages.py --light    # 浅色主题
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_SRC = os.path.join(_ROOT, "src")
for p in (_SRC, _ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

OUT_DIR = os.path.join(_ROOT, "_shots_ui")


def main():
    light = "--light" in sys.argv
    # ★ 不用 offscreen（它缺中文字体，全渲染成方框）；
    #   Windows 下不 show() 也能 grab()（布局照常计算）
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)

    from ui.main_window import MainWindow
    from ui import theme as TH

    if light:
        try:
            TH.set_theme("light")
        except Exception:
            pass

    win = MainWindow()
    win.resize(1280, 820)
    win.showMinimized()          # 不在桌面正中弹（最小化），但布局事件正常走
    app.processEvents()

    os.makedirs(OUT_DIR, exist_ok=True)
    tag = "浅色" if light else "深色"
    out = []
    for key, label in win.PAGE_LABELS:
        win.goto(key)
        for _ in range(6):
            app.processEvents()
        png = os.path.join(OUT_DIR, "审视-%s-%s.png" % (tag, label))
        win.grab().save(png)
        out.append(png)
        print("  ✓ %s" % os.path.basename(png))

    win.close()
    print("共 %d 张 → %s" % (len(out), OUT_DIR))
    return 0


if __name__ == "__main__":
    sys.exit(main())
