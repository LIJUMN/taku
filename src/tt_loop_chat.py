# -*- coding: utf-8 -*-
"""
拓客台 · 聊天闭环（P8b）

★ 这是整个项目**第一条完整的一条龙**：
    看消息 → 想回复 → 打字 → 发送 → 验证 → 落库

在此之前，每个环节都是单独跑通的（P1 眼睛手 / P5 脑子 / P7 嘴 / P8 发送），
本模块把它们**串成一轮自动跑**，不需要人插手。

★ 一条龙的六步（每步都有回读，不许"点了就算成功"）：
  ① 看消息   —— 截图 + 让模型读出对方最后说了什么
  ② 想回复   —— 调模型生成一句人话（带上历史 + 人格 + 风控）
  ③ 找输入框 —— 网格法定位
  ④ 打字     —— ADB Keyboard 广播（中文）
  ⑤ 发送     —— 点发送 + 回读验证（最多 3 次）
  ⑥ 落库     —— 把这一轮存进 conversations

★ 安全闸（P8b 必须先卡住，不能让 AI 乱发）：
  - dry_run 模式：全流程照跑，**到"点发送"停下**，只报告"我会发这句"
  - 发送前核对：输入框里必须真的是我们要发的内容（防串行/残留）
  - 敏感词拦截：命中硬拦词（钱、转账、身份证等）一律不发，交人处理

★ 纯视觉：截图 → 模型 → 网格定位 → 点击 → 广播，无控件树、无注入（规格书 0.1）
"""
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from phone import Phone, PhoneError            # noqa: E402
from vision import VisionEngine    # noqa: E402
from tt_typing import Typist, TypeError_        # noqa: E402
from tt_send import Sender, SendError, _clean_input_text  # noqa: E402
from tt_navigate import Navigator, NavError, PLATFORM2APP, APP_LABEL  # noqa: E402


class ChatError(Exception):
    """聊天闭环失败。msg 是给用户看的中文大白话。"""
    def __init__(self, msg, detail=""):
        super().__init__(msg)
        self.msg = msg
        self.detail = detail


# ★ 硬拦词：命中就绝不自动发，交人处理（规格书 4.4 发送策略双层）
BLOCK_WORDS = [
    "转账", "打钱", "借钱", "汇款", "银行卡", "卡号", "密码", "验证码",
    "身份证", "住址", "门牌", "家里地址", "公司地址",
    "投资", "理财", "刷单", "兼职日结", "贷款", "裸聊", "红包",
]

# ★ 默认人格（规格书 3.6 人格全局统一；此处是兜底，正式版从 DB 读）
DEFAULT_PERSONA = (
    "你是一个住在云南大理、性格开朗爱聊天的年轻人。"
    "说话短、口语、像微信里聊天那样，一句不超过 25 个字，"
    "不用书面语，不写小作文，不用「哦呢啦呀」以外的表情符号，"
    "不主动提钱、不主动要联系方式、不主动约见面。"
    "对方说什么你就顺着接，可以开个玩笑、问个小问题，让话题能继续。"
)


