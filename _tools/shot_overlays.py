# -*- coding: utf-8 -*-
"""
★ 弹层截图脚本 —— 把 4 种弹层（命令面板 / 统一弹层 / 轻提示 / 引导）拍下来。

为什么要单独拍：
    弹层是"浮在上面"的东西，一闪而过或者要按键才出来。
    拍成图，用户一眼就能验收，不用自己去按 Ctrl+K。

用法：
    python _tools/shot_overlays.py
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


def pump(app, n=12):
    for _ in range(n):
        app.processEvents()


def main():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt

    app = QApplication(sys.argv)

    from ui.main_window import MainWindow

    os.makedirs(OUT, exist_ok=True)
    win = MainWindow()
    win.resize(1440, 900)
    win.show()
    pump(app, 20)

    shots = []

    # ① 命令面板
    win.overlay.palette()
    pump(app, 20)
    f = os.path.join(OUT, "overlay_1-命令面板.png")
    win.grab().save(f)
    shots.append(f)
    print("  " + f)

    # 面板里输入几个字，看过滤效果
    if win.overlay._layer is not None:
        for card in win.overlay._layer.findChildren(type(win.overlay._layer))[:0]:
            pass
    from ui.overlays import _Palette
    pal = win.overlay._layer.findChild(_Palette) if win.overlay._layer else None
    if pal:
        pal.input.setText("设置")
        pump(app, 10)
        f = os.path.join(OUT, "overlay_2-命令面板-过滤.png")
        win.grab().save(f)
        shots.append(f)
        print("  " + f)
    win.overlay.close()
    pump(app, 10)

    # ② 统一弹层（Modal）
    win.overlay.modal(
        "确认把「大熊」移出客户列表？",
        "移出后他会先进回收站，30 天内随时可以捞回来，不会真的消失。",
        [("再想想", None, "ghost"), ("移出去", None, "danger")],
    )
    pump(app, 20)
    f = os.path.join(OUT, "overlay_3-统一弹层.png")
    win.grab().save(f)
    shots.append(f)
    print("  " + f)
    win.overlay.close()
    pump(app, 10)

    # ③ 轻提示（Toast）四种
    win.overlay.toast("已回复「小鹿」的消息", "ok", 99000)
    pump(app, 20)
    f = os.path.join(OUT, "overlay_4-轻提示.png")
    win.grab().save(f)
    shots.append(f)
    print("  " + f)

    # ④ 新手引导
    win.overlay.guide()
    pump(app, 24)
    f = os.path.join(OUT, "overlay_5-新手引导.png")
    win.grab().save(f)
    shots.append(f)
    print("  " + f)

    print("\n拍了 %d 张弹层图 → %s" % (len(shots), OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
