# -*- coding: utf-8 -*-
"""
拓客台 · 视觉引擎（P1 + P5 骨架）

★ 职责：把"手机截图"喂给视觉大模型，拿回"该点哪里 / 屏幕上有什么"。
★ 这是纯视觉路线的大脑接口 —— 不读控件树，只看图（规格书 0.1）。

核心能力（P1 先做前两个）：
  1. describe(img)     → 看懂屏幕在说什么（一句话）
  2. locate(img, 目标)  → 给出目标的点击坐标（x, y）
  3. plan(img, 任务)    → 决定下一步做什么（P5 再扩展）

★ 省钱三道闸（规格书 1.7.1 三级成本控制）：
  - 截图先压尺寸（540 宽够用，比 1080 省 ~4 倍 token）
  - 短问题用小模型 flash，复杂判断才用大模型
  - 同一张图问多次 → 本地缓存，不重复付费
"""
import base64
import hashlib
import io
import json
import os
import re
import sys
import time

try:
    import requests
except ImportError:
    requests = None


def _project_root():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _img_size(img_bytes):
    """读图片尺寸。先用 phone 里的纯字节解析，不行再退回 PIL。"""
    try:
        from phone import _png_size
        W, H = _png_size(img_bytes)
        if W:
            return W, H
    except Exception:
        pass
    try:
        from PIL import Image
        import io as _io
        return Image.open(_io.BytesIO(img_bytes)).size
    except Exception:
        return (0, 0)


def load_cfg():
    p = os.path.join(_project_root(), "config", "config.json")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


class VisionError(Exception):
    """看图失败。msg 是给用户看的中文大白话。"""
    def __init__(self, msg, detail=""):
        super().__init__(msg)
        self.msg = msg
        self.detail = detail


# ★★★ 实测踩坑（P8）：autoglm-phone 这个模型会把答案裹在壳里返回 ★★★
#   例：finish(message="空")  /  finish(message={"found": true, ...})
#   这是个"手机操作专用模型"的固定输出协议，不是通用格式。
#   解法：统一剥壳 —— 不管哪个模型，拿到的都是干净内容。


def _unwrap(raw):
    """
    把模型返回的外壳剥掉，只留内容。
    处理三种情况：
      1. finish(message="...")        → 取引号里的
      2. finish(message={"a": 1})     → 取大括号里的（JSON）
      3. ```json ... ``` 代码块        → 取块里的
    """
    if not raw:
        return raw
    t = raw.strip()
    # 情况 3：markdown 代码块
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", t)
    if m:
        t = m.group(1).strip()
    # 情况 1/2：finish(...)
    m = re.search(r"finish\s*\(\s*\w+\s*=\s*", t)
    if m:
        rest = t[m.end():]
        # 2a：参数是 JSON 对象
        jm = re.search(r"\{[\s\S]*\}", rest)
        qm = re.search(r"""(['"])([\s\S]*?)\1""", rest)
        if jm and (not qm or jm.start() < qm.start()):
            t = jm.group(0)
        elif qm:
            t = qm.group(2)
        else:
            t = rest.rstrip(")").strip().strip('"')
    return t.strip()


