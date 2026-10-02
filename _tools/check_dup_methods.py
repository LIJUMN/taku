# -*- coding: utf-8 -*-
"""
★★★ 重复方法扫描（第 41 轮建，每轮必跑）★★★

★ 它为什么存在（血泪）：
    第 41 轮发现 `CustRow` 的代码被编辑改断了——"名字/最后一句"那段
    被拼进了第一个 `mousePressEvent` 里，后面又定义了第二个同名方法
    把第一个**整个覆盖**。缩进完全合法、py_compile 全过、
    审计（点按钮看反应）也全绿 —— 但客户列表**只剩头像**，
    名字根本没画出来，用户对着一行头像加"移出"按钮，能不炸吗。

★ 这类伤的特点：
    · 语法完全合法（不会报错）
    · 行为被**静默改变**（前一个同名方法直接消失）
    · "点按钮看反应"式审计抓不到（它只查"点了变没变"，不查"该显示的显示全没"）

★ 本脚本查什么：
    1. 同一个类里的**同名方法**（后者覆盖前者 = 前一个白写）
    2. 顺带把模块级的同名函数也查了

用法：python _tools/check_dup_methods.py
"""
import ast
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)


def scan_dir(dirpath, label):
    problems = []
    for dirpath2, _dirs, files in os.walk(dirpath):
        if "__pycache__" in dirpath2 or "legacy" in dirpath2:
            continue
        for fn in sorted(files):
            if not fn.endswith(".py"):
                continue
            p = os.path.join(dirpath2, fn)
            try:
                src = open(p, encoding="utf-8").read()
                tree = ast.parse(src)
            except Exception:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    names = [n.name for n in node.body
                             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                    dup = sorted(set(n for n in names if names.count(n) > 1))
                    if dup:
                        problems.append("%s :: 类 %s 有同名方法覆盖：%s"
                                        % (os.path.relpath(p, _ROOT), node.name, dup))
            # 模块级同名函数
            top = [n.name for n in tree.body
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            dup = sorted(set(n for n in top if top.count(n) > 1))
            if dup:
                problems.append("%s :: 模块级同名函数覆盖：%s"
                                % (os.path.relpath(p, _ROOT), dup))
    return problems


def main():
    print("=" * 70)
    print("重复方法扫描（同名方法/函数会互相覆盖 —— 第 41 轮的病根）")
    print("=" * 70)
    problems = []
    problems += scan_dir(os.path.join(_ROOT, "src"), "src")
    problems += scan_dir(os.path.join(_ROOT, "_tools"), "_tools")

    if problems:
        for p in problems:
            print("  ✘", p)
        print("\n发现 %d 处 —— 同名 = 后一个把前一个整个覆盖，前一个就是死代码。" % len(problems))
        return 1
    print("  ✅ src 与 _tools 下所有类/模块：无同名方法覆盖")
    return 0


if __name__ == "__main__":
    sys.exit(main())
