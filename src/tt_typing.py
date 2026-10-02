# -*- coding: utf-8 -*-
"""
拓客台 · 打字输入（P7）

★ 为什么用 ADB Keyboard 广播？
  中文打不进 `input text`（它只认 ASCII，中文会变乱码）。
  ADB Keyboard 是个特殊输入法，收到广播就把文字"敲"进当前输入框，
  全程相当于在手机上打字 —— **属于纯视觉允许范围**（规格书 1.2.1 白名单）。

★ 三级降级链（规格书 1.3.1）
  ① 首选：ADB Keyboard 广播（支持中文、最快）
  ② 兜底：`input text`（只支持 ASCII，英文数字用）
  ③ 都失败：报告失败，交 AI 判断（规格书 1.7：AI 判断失败取最保守动作）

★ ★ 输入法看门狗（规格书 1.10.1，极重要）
  用 ADB Keyboard 时必须临时切走用户的输入法；
  **干完活必须切回来**，否则用户自己拿手机打字会打不了。
  规则：1 秒内不再发新动作 + 再等最多 0.8s 收尾（给输入法时间恢复）。
"""
import re
import time

# ADB Keyboard 的包名 / 组件名（固定值）
ADB_IME = "com.android.adbkeyboard/.AdbIME"
# 广播动作
ACTION_INPUT = "ADB_INPUT_TEXT"
ACTION_CLEAR = "ADB_CLEAR_TEXT"
ACTION_B64 = "ADB_INPUT_B64"      # base64 传中文，避免 shell 转义问题


class TypeError_(Exception):
    """打字失败。msg 是给用户看的中文大白话。"""
    def __init__(self, msg, detail=""):
        super().__init__(msg)
        self.msg = msg
        self.detail = detail


