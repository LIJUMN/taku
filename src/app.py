# -*- coding: utf-8 -*-
"""
Taku · 拓客台 —— 启动入口

用法：
    python src/app.py            启动界面
    python src/app.py --check    只检查环境，不开窗口（打包前自检用）

★ 为什么要这个文件：
    - 以后打包 exe 时，入口就是它（PyInstaller --windowed src/app.py）
    - 用户电脑上双击 exe 就等于跑这个文件
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


def check_env():
    """打包前自检：把要说清楚的东西一次说完。"""
    print("=" * 56)
    print("Taku · 拓客台 —— 环境自检")
    print("=" * 56)
    print("Python :", sys.version.split()[0])
    print("路径   :", sys.executable)

    ok = True

    try:
        import PySide6
        print("PySide6:", PySide6.__version__)
    except Exception as e:
        print("PySide6: 缺！", e)
        ok = False

    try:
        from PIL import Image  # noqa
        print("Pillow : OK")
    except Exception as e:
        print("Pillow : 缺！", e)
        ok = False

    # adb（真机操作用）
    adb = os.path.join(os.path.dirname(_HERE), "_tools", "scrcpy",
                       "scrcpy-win64-v4.1", "adb.exe")
    print("adb    :", "OK" if os.path.exists(adb) else "没找到（%s）" % adb)

    print("-" * 56)
    print("结论   :", "可以开跑" if ok else "还差点东西，见上面")
    print("=" * 56)
    return ok


def main():
    argv = sys.argv[1:]

    if "--check" in argv:
        return 0 if check_env() else 1

    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
    except Exception as e:
        print("启动失败：没装 PySide6。")
        print("  命令行跑一次：pip install PySide6")
        print("  原始错误：%s" % e)
        return 2

    from ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Taku")
    app.setApplicationDisplayName("Taku · 拓客台")


    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
