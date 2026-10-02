# -*- coding: utf-8 -*-
"""
Taku · 路径（全软件只此一份）

★★★ 为什么要单独一个文件（第 34 轮踩的坑）★★★

同一个"项目根目录"，各文件各算各的，结果算出了**两个不同的根**：

    src/ui/pages_settings.py   here = src/ui → dirname(dirname(here)) = 项目根  ✅
    src/ui/store.py            dirname(dirname(__file__))             = src      ❌
    src/ui/main_window.py      dirname(dirname(__file__))             = src      ❌
    src/ui/pages_stats.py      dirname(dirname(__file__))             = src      ❌

后果（真发生过）：
    · 数据仓库 store.json 落到了 `src/data/`，而备份/导出落在根目录 `data/`
      → 用户在 `data/` 里**找不到自己的数据**，备份也压根没带上它。
    · 统计导出、首次引导标记，也都跑到 `src/data/` 下面去了。

修法：**只留这一份实现**，谁要路径都来这儿拿。以后改一处就够了。
"""

import os
import sys


def project_root():
    """
    项目根目录。

    ★ 三种运行方式都要对（踩过坑 21）：
      · 打包成 exe（--onefile）：资源被解到临时目录 sys._MEIPASS，
        但**数据要放在 exe 旁边**，不然用户找不到、卸载也带不走。
      · 打包成 exe（--onedir / frozen）：sys.executable 旁边。
      · 从源码跑：往上三级就是项目根。
    """
    if getattr(sys, "_MEIPASS", None) or getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    # src/ui/paths.py → src/ui → src → 项目根
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def data_dir():
    """数据目录（不存在就建）。全软件的数据都在这儿。"""
    d = os.path.join(project_root(), "data")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def sub_dir(*parts):
    """data 下面的子目录，比如 sub_dir("shots", "ai_runs")。"""
    d = os.path.join(data_dir(), *parts)
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d
