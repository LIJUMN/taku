# -*- coding: utf-8 -*-
"""
拓客台 · 通知监听（Plan B：ADB 轮询，无需手机端 APK）
M2 事件闭环的通知来源。默认实现是自研 NotificationListener APK（待 JDK 环境搭好后构建，
见明日事项）；本模块为降级方案，用 adb shell dumpsys notification 轮询，纯 PC 侧、只读。

用法：
  python notify_poll.py --once        # 拉一次当前通知并打印（自检用）
  python notify_poll.py --interval 3  # 持续轮询，新通知入库并打印
"""
import argparse, re, subprocess, sys, time, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tt_db import TuokeDB

ADB = r"C:\Users\Administrator\Desktop\手机自动\_tools\scrcpy\scrcpy-win64-v4.1\adb.exe"
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "tuoke.db")

REC = re.compile(r"NotificationRecord\(0x[0-9a-f]+:\s*pkg=([^\s]+).*?\n\s*key=([^\s]+)", re.S)
KEYLEN = re.compile(r"android\.(title|text)=String \[length=(\d+)\]")


def dump_notifications():
    """执行 dumpsys notification，返回原始文本。"""
    for flag in (["--noredact"], []):
        try:
            r = subprocess.run([ADB, "shell", "dumpsys", "notification"] + flag,
                               capture_output=True, timeout=60)
            if r.returncode == 0 and r.stdout:
                return r.stdout.decode("utf-8", "replace")
        except subprocess.TimeoutExpired:
            pass
    return ""


def parse(text):
    """解析通知记录 → [(platform, notif_id, title, text)]
    说明（2026-10-02 实测）：realme/Android 16 的 dumpsys 对通知内容脱敏，
    title/text 只给长度不给内容。本模块定位为"触发层"：通知来了即知
    （pkg+key），内容由 AutoGLM 切屏后视觉模型读取，符合 PRD 事件驱动架构。"""
    out = []
    for m in REC.finditer(text):
        pkg, key = m.group(1), m.group(2)
        out.append((pkg, key, "", ""))
    return out


def poll_once(db):
    text = dump_notifications()
    if not text:
        print("[warn] dumpsys 无输出，确认手机 USB 已连接且 adb devices 可见")
        return 0
    items = parse(text)
    new = 0
    for pkg, key, title, txt in items:
        if db.dedupe_notification(pkg, key, title, txt):
            print("[新通知] %s | %s | %s" % (pkg, title, txt))
            new += 1
    return new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="只拉一次")
    ap.add_argument("--interval", type=int, default=3, help="轮询间隔秒")
    args = ap.parse_args()

    db = TuokeDB(DB)
    if args.once:
        n = poll_once(db)
        print("parsed_total=%d new=%d" % (len(parse(dump_notifications())), n))
        return
    print("开始轮询（Ctrl+C 停止），间隔 %ds" % args.interval)
    while True:
        try:
            poll_once(db)
        except Exception as e:
            print("[error]", repr(e))
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
