# -*- coding: utf-8 -*-
r"""
拓客台 · 启动器（PyInstaller 入口）
- 从 config\config.json 读取智谱 Key（外置，§16 拍板）
- 内置 adb/scrcpy（frozen 模式自动加入 PATH）
- 无参数启动 → AutoGLM 交互模式；可传任务参数直接执行
用法：
  拓客台.exe                      → 交互模式（输入任务操作手机）
  拓客台.exe 打开陌陌              → 直接执行任务
"""
import importlib.util
import json
import os
import sys


def _base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _load_zhipu_cfg():
    for base in (_base_dir(), os.path.dirname(_base_dir())):
        p = os.path.join(base, "config", "config.json")
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    cfg = json.load(f)
                return cfg.get("zhipu", {})
            except Exception:
                return {}
    return {}


def main():
    # 0) 强制 UTF-8 输出（frozen 控制台默认 GBK，会崩在 ✓ 等字符上）
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    # 1) 内置 adb/scrcpy 加入 PATH（frozen 模式）
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        scrcpy_dir = os.path.join(meipass, "scrcpy")
        if os.path.isdir(scrcpy_dir):
            os.environ["PATH"] = scrcpy_dir + os.pathsep + os.environ.get("PATH", "")

    # 2) 从外置 config 注入模型参数（未显式指定时）
    z = _load_zhipu_cfg()
    if not any(a in sys.argv for a in ("--base-url",)) and z.get("base_url"):
        sys.argv += ["--base-url", z["base_url"]]
    if not any(a in sys.argv for a in ("--model",)) and z.get("model"):
        sys.argv += ["--model", z["model"]]
    if not any(a in sys.argv for a in ("--apikey",)) and z.get("api_key"):
        sys.argv += ["--apikey", z["api_key"]]
    if not z.get("api_key"):
        print("未找到 config\\config.json 或其中缺少 zhipu.api_key，请先填写（模板：config\\config.example.json）")
        return 1

    # 3) 引入 Open-AutoGLM 主程序并进入其 main()
    src = os.path.join(os.path.dirname(_base_dir()), "Open-AutoGLM")
    if os.path.isdir(src) and src not in sys.path:
        sys.path.insert(0, src)
    import main as autoglm_main
    autoglm_main.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