class ChatLoop:
    """
    一轮完整聊天。用法：

        loop = ChatLoop(phone=..., vision=..., dry_run=True)
        r = loop.run_once(reply_to="大理古城")
        # r = {"ok":True, "heard":"大理古城", "reply":"...", "sent":False, "why":"dry_run"}
    """

    def __init__(self, phone=None, vision=None, typist=None, sender=None,
                 db=None, persona=None, verbose=True, shots_dir=None,
                 on_step=None):
        self.phone = phone or Phone().connect()
        self.vision = vision or VisionEngine()
        self.typist = typist or Typist(self.phone)
        self.sender = sender or Sender(self.phone, self.vision,
                                       shots_dir=shots_dir, verbose=verbose)
        self.db = db
        self.persona = persona or DEFAULT_PERSONA
        self.verbose = verbose
        # ★ 内存里的临时历史（P8b）：DB 还没建表时也能带上文。
        #   为什么要历史：实测"云南 → 大理古城"这种话题接力，
        #   没有历史模型就不懂「大理古城」是地名，会回出「我是海拉，你好！」这种笑话。
        #   正式版由 P9 分层记忆接管（规格书 3.x）。
        self.local_history = []

        # ★★ 报话的嘴（第 29 轮加）
        #   界面想"看着 AI 一步步干活"，但底层逻辑（这几百行）不能重写 ——
        #   里面全是踩坑攒出来的规矩（键盘确认、打字后核对、硬拦词…）。
        #   所以给它装一个回调：每做一步就喊一声，界面照着显示。
        #   回调签名：on_step(第几步, 步骤名, 状态, 说明, 截图bytes)
        #   状态：running（正在做）/ ok（成了）/ fail（没成）/ wait（停下等人）
        self.on_step = on_step

    def _step(self, no, name, state, detail="", png=None):
        """喊一嗓子进度。★ 回调出错绝不能影响主流程（界面崩了 AI 也得干完）。"""
        if not self.on_step:
            return
        try:
            self.on_step(no, name, state, detail, png)
        except Exception:
            pass

    def _log(self, msg):
        if self.verbose:
            print(msg, flush=True)

    def push_history(self, who, text):
        """往临时历史里记一条。who: 'other' | 'me'"""
        if text:
            self.local_history.append({"sender": who, "content": text})

    # ---------- 找输入框（P8b 第四次修正） ----------

    def _find_input_box(self, png=None):
        """
        找聊天输入框的位置。

        ★ 实测踩坑全记录（P8b，试了四种错法，最后才定案）：
          ① 网格法直接找"聊天输入框" → 它窄窄一条，在 4×8 网格里占不到一格，认不出
          ② 复用"发送按钮的行" → **键盘收起时完全错**（收起时输入框贴最底部）
          ③ 只找"屏幕最下面那一条" → **键盘弹起时完全错**（弹起时输入框被顶到 57%）
          ④ 只写死固定百分比 → 键盘一弹一收差 40% 屏高，必错

        ★★ 最终定案：**输入框的位置取决于键盘在不在，所以要分两种情况**：
          | 键盘状态 | 输入框在哪 | 屏高比例 |
          |---|---|---|
          | **弹起** | 屏幕中部偏下（被键盘顶上去） | **48% ~ 60%**（实测中心 ~57%） |
          | **收起** | 屏幕最底部那条 | **~93% ~ 98%** |
          而"键盘在不在"我已经有可靠判断（`_keyboard_up()`，
          走 dumpsys 白名单命令，不猜）。

        ★ 经验值来源（Soul 聊天页实测）：
          键盘弹起：输入框 y=2294/2400 → **57.2%**；发送按钮同一行
          键盘收起：输入框 y≈2270/2400（快捷短语栏下方）→ **~94%**
        """
        if png is None:
            png = self.phone.screenshot_bytes()
        W, H = self.phone.screen_size()

        if self._keyboard_up():
            # ---- 键盘弹起：输入框在 57% 那一带，用发送按钮的 y 最准 ----
            btn = self.sender._find_send_btn(png)
            if btn.get("found") and 0.45 * H < btn["y"] < 0.65 * H:
                return {"found": True, "x": int(W * 0.35), "y": btn["y"],
                        "stage": "kb-up:same-row-as-send"}
            # 发送按钮没找到 → 用实测常数 57.2%
            return {"found": True, "x": int(W * 0.35), "y": int(H * 0.572),
                    "stage": "kb-up:measured-const"}

        # ---- 键盘收起：输入框贴屏幕最底部 ----
        #   ★ R36 真机像素实测（2026-10-02 再次像素级复核）：微信输入框中心
        #     y≈2325/2400 = **96.9%**（不是 94.5%！94.5% 点在聊天区域上，
        #     键盘永远不起来 —— 记忆里记了、代码一直没改，第 47 轮端到端实测暴露）
        return {"found": True, "x": int(W * 0.35), "y": int(H * 0.969),
                "stage": "kb-down:bottom-R36实测96.9%"}

    def _keyboard_up(self):
        """
        判断软键盘有没有弹出来（纯像素 + 白名单命令，不需要模型）。

        ★ 怎么判断：有键盘时，屏幕下半部会从"聊天区/空白"变成"大片整齐按键"。
          用 `dumpsys input_method` 里的 mInputShown 更直接 —— 这是**读配置参数**
          不是"读屏幕内容"，在规格书 1.2.1 白名单内。
        """
        try:
            out, _, _ = self.phone._run(
                ["shell", "dumpsys", "input_method"], timeout=15)
            out = out or ""
            # 不同 ROM 字段名略有差异，两种都认
            if "mInputShown=true" in out:
                return True
            if "mInputShown=false" in out:
                return False
        except Exception:
            pass
        # 命令读不出 → 用像素兜底判断（下半屏是否有大片"整齐按键"）
        try:
            from PIL import Image
            import io
            png = self.phone.screenshot_bytes()
            W, H = self.phone.screen_size()
            im = Image.open(io.BytesIO(png)).convert("L")
            px = im.load()
            y = int(H * 0.85)
            vals = [px[x, y] for x in range(0, W, max(1, W // 60))]
            if len(vals) < 5:
                return False
            # 键盘按键区颜色浅且规律（相邻差小）；聊天区有深色文字（差大）
            d = sum(abs(vals[i + 1] - vals[i]) for i in range(len(vals) - 1))
            return (d / (len(vals) - 1)) < 12
        except Exception:
            return False

    def read_visible_history(self, png=None, max_msgs=8):
        """
        ★ 直接从屏幕上读最近的聊天记录（不依赖 DB）。
        用来给"生成回复"当上下文 —— 这是"接得住话题"的关键。

        ★ 实测踩坑（P8b 第二次）：
          第一版提示词里给了"对方：xxx / 我：xxx"的**格式示例**，
          结果模型**把示例本身当成答案抄回来了**（读出「对方（对方发来）」这种鬼东西）。
          → **教训：提示词里绝不能带"看起来像答案"的示例。**
          改用纯 JSON 输出（JSON 结构里没有像答案的东西）。

        ★ 实测踩坑（P8b 第三次）：用 `vision.ask()`（autoglm-phone）要 JSON，
          它**不给 JSON**，而给出自己那套格式/或直接答个昵称（「测试用户A」）。
          → **修法：改用 `ask_chat_with_image()`（说话模型 glm-4v-flash）。**
          → 规律（写死进脑子）：**任何"要按格式输出"的活，都别交给 autoglm-phone。**

        返回 [{"sender":"other"/"me", "content": "..."}, ...]（时间从旧到新）
        """
        if png is None:
            png = self.phone.screenshot_bytes()
        from PIL import Image
        import io
        W, H = self.phone.screen_size()
        im = Image.open(io.BytesIO(png)).convert("RGB")
        im = im.crop((0, int(H * 0.08), W, int(H * 0.72)))
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=92)
        txt = self.vision.ask_chat_with_image(
            buf.getvalue(),
            "这是一个手机聊天界面截图。屏幕上的聊天气泡分两种：\n"
            "- **对方**发的：浅色或白色，靠左边\n"
            "- **我自己**发的：彩色（紫色或蓝色），靠右边\n\n"
            "请按从上到下的顺序，把屏幕上的**对话气泡**读出来（最多 %d 条）。\n"
            "注意：最上面那个**头像旁边的昵称**（比如「测试用户A」「在线」）"
            "**不是对话内容，不要读**。\n\n"
            "只输出一个 JSON 数组，不要任何解释、不要 markdown 代码块。\n"
            "数组里每个元素是 {\"who\": \"对方\", \"text\": \"气泡里的原话\"} 或 "
            "{\"who\": \"我\", \"text\": \"气泡里的原话\"}\n"
            "读不出的气泡就不要放进去。没有气泡就输出 []" % max_msgs,
            max_tokens=700, hd=True)
        return _parse_dialogue(txt, max_msgs)

    # ---------- ① 看消息 ----------

    def read_last_message(self, png=None, from_other=True):
        """
        读出聊天里**对方最后说的那句话**。

        ★ 实测踩坑（P8b）：
          ① 裁剪范围写死 10%~48%，结果对方最后那句在 52% —— **裁掉了**。
             聊天区内容会随消息条数上下浮动，**范围必须放宽**。
          ② 光在提示词里说"左边"不够，模型仍然读出我自己发的。
             → 改用**颜色特征**区分：对方气泡是浅色/白色、我方气泡是彩色（紫蓝）。
             颜色是稳定特征，比"左右"更可靠（左右还可能被机型翻转）。

        ★ 做法：裁到"输入框带"上沿为止（下方不裁输入框），让模型找
          **最下面那一条浅色气泡**。
        """
        if png is None:
            png = self.phone.screenshot_bytes()
        from PIL import Image
        import io
        W, H = self.phone.screen_size()
        im = Image.open(io.BytesIO(png)).convert("RGB")
        # ★ 聊天记录区：状态栏以下 ~ 输入框带以上。
        #   实测踩坑（P8b）：裁 0.09~0.52 时，「大理古城」被裁成「海拉」——
        #   **最后一句的下沿被切掉了**。放宽到 0.58，宁可多带一点输入框上边缘。
        im = im.crop((0, int(H * 0.08), W, int(H * 0.58)))
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=92)

        txt = self.vision.ask(
            buf.getvalue(),
            "这是一个手机聊天界面截图的中间部分。\n"
            "屏幕上的聊天气泡分两种：\n"
            "- **对方**发的：浅色或白色，靠左边\n"
            "- **我自己**发的：彩色（紫色或蓝色），靠右边\n\n"
            "请找出**位置最靠下那一条「对方」的浅色气泡**，只输出它里面的文字。\n"
            "只输出那串文字本身，不要引号、不要解释、不要加任何前缀。\n"
            "如果整块里没有任何浅色（对方）气泡，就只输出：没有",
            max_tokens=150, hd=True)
        return _clean_bubble(txt)

    # ---------- ② 想回复 ----------

    def make_reply(self, heard, history=None, extra="", max_chars=60):
        """
        让模型根据对方说的话 + 历史，生成一句回复。

        ★ 输出要求（都踩过坑）：
          - 只输出这一句话本身，不许带引号、不许带"回复："前缀（否则会发出去）
          - 不许带括号动作描写（"（笑）"会被当文字发出去）
          - 长度上限硬卡（超过就截断，防小作文）
        """
        hist_txt = ""
        if history:
            lines = []
            for h in history[-8:]:
                who = "她" if h.get("sender") == "other" else "我"
                lines.append("%s：%s" % (who, h.get("content", "")))
            hist_txt = "最近的聊天记录：\n" + "\n".join(lines) + "\n\n"

        txt = self.vision.ask_text(
            "%s%s对方刚说了：「%s」\n%s\n"
            "请以「我」的身份回一句。\n\n"
            "硬要求：\n"
            "1. 只输出要发的那句话本身，不要任何前缀、不要引号、不要括号里的动作描写\n"
            "2. 不超过 %d 个字，口语，像微信聊天\n"
            "3. 顺着对方的话接，可以开个小玩笑或问个小问题\n"
            "4. **绝对不能把对方的话原样抄回来**（必须是你自己的回应）\n"
            "5. 不提钱、不要联系方式、不提见面"
            % (self.persona + "\n\n", hist_txt, heard, extra, max_chars),
            max_tokens=200)
        out = _clean_reply(txt, max_chars)
        # ★ 兜底：万一还是把对方的话抄回来了，强制换一句
        if _norm(out) == _norm(heard):
            self._log("    ⚠ 模型把对方的话抄回来了，换一种说法")
            out = _clean_reply(self.vision.ask_text(
                "对方说：「%s」。请**换一句话**回应她，"
                "不要重复她的原话。只输出那一句话，不超过 %d 个字。"
                % (heard, max_chars), max_tokens=200), max_chars)
        return out

    # ---------- ③④⑤ 打字 + 发送 ----------

    def type_and_send(self, reply, dry_run=True):
        """
        打字 → 发送 → 验证。

        dry_run=True 时：**只打字，不点发送**（给你看 AI 会发什么）。
        返回 {"typed": bool, "sent": bool, "why": str, "verify": {...}}
        """
        r = {"typed": False, "sent": False, "why": "", "verify": None}

        # ---- ① 安全检查：硬拦词 ----
        hit = [w for w in BLOCK_WORDS if w in reply]
        if hit:
            self._step(6, "把字打进去", "fail",
                       "这句话里有「%s」，按规矩不能自动发，得你拿主意" % "、".join(hit))
            r["why"] = "命中硬拦词 %s，不自动发（交人处理）" % hit
            return r

        # ---- ② 找输入框 & 确保键盘弹起 ----
        # ★ 实测踩坑（P8b 第四次）：之前"复用发送按钮的 y"在**键盘收起**时会完全错
        #   （收起时输入框跑到屏幕最底部 ~94%，而发送按钮不在那条带上）。
        #   点错位置 = 键盘没弹起 = 打字广播打进空气 = 后面全白干。
        #
        #   ★ 定案：**输入框位置取决于键盘在不在**（见 _find_input_box 注释），
        #     而且顺序必须是：找输入框 → 点它 → **确认键盘弹起** → 清空 → 打字。
        png = self.phone.screenshot_bytes()
        self._step(5, "找输入框在哪", "running", "定位输入框、顺手把键盘叫起来…")
        src_guard = 0
        for attempt in range(3):
            box = self._find_input_box(png)
            self._log("    → 输入框定位 (%d, %d) %s" % (box["x"], box["y"], box["stage"]))
            self.phone.tap(box["x"], box["y"])
            time.sleep(0.9)
            if self._keyboard_up():
                self._log("    ✓ 键盘已弹起")
                break
            self._log("    ! 键盘没起来，重新找位置再点")
            png = self.phone.screenshot_bytes()
            src_guard += 1
        if not self._keyboard_up():
            # ★ 实测踩坑（2026-10-02）：提示要说**人话**。
            #   手机上停在 Soul 的"通讯录"页（没有聊天输入框）时，
            #   原来的提示是"点了输入框但键盘没弹出来" ——
            #   用户看了会一头雾水（"什么叫键盘没弹出来？我该干嘛？"）。
            #   真正的原因是：**这个页面上根本没有聊天输入框。**
            self._step(5, "找输入框在哪", "fail",
                       "这个页面上没有聊天输入框 —— 手机上大概停在首页，不是聊天页")
            r["why"] = ("手机上这个页面**没有聊天输入框**。\n\n"
                        "大概是停在 App 的首页或通讯录了，不是跟某个人聊天的窗口。\n\n"
                        "先用手点进某个人的聊天窗口，再点这个按钮。")
            return r
        self._step(5, "找输入框在哪", "ok", "找到了，键盘也起来了")

        # ★ 清空输入框里可能残留的旧内容（实测：上一轮没发成的字会留在里面）
        try:
            with Typist(self.phone) as t0:
                t0.clear()
            time.sleep(0.4)
            self._log("    → 已清空输入框（防残留）")
        except Exception as e:
            self._log("    ! 清空失败（继续）：" + str(e)[:60])

        # ---- ③ 打字（中文走 b64 广播）----
        self._step(6, "把字打进去", "running", "正在打字…")
        try:
            with Typist(self.phone) as t:
                way = t.type_text(reply)
            r["typed"] = True
            self._log("    → 已打入（%s）：%s" % (way, reply))
        except TypeError_ as e:
            self._step(6, "把字打进去", "fail", "打字失败：" + e.msg)
            r["why"] = "打字失败：" + e.msg
            return r

        # ---- ④ 打字后核对（输入框里必须真的是我们要发的）----
        time.sleep(0.5)
        after_type = self.phone.screenshot_bytes()
        self.sender._shot(after_type, "typed")
        try:
            actual = self.sender.read_input_box(after_type)
        except Exception:
            actual = ""
        r["typed_actual"] = actual
        if actual and _norm(actual) != _norm(reply):
            self._log("    ⚠ 输入框里是「%s」，本要写「%s」" % (actual, reply))
            r["why"] = "打字后核对不一致（输入框里是「%s」）" % actual
            if _norm(reply) not in _norm(actual):
                self._step(6, "把字打进去", "fail",
                           "打进去的和想写的不一样：框里是「%s」" % actual, after_type)
                return r
        self._step(6, "把字打进去", "ok",
                   "字已经在输入框里了：「%s」" % (actual or reply), after_type)

        # ---- ⑤ dry_run 就到此为止 ----
        if dry_run:
            self._step(7, "发送", "wait",
                       "试跑模式：**没点发送**。你看过觉得行，再让它发", after_type)
            r["why"] = "演练模式：已打进输入框，未点发送"
            return r

        # ---- ⑥ 真发 ----
        self._step(7, "发送", "running", "点了一下发送…")
        try:
            v = self.sender.send_and_verify(reply)
        except SendError as e:
            self._step(7, "发送", "fail", "发送失败：" + e.msg)
            r["why"] = "发送失败：" + e.msg
            return r
        r["verify"] = v
        r["sent"] = bool(v.get("ok"))
        r["why"] = v.get("how", "")
        self._step(8, "确认发出去了", "ok" if r["sent"] else "fail",
                   r["why"] or ("发出去了" if r["sent"] else "没确认到"))
        return r

    # ---------- ⑦ 一整轮 ----------

    def run_once(self, dry_run=True, customer_id=None, reply_to=None,
                 target_app=None, contact_name=None):
        """
        跑一整轮：看消息 → 想回复 → 打字（→ 发送）。

        参数：
          dry_run       True = 只到"打进输入框"为止，不真发（**默认，安全**）
          reply_to      指定回复内容（跳过模型生成，测链路用）
          customer_id   有的话，把这一轮存进 DB
          target_app    目标平台（wechat/momo/soul， customers.platform 的值）。
                        ★ 有它 AI 才会**自己认路**（不在聊天页就自己走过去）
          contact_name  要找的人（客户昵称），配合 target_app 用

        返回一份完整报告 dict。
        """
        rep = {"ok": False, "step": "", "heard": "", "reply": "",
               "typed": False, "sent": False, "why": "", "shots": []}
        try:
            # ---- ① 看一眼手机 ----
            rep["step"] = "看消息"
            self._step(1, "看一眼手机", "running", "正在拍手机屏幕…")
            png = self.phone.screenshot_bytes()
            rep["shots"].append(self.sender._shot(png, "loop_start"))
            self._step(1, "看一眼手机", "ok", "拍到了", png)

            # ---- ② 认清这是哪个 App ----
            self._step(2, "认清这是哪个 App", "running", "看看现在停在哪个软件…")
            try:
                app = self.vision.which_app(png)
            except Exception as e:
                if self.verbose:
                    print("    ! which_app 判断失败：%s" % str(e)[:60], flush=True)
                app = "看不出来"
            rep["app"] = app

            # ★★★ 认路（2026-10-02 用户拍板；第 46 轮审查修正接线）★★★
            #   客户档案里写着 platform + 昵称，AI 就该自己走到 TA 的聊天页。
            #   ★ 只要有目标和联系人就**无条件走 ensure_chat**：
            #     它内部第一步就问系统前台包名（零误判），已经在聊天页会秒回；
            #     外层不再用 which_app/is_on_page 自行判断 ——
            #     那道纯视觉防线幻觉答错一次，就会**在错误的 App 里读消息**。
            target = PLATFORM2APP.get(str(target_app or "").strip())
            if target_app and not target:
                # 档案里写了平台但认不出 → 停手叫人，绝不"在哪聊哪"
                self._step(2, "认清这是哪个 App", "fail",
                           "客户档案里的平台「%s」认不出来" % target_app)
                rep["why"] = ("客户档案里的平台（%s）不是微信/陌陌/Soul，"
                              "AI 不知道该去哪个 App 找 TA。" % target_app)
                rep["need_open_chat"] = True
                return rep

            if target and contact_name:
                label = APP_LABEL.get(target, target)
                self._step(2, "认清这是哪个 App", "running",
                           "目标：%s 的「%s」—— AI 自己认路过去…" % (label, contact_name))
                try:
                    nav = Navigator(self.phone, self.vision, verbose=self.verbose)
                    nav.on_step = (lambda nm, st, dt, png2=None:
                                   self._step(2, "认清这是哪个 App", st, dt, png2))
                    nav.ensure_chat(contact_name, target_app, png=png)
                    png = self.phone.screenshot_bytes()      # 认路成功 → 拿新画面继续
                    rep["app"] = app = target
                    rep["navigated"] = True
                    self._step(2, "认清这是哪个 App", "ok",
                               "已经自己走到「%s」和 %s 的聊天页" % (label, contact_name), png)
                except NavError as e:
                    self._step(2, "认清这是哪个 App", "fail", e.msg, png)
                    rep["why"] = e.msg
                    rep["need_open_chat"] = True
                    return rep

            # ★ 一道必须有的闸（实测踩坑，2026-10-02）★★★
            #   没这道闸会出大丑：手机停在**桌面**时，AI 把桌面上的
            #   「10月2日周五」「每一天都是一个新的开始」当成了**对方说的话**，
            #   还认真回了一句「那咱们就一起加油吧！」—— 完全是在跟壁纸聊天。
            #   规矩：**认不出 App 就先停下**，别在不知道自己在哪的时候乱读乱猜。
            if app in ("unknown", "看不出来", "", None) or app == "没有":
                self._step(2, "认清这是哪个 App", "fail",
                           "认不出这是哪个软件，也不知道该去哪个 App 找谁")
                rep["why"] = ("手机上现在**不在聊天 App 里**，AI 也不知道去哪个 App、"
                              "找谁聊。\n\n去「客户」页先选中一个客户再点按钮 —— "
                              "档案里写着 TA 在哪个平台，AI 就自己认路过去了。")
                rep["need_open_chat"] = True
                return rep

            # ★ 先读整段可见对话（当上下文），再取最后一条对方的话当"要回的那句"
            self._step(3, "读最近的对话", "running", "把屏幕上的聊天读下来…")
            visible = self.read_visible_history(png)
            rep["visible"] = visible
            if visible:
                self._log("  ① 屏幕上的对话（%d 条）：" % len(visible))
                for m in visible[-5:]:
                    self._log("      %s：%s"
                              % ("她" if m["sender"] == "other" else "我",
                                 m["content"]))
                others = [m["content"] for m in visible if m["sender"] == "other"]
                heard = others[-1] if others else ""
            else:
                heard = self.read_last_message(png)
            rep["heard"] = heard
            self._log("  ① 要回的那句：「%s」" % heard)
            if not heard or heard == "没有":
                self._step(3, "读最近的对话", "fail",
                           "屏幕上没看到对方说的话", png)
                rep["why"] = "对方最近没说话（没有可回的气泡）"
                rep["ok"] = True          # 没消息不算失败
                return rep
            self._step(3, "读最近的对话", "ok",
                       "读到 %d 条；对方最后说：「%s」" % (len(visible or []), heard),
                       png)

            # ---- ② 想 ----
            rep["step"] = "想回复"
            self._step(4, "想一句回复", "running", "正在琢磨怎么接这句话…")
            # ★ 上下文优先级：DB 历史 > 屏幕上读到的历史 > 内存临时历史
            hist = None
            if self.db and customer_id:
                try:
                    hist = self.db.history(customer_id, limit=20)
                except Exception:
                    hist = None
            if not hist:
                hist = visible or self.local_history
            reply = reply_to or self.make_reply(heard, history=hist)
            rep["reply"] = reply
            self._log("  ② 打算回：「%s」" % reply)
            if not reply:
                self._step(4, "想一句回复", "fail", "没想出合适的回复")
                rep["why"] = "模型没生成出回复"
                return rep
            self._step(4, "想一句回复", "ok", "想好了：「%s」" % reply)

            # ---- ③④⑤ 打 + 发 ----
            rep["step"] = "打字发发送"
            tr = self.type_and_send(reply, dry_run=dry_run)
            rep.update({k: tr.get(k) for k in ("typed", "sent", "why")})
            rep["typed_actual"] = tr.get("typed_actual", "")
            rep["verify"] = tr.get("verify")

            # ---- ⑥ 落库 ----
            #   ★ 第 33 轮修正：AI 发出的消息 sender 统一写 **"ai"**
            #     （原来写的是 "me"，跟 tt_db 自检 / 统计层对不上，
            #       导致"今天 AI 回了几条"永远算不出来。
            #       历史遗留的 "me" 行由 stats.py 兼容读取，不改老数据。）
            if self.db and customer_id and tr.get("typed"):
                try:
                    self.db.add_message(customer_id, "other", heard, verified=1)
                    if tr.get("sent"):
                        self.db.add_message(customer_id, "ai", reply,
                                            strategy_note="自动回复",
                                            verified=1)
                        rep["saved"] = True
                    else:
                        rep["saved"] = False
                except Exception as e:
                    rep["save_error"] = str(e)[:100]

            rep["ok"] = bool(tr.get("typed"))
            rep["step"] = "完成"
            return rep
        except Exception as e:
            rep["why"] = str(e)[:200]
            rep["error"] = str(e)[:200]
            return rep


# ---------- 文本清洗（每个坑都吃过） ----------

# ★ 界面上的"非聊天内容"噪声词（出现这些一律不算对话气泡）
UI_NOISE = re.compile(
    r"^(在线|离线|关注|展开|收起|举报|拉黑|置顶|删除|删除聊天|"
    r"对方正在输入|已读|未读|发送失败|重新发送|"
    r"聊天气派上新啦|去商城看看|看看对方主页.*|"
    r"晚上好|交换答案|桌球|礼物|掷骰|打招呼)$")


def _parse_dialogue(txt, max_msgs=8):
    """
    把模型读出的对话解析成 [{sender, content}, ...]。

    ★ 主格式是 JSON 数组：[{"who":"对方","text":"云南"}, ...]
      （为什么改 JSON：给"对方：xxx"这种示例时，模型会把示例抄回来 —— P8b 实测）
    ★ 同时也兼容纯文本行（"对方：xxx"），双保险。
    ★ 过滤 UI 噪声（"在线"/"关注"/快捷短语条），以及抄提示词的情况。
    """
    if not txt:
        return []
    out = []

    # ---- 主路径：JSON ----
    import json as _json
    m = re.search(r"\[[\s\S]*\]", txt)
    if m:
        try:
            arr = _json.loads(m.group(0))
            for it in arr:
                if not isinstance(it, dict):
                    continue
                who = str(it.get("who", "")).strip()
                text = str(it.get("text", "")).strip()
                if not text or UI_NOISE.match(text):
                    continue
                sender = "other" if who in ("对方", "她", "他", "女方", "对面") else "me"
                out.append({"sender": sender, "content": text})
            if out:
                return out[-max_msgs:]
        except Exception:
            pass

    # ---- 兜底：纯文本行 ----
    for line in txt.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^\s*(?:[-*•·]|\d+[.、)])\s*", "", line)
        mm = re.match(r"^(对方|她|他|女方|对面|我|自己|我方)\s*[：:，,]\s*(.+)$", line)
        if not mm:
            continue
        who = "other" if mm.group(1) in ("对方", "她", "他", "女方", "对面") else "me"
        content = mm.group(2).strip().strip('"').strip("「」").strip()
        # ★ 过滤掉"把提示词模板抄回来"的情况
        if content and not re.match(r"^[（(]?(对方|我)[）)]?(发来|发送)?$", content) \
                and not UI_NOISE.match(content):
            out.append({"sender": who, "content": content})
    return out[-max_msgs:]


