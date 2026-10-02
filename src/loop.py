# -*- coding: utf-8 -*-
"""
拓客台 · 事件闭环主循环（M2 核心）
链路：通知触发 → 平台判定 → 活跃时段检查 → 生成回复 → 手机执行 → 落库
用法：
  python loop.py --dry --test      # 模拟一条陌陌来消息，只生成+落库，不操作手机（今晚验证）
  python loop.py --dry --once      # 真实轮询一轮，不操作手机
  python loop.py --once            # 真实轮询一轮，AutoGLM 实际回复（需陌陌已登录）
  python loop.py                   # 持续运行（Ctrl+C 停止）
"""
import argparse, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tt_db import TuokeDB
from tt_engine import ChatEngine, VisionEngine, DEFAULT_PERSONA, DEFAULT_PROFILE
from notify_poll import poll_once, dump_notifications, parse

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "tuoke.db")
MOMO_PKGS = ("momo", "immomo", "陌陌", "com.immomo")
ACTIVE_HOURS = "19:00-23:00"   # 默认活跃时段（settings 可改）


def in_active_hours():
    try:
        db = TuokeDB(DB)
        spec = db.get_setting("active_hours", ACTIVE_HOURS)
        a, b = spec.split("-")
        ah, am = map(int, a.split(":"))
        bh, bm = map(int, b.split(":"))
        now = time.localtime()
        cur = now.tm_hour * 60 + now.tm_min
        return ah * 60 + am <= cur <= bh * 60 + bm
    except Exception:
        return True


def is_momo(pkg):
    return any(k in (pkg or "").lower() for k in MOMO_PKGS)


def handle_event(db, ce, ve, pkg, title, text, dry=True):
    """一条新通知 → 判定 → 生成 → （执行）→ 落库"""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    if not is_momo(pkg):
        print("[跳过] 非主平台:", pkg)
        return
    if not in_active_hours():
        print("[跳过] 非活跃时段")
        return

    # 客户档案：按平台+昵称兜底（通知内容脱敏时用占位）
    cid = db.upsert_customer(platform="momo", nickname=title or "未知",
                             summary="破冰期" if not text else None)
    history = [{"sender": "other", "content": text}] if text else []
    reply = ce.generate(profile=DEFAULT_PROFILE, history=history, incoming=text or "在吗")

    if dry:
        print("[模拟回复] 客户=%s | %s" % (title, reply))
        db.add_message(cid, "ai", reply, strategy_note="dry-run", verified=0)
        return

    task = f"打开陌陌，找到最新对话，回复这条消息：{reply}，发送"
    print("[执行] AutoGLM 任务中…")
    out = ve.run_task(task)
    db.add_message(cid, "ai", reply, strategy_note="autoglm", verified=1)
    print("[执行完成] 输出尾部:\n" + out[-1500:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=int, default=5)
    ap.add_argument("--dry", action="store_true", help="不操作手机，只生成+落库")
    ap.add_argument("--test", action="store_true", help="模拟一条陌陌来消息")
    args = ap.parse_args()

    db = TuokeDB(DB)
    ce = ChatEngine()
    ve = None if args.dry else VisionEngine()

    if args.test:
        handle_event(db, ce, ve, "com.immomo.momo", "小鹿", "在吗 你是哪里人啊", dry=args.dry)
        return

    print("事件闭环运行中（dry=%s）…" % args.dry)
    while True:
        try:
            new = poll_once(db)
            if new:
                for pkg, key, title, text in parse(dump_notifications()):
                    handle_event(db, ce, ve, pkg, title, text, dry=args.dry)
        except Exception as e:
            print("[error]", repr(e))
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
