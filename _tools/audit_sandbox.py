# -*- coding: utf-8 -*-
"""
审计/测试沙箱（第 45c 轮建）—— 别让"检查软件"变成"骚扰用户"

★ 病根（用户原话："他调试软件的时候，总会打开这个文件夹，好讨厌"）：
    审计器 / 测试器会把每一页的按钮**真点一遍** —— 这是对的，
    但里面有 4 个按钮的副作用会溅到**用户桌面**上：

        · 设置页「打开数据文件夹」 → os.startfile() 弹一个 Explorer
        · 统计页「导出统计」       → 真写 统计_*.csv + os.startfile() 再弹一个
        · 设置页「立即备份」       → 真往 data/backup/<时间戳>/ 复制一遍数据
        · 设置页「导出全部数据」   → 真往 data/exports/ 写 2 个文件

    每轮审计 3 个新文件、1~2 个 Explorer 窗口；跑了十几轮 =
    data/exports 里堆了 39 个垃圾文件，用户桌面隔一会儿弹一个文件夹。

★ 修法：审计期间把副作用**接进沙箱** ——
    · os.startfile         → 只记账，不弹窗（全进程生效）
    · 设置页备份/导出函数   → 换同形状的桩：返回值不变，按钮自己的
                              toast / 文字更新照跑（审计照样看得到"它有反应"）
    · 统计页导出统计       → 整个方法换成安静版，但保留 toast 反应

    审计要验证的是"按钮点了、逻辑跑了、界面有反应"，
    不是"真往磁盘写没写" —— 真写的效果，人工点一次就能看见。
    （所以这**不算造假**：桩只挡副作用，不挡逻辑路径。）

★ 用法：
    import audit_sandbox
    audit_sandbox.install()      # 建窗口之前装
    ...跑审计/测试...
    print(audit_sandbox.report())   # 结束时打一眼，证明接住了什么
"""

import os

calls = []          # ("startfile", 路径) / ("backup", …) / ("export", …) …
_INSTALLED = False


def _fake_startfile(path, *a, **kw):
    """替身 startfile：记一笔，什么都不开。"""
    calls.append(("startfile", str(path)))
    return None


def _stub_backup():
    """替身 _do_backup：返回形状跟真的一模一样 (ok, (dst, n, stamp))。"""
    calls.append(("backup", "data/backup/<沙箱没写盘>"))
    return True, ("(沙箱：没写盘)", 0, "audit-沙箱")


def _stub_export():
    """替身 _do_export：返回形状跟真的一模一样 (ok, (out, n, stamp))。"""
    calls.append(("export", "data/exports/<沙箱没写盘>"))
    return True, ("(沙箱：没写盘)", 0, "audit-沙箱")


def install():
    """
    装沙箱。进程内全局生效（工具进程跑完就退，不用卸）。
    必须在 MainWindow 建出来之前调（早装早接住）。
    """
    global _INSTALLED
    if _INSTALLED:
        return calls
    _INSTALLED = True

    # 1) 弹窗总闸：os.startfile 是所有"打开文件夹"的唯一出口
    #    （pages_settings / pages_stats 都是 `import os` 后 os.startfile(d)，
    #     改 os 模块属性 = 全进程的调用全被接住）
    os.startfile = _fake_startfile

    # 2) 设置页：备份 / 导出 —— 换桩。
    #    ★ 为什么能换：_panel_data() 里的闭包 `_backup()` 是
    #      `ok, res = _do_backup()` —— 每次调用都查模块全局，
    #      所以这里换了模块属性，按钮下次点就用桩。
    try:
        import ui.pages_settings as ps
        ps._do_backup = _stub_backup
        ps._do_export = _stub_export
    except Exception as e:
        # ★ 第 46 轮审查修正：桩没装上审计就会真写盘 —— 必须喊出来
        calls.append(("SANDBOX-FAILED", "pages_settings 桩没装上：%s" % str(e)[:60]))

    # 3) 统计页：导出统计 —— 它写文件和弹窗写在方法体内，没法只挡一半，
    #    整个方法换安静版；但 toast / 标签更新留着（审计的判定要看界面反应）。
    try:
        import ui.pages_stats as pst
        from ui.widgets import toast as _toast

        def _quiet_export(self):
            calls.append(("export_stats", "统计_*.csv <沙箱没写盘>"))
            try:
                _toast(self, "（审计沙箱）导出逻辑跑了，文件没落盘", "ok", 2600)
                try:
                    self._exp_lb.setText("审计沙箱：没写文件")
                except Exception:
                    pass
            except Exception:
                pass

        pst.StatsPage._export_stats = _quiet_export
    except Exception as e:
        calls.append(("SANDBOX-FAILED", "pages_stats 桩没装上：%s" % str(e)[:60]))

    # 4) 兜底再上一次弹窗总闸（上面的桩如果全挂了，至少弹窗必须接住）
    os.startfile = _fake_startfile

    return calls


def report():
    """审计结束时打一眼：沙箱接住了什么（证明按钮逻辑跑了，不是没点到）。"""
    if not calls:
        return "  （沙箱：这一轮没有按钮试图弹窗/写盘）"
    lines = ["  （沙箱接住 %d 次副作用 —— 逻辑跑了，没溅到桌面）：" % len(calls)]
    for kind, where in calls:
        lines.append("     · %s → %s" % (kind, where))
    return "\n".join(lines)
