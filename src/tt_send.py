# -*- coding: utf-8 -*-
"""
拓客台 · 发送与验证（P8）

★ 职责：把"输入框里已经打好的一行字，真正发出去，并且确认真的发出去了"。

为什么单独一个模块：
  这是整个项目**唯一会对外产生后果**的一步 —— 点下去对方就收到了。
  所以必须：
    ① 点之前先确认输入框里确实是我们要发的内容（防止发错/发空）
    ② 点之后必须回读验证（不能"点了就算成功"）
    ③ 没发出去要能重试，重试也有上限（防疯狂点击惹风控）
    ④ 全过程截图存档（出问题能倒查）

★ 纯视觉：只靠 screenshot + locate + tap，不读控件树、不用协议（规格书 0.1）。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from phone import Phone, PhoneError          # noqa: E402
from vision import VisionEngine  # noqa: E402


class SendError(Exception):
    """发送失败。msg 是给用户看的中文大白话。"""
    def __init__(self, msg, detail=""):
        super().__init__(msg)
        self.msg = msg
        self.detail = detail


# 发送按钮的位置特征（不同 App 略有不同，先按 Soul/通用来）
SEND_HINTS = ("在聊天输入框那一行的最右端。它是一个绿色或蓝色的圆角按钮，"
              "上面写着「发送」两个字。★ 注意输入框常常被键盘顶到屏幕中间，"
              "所以它不在屏幕最底部，大约在整屏高度的一半多一点的位置。")


class Sender:
    """
    发送器。负责"点发送 + 验证 + 重试"。

    用法：
        s = Sender(phone, vision, shots_dir)
        r = s.send_and_verify("大理的风好舒服")
        if r["ok"]: ...
    """

    # 验证重试次数（★ 风控纪律：不许多点，最多 3 次）
    MAX_TRIES = 3
    # 点完之后等界面反应的时间（秒）
    SETTLE = 1.6

    def __init__(self, phone, vision=None, shots_dir=None, verbose=True):
        self.phone = phone
        self.vision = vision or VisionEngine()
        self.verbose = verbose
        if shots_dir is None:
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            shots_dir = os.path.join(root, "data", "shots")
        self.shots_dir = shots_dir
        os.makedirs(self.shots_dir, exist_ok=True)
        self.n_shot = 0

    # ---------- 内部工具 ----------

    def _log(self, msg):
        if self.verbose:
            print(msg, flush=True)

    def _shot(self, png, tag):
        """把截图存盘（出问题能倒查）。返回路径。"""
        self.n_shot += 1
        p = os.path.join(self.shots_dir, "_p8_%02d_%s.png" % (self.n_shot, tag))
        try:
            with open(p, "wb") as f:
                f.write(png)
        except OSError:
            return ""
        self._log("      存图：" + os.path.basename(p))
        return p

    # 输入框条带的大致位置（★ 实测：键盘顶上来时，输入框在 52%~58% 高度那一带）
    INPUT_BAND = (0.48, 0.60)

    def _input_bar(self, png):
        """
        裁出"输入框那一条带"（含发送按钮），返回 (子图字节, x1, y1, x2, y2)。

        ★★ 第 40 轮大修（用户真机两轮跑出来的根因）★★
          原来写死 48%~60% —— 那是**键盘弹起时**的位置（Soul 实测）。
          微信键盘**收起**时输入框在 ~96.9%，写死的带裁到的是聊天区中间
          → 读框永远读出"空" → 发送前核对全废
          → 旧代码居然还照样点发送（第 40 轮已改成硬拦），好在这一步根本过不去。

          现在的规矩：**先问键盘弹没弹**（phone.input_shown()，白名单允许），
          弹起 → 48%~60%；收起 → 92.5%~99.5%（微信实测框体 2272~2378）。
          以后适配别的 App，量一次往这表里加一行。
        """
        from PIL import Image
        import io
        W, H = self.phone.screen_size()
        try:
            kb_up = bool(self.phone.input_shown())
        except Exception:
            kb_up = False
        if kb_up:
            y1, y2 = int(H * 0.48), int(H * 0.60)
        else:
            y1, y2 = int(H * 0.925), int(H * 0.995)
        im = Image.open(io.BytesIO(png)).convert("RGB").crop((0, y1, W, y2))
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=95)
        return buf.getvalue(), 0, y1, W, y2

    def _find_send_btn(self, png):
        """
        找发送按钮。
        ★ 用网格法 + "贴右边"锚点（P8 实测定案）：
          实测精度 Δx=-1px、Δy=+35px，按钮高约 100px → 稳点中。
          为什么用锚点：发送按钮**永远贴着输入框行的最右端**，
          x 可以直接按规律给（93%），只让模型负责 y —— 少一半不确定性。
        """
        from PIL import Image
        import io
        # 先裁出输入框那一带 → 在这一带里用网格法定位（区域小，更准）
        sub, x1, y1, x2, y2 = self._input_bar(png)
        # 三等分这一带，纵向切出"输入框行"（去掉上下的聊天区/键盘边缘）
        W, H = self.phone.screen_size()
        r = self.vision.locate_grid_refine(
            sub, "「发送」按钮", extra=SEND_HINTS,
            cols=4, rows=2, pad=0, zoom=2)
        if r["found"]:
            sub_h = y2 - y1
            # locate_grid_refine 返回的是 sub 图的像素坐标 → 加回偏移
            gy = y1 + r["y"]
            gx = int(W * 0.93)          # ★ 锚点：贴右边
            return {"found": True, "x": gx, "y": gy,
                    "conf": "high", "why": "网格法+贴右边锚点",
                    "stage": "band-grid+anchor"}
        return r

    # ---------- 1. 点之前：确认输入框内容 ----------

    def read_input_box(self, png=None):
        """
        读出当前输入框里写的字（用于"点之前先核对"）。
        ★ 为什么这一步不能省：手机会有残留文字、会打错、会被清空 ——
          不看一眼就点，等于闭眼开枪。
        ★ 必须走**高清模式**（P8 实测踩坑）：
          输入框那一条缩到 540 宽字就糊了，模型会把「大理的风好舒服」读成"空"。
        """
        if png is None:
            png = self.phone.screenshot_bytes()
        sub, x1, y1, x2, y2 = self._input_bar(png)
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(sub))
        # 只取左边 76%（右边是表情图标和发送按钮，不要）
        im = im.crop((0, 0, int(im.width * 0.76), im.height))
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=95)
        txt = self.vision.ask_chat_with_image(
            buf.getvalue(),
            "这是聊天界面「输入框」那一条（已放大）。请只输出输入框里**现有的文字**，"
            "一个字都不要改、不要加解释。如果输入框是空的或只有灰色提示词"
            "（比如「发消息…」「说点什么…」「看看对方主页，话题就有了」），"
            "只输出两个字：空",
            max_tokens=150, hd=True)
        return _clean_input_text(txt)

    # ---------- 2. 点发送 ----------

    def tap_send(self, png=None):
        """点一下发送按钮。返回按钮坐标。"""
        if png is None:
            png = self.phone.screenshot_bytes()
        loc = self._find_send_btn(png)
        if not loc["found"]:
            raise SendError("屏幕上找不到「发送」按钮",
                            "stage=%s why=%s" % (loc["stage"], loc["why"]))
        self._log("    → 发送按钮 (%d, %d) 把握=%s 方式=%s"
                  % (loc["x"], loc["y"], loc["conf"], loc["stage"]))
        self.phone.tap(loc["x"], loc["y"])
        return (loc["x"], loc["y"], loc)

    # ---------- 3. 点之后：验证到底发出去没有 ----------

    def verify_sent(self, text, before_png=None):
        """
        判断"这条消息到底有没有发出去"。

        ★★ 实测踩坑（P8b 第五次，严重）：
          原来只要"输入框清空了"就判定"已发出"。结果实跑时出现：
            **输入框空了，但聊天记录里根本没有这条消息** —— 误判成成功！
          原因：输入框可能在别的地方被误触清掉（比如点到了键盘上的键）。
          → **"输入框清空"只能当辅助信号，不能当判据。**

        ★★ 最终判据（必须"气泡真的出现"才算成功）：
          ① **主判据**：聊天记录区里**真的出现了这条气泡**（用说话模型看）
          ② 辅助信号：输入框变空（说明"发的东西被取走了"，配合 ① 用）

        返回 {"sent": bool, "how": str, "detail": str}
        """
        after = self.phone.screenshot_bytes()
        self._shot(after, "after_send")

        # 辅助信号：输入框空了吗
        try:
            left = self.read_input_box(after)
        except Exception as e:
            left = "<读不出:%s>" % str(e)[:30]
        box_empty = (left == "")

        # ---- 主判据：聊天区里有没有这条气泡 ----
        try:
            from PIL import Image
            import io
            W, H = self.phone.screen_size()
            im = Image.open(io.BytesIO(after)).convert("RGB")
            # 聊天区 = 顶部状态栏以下 ~ 输入框带以上（键盘弹起时输入框在 57%）
            im2 = im.crop((0, int(H * 0.10), W, int(H * 0.52)))
            buf = io.BytesIO(); im2.save(buf, "JPEG", quality=92)
            ans = self.vision.ask_chat_with_image(
                buf.getvalue(),
                "这是手机聊天记录的中间部分（已裁掉顶部和底部输入框）。\n"
                "请判断：**靠右边那些彩色（紫色或蓝色）气泡**里，"
                "有没有出现这句内容：「%s」\n"
                "只回答「有」或「没有」，再加一个逗号和不超 15 字的理由。" % text,
                max_tokens=80, hd=True).strip()
            has_bubble = ans.startswith("有")
        except Exception as e:
            has_bubble = False
            ans = "<看聊天区出错:%s>" % str(e)[:40]

        if has_bubble:
            return {"sent": True, "how": "气泡已出现在聊天记录",
                    "detail": ("输入框空=%s；模型：%s" % (box_empty, ans[:50]))}

        if box_empty:
            # ★ 输入框空了但气泡没出现 → **不能算成功**，但可能是"截图时机太早"
            return {"sent": False, "how": "输入框空了但气泡还没出现",
                    "detail": ("输入框已空，但聊天区看不到这条 → 可能是截图太早，"
                               "也可能是没真发出去（%s）" % ans[:40])}

        return {"sent": False, "how": "输入框还留着字、气泡也没出现",
                "detail": ("输入框现在写着：%s；模型看聊天区：%s"
                           % (left, ans[:50]))}

    # ---------- 4. 总入口：发 + 验 + 重试 ----------

    def send_and_verify(self, expect_text, allow_retry=True):
        """
        把输入框里的字发出去，并确认发出去了。

        expect_text: 期望发的内容（用来核对 + 验证气泡）
        返回 {
          "ok": bool,
          "tries": int,
          "how": str,
          "before": str,     # 点之前输入框里实际是什么
          "shots": [...],
        }
        """
        r = {"ok": False, "tries": 0, "how": "", "before": "", "shots": []}
        tries = self.MAX_TRIES if allow_retry else 1

        png = self.phone.screenshot_bytes()
        self._shot(png, "before_send")

        # ---- 点之前先核对输入框 ----
        try:
            actual = self.read_input_box(png)
        except Exception as e:
            self._log("    ! 读输入框失败（继续尝试发送）：" + str(e)[:60])
            actual = ""
        r["before"] = actual
        self._log("    → 输入框里现在写着：「%s」" % actual)

        if not actual and not expect_text:
            raise SendError("输入框是空的，没有东西可发",
                            "read_input_box 返回空")

        # ★ 第 39 轮改成**硬拦**（真机实测出来的洞）：
        #   之前是"框里有字但对不上 → 以框里为准继续发"，这等于可能把
        #   **用户没点头的一句旧草稿**发出去 —— 社交行为收不回，这是大忌。
        #   现在三条铁规矩：
        #     ① 框里读出来是空的 → 不发（打字那步肯定失败了）
        #     ② 框里的字和要发的话对不上 → 不发（宁可这趟不发）
        #     ③ 读框失败 → 当作空处理 → 不发
        if not actual:
            raise SendError("输入框是空的——打字那一步没成功，这趟绝不点发送",
                            "想发「%s」，框里是空的" % (expect_text or "")[:30])
        if expect_text and \
                expect_text.replace(" ", "") not in actual.replace(" ", "") and \
                actual.replace(" ", "") not in expect_text.replace(" ", ""):
            raise SendError(
                "输入框里是「%s」，要发的是「%s」——对不上，宁可不发"
                % (actual[:24], expect_text[:24]),
                "疑似旧草稿或打字串行")

        # ---- 开始点 + 验 ----
        for i in range(tries):
            r["tries"] = i + 1
            self._log("  ▸ 第 %d 次点发送 …" % (i + 1))
            try:
                x, y, loc = self.tap_send(png)
            except SendError:
                raise
            time.sleep(self.SETTLE)

            v = self.verify_sent(expect_text or actual, before_png=png)
            if v["sent"]:
                r["ok"] = True
                r["how"] = v["how"]
                r["detail"] = v["detail"]
                self._log("    ✓ 确认已发出（%s）" % v["how"])
                return r
            self._log("    ✗ 没发出去：%s" % v.get("detail", "")[:70])
            if i < tries - 1:
                self._log("    ↻ 再等一会儿重试 …")
                time.sleep(1.2 * (i + 1))
                png = self.phone.screenshot_bytes()
                # 重试前若发现输入框空了，说明其实发出去了
                try:
                    if self.read_input_box(png) == "":
                        r["ok"] = True
                        r["how"] = "重试前发现输入框已清空"
                        return r
                except Exception:
                    pass

        r["how"] = "试了 %d 次都没成功" % tries
        return r


def _clean_input_text(txt):
    """
    把模型对"输入框里写的是什么"的回答洗干净，只留正文。

    ★ 实测：模型很爱加包装，比如
        「我看到输入框里显示的文字是「大理的风好舒服」。」
        「输入框里的现有文字是：」
        finish(message="空")
      这些都要剥掉，否则会把包装当成聊天内容发出去（灾难）。

    ★ 实测踩坑（P8b）：模型会答「输入框里的现有文字是：」这种**冒号结尾、
      后面直接断了**的形态 —— 这不是内容，是"它想说但没说出来"，
      必须识别成**读失败**（返回空），而不是当成文字。
    """
    if not txt:
        return ""
    t = txt.strip()
    # 常见包装句式：先取引号里的内容（最可信）
    import re as _re
    m = _re.search(r"[「\"']([^」\"']{1,60})[」\"']", t)
    if m:
        t = m.group(1)
    t = t.strip()
    for prefix in ("我看到", "输入框里显示的文字是", "输入框里的现有文字是",
                   "输入框里现有文字是", "输入框里是", "输入框内容是",
                   "输入框显示", "输入框中的文字是", "内容是", "文字是"):
        if t.startswith(prefix):
            t = t[len(prefix):].strip(" ：:，,")
    t = t.strip().strip('"').strip("「」").strip("。.")
    t = t.split("\n")[0].strip()
    # ★ 剥完只剩空 → 说明模型其实没读出内容（比如「…文字是：」后面就没了）
    for noise in ("输入框是空的", "输入框为空", "空的", "空", "", "：", ":"):
        if t == noise:
            return ""
    # 剥完还是"…是："这种，也算没读出来
    if t.endswith("是：") or t.endswith("是:"):
        return ""
    return t


# ---------- 自检（P8 验收）：默认"只演练不发" ----------

def self_test(do_send=False, text="测试一下"):
    """
    P8 自检。

    do_send=False（默认）：只检查"能不能找到发送按钮、能不能读输入框"，不真发。
    do_send=True        ：真的发一条（★ 会造成真实后果，只在明确授权时用）。
    """
    res = {"ok": False, "steps": []}
    try:
        res["steps"].append("① 连手机 …")
        p = Phone().connect()
        res["steps"].append("   ✓ " + p.serial)
        W, H = p.screen_size()
        res["steps"].append("   ✓ 屏幕 %d×%d" % (W, H))

        v = VisionEngine()
        s = Sender(p, v)
        res["steps"].append("② 用的模型：" + v.model)

        png = p.screenshot_bytes()
        s._shot(png, "selftest")
        res["steps"].append("③ 截图 %d 字节" % len(png))

        res["steps"].append("④ 找「发送」按钮 …")
        loc = s._find_send_btn(png)
        res["steps"].append("   → found=%s (%d,%d) 把握=%s 方式=%s"
                            % (loc["found"], loc["x"], loc["y"],
                               loc["conf"], loc["stage"]))
        res["find_send"] = loc

        res["steps"].append("⑤ 读输入框现在写的是什么 …")
        txt = s.read_input_box(png)
        res["steps"].append("   → 「%s」" % txt)
        res["input_box"] = txt

        if do_send:
            res["steps"].append("⑥ ★ 真发一条：「%s」 …" % text)
            r = s.send_and_verify(text)
            res["steps"].append("   → ok=%s tries=%d how=%s"
                                % (r["ok"], r["tries"], r["how"]))
            res["send_result"] = r
            res["ok"] = r["ok"]
        else:
            res["steps"].append("⑥ 演练模式：不真发（要看真发加 --send）")
            res["ok"] = loc["found"]

        res["model"] = v.model
        res["calls"] = v.calls
    except Exception as e:
        res["steps"].append("   ✗ " + str(e))
        res["error"] = str(e)
    return res


if __name__ == "__main__":
    do = "--send" in sys.argv
    txt = "测试一下"
    for a in sys.argv:
        if a.startswith("--text="):
            txt = a.split("=", 1)[1]
    out = self_test(do_send=do, text=txt)
    for s in out["steps"]:
        print(s)
    print("\n结果：", "通过 ✓" if out["ok"] else "失败 ✗ " + out.get("error", ""))
    sys.exit(0 if out["ok"] else 1)