def _norm(s):
    """归一化：去空白、去标点，用来比对"是不是同一句"。"""
    if not s:
        return ""
    return re.sub(r"[\s，。！？、,.!?~…「」\"'（）()]", "", s)


def _clean_bubble(txt):
    """
    洗"对方说了什么"的回答。
    模型爱答：「最后一条是「大理古城」」→ 要剥成「大理古城」
    ★ 也要防"把提示词抄回来"（P8b 实测：读出「对方（对方发来）」这种）。
    """
    if not txt:
        return ""
    t = txt.strip()
    m = re.search(r"[「\"']([^」\"']{1,80})[」\"']", t)
    if m:
        t = m.group(1)
    for p in ("最后一条是", "对方说", "内容是", "文字是", "这条是"):
        if t.startswith(p):
            t = t[len(p):].strip(" ：:，,")
    t = t.strip().strip('"').strip("「」").strip("。.")
    t = t.split("\n")[0].strip()
    # ★ 抄提示词的情况 → 当成没读到
    if re.match(r"^[（(]?(对方|我|我自己)[）)]?(发来|发送|发的)?$", t):
        return "没有"
    if t in ("没有", "无", "空", ""):
        return "没有"
    return t


def _clean_reply(txt, max_chars=60):
    """
    洗"我该回什么"的回答 —— ★ 这一步错了会把包装发出去（灾难）。

    实测模型爱加：回复：「好的呀」 / （笑着）在忙吗 / "你好"
    """
    if not txt:
        return ""
    t = txt.strip()
    # 优先取引号里的（最像正文本体）
    m = re.search(r"[「\"']([^」\"']{2,80})[」\"']", t)
    if m:
        t = m.group(1)
    # 去掉前缀
    for p in ("回复：", "回复:", "我：", "可以回：", "建议回：", "回答：", "那就回："):
        if t.startswith(p):
            t = t[len(p):].strip()
    # 去掉开头的括号动作描写
    t = re.sub(r"^[（(][^）)]{0,20}[）)]\s*", "", t)
    t = t.strip().strip('"').strip("「」").strip()
    t = t.split("\n")[0].strip()
    # 长度硬卡
    if len(t) > max_chars:
        t = t[:max_chars]
    return t