class Typist:
    """
    给手机打字。

    用法（推荐用 with，保证输入法一定被还原）：
        with Typist(phone) as t:
            t.type_text("你好呀，在忙吗？")
        # 出 with 块时自动切回原输入法
    """

    # 收尾等待：给输入法时间回到原位（规格书 1.10.1 拍板值）
    SETTLE = 0.8

    def __init__(self, phone):
        self.p = phone
        self.orig_ime = None       # 用户原本的输入法
        self.switched = False      # 是否切过（决定要不要还原）

    # ---- 输入法状态 ----

    def current_ime(self):
        """读当前输入法（白名单允许：读输入法不算"读屏幕"）"""
        out, _, _ = self.p._run(["shell", "settings", "get", "secure",
                                 "default_input_method"])
        return (out or "").strip()

    def list_imes(self):
        """手机上装了哪些输入法"""
        out, _, _ = self.p._run(["shell", "ime", "list", "-s"])
        return [x.strip() for x in (out or "").splitlines() if x.strip()]

    def has_adb_keyboard(self):
        return any("adbkeyboard" in x.lower() for x in self.list_imes())

    # ---- 切换（带看门狗：记住原输入法，用完必须还原） ----

    def switch_to_adb(self):
        if not self.has_adb_keyboard():
            raise TypeError_(
                "手机还没装打字插件（ADB Keyboard）",
                "adbkeyboard not installed")
        if self.orig_ime is None:
            self.orig_ime = self.current_ime()
        self.p._run(["shell", "ime", "enable", ADB_IME])
        self.p._run(["shell", "ime", "set", ADB_IME])
        self.switched = True
        time.sleep(0.4)          # 给系统切换时间
        return self

    def restore(self):
        """★ 看门狗：把输入法还给用户。不还原 = 用户手机打不了字。"""
        if self.switched and self.orig_ime:
            time.sleep(min(self.SETTLE, 0.8))
            self.p._run(["shell", "ime", "set", self.orig_ime])
            time.sleep(0.2)
            self.switched = False
        return self

    def __enter__(self):
        self.switch_to_adb()
        return self

    def __exit__(self, *a):
        self.restore()
        return False

    # ---- 打字 ----

    def type_text(self, text):
        """
        把 text 打进当前输入框。自动处理中文/英文。
        返回实际用的方式："b64" | "text"
        """
        if not text:
            return "text"
        if not self.switched:
            self.switch_to_adb()

        # 含非 ASCII（中文等）→ 用 base64 广播（躲开 shell 转义地狱）
        if any(ord(c) > 127 for c in text):
            import base64
            b64 = base64.b64encode(text.encode("utf-8")).decode()
            self._broadcast(ACTION_B64, "--es", "msg", b64)
            time.sleep(0.35)
            return "b64"

        # 纯 ASCII → 先试 input text（更直接）
        safe = text.replace(" ", "%s")
        out, err, code = self.p._run(["shell", "input", "text", safe])
        if code == 0:
            time.sleep(0.25)
            return "text"
        # 失败就退回广播
        import base64
        b64 = base64.b64encode(text.encode("utf-8")).decode()
        self._broadcast(ACTION_B64, "--es", "msg", b64)
        time.sleep(0.35)
        return "b64"

    def clear(self):
        """清空输入框"""
        self._broadcast(ACTION_CLEAR)
        time.sleep(0.25)
        return self

    def _broadcast(self, action, *extra_args):
        cmd = ["shell", "am", "broadcast", "-a", action] + list(extra_args)
        out, err, code = self.p._run(cmd, timeout=20)
        if code != 0:
            raise TypeError_("打字失败，手机没接收",
                             (err or out or "")[:200])
        return out

    # ---- 按比例拟真打字（规格书 1.10.1 / 13.1 流派3：反AI腔） ----

    def type_human(self, text, per_char=0.12, max_total=8.0):
        """
        分段拟真打字：把文字拆成几段，中间留小停顿，模拟真人思考。
        ★ 单条不超过 max_total 秒（规格书拍板：避免撞 120s 超时）。
        """
        if not text:
            return
        # 按标点/长度切段
        parts = re.split(r"([，。！？、~…,\!?])", text)
        segs, cur = [], ""
        for i, p in enumerate(parts):
            cur += p
            if i % 2 == 1:            # 标点后切一刀
                segs.append(cur); cur = ""
        if cur.strip():
            segs.append(cur)

        # 控制在预算内
        n = max(1, len(segs))
        budget = min(max_total, per_char * max(len(text), 1) + n * 0.25)
        gap = min(0.9, budget / n)

        for s in segs:
            self.type_text(s)
            time.sleep(gap)


# ---------- 自检 ----------

def self_test(text="在吗？今天天气不错"):
    """真机自检：切输入法 → 打字 → 还原。会真的动手机。"""
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from phone import Phone, PhoneError
    r = {"ok": False, "steps": []}
    try:
        p = Phone().connect()
        t = Typist(p)
        r["steps"].append("① 检查 ADB Keyboard 是否已装 …")
        if not t.has_adb_keyboard():
            r["steps"].append("   ✗ 没装。需要先在手机上安装 _tools/ADBKeyboard.apk")
            r["error"] = "缺 ADB Keyboard"
            return r
        r["steps"].append("   ✓ 已装")

        r["steps"].append("② 记下原输入法 …")
        orig = t.current_ime()
        r["steps"].append("   ✓ 原输入法：" + orig)

        r["steps"].append("③ 切到 ADB Keyboard 并打一段字 …")
        with Typist(p) as tt:
            way = tt.type_text(text)
        r["steps"].append("   ✓ 已打入（方式：%s）：%s" % (way, text))

        r["steps"].append("④ 输入法看门狗：还原 …")
        now = t.current_ime()
        ok_back = (now == orig)
        r["steps"].append(("   ✓ 已还原：" if ok_back else "   ✗ 没还原！现在是：") + now)

        r["ok"] = ok_back
        r["orig_ime"] = orig
    except Exception as e:
        r["steps"].append("   ✗ " + str(e))
        r["error"] = str(e)
    return r


if __name__ == "__main__":
    res = self_test()
    for s in res["steps"]:
        print(s)
    print("\n结果：", "通过 ✓" if res["ok"] else "失败 ✗ " + res.get("error", ""))
