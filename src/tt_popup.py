# -*- coding: utf-8 -*-
"""
拓客台 · 弹窗处理（P8c，P10b 的雏形）

★ 为什么单独一个模块（这是实测撞出来的）：
  跑 P8b 聊天闭环时，屏幕上突然弹出一个系统弹窗：
    「要允许应用一直在后台运行吗？ 允许"Soul"始终在后台运行可能会缩短电池续航时间。」
  这个弹窗**把整个聊天界面挡住了** —— 输入框定位、点击、打字全部失效。

  而且这类弹窗**一定会反复出现**：
    - 后台运行许可（Soul/陌陌都爱弹）
    - 评分求好评
    - 通知权限
    - 位置权限
    - 更新提示
    - 开通会员 / 广告

  → **所以"弹窗处理"必须是每一步动作之前的第一件事。**

★ 规格书 1.10.5 的三类动作（必须照这个做）：
  | 类型 | 例子 | 动作 |
  |---|---|---|
  | 无害 | 后台运行许可、通知权限、评分 | **自动点掉**（点"允许"或"拒绝/关闭"） |
  | 干扰 | 广告、更新提示、"开通会员" | **关掉**（找 ✕ 或"以后再说"），**绝不点开通/购买** |
  | 危险 | 支付、短信权限、通讯录、验证码 | **绝不动手，叫人**（规格书 1.9） |

★ 纯视觉：截图 → 模型判断是什么弹窗 → 按规则点哪里（规格书 0.1）
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from phone import Phone                            # noqa: E402
from vision import VisionEngine                     # noqa: E402


class PopupError(Exception):
    """弹窗处理失败。msg 是给用户看的中文大白话。"""
    def __init__(self, msg, detail=""):
        super().__init__(msg)
        self.msg = msg
        self.detail = detail


# ★★ 弹窗分类词表（★ V4.11 实测新增，界面「弹窗日志」要展示这个判断）
#
# 分三类，处理方式完全不同。**新增词只需往对应列表里加一行。**
#
# 无害：可以自动点掉，不影响账号安全
HARMLESS_WORDS = [
    "后台运行", "后台活动", "电池续航", "耗电",
    "通知权限", "允许通知", "消息通知",
    "评分", "好评", "喜欢", "体验如何", "给个评价", "五星",
    "位置权限", "定位", "附近",
    "存储", "相册", "相机权限", "麦克风权限",
    "新版本", "更新提示", "有新版本", "立即更新", "以后再说",
]

# 干扰：要关掉，但**绝不能点"开通/购买/确认付费"**
NUISANCE_WORDS = [
    "会员", "开通", "升级", "vip", "VIP", "充值", "金币",
    "优惠", "特惠", "限时", "礼包", "抽奖", "签到",
    "广告", "推广", "下载app", "下载APP",
]

# 危险：**绝不自动处理，一律叫人**（规格书 1.9）
DANGEROUS_WORDS = [
    "支付", "付款", "转账", "扣费", "扣款", "确认支付",
    "短信权限", "读取短信", "通讯录", "联系人",
    "验证码", "身份证", "实名", "银行卡", "密码",
    "退款", "绑定", "授权登录",
]


def _parse_popup_json(raw):
    """
    解析弹窗判断结果。**兼容三种形态**（实测模型三种都给过）：

    ① 标准 JSON：    {"has_popup": true, "what": "...", "buttons": ["允许"]}
    ② YAML 风格：    has_popup: true
                    what: 关于后台运行
                    buttons: [允许, 拒绝]
    ③ JSON 里套动作：  {"has_popup": true, "do": "Tap(...)"}

    返回 dict 或 None。
    """
    if not raw:
        return None
    import re
    import json as _json

    # ---- ① 先试标准 JSON ----
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        try:
            d = _json.loads(m.group(0))
            if "has_popup" in d:
                return d
        except Exception:
            pass

    # ---- ② YAML 风格 key: value ----
    d = {}
    for key in ("has_popup", "有无弹窗", "有没有弹窗"):
        mm = re.search(r"%s\s*[:：]\s*(true|false|是|否|有|没有|有弹窗|无)"
                       % key, raw, re.I)
        if mm:
            v = mm.group(1).lower()
            d["has_popup"] = v in ("true", "是", "有", "有弹窗")
            break
    if "has_popup" not in d:
        # 整段里出现"有弹窗"也认
        if re.search(r"有弹窗|存在弹窗", raw):
            d["has_popup"] = True
        elif re.search(r"没有弹窗|无弹窗|不存在弹窗", raw):
            d["has_popup"] = False
        else:
            return None

    mm = re.search(r"(?:what|内容|说明|弹窗内容)\s*[:：]\s*(.+)", raw)
    if mm:
        d["what"] = mm.group(1).strip().strip('"').strip("「」")

    mm = re.search(r"(?:buttons|按钮|按钮列表)\s*[:：]\s*(\[[^\]]*\]|.+)", raw)
    if mm:
        seg = mm.group(1).strip()
        bs = re.findall(r"[\"「']?([^\",\'\]\[\s「」]+)[\"」']?", seg)
        # 过滤掉 list 语法残留
        d["buttons"] = [b for b in bs if b not in ("", ",", "[", "]")]
    return d if d else None


class PopupHandler:
    """
    弹窗处理。用法：

        ph = PopupHandler(phone, vision)
        r = ph.check_and_handle()      # 每次动作前先调一下
        if r["handled"]: ...           # 处理掉了，可以继续
        if r["need_human"]: ...        # 要叫人（危险弹窗）
    """

    def __init__(self, phone, vision=None, verbose=True, shots_dir=None):
        self.phone = phone
        self.vision = vision or VisionEngine()
        self.verbose = verbose
        if shots_dir is None:
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            shots_dir = os.path.join(root, "data", "shots")
        self.shots_dir = shots_dir
        os.makedirs(self.shots_dir, exist_ok=True)
        self.log = []          # ★ 弹窗日志（规格书 4.7 全程记录 + 界面「弹窗日志」）

    def _log(self, msg):
        if self.verbose:
            print(msg, flush=True)

    # ---------- 核心：判断有没有弹窗、是哪一类 ----------

    def detect(self, png=None):
        """
        判断当前屏幕上有没有弹窗、是哪一类。

        ★ 实测踩坑（P8c）：一开始用 `vision.ask()`（看图模型 autoglm-phone）做这个判断，
          它**答对了内容但不给 JSON**，而是给自己的动作格式：
              has_popup: true
              do(action="Tap", element=[649,605])
          → 解析失败 → **误判"没有弹窗"** → 弹窗挡着屏幕，后面全错。
        ★ 修法：改用 `ask_chat_with_image()`（说话模型 glm-4v-flash）。
          规律：**任何"要按格式输出"的活，都别交给 autoglm-phone。**
        ★ 另外解析器同时兼容 JSON 和 YAML 风格的 key: value（双保险）。

        返回 {
          "has_popup": bool,
          "kind": "harmless"|"nuisance"|"dangerous"|"none",
          "what": "弹窗在说什么（一句话）",
          "buttons": ["拒绝", "允许"],
          "raw": "模型的原始回答",
        }
        """
        if png is None:
            png = self.phone.screenshot_bytes()
        raw = self.vision.ask_chat_with_image(
            png,
            "这是手机截图。请判断：屏幕上有没有**弹出的小窗口**挡在应用上面？\n"
            "（比如：权限询问、评分邀请、更新提示、广告、会员推广、支付确认）\n\n"
            "只输出一个 JSON 对象，不要解释、不要 markdown 代码块、不要任何其他行：\n"
            "{\"has_popup\": true 或 false,\n"
            " \"what\": \"这个弹窗在说什么，一句中文概括\",\n"
            " \"buttons\": [\"它上面所有按钮的文字，从左到右\"]}\n\n"
            "没有弹窗就输出 {\"has_popup\": false, \"what\": \"\", \"buttons\": []}",
            max_tokens=300, hd=False)

        d = _parse_popup_json(raw)
        if not d or not d.get("has_popup"):
            return {"has_popup": False, "kind": "none", "what": "",
                    "buttons": [], "raw": raw[:200]}

        what = str(d.get("what", ""))
        buttons = [str(b) for b in (d.get("buttons") or [])]
        blob = (what + " " + " ".join(buttons)).lower()

        def hit(words):
            return any(w.lower() in blob for w in words)

        # ★ 危险优先级最高（宁可误判成危险，也不许误点支付）
        if hit(DANGEROUS_WORDS):
            kind = "dangerous"
        elif hit(HARMLESS_WORDS):
            kind = "harmless"
        elif hit(NUISANCE_WORDS):
            kind = "nuisance"
        else:
            # ★ 没认出类别 → **按最保守处理**（规格书第 16 章拍板：AI 判断失败一律取最保守）
            kind = "nuisance"
        return {"has_popup": True, "kind": kind, "what": what,
                "buttons": buttons, "raw": raw[:200]}

    # ---------- 处理 ----------

    def handle(self, info=None, png=None):
        """
        按类别处理弹窗。

        返回 {"handled": bool, "action": str, "need_human": bool, "why": str}
        """
        if info is None:
            info = self.detect(png)
        r = {"handled": False, "action": "", "need_human": False, "why": "",
             "info": info}

        if not info.get("has_popup"):
            r["why"] = "没有弹窗"
            return r

        kind = info["kind"]
        what = info.get("what", "")
        self._log("    ⚠ 发现弹窗（%s）：%s" % (kind, what))
        self._log("      上面有按钮：%s" % info.get("buttons", []))

        # ---- 危险：绝不动手，叫人 ----
        if kind == "dangerous":
            r["need_human"] = True
            r["action"] = "叫人"
            r["why"] = "这是危险弹窗（涉及支付/权限/隐私），不许自动点：" + what
            self._log("    ✋ 危险弹窗，停手叫人")
            self.log.append({"kind": kind, "what": what, "action": "叫人"})
            return r

        # ---- 找要点的按钮 ----
        if kind == "harmless":
            # 无害 → 优先点"允许 / 同意 / 确定 / 以后再说 / 关闭"
            prefer = ["允许", "同意", "确定", "好的", "好", "以后再说",
                      "暂不", "稍后", "关闭", "取消", "拒绝"]
        else:
            # 干扰（广告/会员）→ 优先点"关闭 / ✕ / 以后再说 / 暂不 / 取消"
            # ★★ 绝对不许点"开通 / 购买 / 立即升级 / 确认"
            prefer = ["关闭", "✕", "×", "以后再说", "暂不", "稍后", "取消", "拒绝",
                      "残忍拒绝", "下次再说"]
            forbid = ["开通", "购买", "立即升级", "确认", "支付", "领取", "下载",
                      "立即更新", "马上体验"]

        btn_png = png or self.phone.screenshot_bytes()

        # ★ 先按"按钮文字"精定位（最可靠）；找不到再退回"✕"或角落
        target_btn = None
        for want in prefer:
            for got in info.get("buttons", []):
                if want and want in got:
                    target_btn = got
                    break
            if target_btn:
                break

        # ★ 干扰类：如果找不到允许点里的，但候选里有禁止点的 → 不能瞎点
        if kind == "nuisance" and not target_btn:
            for bad in forbid:
                for got in info.get("buttons", []):
                    if bad in got:
                        r["why"] = ("干扰弹窗上只有「%s」这类按钮，"
                                    "点了会开通东西 → 不点，交人处理" % got)
                        r["need_human"] = True
                        r["action"] = "叫人"
                        self._log("    ✋ " + r["why"])
                        self.log.append({"kind": kind, "what": what,
                                         "action": "叫人"})
                        return r

        if target_btn:
            loc = self.vision.locate_grid_refine(
                btn_png, "按钮「%s」" % target_btn,
                extra="在弹窗的最下面一排按钮里", cols=4, rows=8)
            if loc.get("found"):
                self._log("    → 点「%s」(%d, %d)" % (target_btn, loc["x"], loc["y"]))
                self.phone.tap(loc["x"], loc["y"])
                time.sleep(1.2)
                r["handled"] = True
                r["action"] = "点了「%s」" % target_btn
                self.log.append({"kind": kind, "what": what,
                                 "action": r["action"]})
                return r

        # ★ 兜底：找 ✕ 关闭按钮
        loc = self.vision.locate_grid_refine(
            btn_png, "弹窗右上角或右下角的关闭按钮（✕ 或 ×）",
            extra="在弹窗的边缘", cols=6, rows=10)
        if loc.get("found"):
            self._log("    → 点关闭 (%d, %d)" % (loc["x"], loc["y"]))
            self.phone.tap(loc["x"], loc["y"])
            time.sleep(1.2)
            r["handled"] = True
            r["action"] = "点了关闭按钮"
            self.log.append({"kind": kind, "what": what, "action": r["action"]})
            return r

        # 都找不到 → 叫人（绝不在不知道弹窗是什么的情况下瞎点）
        r["need_human"] = True
        r["action"] = "叫人"
        r["why"] = "弹窗上找不到可以安全点的按钮，交人处理"
        self.log.append({"kind": kind, "what": what, "action": "叫人"})
        return r

    def check_and_handle(self, max_rounds=3):
        """
        一步到位：检测 → 处理 → 复查（有时会连着弹好几个）。
        返回最后一次的 handle 结果；如果要叫人，立刻返回。
        """
        last = {"handled": False, "need_human": False, "why": "没有弹窗"}
        for i in range(max(1, max_rounds)):
            info = self.detect()
            if not info.get("has_popup"):
                if i == 0:
                    last = {"handled": False, "need_human": False,
                            "why": "没有弹窗", "info": info}
                return last
            res = self.handle(info)
            last = res
            if res.get("need_human"):
                return res
            if not res.get("handled"):
                return res
        return last


# ---------- 自检 ----------

def self_test(handle=True):
    """真机自检：看现在屏幕上有没有弹窗。handle=True 时顺便处理掉。"""
    r = {"ok": False, "steps": []}
    try:
        r["steps"].append("① 连手机 …")
        p = Phone().connect()
        r["steps"].append("   ✓ " + p.serial)
        v = VisionEngine()
        ph = PopupHandler(p, v)

        r["steps"].append("② 看有没有弹窗 …")
        info = ph.detect()
        r["steps"].append("   有没有：%s" % info["has_popup"])
        if info["has_popup"]:
            r["steps"].append("   是哪类：%s" % info["kind"])
            r["steps"].append("   在说啥：%s" % info["what"])
            r["steps"].append("   有哪些按钮：%s" % info["buttons"])
        r["info"] = info

        if handle and info["has_popup"]:
            r["steps"].append("③ 处理它 …")
            res = ph.handle(info)
            r["steps"].append("   动作：%s" % res["action"])
            r["steps"].append("   说明：%s" % res["why"])
            r["steps"].append("   要叫人吗：%s" % res["need_human"])
            r["result"] = res
        r["ok"] = True
    except Exception as e:
        r["steps"].append("   ✗ " + str(e))
        r["error"] = str(e)
    return r


if __name__ == "__main__":
    out = self_test(handle="--detect-only" not in sys.argv)
    for s in out["steps"]:
        print(s)
    print("\n结果：", "通过 ✓" if out["ok"] else "失败 ✗ " + out.get("error", ""))
    sys.exit(0 if out["ok"] else 1)