# ---------- 自检：默认 dry_run（演练，不真发） ----------

def self_test(dry_run=True, reply_to=None):
    """
    P8b 自检：跑一整轮聊天闭环。

    ★ 默认 dry_run=True —— 只到"打进输入框"为止，**不点发送**。
    ★ 这条会动真手机（会进聊天页、会打字），但不发出去。
    """
    r = {"ok": False, "steps": []}
    try:
        r["steps"].append("① 连手机 …")
        p = Phone().connect()
        r["steps"].append("   ✓ " + p.serial)

        v = VisionEngine()
        loop = ChatLoop(p, v)
        r["steps"].append("② 模型：" + v.model)

        r["steps"].append("③ 跑一整轮（dry_run=%s）…" % dry_run)
        rep = loop.run_once(dry_run=dry_run, reply_to=reply_to)
        r["report"] = rep

        r["steps"].append("   对方说：「%s」" % rep.get("heard", ""))
        r["steps"].append("   打算回：「%s」" % rep.get("reply", ""))
        r["steps"].append("   打进去了：%s" % rep.get("typed"))
        r["steps"].append("   真发出去了：%s" % rep.get("sent"))
        r["steps"].append("   说明：%s" % rep.get("why", ""))
        r["ok"] = bool(rep.get("ok"))
        r["calls"] = v.calls
    except Exception as e:
        r["steps"].append("   ✗ " + str(e))
        r["error"] = str(e)
    return r


if __name__ == "__main__":
    do_send = "--send" in sys.argv
    rt = None
    for a in sys.argv:
        if a.startswith("--reply="):
            rt = a.split("=", 1)[1]
    out = self_test(dry_run=not do_send, reply_to=rt)
    for s in out["steps"]:
        print(s)
    print("\n结果：", "通过 ✓" if out["ok"] else "失败 ✗ " + out.get("error", ""))
    sys.exit(0 if out["ok"] else 1)
