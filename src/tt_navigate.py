# -*- coding: utf-8 -*-
"""
拓客台 · 认路（P13 的一部分：AI 自己走到目标聊天页）

★ 用户拍板的需求（2026-10-02）：
    「他已经知道这是微信的了，他竟然不知道自己去调用微信」
    —— 客户档案里写着 platform=wechat，AI 就该自己：
        回桌面 → 找到微信图标点开 → 搜索联系人 → 进聊天页
    而不是弹窗叫用户"先用手把手机切过去"。

★ 纯视觉（项目红线）：
    每一步都是 截图 → 模型看图 → 网格法算坐标 → adb 点击。
    不读控件树、不注入、不 hook。

★ 关键防呆（都是从血泪坑里来的）：
    · 坑 30：网格法认格子会认歪（微信图标被说成"中间偏右"，实际左下）
      → **落点前必须裁小块图复核**：裁出落点周围，问模型"这小块里是目标吗"，
         答"否"就当没找到，绝不瞎点。
    · 坑 7：模型认错 App → 每次关键落点之后都回读验证（which_app / is_on_page）。
    · 打字用 ADB Keyboard 广播（嘴），跟聊天闭环同一套。

★ 失败哲学（拍板过的）：AI 判断失败一律取最保守 —— 找不到路就停下叫人，
    绝不瞎点（点错人发错消息是真实社交事故）。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tt_typing import Typist              # noqa: E402


# 平台字段（customers.platform）→ vision.which_app 的键（两边一套词，别写岔）
PLATFORM2APP = {
    "wechat": "wechat", "微信": "wechat",
    "momo": "momo", "陌陌": "momo",
    "soul": "soul", "Soul": "soul",
}

APP_LABEL = {"wechat": "微信", "momo": "陌陌", "soul": "Soul"}

# ★ 直接拉起 App 用的包名（2026-10-02 实测：桌面上根本没有图标 ——
#   图标全在抽屉/文件夹里，让 AI"在桌面找图标"这条路本身就靠不住。
#   拉起 = 一条启动命令，跟手指点图标是**同一个 LAUNCHER 意图**，
#   App 自己分不出来；不读控件树、不注入、不 hook，看屏认人照样全走视觉。）
APP_PACKAGES = {
    "wechat": "com.tencent.mm",
    "momo": "com.immomo.momo",
    "soul": "cn.soulapp.android",
}


# ========================================================
# ★ 经验记忆（第 47 轮，抄 Mobile-Agent-E 的 Shortcuts/Tips lite）
#   论文实测：有经验库后重复任务平均步骤 -37%、成功率 +42%。
#   咱们最吃经验的点：**TA 在不在聊天列表里** ——
#   每次成功认路记一笔（走的哪条路），下次按经验走，少烧模型调用。
#   存 data/experience.json（用户资产，跟 store 一个待遇）。
# ========================================================

def _exp_path():
    from phone import _project_root
    return os.path.join(_project_root(), "data", "experience.json")


def _exp_load():
    try:
        with open(_exp_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _exp_save(data):
    try:
        with open(_exp_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class NavError(Exception):
    """认路失败。msg 是给用户看的中文大白话。"""
    def __init__(self, msg, detail=""):
        super().__init__(msg)
        self.msg = msg
        self.detail = detail


class Navigator:
    """
    认路器。用法：

        nav = Navigator(phone, vision, on_step=回调)
        r = nav.ensure_chat("张三", "wechat")
        # r = {"ok": True, "app": "wechat", "how": "已经走到微信的聊天页"}
    """

    def __init__(self, phone, vision, verbose=True, on_step=None):
        self.phone = phone
        self.vision = vision
        self.verbose = verbose
        # ★ 报话的嘴：跟 ChatLoop._step 一个签名（no, name, state, detail, png）
        self.on_step = on_step
        # 每次模型调用之间留点余量，别把手机和模型都赶得太急
        self._settle = 1.1

    # --------------------------------------------------------
    def _log(self, msg):
        if self.verbose:
            print(msg, flush=True)

    def _step(self, name, state, detail="", png=None):
        self._log("    [认路] %s" % detail)
        if self.on_step:
            try:
                self.on_step(name, state, detail, png)
            except Exception:
                pass

    def _shot(self):
        return self.phone.screenshot_bytes()

    # ========================================================
    # 对外主入口
    # ========================================================
    def ensure_chat(self, contact, platform, png=None):
        """
        保证「手机正停在 target App 里和 contact 的聊天页」。
        不在就想办法走过去；走不过去抛 NavError（让上层叫人）。

        contact   联系人昵称（如 "张三"）
        platform  customers.platform 的值（wechat/momo/soul，中文也认）

        ★★★ 第 46 轮重写（上一版的死法，实测日志钉死的）★★★
          旧版：用视觉模型猜"在哪个 App" → 猜错；靠盲按返回找主页 →
          把微信按退出了都不知道 → 接着在**桌面**上找放大镜 → 必败。
          新版：「在不在这个 App」**问系统**（前台包名，抄 Open-AutoGLM 的
          做法，它就是 dumpsys window 认前台的）——零误判、零模型调用；
          「在哪一页、跟谁聊」照样问视觉（红线没破）；每按一次返回，
          下一轮先查还在不在 App 里（Mobile-Agent 的 Reflection 铁律）。
        """
        target = PLATFORM2APP.get((platform or "").strip())
        if not target:
            raise NavError(
                "客户档案里没写清是哪个平台的（platform=%r），不知道该去哪个 App"
                % platform)
        label = APP_LABEL[target]
        pkg = APP_PACKAGES[target]

        # ---- ① 现在在不在这个 App（问系统，一次 adb，不出错）----
        fg = self._fg()
        in_app = (fg == pkg)
        self._log("  [认路] 前台包=%s（目标 %s）→ %s"
                  % (fg or "读不到", pkg, "在里面" if in_app else "不在"))

        # ---- ② 已经在目标 App 里，看是不是已经在跟 TA 的聊天页（HD）----
        if in_app:
            if png is None:
                png = self._shot()
            try:
                yes, _w = self.vision.is_on_page(
                    png, "这是和「%s」的聊天窗口吗（顶栏名字**正好是**「%s」，"
                         "不是群聊；下方有输入框、有聊天气泡）" % (contact, contact),
                    hd=True)
            except Exception as e:
                self._log("    ! 判断聊天页失败（按不在处理）：%s" % str(e)[:60])
                yes = False
            if yes:
                self._step("认路", "ok", "已经在 %s 和「%s」的聊天页" % (label, contact))
                return {"ok": True, "app": target,
                        "how": "已经在 %s 的聊天页" % label}
            self._step("认路", "running",
                       "在 %s 里，但不在「%s」的聊天页 —— 去找 TA" % (label, contact))
        else:
            self._step("认路", "running", "现在不在 %s，直接把它拉起来" % label)
            self._open_app(target)

            # ---- ②b 拉起后可能直接停在 TA 的聊天页（App 常恢复上次聊天）----
            #   命中了就省掉整个搜索流程
            png = self._shot()
            try:
                yes, _w = self.vision.is_on_page(
                    png, "这是和「%s」的聊天窗口吗（顶栏名字**正好是**「%s」，"
                         "不是群聊；下方有输入框）" % (contact, contact),
                    hd=True)
            except Exception as e:
                self._log("    ! 判断聊天页失败（按不在处理）：%s" % str(e)[:60])
                yes = False
            if yes:
                self._step("认路", "ok",
                           "%s 打开后正好停在和「%s」的聊天页" % (label, contact))
                return {"ok": True, "app": target, "how": "已进 %s 的聊天页" % label}

        # ---- ③ 走到 TA 的聊天页（列表直点/搜索双策略 + 经验记忆）----
        how = self._open_chat_by_search(contact, target)
        self._exp_record(target, contact, how)

        # ---- ④ 终验（HD）----
        png = self._shot()
        try:
            yes, why = self.vision.is_on_page(
                png, "这是和「%s」的聊天窗口吗（顶栏名字**正好是**「%s」，"
                     "不是群聊；下方有输入框）" % (contact, contact),
                hd=True)
        except Exception as e:
            self._log("    ! 终验判断失败：%s" % str(e)[:60])
            yes, why = False, "看不出来"
        if not yes:
            raise NavError(
                "走到 %s 里了，但没进到「%s」的聊天页（%s）—— 先停手，你来确认一下"
                % (label, contact, why or "页面对不上"))
        self._step("认路", "ok", "已经自己走到 %s 和「%s」的聊天页" % (label, contact))
        return {"ok": True, "app": target, "how": "已进 %s 的聊天页" % label}

    def _fg(self):
        """前台包名（问系统）。读不出给 "?"，只当下不在 App 里处理。"""
        try:
            return self.phone.foreground_package() or "?"
        except Exception as e:
            self._log("    ! 读前台包名失败（按不在 App 处理）：%s" % str(e)[:60])
            return "?"

    def _exp_record(self, target, contact, how):
        """成功认路后记一笔经验（走哪条路）。写失败不影响认路本身。"""
        try:
            exp = _exp_load()
            nav = exp.setdefault("nav", {})
            key = "%s|%s" % (target, contact)
            item = nav.get(key) or {"ok": 0, "first": time.strftime("%Y-%m-%d")}
            item["how"] = how
            item["ok"] = int(item.get("ok", 0)) + 1
            item["last"] = time.strftime("%Y-%m-%d %H:%M")
            nav[key] = item
            _exp_save(exp)
            self._log("    （经验已记：%s 走「%s」，第 %d 次）"
                      % (contact, "列表直点" if how == "list_tap" else "搜索", item["ok"]))
        except Exception as e:
            self._log("    ! 经验记忆写失败（不影响认路）：%s" % str(e)[:60])

    # ========================================================
    # 打开 App：先直接拉起（秒级、稳），失败再走视觉兜底
    # ========================================================
    def _launch_by_intent(self, target):
        """
        一条启动命令把 App 拉到前台。

        ★ 为什么要它：真机实测（2026-10-02）桌面第一屏只有快手/陌陌/有道几个图标，
          微信在抽屉/文件夹里 —— 让模型"在桌面找图标"既慢又不可靠。
        ★ 红线核对（写死，不许含糊）：这只是**启动**，跟手指点图标是同一个
          LAUNCHER 意图，App 无法区分也不在意；本项目的"只走视觉"红线管的是
          **感知和操作**（不读控件树、不注入、不 hook）—— 启动后认人、找输入框、
          打字、发送，照样全走 截图→看图→网格→adb 点击。
        """
        pkg = APP_PACKAGES.get(target)
        if not pkg:
            return False
        try:
            out, _, code = self.phone._run(["shell", "pm", "path", pkg], timeout=10)
            if code != 0 or not (out or "").strip():
                self._log("    ! 手机上没找到包 %s" % pkg)
                return False
            self.phone._run(["shell", "monkey", "-p", pkg, "-c",
                             "android.intent.category.LAUNCHER", "1"], timeout=20)
            # ★ 第 46 轮：验证从"问模型"改成"问系统"（前台包名轮询）。
            #   以前每次拉起要烧两次 which_app（门+认），还可能认错；
            #   现在轮询前台包名 —— 又快又准，模型调用省下来给"认页面"。
            deadline = time.time() + 8.0
            while time.time() < deadline:
                time.sleep(0.8)
                fg = self._fg()
                if fg == pkg:
                    time.sleep(1.6)      # 包对了再等页面铺完（别停在启动页）
                    self._log("    → 前台=%s（拉起成功，页面已等 1.6s）" % fg)
                    return True
            self._log("    ! 拉起 8 秒内前台没变成 %s（现在 %s）" % (pkg, self._fg()))
            return False
        except Exception as e:
            self._log("    ! 拉起失败：%s" % str(e)[:60])
            return False

    def _open_app(self, target):
        label = APP_LABEL[target]

        # ---- 第一招：直接拉起（秒级，不用管图标在哪） ----
        self._step("认路", "running", "直接把 %s 拉到前台…" % label)
        if self._launch_by_intent(target):
            self._step("认路", "ok", "%s 已经打开了" % label)
            return True
        self._log("    ! 拉起没成 → 退回视觉找图标")

        # ---- 兜底一：桌面两屏找图标（原来的视觉路子） ----
        try:
            self._open_app_visual(target)
            return True
        except NavError:
            pass

        # ---- 兜底二：上滑打开抽屉（全应用列表）找 ----
        try:
            self._open_app_drawer(target)
            return True
        except NavError:
            pass

        raise NavError(
            "%s 打不开：拉起命令没成、桌面和抽屉里也没认出它的图标。"
            "是不是手机上没装/没登录？你手动打开 %s 再试一次。"
            % (label, label))

    def _open_app_visual(self, target):
        """桌面网格找图标（原第一方案，现在降为兜底）。"""
        label = APP_LABEL[target]
        last_why = ""

        for attempt in range(2):
            # ---- 回桌面 ----
            try:
                self.phone.home()
            except Exception as e:
                self._log("    ! home 失败：%s" % e)
            time.sleep(1.3)

            # ---- 在桌面上找图标（可能不在第一屏 → 划一屏再找） ----
            for page in range(2):
                png = self._shot()
                loc = self.vision.locate_grid_refine(
                    png, "%s 的 App 图标" % label,
                    extra="图标下方一般写着「%s」两个字" % label)
                if loc.get("found") and self._verify_spot(
                        png, loc["x"], loc["y"], "%s 的图标" % label):
                    self._step("认路", "running",
                               "在桌面第 %d 屏找到 %s 图标了，点它" % (page + 1, label))
                    self.phone.tap(loc["x"], loc["y"])
                    time.sleep(2.4)          # App 冷启动要一会儿
                    png = self._shot()
                    try:
                        app = self.vision.which_app(png)
                    except Exception:
                        app = "unknown"
                    if app == target:
                        return True
                    last_why = "点了图标但进去的是「%s」" % app
                    self._log("    ! %s" % last_why)
                    break                    # 图标点了但不对 → 换一次尝试
                # 这屏没找到 → 划到下一屏再找
                if page == 0:
                    W, H = self.phone.screen_size()
                    self.phone.swipe(int(W * 0.8), int(H * 0.5),
                                     int(W * 0.2), int(H * 0.5), 320)
                    time.sleep(1.0)

        raise NavError(
            "在桌面上没找到 %s 的图标（%s）" % (label, last_why or "两屏都没认出来"))

    def _open_app_drawer(self, target):
        """上滑打开全应用抽屉找图标（桌面没有图标时的视觉兜底）。"""
        label = APP_LABEL[target]
        W, H = self.phone.screen_size()

        for page in range(3):
            try:
                self.phone.home()
                time.sleep(1.0)
                # 上滑 = 打开抽屉（在抽屉里再上滑 = 翻页，所以只在第一页做上滑）
                if page == 0:
                    self.phone.swipe(int(W * 0.5), int(H * 0.85),
                                     int(W * 0.5), int(H * 0.30), 380)
                else:
                    self.phone.swipe(int(W * 0.8), int(H * 0.5),
                                     int(W * 0.2), int(H * 0.5), 320)
                time.sleep(1.3)
            except Exception:
                pass

            png = self._shot()
            loc = self.vision.locate_grid_refine(
                png, "%s 的 App 图标" % label,
                extra="这是全部应用的列表，图标下方写着「%s」" % label)
            if loc.get("found") and self._verify_spot(
                    png, loc["x"], loc["y"], "%s 的图标" % label):
                self._step("认路", "running",
                           "在应用列表里找到 %s 了，点它" % label)
                self.phone.tap(loc["x"], loc["y"])
                time.sleep(2.4)
                png = self._shot()
                try:
                    app = self.vision.which_app(png)
                except Exception:
                    app = "unknown"
                if app == target:
                    return True
                self._log("    ! 点了抽屉图标但进去的是「%s」" % app)

        raise NavError("应用列表里没认出 %s 的图标" % label)

    # ========================================================
    # 搜索联系人并进入聊天
    # ========================================================
    def _open_chat_by_search(self, contact, target):
        """
        走进和 contact 的聊天页（列表直点 + 搜索双策略）。

        ★ 第 46 轮重写（实测日志钉死的三个死法 + 一条捷径）：
          ① 上一版"盲按返回找主页"把微信按退出了都不知道 → 每轮开头先问
            系统"还在不在 App 里"（Mobile-Agent 的 Reflection 铁律）。
          ② 定位模型对整屏大图爱写小作文/报鬼格子（实测："36-74"）→
            拿不准就裁**顶部一条**单独认，坐标照样过 _verify_spot 把门。
          ③ ★ 捷径（Mobile-Agent 的做法）：最近聊过的人**就在聊天列表里**，
            先试着直接认人点进去，命中就省掉整个搜索流程。
          ④ 群聊陷阱：列表里可能同时有「张三」和「张三小分队」——问话里
            明写"不要选群聊"，点完再验一次顶栏名字，双保险。
        """
        label = APP_LABEL[target]
        pkg = APP_PACKAGES[target]

        # ---- ① 查经验：这位上次是怎么找到的？（Mobile-Agent-E 的 Shortcut 思想）----
        #   上次走"搜索"才找到 → 这次跳过列表直点，省一轮定位调用；
        #   上次走"列表直点"或没记录 → 默认先试列表（最便宜）
        skip_list_tap = False
        try:
            last_how = (_exp_load().get("nav") or {}).get(
                "%s|%s" % (target, contact), {}).get("how")
            skip_list_tap = (last_how == "search")
            if skip_list_tap:
                self._log("  [认路] 经验记忆：「%s」上次走搜索才找到，这次直接搜" % contact)
        except Exception:
            pass

        for attempt in range(3):
            # ---- ① 还在不在目标 App 里？（问系统，别猜）----
            fg = self._fg()
            if fg != pkg:
                self._log("    ! 第 %d 轮前台=%s，不在 %s 里 → 重新拉起"
                          % (attempt + 1, fg, label))
                if not self._launch_by_intent(target):
                    raise NavError(
                        "%s 拉不起来了（前台一直停在 %s）—— 你手动点开 %s 再试一次"
                        % (label, fg, label))
            png = self._shot()

            # ---- ② 策略 A：TA 就在当前列表里（最近聊过的基本都在）----
            #   ★ x_anchor=0.15：锚在行的**名字区**——不但复核裁块（±110px）
            #     能框到名字（锚在 0.42 时框到的是消息预览字，复核必否），
            #     点名字也是点这一行，一举两得（第 46 轮实测修正）。
            if skip_list_tap:
                loc0 = {"found": False}
            else:
                loc0 = self.vision.locate_grid_refine(
                    png, "聊天列表里名字**正好是**「%s」的那一行" % contact,
                    extra="注意：不要选「%s」开头的群聊（比如「%s小分队」），"
                          "要的是**一个人**的那行：头像 + 名字 + 最后一条消息" % (contact, contact),
                    x_anchor=0.15, pad=1)
                if not loc0.get("found"):
                    self._log("    (列表没认出人：%s)" % loc0.get("why", ""))
            if loc0.get("found") and self._verify_spot(
                    png, loc0["x"], loc0["y"],
                    "聊天列表的一行（头像+名字），名字**正好是**「%s」两个字，"
                    "不是「%s小分队」这种群聊" % (contact, contact)):
                self._log("    → 列表里直接认出「%s」，点进去" % contact)
                self.phone.tap(loc0["x"], loc0["y"])
                time.sleep(1.6)
                if self._looks_like_chat(contact):
                    return "list_tap"
                try:
                    self.phone.back()          # 点错了（比如点成群）→ 退回来
                    time.sleep(1.1)
                except Exception as e:
                    self._log("    ! 按返回失败：%s" % str(e)[:60])

            # ---- ③ 策略 B：点搜索（放大镜） ----
            #   ★ 截图必须重拍：上面那下 back 可能已经把页面换了
            #     （甚至把 App 按退出了），拿旧图定位 = 对着现在的屏幕盲点
            png = self._shot()
            spot = self._find_search_icon(png)
            if not spot:
                self._log("    ! 没找到搜索图标（第 %d 次）" % (attempt + 1))
                # 按一次返回，把可能开着的内层页收起来 ——
                # 就算这一下把 App 按退出了，下一轮开头也会查出来并重新拉起
                try:
                    self.phone.back()
                    time.sleep(1.1)
                except Exception as e:
                    self._log("    ! 按返回失败：%s" % str(e)[:60])
                continue
            self.phone.tap(spot[0], spot[1])
            time.sleep(1.4)

            # ---- ③ 输入联系人名字 ----
            try:
                with Typist(self.phone) as t:
                    t.type_text(contact)
            except Exception as e:
                raise NavError("在搜索框里打字失败：%s" % str(e)[:60])
            time.sleep(1.6)      # 等搜索结果刷出来

            # ---- ⑤ 在结果里找 TA 的名字那一条 ----
            png = self._shot()
            loc2 = self.vision.locate_grid_refine(
                png, "搜索结果里名字**正好是**「%s」的那一条" % contact,
                extra="注意：不要选「%s」开头的群聊，要**一个人**的那条" % contact,
                x_anchor=0.15, pad=1)
            if not loc2.get("found") or not self._verify_spot(
                    png, loc2["x"], loc2["y"],
                    "一条搜索结果，名字**正好是**「%s」，不是群聊" % contact):
                self._log("    ! 搜索结果里没认出「%s」" % contact)
                try:
                    self.phone.back()      # 收起搜索，下一轮重来
                    time.sleep(1.1)
                except Exception as e:
                    self._log("    ! 按返回失败：%s" % str(e)[:60])
                continue
            self.phone.tap(loc2["x"], loc2["y"])
            time.sleep(1.6)
            if self._looks_like_chat(contact):
                return "search"
            try:
                self.phone.back()
                time.sleep(1.1)
            except Exception as e:
                self._log("    ! 按返回失败：%s" % str(e)[:60])

        raise NavError(
            "在 %s 里搜「%s」没走进聊天页（最后一眼前台在 %s）。"
            "可能 TA 的备注名对不上、屏幕上有弹窗挡着，也可能微信停在应用锁/验证页"
            " —— 你瞄一眼手机手动进一下聊天页再试。" % (label, contact, self._fg()))

    # --------------------------------------------------------
    def _find_search_icon(self, png):
        """
        找搜索图标（放大镜），三路兜底，落点前都过 _verify_spot：
          0. ★ 锚点直猜（第 47 轮）：放大镜**永远**在顶栏右侧 x≈85%、y≈7% ——
             位置是死的，直接按规律猜 + 复核一次，零定位模型调用。
             （实测教训：定位模型的 y 在 150/262/500 之间乱跳，复核一直在
              正确地把关，但白白浪费三轮。能用领域规律锚死的就别问模型。）
          1. 裁**顶部一条**单独认（locate 的 crop_hint 两段式）
          2. 整屏网格定位 + x_anchor=0.85
        找到返回 (x, y)，没找到返回 None。
        """
        # 路径 0：领域锚点直猜
        try:
            from phone import _png_size
            W, H = _png_size(png)
            gx, gy = int(W * 0.85), int(H * 0.07)
            if self._verify_spot(png, gx, gy, "搜索图标（放大镜）"):
                self._log("    → 锚点直猜命中放大镜 (%d,%d)" % (gx, gy))
                return (gx, gy)
        except Exception as e:
            self._log("    ! 锚点直猜出错（走模型兜底）：%s" % str(e)[:60])

        # 路径 1：顶部 15% 区域两段式定位
        try:
            r = self.vision.locate(
                png, "搜索图标（放大镜）",
                extra="在顶部标题栏右侧，挨着「＋」",
                crop_hint=(55, 0, 100, 15))
            if r.get("found") and self._verify_spot(
                    png, r["x"], r["y"], "搜索图标（放大镜）"):
                self._log("    → 顶条认到了放大镜 (%d,%d)" % (r["x"], r["y"]))
                return (r["x"], r["y"])
        except Exception as e:
            self._log("    ! 顶条定位出错（走网格兜底）：%s" % str(e)[:60])

        # 兜底：整屏网格
        loc = self.vision.locate_grid_refine(
            png, "搜索图标（放大镜）",
            extra="在页面顶部那一排，通常靠右上角",
            x_anchor=0.85, pad=1)
        if not loc.get("found"):
            self._log("    (网格没认出放大镜：%s)" % loc.get("why", ""))
        elif self._verify_spot(
                png, loc["x"], loc["y"], "搜索图标（放大镜）"):
            return (loc["x"], loc["y"])
        return None

    def _looks_like_chat(self, contact):
        """粗验当前是不是和 contact 的聊天页（顶栏名字对上、不是群聊）。"""
        png = self._shot()
        try:
            yes, _why = self.vision.is_on_page(
                png, "这是一个聊天窗口吗，而且顶栏名字**正好是**「%s」"
                     "（不是群聊——群聊名字后面会带人数）？下方有输入框。" % contact,
                hd=True)
            return bool(yes)
        except Exception as e:
            self._log("    ! 粗验聊天页失败（按不是处理）：%s" % str(e)[:60])
            return False

    # ========================================================
    # ★ 落点复核（坑 30 的解法，写死在这里，谁都不许跳过）
    # ========================================================
    def _verify_spot(self, png, x, y, what, half=110):
        """
        裁出落点周围一小块，问模型"这小块里是目标吗"。
        ★ 为什么必须做：网格法会把图标认歪（坑 30 实测），直接点会点到别的地方。
          裁块复核让模型只看一小张干净的图，准确率高得多；答"否"就当没找到。
        ★★ 第 46 轮血泪教训：这个函数原来有 4 条**静默 return False** 的路 ——
          实测踩中一条（vision.ask() 收了个它没有的 temperature 参数，
          每次都 TypeError），结果前面修好的每一步定位全被它拦死，
          而且一条日志都不留，查了半天。现在每条早退路都开口说话。
        """
        from PIL import Image
        import io
        # ★ 第 46 轮审查修正：裁剪框必须跟 png **同一个坐标系**——
        #   wm size 报的是物理分辨率，截图实际尺寸可能因显示大小/DPI 而不同；
        #   直接量截图（零成本），永远不会错位
        try:
            from phone import _png_size
            W, H = _png_size(png)
        except Exception as e:
            self._log("    ! 复核读不出截图尺寸：%s" % str(e)[:60])
            return False
        x1, y1 = max(0, x - half), max(0, y - half)
        x2, y2 = min(W, x + half), min(H, y + half)
        if x2 - x1 < 24 or y2 - y1 < 24:
            self._log("    ! 复核裁剪框不对：(%.2d,%.2d)-(%.2d,%.2d)" % (x1, y1, x2, y2))
            return False
        try:
            im = Image.open(io.BytesIO(png)).convert("RGB").crop((x1, y1, x2, y2))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=90)
        except Exception as e:
            self._log("    ! 复核裁图失败：%s" % str(e)[:60])
            return False
        try:
            ans = self.vision.ask(
                buf.getvalue(),
                "这张小图（从手机截图裁出来的）的**中心**是什么？请判断：%s在这张图的"
                "中心附近吗？只回答「是」或「否」，不要解释。" % what,
                max_tokens=12).strip()
        except Exception as e:
            self._log("    ! 复核问模型失败：%s" % str(e)[:60])
            return False
        ok = ans.startswith("是") or ans.lower().startswith("yes")
        self._log("    → 落点复核 (%d,%d)「%s」：%s" % (x, y, what, "是" if ok else "否"))
        return ok


# ---------- 自检（要插着真机 + 配好模型才有意义） ----------

def self_test(contact=None, platform="wechat"):
    r = {"ok": False, "steps": []}
    try:
        from phone import Phone
        from vision import VisionEngine
        r["steps"].append("① 连手机 …")
        p = Phone().connect()
        v = VisionEngine()
        r["steps"].append("② 模型：" + v.model)
        nav = Navigator(p, v)
        if contact:
            r["steps"].append("③ 认路：%s → %s …" % (contact, platform))
            out = nav.ensure_chat(contact, platform)
            r["steps"].append("   ✓ %s" % out.get("how"))
            r["ok"] = bool(out.get("ok"))
        else:
            r["steps"].append("（没给联系人，只测 open_app）")
            nav._open_app(PLATFORM2APP.get(platform, "wechat"))
            r["ok"] = True
    except Exception as e:
        r["steps"].append("   ✗ " + str(e))
        r["error"] = str(e)
    return r


if __name__ == "__main__":
    name = None
    plat = "wechat"
    for a in sys.argv[1:]:
        if a.startswith("--name="):
            name = a.split("=", 1)[1]
        elif a.startswith("--platform="):
            plat = a.split("=", 1)[1]
    out = self_test(name, plat)
    for s in out["steps"]:
        print(s)
    print("\n结果：", "通过 ✓" if out["ok"] else "失败 ✗")
    sys.exit(0 if out["ok"] else 1)
