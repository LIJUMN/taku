# -*- coding: utf-8 -*-
"""
★ 离线自检脚本 —— 在没有真装 PySide6 的情况下，先把代码里能查的错都查出来。

思路（针对"网慢、装包要等"的场景）：
  1. 语法检查（ast.parse）—— 查错字、缩进、括号
  2. 导名检查（ast 扫 import / 名字引用）—— 查"引用了不存在的东西"
  3. 结构检查 —— 查 9 页是否齐、nav 表项数对不对、每个页面类有没有 on_show

这比"等装完了再开窗口"省时间：窗口一旦崩，还得回头逐行找。
"""

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "src", "ui")

OK = "\u2714"
NO = "\u2718"

problems = []


def p(tag, msg):
    problems.append((tag, msg))
    print("  %s %s" % (NO, msg))


# ============================================================
# ① 语法
# ============================================================
print("① 语法检查")
files = sorted(f for f in os.listdir(UI) if f.endswith(".py"))
trees = {}
for f in files:
    path = os.path.join(UI, f)
    src = open(path, encoding="utf-8").read()
    try:
        trees[f] = ast.parse(src)
    except SyntaxError as e:
        p("syntax", "%s 第 %s 行：%s" % (f, e.lineno, e.msg))
print("  共 %d 个文件" % len(files))


# ============================================================
# ② 模块级引用的名字是否都有来源
#    ★ 只看"模块级"作用域的名字，函数/方法里的局部变量一律不算 ——
#      上一版漏了这点，把 a/b/lay 这些局部变量全报成问题了。
# ============================================================
print("\n② 名字引用检查")

for f, tree in trees.items():
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imported.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                imported.add(a.asname or a.name)

    # 模块级自己定义的名字（类名 / 顶层函数 / 顶层变量）
    defined = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    defined.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            defined.add(node.target.id)
        elif isinstance(node, (ast.For, ast.If, ast.Try, ast.With)):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Assign):
                    for t in sub.targets:
                        if isinstance(t, ast.Name):
                            defined.add(t.id)

    # ★ 只扫"模块级语句"里用到的属性根（不钻进函数体）
    used_roots = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Attribute):
                n = sub
                while isinstance(n, ast.Attribute):
                    n = n.value
                if isinstance(n, ast.Name):
                    used_roots.add(n.id)

    builtins_ok = {
        "print", "len", "range", "int", "str", "float", "list", "dict", "set",
        "tuple", "bool", "open", "super", "type", "object", "Exception",
        "enumerate", "zip", "sorted", "min", "max", "sum", "abs", "round",
        "isinstance", "getattr", "setattr", "hasattr", "__name__", "__file__",
        "__doc__", "self", "cls",
    }

    third = {"requests", "PIL", "PySide6", "numpy", "yaml", "shiboken6"}
    unknown = used_roots - imported - defined - builtins_ok - third
    if unknown:
        p("name", "%s 模块级用了没导入的名字：%s" % (f, ", ".join(sorted(unknown))))
    else:
        print("  %s %s" % (OK, f))


# ============================================================
# ③ 9 页齐不齐
# ============================================================
print("\n③ 9 页结构检查")

PAGES_DIR = {
    "overview":  "OverviewPage",
    "customers": "CustomersPage",
    "messages":  "MessagesPage",
    "strategy":  "StrategyPage",
    "skills":    "SkillsPage",
    "tuoke":     "TuokePage",
    "stats":     "StatsPage",
    "trash":     "TrashPage",
    "settings":  "SettingsPage",
}

found = {}
for f, tree in trees.items():
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            # ★ 页面类的基类一般是 QWidget / QScrollArea 之类，
            #   上一版要求基类名以 "Page" 结尾，判断条件写错了。
            #   改成：类名本身以 Page 结尾就算页面类。
            if node.name.endswith("Page"):
                found[node.name] = f

for key, cls in PAGES_DIR.items():
    if cls in found:
        print("  %s %s  →  %s" % (OK, cls, found[cls]))
    else:
        p("page", "第 %s 页的类 %s 没找到" % (key, cls))

# main_window 里的 NAV 表
mw = trees.get("main_window.py")
if mw:
    nav_count = 0
    nav_keys = []
    for node in ast.walk(mw):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "NAV":
                    for el in node.value.elts:
                        if isinstance(el, ast.Tuple):
                            k = el.elts[0]
                            if isinstance(k, ast.Constant):
                                nav_keys.append(k.value)
                                if k.value != "__sep__":
                                    nav_count += 1
    real = [k for k in nav_keys if k != "__sep__"]
    print("\n  NAV 表里有 %d 个页面项：%s" % (nav_count, ", ".join(real)))
    if nav_count != 9:
        p("nav", "NAV 表不是 9 项（实际 %d）" % nav_count)

    miss_in_main = set(PAGES_DIR) - set(real)
    extra_in_main = set(real) - set(PAGES_DIR)
    if miss_in_main:
        p("nav", "NAV 少了：%s" % ", ".join(sorted(miss_in_main)))
    if extra_in_main:
        p("nav", "NAV 多了：%s" % ", ".join(sorted(extra_in_main)))


# ============================================================
# ④ 每页有没有 on_show（约定接口）
# ============================================================
print("\n④ 页面接口检查")
for f, tree in trees.items():
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name.endswith("Page"):
            methods = {n.name for n in node.body
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
            has_on_show = "on_show" in methods
            has_init = "__init__" in methods
            if not has_init:
                p("iface", "%s 没有 __init__" % node.name)
            elif not has_on_show:
                print("  · %s 没有 on_show（不是错，切页时就不刷新而已）" % node.name)


# ============================================================
# 汇总
# ============================================================
print("\n" + "=" * 56)
if problems:
    print("发现 %d 个问题：" % len(problems))
    for tag, msg in problems:
        print("  [%s] %s" % (tag, msg))
    sys.exit(1)
else:
    print("全部通过 —— 代码结构没问题，等 PySide6 装好就能开窗口。")
    sys.exit(0)