class VisionEngine:
    """
    视觉引擎 + 文字引擎（一个 API 下两个模型分工，规格书第 2 章）。

    ★★★ 为什么要两个模型名（P8b 实测定案，重要）★★★
      实测同一个"手机操作专用模型"（autoglm-phone）干两件事会互相干扰：

        | 任务 | autoglm-phone | glm-4v-flash |
        |---|---|---|
        | 看屏找元素/认格子 | ✅ 很好 | ✅ 可以 |
        | 生成聊天回复 | ❌ 写小作文 + **幻觉**（"我注意到屏幕上…"） | ✅ 完美 |

      实测同一句提示词：
        - autoglm-phone → 「…大理和丽江古城都是云南的边城，我常去那里旅游…」
          竟然还接着写「我注意到屏幕上只显示了最后一句的末尾」—— **它以为自己在看屏幕**
        - glm-4v-flash   → 「大理古城离这里不远，有空一起玩吧！」✅ 17 字，接住话题

      → **结论：看图的事交给 vision_model，说话的事交给 chat_model。**
      → 注意这不违反规格书"只填一个 API"：**一个账号、一个 Key、一个 base_url**，
        只是同账号下用两个模型名（都填在 config 里，界面上是"高级设置"）。

    用法：
        v = VisionEngine()                  # 两个模型自动从 config 读
        v.locate(...)  v.describe(...)      # → 用 vision_model
        v.ask_text(...)                     # → 用 chat_model
    """

    # 图片压缩参数（省 token；540 宽足够认出按钮文字）
    MAX_W = 540
    JPEG_Q = 80

    # 默认模型分工（config 没填时用这两个）
    DEFAULT_VISION_MODEL = "glm-4v-flash"
    DEFAULT_CHAT_MODEL = "glm-4v-flash"

    def __init__(self, model=None, api_key=None, base_url=None, timeout=60,
                 vision_model=None, chat_model=None):
        if requests is None:
            raise VisionError("缺少 requests 库", "pip install requests")
        cfg = load_cfg()
        z = cfg.get("zhipu") or {}
        self.api_key = api_key or z.get("api_key") or ""
        self.base_url = (base_url or z.get("base_url")
                         or "https://open.bigmodel.cn/api/paas/v4").rstrip("/")
        # ★ 双模型分工：
        #   看图（定位/读屏/认 App）→ vision_model
        #   说话（生成回复/判断）    → chat_model
        #   老配置只有一个 model 字段时，两边都用它（向后兼容）
        one = model or z.get("model") or self.DEFAULT_VISION_MODEL
        self.vision_model = vision_model or z.get("vision_model") or one
        self.chat_model = (chat_model or z.get("chat_model")
                           or z.get("reply_model") or one)
        # 兼容旧代码：self.model 指向看图那个
        self.model = self.vision_model
        self.timeout = timeout
        self._cache = {}          # 图 hash -> 描述，避免重复付费
        self.calls = 0            # 统计调用次数（省钱的可见性）
        if not self.api_key:
            raise VisionError("还没填模型 Key", "config.json 里 zhipu.api_key 为空")

    # ---------- 内部：图片处理 ----------

    def _encode(self, png_bytes, max_w=None, quality=None):
        """
        PNG 字节 → base64（省 token）。

        ★ 两种模式（P8 实测踩坑后加的）：
          普通模式（默认）：缩到 540 宽、JPEG 80 —— 认"屏幕大概是什么"够用，省 token。
          高清模式（hd=True）：不缩尺寸，只把 PNG 转 JPEG 92 —— **读小字、找小按钮必须用**。
            实测教训：输入框那一条裁出来宽 1037px，缩到 540 后字全糊了，
            模型把「大理古城也不错呀」读成了"空"，还把亮着的发送按钮判成"找不到"。
        """
        if max_w is None:
            max_w = self.MAX_W
        if quality is None:
            quality = self.JPEG_Q
        try:
            from PIL import Image
            im = Image.open(io.BytesIO(png_bytes)).convert("RGB")
            if max_w > 0:
                im.thumbnail((max_w, max_w * 4))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=quality)
            return base64.b64encode(buf.getvalue()).decode()
        except Exception:
            return base64.b64encode(png_bytes).decode()

    def _key(self, png_bytes, prompt, hd=False):
        h = hashlib.md5(png_bytes).hexdigest()[:16]
        return h + ("|HD|" if hd else "|") + prompt[:60]

    def _ask(self, png_bytes, prompt, max_tokens=400, temperature=0.1, hd=False):
        """
        发一次多模态请求（**用看图模型 vision_model**），返回文本。
        hd=True → 不缩图、JPEG 高质量（读小字/找小按钮用，会贵一点但准）。
        """
        cache_k = self._key(png_bytes, prompt, hd)
        if cache_k in self._cache:
            return self._cache[cache_k]

        if hd:
            b64 = self._encode(png_bytes, max_w=0, quality=92)
        else:
            b64 = self._encode(png_bytes)

        txt = self._post(self.vision_model, [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url",
                 "image_url": {"url": "data:image/jpeg;base64," + b64}},
            ],
        }], max_tokens, temperature)
        self._cache[cache_k] = txt
        return txt

    def _post(self, model, messages, max_tokens, temperature):
        """
        统一发一次请求（模型名由调用方给）。
        ★ 抽出来是为了让"看图"和"说话"走同一个通道、却用不同模型（见类注释）。
        """
        body = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        try:
            r = requests.post(self.base_url + "/chat/completions",
                              headers={"Authorization": "Bearer " + self.api_key},
                              json=body, timeout=self.timeout)
        except Exception as e:
            raise VisionError("连不上模型，检查一下网络", str(e)[:200])
        self.calls += 1
        if r.status_code != 200:
            hint = ""
            if r.status_code == 401:
                hint = "（Key 可能不对，去设置里重填）"
            elif r.status_code == 429:
                hint = "（调用太频繁或余额不够）"
            raise VisionError("模型返回错误 %d %s" % (r.status_code, hint),
                              r.text[:200])
        try:
            return r.json()["choices"][0]["message"].get("content") or ""
        except Exception as e:
            raise VisionError("模型返回看不懂",
                              str(e)[:200] + " | " + r.text[:150])

    # ---------- 能力 1：看懂屏幕 ----------

    def describe(self, png_bytes):
        """一句话说清屏幕上是什么。"""
        return _unwrap(self._ask(
            png_bytes,
            "用一句中文说清楚：这是什么 App 的什么界面？屏幕上最显眼的东西是什么？只输出这句话。",
            max_tokens=150)).strip()

    # ---------- 能力 2：找东西在哪（给坐标） ----------

    # ★★★★★★ 网格法定位（P8 实测逼出来的核心方案）★★★★★★
    #
    #   为什么必须用网格（这是本项目最硬的一个坑）：
    #     实测：模型能"看见"发送按钮，但让它报坐标，它给出 (897, 567)，
    #     而屏幕是 1080×2400 —— y=567 在屏幕上方 1/4 处，那里根本没有按钮。
    #     换个提示词也没用，它还会把"推理过程"一起吐出来。
    #     结论：**模型不擅长"算坐标"，但很擅长"认格子"。**
    #
    #   所以：我先把截图**画上网格、每个格子标上编号**，再问它
    #        "按钮在第几行第几列"。它只要认格子，不用做算术。
    #   拿到行号列号后，坐标由**我**用算术算出来（我的算术比它准且免费）。
    #
    GRID_COLS = 4      # 横向 4 格（★ 实测：粗网格才认得住，8 列就会读错编号）
    GRID_ROWS = 8      # 纵向 8 格（手机是长条，行数多一点）

    def locate_grid_refine(self, png_bytes, target, extra="",
                           cols=None, rows=None, pad=0, zoom=2,
                           x_anchor=None):
        """
        ★★ 两段式网格定位（P8 实测定案，本项目的标准定位法）★★

        第一段：整屏 4×8 粗网格 → 得到大概在哪一格
        第二段：把那**一格**裁出来放大再画一次网格 → 精定位

        ★ 实测数据（这是本方案的全部依据）：
          真值：发送按钮在 (≈1005, ≈1315)（用画了标尺的图人工量的）
          - 让模型直接报坐标      → (897, 567)    ✗ 离谱
          细网格 8×16            → 读出 "63-95"  ✗ 编号都读错
          粗网格 4×8             → (945, 1350)   ✓ Δx=60 Δy=35（已经能用）
          粗网格 + 外扩2格放大精定位 → (1013, 1463) ✗ Δy 反而变大
            原因：外扩后裁进来一大片键盘，放大 3 倍后图太大，模型更不准。

        ★ 所以本版做了三个修正：
          1. pad 默认 0 —— 精定位**只裁那一格本身**，不外扩（不引入干扰）
          2. zoom 默认 2 —— 放太大反而糊、反而贵
          3. x_anchor —— 支持"x 坐标用固定值"。
             比如「发送」按钮永远贴着屏幕右边，x 就可以直接给，
             只让模型负责 y。**用领域规律干掉模型的不确定性，这是最稳的。**

        返回 {"found":bool, "x":int, "y":int, "stage":str, "cell":..., "ref_cell":...}
        """
        from PIL import Image
        import io
        cols = cols or self.GRID_COLS
        rows = rows or self.GRID_ROWS

        # ---- 第一段：粗定位 ----
        r1 = self.locate_grid(png_bytes, target, extra, cols=cols, rows=rows)
        if not r1["found"]:
            return {"found": False, "x": 0, "y": 0, "stage": "grid-coarse",
                    "cell": r1.get("cell"), "why": r1.get("why", "")}

        W, H = _img_size(png_bytes)
        cw = W / float(cols); ch = H / float(rows)
        cr, cc = r1["cell"]          # 行, 列（1-based）

        # ---- 第二段：在那一格（pad=0 时就是这一格本身）里再定位一次 ----
        best = None
        try:
            x1 = int(max(0, (cc - 1 - pad)) * cw)
            y1 = int(max(0, (cr - 1 - pad)) * ch)
            x2 = int(min(W, (cc + pad) * cw))
            y2 = int(min(H, (cr + pad) * ch))
            im = Image.open(io.BytesIO(png_bytes)).convert("RGB").crop((x1, y1, x2, y2))
            im = im.resize((im.width * zoom, im.height * zoom), Image.LANCZOS)
            buf = io.BytesIO(); im.save(buf, "JPEG", quality=90)
            r2 = self.locate_grid(buf.getvalue(), target, extra, cols=3, rows=3)
            if r2["found"]:
                # r2 的坐标是"放大后子图"的像素 → 换回原图
                gx = r2["x"] / float(zoom) + x1
                gy = r2["y"] / float(zoom) + y1
                best = {"found": True, "x": int(round(gx)), "y": int(round(gy)),
                        "stage": "grid+refine", "cell": r1["cell"],
                        "ref_cell": r2["cell"]}
        except Exception:
            best = None

        result = best or {"found": True, "x": r1["x"], "y": r1["y"],
                          "stage": "grid-coarse-only", "cell": r1["cell"]}

        # ---- x_anchor：x 用固定规律（比如"贴右边"），只信模型给的 y ----
        if x_anchor is not None and result["found"]:
            if x_anchor == "right":
                result["x"] = int(W * 0.93)
            elif x_anchor == "left":
                result["x"] = int(W * 0.07)
            elif x_anchor == "center":
                result["x"] = int(W * 0.50)
            elif isinstance(x_anchor, (int, float)) and 0 < x_anchor <= 1:
                result["x"] = int(W * x_anchor)
            result["stage"] += "+anchor"
        return result

    def locate_grid(self, img_bytes, target, extra="", cols=None, rows=None,
                    hd=True):
        """
        网格法定位：在图1 上画网格 → 问模型"在第几行第几列"→ 我算坐标。

        返回 {"found": bool, "x": int, "y": int, "cell": (r,c), "raw": str}
        坐标是该图的**像素**坐标。
        """
        from PIL import Image, ImageDraw
        import io
        cols = cols or self.GRID_COLS
        rows = rows or self.GRID_ROWS

        try:
            im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        except Exception:
            raise VisionError("这张图打不开", "grid locate")

        W, H = im.size
        # 放大一点，网格线和编号才看得清（太大费 token，2 倍够）
        scale = 2 if W < 800 else 1
        if scale > 1:
            im = im.resize((W * scale, H * scale), Image.LANCZOS)
            W, H = im.size

        d = ImageDraw.Draw(im)
        cw = W / float(cols)
        ch = H / float(rows)
        # 用不刺眼的青色画网格
        line = (0, 200, 200)
        for c in range(cols + 1):
            x = int(c * cw)
            d.line([(x, 0), (x, H)], fill=line, width=max(1, scale))
        for r in range(rows + 1):
            y = int(r * ch)
            d.line([(0, y), (W, y)], fill=line, width=max(1, scale))
        # 每个格子左上角标编号，如 "3-5"（列-行）
        try:
            from PIL import ImageFont
            fsize = max(12, int(min(cw, ch) * 0.32))
            try:
                font = ImageFont.truetype("msyh.ttc", fsize)
            except Exception:
                try:
                    font = ImageFont.truetype("arial.ttf", fsize)
                except Exception:
                    font = ImageFont.load_default()
            for r in range(rows):
                for c in range(cols):
                    d.text((c * cw + 2, r * ch + 2), "%d-%d" % (c + 1, r + 1),
                           fill=(255, 0, 80), font=font)
        except Exception:
            pass

        buf = io.BytesIO(); im.save(buf, "JPEG", quality=88)
        grid_img = buf.getvalue()

        # ★ 第 46 轮实验定案（三通道对比实测，微信主页放大镜）：
        #   autoglm-phone 认格子 → 写小作文 / 报"36-74"鬼格子（根本不按格式）；
        #   glm-4v-flash 认格子 → "4-1"，一击命中。
        #   老规矩"认格子交给 autoglm"就此修正：**粗网格主答 glm-4v-flash**，
        #   autoglm 降为兜底。落点反正全过 _verify_spot 裁块复核，谁幻觉都进不了点击。
        gq = ("这张手机截图上画了网格（青色线），每个格子左上角有编号，格式是【列号-行号】，"
              "列号从 1 数到 %d（从左到右），行号从 1 数到 %d（从上到下）。\n\n"
              "请找到【%s】。%s\n\n"
              "只回答这个格式（一行，不要推理过程、不要解释）：\n"
              "找到就回答：列号-行号     例如：2-2\n"
              "找不到就回答：无\n\n"
              "注意：只要给出目标**中心点所在**的那一个格子。" % (cols, rows, target, extra))

        ans = ""
        try:
            ans = (self.ask_chat_with_image(grid_img, gq, max_tokens=20,
                                            temperature=0, hd=hd) or "").strip()
        except Exception:
            ans = ""
        # 答了"无"就信它（它诚实）；没答出格子编号才换兜底再问一次
        if not ans or ("无" not in ans and
                       not re.search(r"(\d{1,2})\s*-\s*(\d{1,2})", ans)):
            try:
                a2 = _unwrap(self._ask(grid_img, gq, max_tokens=300,
                                       temperature=0, hd=hd)).strip()
                if a2:
                    ans = a2
            except Exception:
                pass
        ans = ans.strip()

        # 抠出 "7-9" 这种
        m = re.search(r"(\d{1,2})\s*-\s*(\d{1,2})", ans)
        if not m:
            # 试试"第7列第9行"
            m2 = re.search(r"第?\s*(\d{1,2})\s*列[^\d]{0,4}第?\s*(\d{1,2})\s*行", ans)
            if m2:
                m = m2

        # ★ 第 46 轮兜底 A：autoglm-phone 有时不按格式答题，改写小作文
        #   （实测原话："完成！搜索图标位于右上角，坐标大约在 (836, 75)…"）。
        #   小作文里若有坐标就抠出来**当粗定位**——后面反正有 _verify_spot
        #   裁块复核把门，报歪了也进不了点击；refine 还会在那一格里精修。
        if not m:
            mc = re.search(r"[（(]\s*(\d{2,5})\s*[,，]\s*(\d{1,5})\s*[)）]", ans)
            if mc:
                sx = int(mc.group(1)) // scale
                sy = int(mc.group(2)) // scale
                cw = W / float(cols); ch = H / float(rows)
                cc = int(sx // cw) + 1
                cr = int(sy // ch) + 1
                if 1 <= cc <= cols and 1 <= cr <= rows:
                    return {"found": True, "x": int(sx), "y": int(sy),
                            "cell": (cr, cc), "raw": ans[:120],
                            "why": "模型没按格式答，从小作文里抠出坐标当粗定位"}

        # ★ 第 46 轮兜底 B：彻底没数 → 换更凶的格式提示重问一次（就一次）
        if not m:
            try:
                ans2 = _unwrap(self._ask(
                    grid_img,
                    "上一条回答没按格式，重新来。这张图上有网格，每个格子左上角"
                    "有【列号-行号】编号。\n"
                    "【%s】在哪一格？\n"
                    "只允许两种回答：\n"
                    "  列号-行号（例如 2-2）\n"
                    "  无\n"
                    "别的字一个都不许有。" % target,
                    max_tokens=40, temperature=0, hd=hd)).strip()
                m = re.search(r"(\d{1,2})\s*-\s*(\d{1,2})", ans2)
                if m:
                    ans = ans2
            except Exception:
                pass

        if not m:
            return {"found": False, "x": 0, "y": 0, "cell": None,
                    "raw": ans[:120],
                    "why": "模型没给出格子编号（它说：%s）" % ans[:60].replace("\n", " ")}

        c_i = int(m.group(1)); r_i = int(m.group(2))
        if not (1 <= c_i <= cols and 1 <= r_i <= rows):
            return {"found": False, "x": 0, "y": 0, "cell": (r_i, c_i),
                    "raw": ans[:120],
                    "why": "模型给的格子超出范围 %d-%d" % (c_i, r_i)}

        # ★ 坐标由我算（注意尺寸要换回原图比例）
        cx = (c_i - 0.5) / float(cols) * W
        cy = (r_i - 0.5) / float(rows) * H
        if scale > 1:
            cx /= scale; cy /= scale
        return {"found": True, "x": int(round(cx)), "y": int(round(cy)),
                "cell": (r_i, c_i), "raw": ans[:60], "why": "网格法认格子"}

    def _locate_once(self, img_bytes, target, extra="", hd=False):
        """在给定图上找 target，返回 {found,px,py,conf,why}，坐标是**该图的百分比**。"""
        # ★ 第 46 轮审查修正：要按格式输出（JSON）的活主答 glm-4v-flash，
        #   autoglm-phone 降为兜底 —— 跟 is_on_page/locate_grid 同一条规矩
        q = ("请在这张手机截图里找到【%s】的位置。%s\n\n"
             "要求：\n"
             "1. 只回答一个 JSON，不要解释、不要 markdown 代码块\n"
             "2. 格式：{\"found\": true/false, \"x\": 数字, \"y\": 数字, \"conf\": \"high\"/\"low\"}\n"
             "3. x、y 是**相对于这张图的百分比**（0-100，保留一位小数），点目标正中\n"
             "4. 找不到就 found=false，x、y 填 0\n"
             "5. 没把握 conf 填 low\n\n"
             "示例：{\"found\": true, \"x\": 50.0, \"y\": 87.5, \"conf\": \"high\"}"
             % (target, extra))
        raw = ""
        try:
            raw = self.ask_chat_with_image(img_bytes, q, max_tokens=200,
                                           temperature=0, hd=hd) or ""
        except Exception:
            raw = ""
        if "{" not in raw:
            try:
                raw = self._ask(img_bytes, q, max_tokens=200,
                                temperature=0, hd=hd)
            except Exception:
                raw = ""

        # ★ autoglm-phone 会把答案裹在 finish(message="...") 里 —— 剥掉
        raw = _unwrap(raw)
        m = re.search(r"\{[^{}]*\}", raw, re.S)
        if not m:
            return {"found": False, "pct": (0, 0), "conf": "low",
                    "why": "模型没说清楚（" + raw[:60].replace("\n", " ") + "）"}
        try:
            d = json.loads(m.group(0))
        except Exception:
            return {"found": False, "pct": (0, 0), "conf": "low",
                    "why": "模型返回的不是标准格式"}
        if not d.get("found"):
            return {"found": False, "pct": (0, 0),
                    "conf": d.get("conf", "low"), "why": "屏幕上没找到"}
        try:
            return {"found": True,
                    "pct": (float(d.get("x", 0)), float(d.get("y", 0))),
                    "conf": d.get("conf", "low"), "why": "模型指认"}
        except Exception:
            return {"found": False, "pct": (0, 0), "conf": "low",
                    "why": "坐标解析不了"}

    def locate(self, png_bytes, target, extra="", crop_hint=None):
        """
        找 target 在屏幕上的位置 —— **两段式定位**（规格书 1.6 的"局部放大重试"）。

        第一段：全屏图，让模型给百分比
        第二段：如果模型说"没把握"或给了 crop_hint 区域 → 把那一块裁出来放大再问一遍
                （截图放大后，小图标/小字在模型眼里会清楚得多，坐标更准）

        crop_hint: (x1%, y1%, x2%, y2%) 告诉引擎"东西大概在这个区域"，先裁这里精定位。
                   实测教训：底部导航栏那种贴边的小图标，全屏问必偏，必须裁剪。

        返回 {"found": bool, "x": int, "y": int, "why": str, "conf": "high|low", "stage": str}
        坐标是按 **原图（截图像素）** 给的。
        """
        from phone import _png_size
        W, H = _png_size(png_bytes)
        if not W:
            try:
                from PIL import Image
                W, H = Image.open(io.BytesIO(png_bytes)).size
            except Exception:
                raise VisionError("这张截图读不出尺寸", "invalid png")

        def to_px(pct, w, h):
            return (max(0, min(w - 1, int(round(pct[0] / 100.0 * w)))),
                    max(0, min(h - 1, int(round(pct[1] / 100.0 * h)))))

        # ---- 第二段优先：指定区域 → 直接裁了精定位 ----
        if crop_hint:
            try:
                from PIL import Image
                x1 = int(W * crop_hint[0] / 100.0); y1 = int(H * crop_hint[1] / 100.0)
                x2 = int(W * crop_hint[2] / 100.0); y2 = int(H * crop_hint[3] / 100.0)
                im = Image.open(io.BytesIO(png_bytes)).convert("RGB").crop((x1, y1, x2, y2))
                buf = io.BytesIO(); im.save(buf, "JPEG", quality=90)
                sub = buf.getvalue()
                r2 = self._locate_once(sub, target, extra)
                if r2["found"]:
                    sw, sh = im.size
                    dx, dy = to_px(r2["pct"], sw, sh)
                    return {"found": True, "x": x1 + dx, "y": y1 + dy,
                            "conf": r2["conf"], "why": "局部放大定位", "stage": "crop"}
            except Exception:
                pass  # 裁图失败 → 退回全屏

        # ---- 第一段：全屏 ----
        r1 = self._locate_once(png_bytes, target, extra)
        if r1["found"] and r1["conf"] == "high":
            px, py = to_px(r1["pct"], W, H)
            return {"found": True, "x": px, "y": py,
                    "conf": "high", "why": "全屏定位", "stage": "full"}

        # ---- 全屏没把握 → 拿模型的粗略位置裁一块放大再来 ----
        if r1["found"]:
            try:
                from PIL import Image
                cx, cy = r1["pct"]
                # 以模型给的点为中心，裁一块 40% x 25% 的区域放大
                bx1 = max(0, int(W * (cx - 20) / 100.0)); bx2 = min(W, int(W * (cx + 20) / 100.0))
                by1 = max(0, int(H * (cy - 12) / 100.0)); by2 = min(H, int(H * (cy + 12) / 100.0))
                if bx2 - bx1 > 20 and by2 - by1 > 20:
                    im = Image.open(io.BytesIO(png_bytes)).convert("RGB").crop((bx1, by1, bx2, by2))
                    buf = io.BytesIO(); im.save(buf, "JPEG", quality=90)
                    r2 = self._locate_once(buf.getvalue(), target, extra)
                    if r2["found"]:
                        sw, sh = im.size
                        dx, dy = to_px(r2["pct"], sw, sh)
                        return {"found": True, "x": bx1 + dx, "y": by1 + dy,
                                "conf": "high", "why": "全屏+局部放大",
                                "stage": "full+crop"}
            except Exception:
                pass
            px, py = to_px(r1["pct"], W, H)
            return {"found": True, "x": px, "y": py,
                    "conf": "low", "why": r1["why"], "stage": "full"}

        return {"found": False, "x": 0, "y": 0,
                "conf": r1["conf"], "why": r1["why"], "stage": "full"}

    # ---------- 能力 3：问一个判断题（P5 用） ----------

    def ask(self, png_bytes, question, max_tokens=300, hd=False):
        """拿截图问一个是非/短答问题。hd=True 走高清（读小字用）。"""
        return _unwrap(self._ask(png_bytes, question, max_tokens=max_tokens,
                                 hd=hd)).strip()

    # ---------- 能力 5：纯文本提问（不给图，P8b 生成回复用） ----------

    def ask_text(self, prompt, max_tokens=400, temperature=0.7):
        """
        不给图片，纯文本提问 —— 用来"生成一句回复"（**用说话模型 chat_model**）。

        ★ 为什么必须换模型（P8b 实测定案，见类注释）：
          autoglm-phone 干这个活会**写小作文 + 幻觉**（它以为自己在看屏幕）。
          glm-4v-flash 同一句提示词给出「大理古城离这里不远，有空一起玩吧！」✅
        ★ 温度默认 **0.7**（不是 0.1）—— 聊天要有人味，温度 0 会每次说同一句。
        """
        return self._post(self.chat_model,
                          [{"role": "user", "content": prompt}],
                          max_tokens, temperature).strip()

    def ask_chat_with_image(self, png_bytes, prompt, max_tokens=400,
                            temperature=0.1, hd=False):
        """
        ★ 用**说话模型**看图问答（P8c 实测定案）。

        ★ 什么时候用它，什么时候用 ask()：
          | 任务 | 用哪个 | 为什么 |
          |---|---|---|
          | "东西在哪，在第几格" | **ask()** vision_model | 看图定位是它的强项 |
          | "屏幕上是什么/是不是弹窗/该点哪个按钮" | **本方法** chat_model | 要**按格式输出**、要**判断** |
          | "生成一句回复" | ask_text() | 纯文字 |

        ★ 实测依据（P8c）：让 autoglm-phone 判断"有没有弹窗、输出 JSON"，
          它答对了内容但**不按 JSON 输出**，给的是它自己的动作格式：
              has_popup: true
              do(action="Tap", element=[649,605])
          → 解析失败 → 误判"没有弹窗" → 弹窗挡着屏幕后面全错。
          换 glm-4v-flash 就老老实实输出 JSON。
          **规律：任何"要按格式输出"的活，都别交给 autoglm-phone。**
        """
        b64 = self._encode(png_bytes, max_w=(0 if hd else None),
                           quality=(92 if hd else None))
        return self._post(self.chat_model, [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url",
                 "image_url": {"url": "data:image/jpeg;base64," + b64}},
            ],
        }], max_tokens, temperature).strip()

    # ---------- 能力 4：认出现在在哪个 App / 哪个页（P5 状态感知） ----------

    # 已知 App 的"长相特征"（★ 规格书 13.1.6：AI 自学 App 界面，这是种子表）
    # ★ 2026-10-02 大坑修正：光认"主页底部标签栏"不够 ——
    #   聊天**对话页**没有那排标签（底部是输入栏），实测微信对话页被认成 unknown，
    #   直接害得 AI"明知道是微信却要重新找"。主页/对话页两种长相都要认。
    APP_HINTS = {
        "soul":    "Soul：主页底部有「星球 / 广场 / 发布瞬间 / 聊天 / 我」，配色偏紫蓝；"
                   "聊天对话页：主题偏深色，气泡是蓝紫色圆角",
        "momo":    "陌陌：主页底部有「消息 / 附近 / 动态 / 直播 / 我」；"
                   "聊天对话页：气泡偏黄橙色，顶部是对方昵称",
        "wechat":  "微信：主页底部有「微信 / 通讯录 / 发现 / 我」；"
                   "聊天对话页：整体白底，顶部左边是联系人名字、右边一个「…」，"
                   "底部一条输入栏（带笑脸图标和「+」），对方气泡白色、自己的气泡浅绿",
        "browser": "浏览器：顶部是网址搜索栏，页面大片空白或是网页",
    }

    def which_app(self, png_bytes):
        """
        判断现在在哪个 App。返回 "soul"/"momo"/"wechat"/"browser"/"unknown"。

        ★ 实测教训①：模型会把 Soul 认成探探 —— 给它"长相特征"提示。
        ★ 实测教训②（2026-10-02）：光认"主页底部标签栏"不够 —— 聊天**对话页**
          没有那排标签，微信对话页被认成 unknown。提示词里补上对话页特征。
        ★ 实测教训③（2026-10-02，最关键）：**判断类问题主答必须用说话模型**
          （规矩早就定了：要按格式输出的活别交给 autoglm-phone）。
        ★ 实测教训④（2026-10-02）：一道大题里又让认桌面又让认 App，
          模型会把**桌面**也认成 wechat（桌面上有图标它就蒙）。
          实测分开问它答得很准（"这是桌面吗"→"桌面"，秒答）。
          → 所以**先过一道门**：桌面/系统页直接返回 unknown，
            确认在 App 内部才去认是哪个 App。
        """
        # ---- 第一道门：这是桌面/锁屏/系统页吗？（分开问，模型很准） ----
        try:
            gate = (self.ask_chat_with_image(
                png_bytes,
                "这张手机截图是哪一类？\n"
                "- 桌面：手机桌面/launcher（大壁纸 + 散排的应用图标，"
                "底部可能有一排固定小图标），或锁屏、下拉通知栏、系统设置这类系统页面\n"
                "- App内部：某个应用打开后的页面\n\n"
                "只回答一个词：桌面 / App内部",
                max_tokens=10, temperature=0) or "").strip()
        except Exception:
            gate = ""
        self._log_gate(gate)
        if "桌面" in gate or "锁屏" in gate or "系统" in gate:
            return "unknown"
        # 模型没按格式答（空/乱词）→ 当作"没认出来"，继续往下认一次也无妨

        # ---- 第二步：确认在 App 内部 → 认是哪个 App ----
        hints = "\n".join("- %s：%s" % (k, v) for k, v in self.APP_HINTS.items())
        q = ("这是手机截图，现在是**某个 App 的内部页面**。请判断是下面哪个 App：\n"
             + hints + "\n\n"
             "判断要点：聊天**主页**看底部的标签栏；聊天**对话页**（正在跟某人聊，"
             "有输入框和气泡）看气泡颜色和顶栏/输入栏的样子。\n"
             "只回答一个词：soul / momo / wechat / browser / unknown")

        # ---- 主答：说话模型（判断/格式输出是它的活） ----
        try:
            ans = (self.ask_chat_with_image(png_bytes, q, max_tokens=20,
                                            temperature=0) or "").strip().lower()
            for k in ("soul", "momo", "wechat", "browser"):
                if k in ans:
                    return k
        except Exception:
            pass

        # ---- 兜底：看图定位模型（认主页标签栏快） ----
        try:
            ans = _unwrap(self._ask(png_bytes, q, max_tokens=20,
                                    temperature=0)).strip().lower()
            for k in ("soul", "momo", "wechat", "browser"):
                if k in ans:
                    return k
        except Exception:
            pass
        return "unknown"

    def _log_gate(self, gate):
        try:
            print("    [which_app] 门：%s" % gate[:12], flush=True)
        except Exception:
            pass

    def is_on_page(self, png_bytes, expect, hd=False):
        """
        判断当前是不是在某个页面上（返回 (bool, 理由)）。
        用于"点完之后检查有没有点对"，点错了就回退（规格书 1.8）。

        ★ 第 46 轮升级（两个都是实打实栽过的坑）：
          ① 判断类问题主答换**说话模型**（ask_chat_with_image）——
            跟 which_app 教训③同一条规矩：要按格式输出的活别交给 autoglm-phone；
          ② 支持 hd=True —— 读"微信主页底部那排小标签"这种小字，
            缩到 540px 就是瞎的（老坑 4）。认路里的页面判断一律传 hd=True。
        """
        q = ("这是手机截图。请回答：%s\n"
             "只回答「是」或「否」，再加一个逗号和一个不超过 15 字的理由。\n"
             "示例：是，能看到底部有聊天列表" % expect)
        ans = ""
        # ---- 主答：说话模型（判断/格式输出是它的活） ----
        try:
            ans = (self.ask_chat_with_image(png_bytes, q, max_tokens=60,
                                            temperature=0, hd=hd) or "").strip()
        except Exception:
            pass
        # ---- 兜底：看图定位模型 ----
        if not ans:
            try:
                ans = _unwrap(self._ask(png_bytes, q,
                                        max_tokens=60, temperature=0, hd=hd)).strip()
            except Exception:
                ans = ""
        yes = ans.startswith("是") or ans.startswith("yes")
        why = ans.split("，", 1)[-1].split(",", 1)[-1].strip()[:40]
        return yes, why

    def screen_changed(self, png_a, png_b):
        """
        两张图是不是**明显不同**（判断"点了之后屏幕有没有反应"）。
        纯本地像素比对，不花钱、不调模型。
        """
        if len(png_a) != len(png_b):
            # 长度差异大 → 肯定变了
            if abs(len(png_a) - len(png_b)) > 5000:
                return True
        # 快速抽样比对（取中部若干字节）
        n = min(len(png_a), len(png_b))
        if n < 200:
            return True
        step = max(1, n // 400)
        diff = sum(1 for i in range(0, n - 4, step)
                   if png_a[i:i + 4] != png_b[i:i + 4])
        checks = len(range(0, n - 4, step)) or 1
        ratio = diff / checks
        # 压缩后的 PNG 字节流本身就反映图像内容，差异 > 2% 算变了
        return ratio > 0.02


# ---------- 自检（P1 验收） ----------

def self_test():
    """真机 + 真模型 全链路自检：截图 → 模型看图 → 找元素 → 拿坐标。"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from phone import Phone
    r = {"ok": False, "steps": []}
    try:
        r["steps"].append("① 连手机 …")
        p = Phone().connect()
        r["steps"].append("   ✓ " + p.serial)

        r["steps"].append("② 截图 …")
        png = p.screenshot_bytes()
        r["steps"].append("   ✓ %d 字节" % len(png))

        r["steps"].append("③ 让模型看这张图 …")
        v = VisionEngine()
        r["steps"].append("   用的模型：" + v.model)
        desc = v.describe(png)
        r["steps"].append("   ✓ 模型说：" + desc)

        r["steps"].append("④ 让模型找「聊天列表」并在图上指位置 …")
        loc = v.locate(png, "页面顶部的「聊天」标签")
        r["steps"].append("   ✓ found=%s 坐标=(%d,%d) 把握=%s"
                          % (loc["found"], loc["x"], loc["y"], loc["conf"]))

        r["ok"] = True
        r["desc"] = desc
        r["loc"] = loc
        r["model"] = v.model
        r["calls"] = v.calls
    except Exception as e:
        r["steps"].append("   ✗ " + str(e))
        r["error"] = str(e)
    return r


if __name__ == "__main__":
    res = self_test()
    for s in res["steps"]:
        print(s)
    print("\n结果：", "通过 ✓" if res["ok"] else "失败 ✗ " + res.get("error", ""))
    sys.exit(0 if res["ok"] else 1)
