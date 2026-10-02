# -*- coding: utf-8 -*-
"""
页面 ⑨ 设置（图纸 view-settings，第 1301~1323 行）

★ 左导航 10 项、分 4 组（照抄图纸 set-nav，一字不改）：

    连接：账号与设备 / 模型设置 / 外观主题
    内容：人设管理 / 聊天策略 / 平台与配额
    运行：今日目标 / 通知与告警 / 数据与备份
    其他：关于与升级

★ 第 12 轮拍板的关键变化（写进这一页）：
    - 只填一个模型 API（不再分视觉/文本两组连接卡）
    - 模型两种能力档自适应（A 档多模态 / B 档纯文本降级并明确提示用户）
"""

from PySide6.QtCore import Qt, QSize, QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QLineEdit,
    QComboBox, QScrollArea, QStackedWidget, QPushButton, QCheckBox,
    QPlainTextEdit,
)
from ui import theme as TH
from ui import icons
from ui.widgets import Card, Btn, KV, page_title, faint, toast, modal, ask


# ============================================================
# 真活儿：备份 / 导出 / 连模型
#
# ★ 第 34 轮：设置页里原来有好几个按钮"点了只弹一句提示"。
#   用户骂的正是这种「装了样子但没功能」。
#   下面这些是**真会动磁盘 / 真会发网络请求**的实现。
# ============================================================
def _data_root():
    """项目根目录 —— 统一问 paths（别自己算，算错过）。"""
    from ui.paths import project_root
    return project_root()


def _do_backup():
    """
    真把 data/ 下的文件复制一份到 data/backup/<时间戳>/。
    ★ 只复制**文件**（数据库、store.json…），不递归子目录，
      免得把几百张截图和导出目录也拖进来，一备份好几百兆。
    """
    import os
    import shutil
    import time
    data = os.path.join(_data_root(), "data")
    if not os.path.isdir(data):
        return False, "还没有数据文件夹"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dst = os.path.join(data, "backup", stamp)
    os.makedirs(dst, exist_ok=True)
    n = 0
    for fn in sorted(os.listdir(data)):
        src = os.path.join(data, fn)
        if os.path.isfile(src) and not fn.startswith("~"):
            try:
                shutil.copy2(src, os.path.join(dst, fn))
                n += 1
            except Exception:
                pass
    return True, (dst, n, stamp)


def _do_export():
    """
    真导出：客户一份 CSV（Excel 能直接打开）+ 全量一份 JSON。
    写到 data/exports/ 下面。
    """
    import csv
    import json
    import os
    import time
    out = os.path.join(_data_root(), "data", "exports")
    os.makedirs(out, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")

    from ui.store import get_store
    st = get_store()
    rows = st.customers()

    csv_path = os.path.join(out, "客户-%s.csv" % stamp)
    cols = ["id", "name", "src", "stage", "heat", "familiar", "last", "tm", "note"]
    head = ["编号", "昵称", "平台", "阶段", "热度", "熟悉度", "最后一句", "时间", "备注"]
    # ★ utf-8-sig：Excel 打开中文不乱码（少了它整列变问号）
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(head)
        for r in rows:
            w.writerow([r.get(k, "") for k in cols])

    json_path = os.path.join(out, "全部数据-%s.json" % stamp)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "导出时间": time.strftime("%Y-%m-%d %H:%M:%S"),
            "客户": rows,
            "回收站": st.trash(),
            "消息": st.messages(),
            "设置": st.settings(),
        }, f, ensure_ascii=False, indent=2)

    return True, (out, len(rows), stamp)


def _test_api(base_url, key, model):
    """
    ★ 真发一次请求去问模型「在不在」，验证 Key 到底能不能用。
      原来点「测一下能不能用」是直接弹"测通了"—— 那是假的。
      现在：没填 Key 就直说没填；填了就真发，服务器回什么照实报。
    """
    import json
    import urllib.error
    import urllib.request
    if not key or key.strip() in ("", "在这里填", "粘贴你的 Key"):
        return False, "还没填 API Key（先粘贴再测）"
    url = (base_url or "https://open.bigmodel.cn/api/paas/v4").rstrip("/") + "/chat/completions"
    body = json.dumps({
        "model": model or "glm-4v-flash",
        "messages": [{"role": "user", "content": "回复两个字：在的"}],
        "max_tokens": 16,
        "temperature": 0,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", "Bearer " + key.strip())
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8"))
        txt = d["choices"][0]["message"]["content"].strip()
        return True, (txt[:40] or "（回了个空的，但钥匙是通的）")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "ignore")[:150]
        return False, "钥匙不对或没权限（HTTP %s）：%s" % (e.code, raw)
    except Exception as e:
        return False, "连不上：%s" % str(e)[:100]


def _ai_rewrite(base_url, key, model, old_text):
    """★ 真让模型把这段人设改写一版（不是假弹提示）。"""
    import json
    import urllib.error
    import urllib.request
    if not key or key.strip() in ("", "在这里填", "粘贴你的 Key"):
        return False, "还没填 API Key —— 填了才能让 AI 改"
    url = (base_url or "https://open.bigmodel.cn/api/paas/v4").rstrip("/") + "/chat/completions"
    prompt = ("下面是一段「替人聊天」的说话风格设定，请帮我改写得更自然、更好用，"
              "保持简短口语、不用书面语。只输出改写后的那段话，不要解释。\n\n原文：\n" + (old_text or ""))
    body = json.dumps({
        "model": model or "glm-4v-flash",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 400,
        "temperature": 0.8,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", "Bearer " + key.strip())
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            d = json.loads(r.read().decode("utf-8"))
        return True, d["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        return False, "模型没答应（HTTP %s）" % e.code
    except Exception as e:
        return False, "连不上：%s" % str(e)[:100]


class _ApiWorker(QThread):
    """
    ★ 发网络请求别卡界面：丢到后台线程跑，跑完用信号送回主线程。
      （界面线程一卡，用户就以为软件死了。）
    """
    done = Signal(bool, str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            ok, msg = self._fn()
        except Exception as e:
            ok, msg = False, str(e)[:120]
        self.done.emit(ok, msg)


# ============================================================
# 各组面板内容
# ============================================================
# ============================================================
# adb 真检测（「检测连接」按钮用）
# ============================================================
def _find_adb():
    import os
    here = os.path.dirname(os.path.abspath(__file__))          # src/ui
    root = os.path.dirname(os.path.dirname(here))              # 项目根
    for p in (
        os.path.join(root, "_tools", "scrcpy", "scrcpy-win64-v4.1", "adb.exe"),
        os.path.join(root, "_tools", "adb", "adb.exe"),
    ):
        if os.path.exists(p):
            return p
    return "adb"          # 退而求其次，走 PATH


def _adb_devices():
    """真跑一次 adb devices。返回 (设备列表, 错误说明)。"""
    import subprocess
    try:
        # ★ 别弹黑窗口（见 phone.py 里 _NO_WINDOW 的说明）
        from phone import _NO_WINDOW
    except Exception:
        _NO_WINDOW = 0x08000000
    try:
        r = subprocess.run([_find_adb(), "devices"],
                           capture_output=True, text=True, timeout=10,
                           creationflags=_NO_WINDOW)
        lines = [x for x in (r.stdout or "").splitlines()[1:] if x.strip()]
        devs = []
        for ln in lines:
            parts = ln.split()
            if len(parts) >= 2 and parts[1] == "device":
                devs.append(parts[0])
        return devs, None
    except FileNotFoundError:
        return [], "没找到 adb（数据线工具没装）"
    except subprocess.TimeoutExpired:
        return [], "adb 没反应（超过 10 秒）"
    except Exception as e:
        return [], str(e)[:80]


def _device_state(fresh=False):
    """
    问设备管家当前状态。

    ★ 拿不到就返回"未连接"，不给假数据（规格书 5.5 数据来源约束）。
    ★ fresh=True 时催它立刻重连 + 重拍（用户点「检测连接」时用）。
    """
    try:
        from ui import device_hub
        hub = device_hub.get_hub()
        if fresh:
            hub.poke()
        st = hub.state()
        info = hub.device_info()
        if info.get("model") and info.get("model") != "—":
            st.update(info)
        return st
    except Exception as e:
        d = {"connected": False, "serial": "—", "model": "—", "brand": "—",
             "android": "—", "width": "—", "height": "—", "density": "—",
             "why": "设备组件没起来：%s" % str(e)[:40]}
        return d


def _panel_account():
    c = Card()
    c.body().addWidget(_t("手机与设备"))

    kv_status = KV("设备状态", "正在查…")
    kv_serial = KV("设备编号", "—")
    kv_model = KV("设备型号", "—")
    kv_android = KV("安卓版本", "—")
    kv_screen = KV("屏幕尺寸", "—")

    for w in (kv_status, kv_serial, kv_model, kv_android, kv_screen):
        c.body().addWidget(w)

    def _paint(st=None):
        st = st or _device_state()
        ok = bool(st.get("connected"))
        t = TH.cur()
        kv_status.set_value("✔ 已连接" if ok else "✘ 没连上")
        kv_status.set_value_color(t["green"] if ok else t["red"])
        kv_serial.set_value(st.get("serial", "—"))
        kv_model.set_value(st.get("model", "—"))
        kv_android.set_value(st.get("android", "—"))
        w_, h_ = st.get("width", "—"), st.get("height", "—")
        kv_screen.set_value("%s×%s" % (w_, h_) if ok else "—")

    _paint()

    def _detect():
        """★ 真去查手机（这一段是真功能，不是演示）。"""
        _paint(_device_state(fresh=True))
        st = _device_state()
        if st.get("connected"):
            toast(c, "接上了：%s" % st.get("model", ""), "ok", 3200)
        else:
            toast(c, "没接上：%s" % (st.get("why") or "没找到手机"), "warn", 4600)

    row = QHBoxLayout()
    b1 = Btn("检测连接", "primary", icon_name="refresh")
    b1.clicked.connect(_detect)
    b2 = Btn("看一眼手机现在什么样", "ghost", icon_name="phone")
    b2.setToolTip("抓一张手机现在的画面（走的是真截图）")
    b2.clicked.connect(lambda: _peek_phone(c))
    row.addWidget(b1)
    row.addWidget(b2)
    row.addStretch(1)
    c.body().addLayout(row)

    tip = _tip("插上数据线，手机弹「允许 USB 调试吗」勾选「始终允许」再确定。"
               "顶栏左上角那个点变绿，就说明认出来了。")
    c.body().addWidget(tip)
    return c


def _peek_phone(widget):
    """抓一张手机现在的画面，弹层里给用户看（真截图）。"""
    try:
        from ui import device_hub
        hub = device_hub.get_hub()
        st = hub.state()
        if not st.get("connected"):
            toast(widget, "手机没连上，看不到画面", "warn")
            return
        png = hub.last_png()
        if not png:
            toast(widget, "还在拍，等两秒再点一次", "info")
            return

        from PySide6.QtGui import QPixmap
        from PySide6.QtCore import Qt as _Qt
        pm = QPixmap()
        pm.loadFromData(png)

        box = QWidget()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(0, 0, 0, 0)
        lb = QLabel()
        lb.setAlignment(_Qt.AlignCenter)
        lb.setPixmap(pm.scaled(230, 510, _Qt.KeepAspectRatio, _Qt.SmoothTransformation))
        bl.addWidget(lb)

        modal(widget, "手机现在是这样",
              box,
              [("知道了", None, "primary")])
    except Exception as e:
        toast(widget, "看不到画面：%s" % str(e)[:50], "error")


def _config_zhipu():
    """
    从 config/config.json 读**默认**的接口地址和 Key。

    ★ 为什么要读它：用户第一次打开"模型设置"，如果两栏都是空的，
      「测一下能不能用」和「让 AI 帮我改一版」就都用不了 ——
      明明配置文件里已经有钥匙了。所以这里把它当默认值填进去，
      用户看得见、改得动，软件也开箱能用。
    """
    import json
    import os
    try:
        p = os.path.join(_data_root(), "config", "config.json")
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        z = d.get("zhipu", {}) or {}
        return z.get("base_url", "") or "", z.get("api_key", "") or ""
    except Exception:
        return "", ""


def _panel_model():
    """
    ★ 第 12 轮拍板 #15：只填一个模型 API。
      一个 Key、一个 base_url，同账号下用两个模型名（看图 / 说话）。
    ★ 第 34 轮：填进去的地址/Key **真的存下来**（重开还在）；
      「测一下能不能用」**真发一次请求**，不再假弹"测通了"。
    """
    from ui.store import get_store
    st = get_store()
    _cfg_base, _cfg_key = _config_zhipu()

    c = Card()
    c.body().addWidget(_t("模型（只填一个 API）"))

    c.body().addWidget(_sub("一个账号、一个 Key，就够用。"
                            "看图的事和说话的事，软件自己分工。"))

    r1 = QHBoxLayout()
    r1.addWidget(QLabel("接口地址"), 0)
    e1 = QLineEdit(st.get_setting("api_base", "")
                   or _cfg_base or "https://open.bigmodel.cn/api/paas/v4")
    r1.addWidget(e1, 1)
    c.body().addLayout(r1)

    r2 = QHBoxLayout()
    r2.addWidget(QLabel("API Key"), 0)
    e2 = QLineEdit(st.get_setting("api_key", "") or _cfg_key)
    e2.setEchoMode(QLineEdit.Password)
    e2.setPlaceholderText("粘贴你的 Key")
    r2.addWidget(e2, 1)
    c.body().addLayout(r2)

    kv_test = KV("最近一次测试", "还没测过")
    c.body().addWidget(kv_test)

    c.body().addWidget(_line())

    c.body().addWidget(_t("软件自己分工会用到的两个模型名"))
    c.body().addWidget(KV("看图 / 找按钮", "autoglm-phone"))
    c.body().addWidget(KV("想回复 / 做判断", "glm-4v-flash"))

    tip = _tip("不用你管哪个是哪个。实测：看图交给专用模型更准，"
               "让它写回复会跑偏；所以软件分开用。")
    c.body().addWidget(tip)

    def _save_settings(*_):
        st.set_setting("api_base", e1.text().strip())
        st.set_setting("api_key", e2.text().strip())

    e1.editingFinished.connect(_save_settings)
    e2.editingFinished.connect(_save_settings)

    row = QHBoxLayout()
    b1 = Btn("测一下能不能用", "primary", icon_name="check")
    b2 = Btn("恢复默认", "ghost")
    row.addWidget(b1)
    row.addWidget(b2)
    row.addStretch(1)
    c.body().addLayout(row)

    cap = _tip("★ 能力档：这个模型如果是「能看图」的，走 A 档（全功能）；"
               "如果是「只能读字」的，自动降 B 档（会明确提示你哪些功能不能用）。")
    c.body().addWidget(cap)

    # ---- 真测：后台发一次请求，回来再说话 ----
    def _on_test_done(ok, msg):
        from PySide6.QtCore import QDateTime
        ts = QDateTime.currentDateTime().toString("MM-dd HH:mm")
        kv_test.set_value(("✔ %s" % msg) if ok else ("✘ %s" % msg))
        kv_test.set_value_color(TH.cur()["green"] if ok else TH.cur()["red"])
        st.set_setting("api_test_at", ts)
        st.set_setting("api_test_ok", bool(ok))
        if ok:
            toast(c, "测通了 —— 模型回了：%s" % msg, "ok", 3600)
        else:
            toast(c, "没通：%s" % msg, "error", 5200)

    def _test():
        _save_settings()
        kv_test.set_value("正在测…")
        kv_test.set_value_color(TH.cur()["sub"])
        w = _ApiWorker(lambda: _test_api(e1.text(), e2.text(), "glm-4v-flash"), c)
        w.done.connect(_on_test_done)
        w.finished.connect(w.deleteLater)
        c._tw = w              # ★ 留住引用，别让线程被回收器收走
        w.start()

    b1.clicked.connect(_test)

    def _reset():
        e1.setText("https://open.bigmodel.cn/api/paas/v4")
        e2.clear()
        _save_settings()
        kv_test.set_value("已恢复默认")
        kv_test.set_value_color(TH.cur()["sub"])
        toast(c, "已恢复默认（智谱的地址，Key 清空了，重新粘贴即可）", "info", 3600)

    b2.clicked.connect(_reset)

    # 进来先显示上次测的结果
    if st.get_setting("api_test_at"):
        ok = st.get_setting("api_test_ok")
        kv_test.set_value(("✔ 上次测通了" if ok else "✘ 上次没测通")
                          + " · " + str(st.get_setting("api_test_at")))
        kv_test.set_value_color(TH.cur()["green"] if ok else TH.cur()["red"])
    return c


def _panel_appearance():
    c = Card()
    c.body().addWidget(_t("外观主题"))
    c.body().addWidget(_sub("切换只改配色，不改任何布局和功能。"))

    row = QHBoxLayout()
    row.setSpacing(12)
    row.addWidget(_theme_card("深色", "默认。晚上看着不刺眼", True))
    row.addWidget(_theme_card("浅色", "白天在亮地方更清楚", False))
    row.addStretch(1)
    c.body().addLayout(row)
    return c


def _theme_card(name, desc, checked):
    f = QFrame()
    f.setObjectName("Card")
    f.setFixedSize(200, 118)
    border = TH.cur()["blue"] if checked else TH.cur()["line"]
    f.setStyleSheet("QFrame#Card{background:%s; border:1.5px solid %s;"
                    "border-radius:%s;}" % (TH.cur()["card"], border, TH.cur()["r_lg"]))
    l = QVBoxLayout(f)
    l.setContentsMargins(12, 11, 12, 11)
    l.setSpacing(5)

    prev = QFrame()
    prev.setFixedHeight(52)
    prev.setStyleSheet("background:%s; border-radius:8px;" % TH.cur()["bg"])
    pl = QHBoxLayout(prev)
    pl.setContentsMargins(6, 6, 6, 6)
    pl.setSpacing(5)
    side = QFrame()
    side.setFixedWidth(28)
    side.setStyleSheet("background:%s; border-radius:5px;" % TH.cur()["panel"])
    main = QFrame()
    main.setStyleSheet("background:%s; border-radius:5px;" % TH.cur()["card3"])
    pl.addWidget(side); pl.addWidget(main, 1)
    l.addWidget(prev)

    nm = QLabel("%s  %s" % ("✔" if checked else "  ", name))
    nm.setStyleSheet("font-weight:600; font-size:12.5px;"
                     + ("color:%s;" % TH.cur()["blue"] if checked else ""))
    ds = QLabel(desc)
    ds.setObjectName("Faint")
    ds.setStyleSheet("font-size:10.5px;")
    l.addWidget(nm); l.addWidget(ds)
    return f


def _panel_persona():
    """★ 第 11 轮 #9：人格 = 全局统一，不做按客户自定义。
    ★ 第 34 轮：「保存」真的存下来（重开还在）；「让 AI 帮我改一版」真调模型。"""
    from ui.store import get_store
    st = get_store()

    c = Card()
    c.body().addWidget(_t("人设（全局一份，所有客户共用）"))

    for k, v in (("称呼", "小周"), ("年龄", "24"), ("城市", "云南 · 大理"),
                 ("职业", "做设计的")):
        c.body().addWidget(KV(k, v))

    c.body().addWidget(_line())
    c.body().addWidget(_sub("说话风格（AI 照这个口气说话）"))

    _DEFAULT = ("性格开朗爱聊天。说话短、口语、像微信里聊天那样，"
                "一句不超过 25 个字。不用书面语，不爱用感叹号。")
    e = QPlainTextEdit(st.get_setting("persona_style", _DEFAULT))
    e.setFixedHeight(78)
    c.body().addWidget(e)

    kv_saved = KV("保存状态",
                  "已保存 · " + str(st.get_setting("persona_saved_at"))
                  if st.get_setting("persona_saved_at") else "还没改过（用的是默认那版）")
    c.body().addWidget(kv_saved)

    r = QHBoxLayout()
    b1 = Btn("保存", "primary", icon_name="save")
    b2 = Btn("让 AI 帮我改一版", "ghost", icon_name="robot")
    r.addWidget(b1)
    r.addWidget(b2)
    r.addStretch(1)
    c.body().addLayout(r)

    def _save():
        st.set_setting("persona_style", e.toPlainText().strip())
        import time as _tm
        ts = _tm.strftime("%m-%d %H:%M")
        st.set_setting("persona_saved_at", ts)
        kv_saved.set_value("已保存 · " + ts)
        kv_saved.set_value_color(TH.cur()["green"])
        toast(c, "人设已保存（重开软件也还在）", "ok")

    b1.clicked.connect(_save)

    def _on_rewrite(ok, msg):
        if not ok:
            toast(c, "AI 没帮上忙：%s" % msg, "error", 5200)
            return
        e.setPlainText(msg)
        st.set_setting("persona_style", msg)
        import time as _tm
        ts = _tm.strftime("%m-%d %H:%M")
        st.set_setting("persona_saved_at", ts)
        kv_saved.set_value("AI 改过一版 · " + ts)
        kv_saved.set_value_color(TH.cur()["blue"])
        toast(c, "AI 改好了 —— 你看看顺不顺口，不满意再点一次", "ok", 3600)

    def _rewrite():
        base = st.get_setting("api_base", "") or _config_zhipu()[0] \
            or "https://open.bigmodel.cn/api/paas/v4"
        key = st.get_setting("api_key", "") or _config_zhipu()[1]
        w = _ApiWorker(lambda: _ai_rewrite(base, key, "glm-4v-flash", e.toPlainText()), c)
        w.done.connect(_on_rewrite)
        w.finished.connect(w.deleteLater)
        c._rw = w
        # ★ 页面上立刻有反应（不只是飘一下提示）—— 用户盯着这一行就知道"在干活"。
        kv_saved.set_value("正在让 AI 改…（几秒钟，别关窗口）")
        kv_saved.set_value_color(TH.cur()["sub"])
        toast(c, "正在让 AI 改…（几秒钟）", "info", 2000)
        w.start()

    b2.clicked.connect(_rewrite)

    c.body().addWidget(_tip("人设是全局一份 —— 不用给每个客户单独设，太累。"
                            "（这条是当时拍板定下的）"))
    return c


def _panel_chat():
    """★ 第 11 轮 #11：聊天节奏界面可调（4 滑杆 + 3 档位）。"""
    c = Card()
    c.body().addWidget(_t("聊天节奏"))

    c.body().addWidget(_sub("★ 规矩：回复延迟必须是随机区间，不许写死一个数。"
                            "固定值一眼就看出来是机器人。"))
    c.body().addWidget(KV("回复延迟", "60 ~ 180 秒（随机）"))
    c.body().addWidget(KV("每次回复字数", "不超过 25 字"))
    c.body().addWidget(KV("同一个人两次回复间隔", "≥ 3 分钟"))
    c.body().addWidget(KV("每天主动开口上限", "6 条"))

    c.body().addWidget(_line())
    c.body().addWidget(_sub("整体节奏"))

    row = QHBoxLayout()
    row.addWidget(QLabel("整体节奏"))
    cb = QComboBox()
    cb.addItems(["慢（稳妥）", "中（默认）", "快（激进）"])
    from ui.store import get_store
    _st = get_store()
    cb.setCurrentIndex(int(_st.get_setting("tempo_idx", 1) or 0))
    cb.currentIndexChanged.connect(
        lambda i: (_st.set_setting("tempo_idx", i),
                   toast(c, "整体节奏改成：%s" % cb.currentText(), "info", 1800)))
    row.addWidget(cb)
    row.addStretch(1)
    c.body().addLayout(row)

    # ★ 第 38 轮：挂机模式下的发送方式
    #   试跑（默认）= AI 打好字弹卡片等你点头，**社交行为收不回，默认攥在你手里**；
    #   自动发 = 你在旁边看着的时候才开，省得每条都点。
    c.body().addWidget(_line())
    c.body().addWidget(_sub("挂机的时候，回话要不要等你点头？"))
    _auto = QCheckBox("自动发（不开的话，AI 每回一句都先弹卡片问你）")
    _auto.setChecked(bool(_st.get_setting("watch_auto_send", False)))
    _auto.setCursor(Qt.PointingHandCursor)
    _auto.toggled.connect(
        lambda v: (_st.set_setting("watch_auto_send", bool(v)),
                   toast(c, "挂机回复改成：%s" % ("自动发（你盯着的时候再开）" if v
                                                 else "先问你，你点头才发"),
                         "info", 3600)))
    c.body().addWidget(_auto)

    # ★ 第 39 轮：半夜聊不聊 —— 有些人就爱半夜聊，默认**不静默**
    _quiet = QCheckBox("半夜静默（23:00~08:00 不干活。默认不开 —— 半夜有人找就接着聊）")
    _quiet.setChecked(bool(_st.get_setting("watch_quiet", False)))
    _quiet.setCursor(Qt.PointingHandCursor)
    _quiet.toggled.connect(
        lambda v: (_st.set_setting("watch_quiet", bool(v)),
                   toast(c, "半夜静默：%s" % ("开了，23 点到早 8 点不动手机" if v
                                             else "关了，半夜有消息照样接"),
                         "info", 3200)))
    c.body().addWidget(_quiet)

    # ★ 第 39 轮：军师心法 —— 治"谢谢夸奖"那种客服腔
    _jun = QCheckBox("带上狗头军师（让回话更像真人聊天，默认开）")
    _jun.setChecked(bool(_st.get_setting("use_junshi", True)))
    _jun.setCursor(Qt.PointingHandCursor)
    _jun.toggled.connect(
        lambda v: (_st.set_setting("use_junshi", bool(v)),
                   toast(c, "狗头军师：%s" % ("已带上" if v else "已摘下"), "info", 2600)))
    c.body().addWidget(_jun)

    c.body().addWidget(_tip("★ 提醒：聊到借钱/转账这类话题，AI 会自己**岔开话题接着聊**，"
                            "不会罢工；但要是有人要**验证码/密码**，它一定停手叫你 —— "
                            "这两条是写死的，不归开关管。"))
    return c


def _panel_quota():
    """
    ★ 规格书 4.8.1 / 4.8.4：
        平台额度是**死红线**（程序写死，AI 不许超）；
        AI 自己控的是**节奏**（天花板以内调度）。
    ★ 第 13 轮 #40：微信「只承接不拓客」—— 界面上根本不给微信拓客开关。
    """
    c = Card()
    c.body().addWidget(_t("平台与配额"))
    c.body().addWidget(_sub("这里的数字是平台的天花板，程序写死，AI 不许超。"
                            "AI 只能在天花板以内调快慢。"))

    for plat, quota, note in (
        ("陌陌", "10", "当前主攻平台（产出最高、风控最低）"),
        ("Soul", "10", "正常"),
        ("微信", "3",  "★ 微信只承接不拓客 —— 不给拓客开关"),
    ):
        row = QHBoxLayout()
        a = QLabel(plat); a.setFixedWidth(52)
        a.setStyleSheet("font-weight:600;")
        b = QLabel("每天 %s 次" % quota)
        b.setObjectName("Sub")
        n = QLabel(note)
        n.setObjectName("Faint")
        n.setStyleSheet("font-size:11px;")
        row.addWidget(a); row.addWidget(b); row.addWidget(n, 1)
        c.body().addLayout(row)

    c.body().addWidget(_line())
    c.body().addWidget(_sub("安全锁（改不了，属于硬底线）"))
    for x in ("同一句话不发给超过 2 个人",
              "连续 3 次没人回，当天自动停",
              "打招呼分早 / 午 / 晚 3 批，不集中发",
              "同一 App 两次招呼间隔 ≥ 3 分钟"):
        lb = QLabel("· " + x)
        lb.setObjectName("Sub")
        lb.setStyleSheet("font-size:11.5px;")
        c.body().addWidget(lb)
    return c


def _panel_goal():
    c = Card()
    c.body().addWidget(_t("今日目标"))
    for k, v in (("今日新客", "3 位"), ("今日已回", "不限（有消息就回）"),
                 ("打招呼上限", "按平台天花板")):
        c.body().addWidget(KV(k, v))
    c.body().addWidget(_tip("目标只影响统计怎么算，不会让 AI 硬凑数。"))
    return c


def _panel_notify():
    """★ 第 12 轮 #26：聊热提醒只做界面内（声音+气泡+置顶），不做微信/邮件外推，但留接口。
    ★ 第 34 轮：每个开关**真的存下来**（重开还在），不再是"点了个寂寞"。"""
    from ui.store import get_store
    st = get_store()
    c = Card()
    c.body().addWidget(_t("通知与告警"))

    def _toggle(key, name, on):
        r = QHBoxLayout()
        a = QLabel(name); a.setObjectName("Sub")
        cb = QCheckBox()
        cb.setChecked(bool(st.get_setting("notify_" + key, on)))
        cb.toggled.connect(
            lambda v, k=key, nm=name: (st.set_setting("notify_" + k, bool(v)),
                                       toast(c, "%s：%s" % (nm, "开" if v else "关"),
                                             "info", 1600)))
        r.addWidget(a); r.addStretch(1); r.addWidget(cb)
        c.body().addLayout(r)

    for name, on in (("聊热了的时候提醒我（界面内）", True),
                     ("有人要见面信号时提醒我", True),
                     ("出错了提醒我", True),
                     ("声音提醒", True),
                     ("弹窗（右下角小条）", True)):
        _toggle(name, name, on)

    c.body().addWidget(_line())
    c.body().addWidget(_sub("外推（默认关闭）"))
    for name in ("推到微信", "推到邮件"):
        _toggle(name, name, False)

    c.body().addWidget(_tip("★ 当时拍板：聊热提醒只做软件内，不往微信/邮件推。"
                            "接口留着，以后想开随时开。"))
    return c


def _open_data_dir(widget):
    """真打开系统文件管理器（这个是能立刻验证的真功能）。"""
    import os
    import sys
    import subprocess
    from ui.paths import data_dir
    d = data_dir()
    if not os.path.isdir(d):
        toast(widget, "还没建数据文件夹（跑一次就自动有了）", "warn")
        return
    try:
        if sys.platform.startswith("win"):
            os.startfile(d)              # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", d])
        else:
            subprocess.Popen(["xdg-open", d])
        toast(widget, "已打开数据文件夹：%s" % d, "ok", 3600)
    except Exception as e:
        toast(widget, "打不开：%s" % str(e)[:50], "error")


def _panel_data():
    """
    ★ 第 34 轮：这三个按钮原来**只弹一句提示**（"已备份到 data/backup/"），
      磁盘上啥也没发生 —— 用户骂的就是这种。
      现在真复制、真导出、真打开文件夹，并且**界面上看得到结果**。
    """
    from ui.store import get_store
    st = get_store()

    c = Card()
    c.body().addWidget(_t("数据与备份"))
    c.body().addWidget(KV("数据位置", "data/"))
    c.body().addWidget(KV("数据库", "tuoke.db"))
    c.body().addWidget(KV("聊天记录保留", "180 天"))
    c.body().addWidget(KV("截图保留", "7 天"))

    kv_backup = KV("上次备份",
                   str(st.get_setting("last_backup")) if st.get_setting("last_backup")
                   else "还没备份过")
    kv_export = KV("上次导出",
                   str(st.get_setting("last_export")) if st.get_setting("last_export")
                   else "还没导出过")
    kv_open = KV("上次打开文件夹",
                 str(st.get_setting("last_open_dir")) if st.get_setting("last_open_dir")
                 else "还没打开过")
    c.body().addWidget(kv_backup)
    c.body().addWidget(kv_export)
    c.body().addWidget(kv_open)

    row = QHBoxLayout()
    b1 = Btn("立即备份", "primary", icon_name="save")
    b2 = Btn("打开数据文件夹", "ghost", icon_name="folder")
    b3 = Btn("导出全部数据", "ghost")
    row.addWidget(b1)
    row.addWidget(b2)
    row.addWidget(b3)
    row.addStretch(1)
    c.body().addLayout(row)

    def _backup():
        ok, res = _do_backup()
        if not ok:
            toast(c, "备份没成：%s" % res, "warn", 4600)
            return
        dst, n, stamp = res
        st.set_setting("last_backup", stamp)
        kv_backup.set_value(stamp + "（%d 个文件）" % n)
        kv_backup.set_value_color(TH.cur()["green"])
        toast(c, "备份好了：data/backup/%s（%d 个文件）" % (stamp, n), "ok", 4200)

    def _export():
        try:
            ok, res = _do_export()
        except Exception as e:
            toast(c, "导出没成：%s" % str(e)[:70], "error", 5200)
            return
        if not ok:
            toast(c, "导出没成：%s" % res, "warn", 4600)
            return
        out, n, stamp = res
        st.set_setting("last_export", stamp)
        kv_export.set_value(stamp + "（%d 位客户）" % n)
        kv_export.set_value_color(TH.cur()["green"])
        toast(c, "导出了：客户 CSV + 全部数据 JSON（%d 位客户）" % n, "ok", 4200)

    def _open():
        """真打开系统文件管理器；顺手把"上次打开时间"记上（界面看得见）。"""
        import time as _tm
        _open_data_dir(c)
        ts = _tm.strftime("%m-%d %H:%M")
        st.set_setting("last_open_dir", ts)
        kv_open.set_value(ts)
        kv_open.set_value_color(TH.cur()["green"])

    b1.clicked.connect(_backup)
    b2.clicked.connect(_open)
    b3.clicked.connect(_export)

    c.body().addWidget(_tip("★ 换大模型 API 不丢进度：阶段 / 热度 / 记忆 / 摘要 / 设置"
                            "全部在数据库里，模型只负责开口说话。"))
    return c


def _panel_about():
    """
    ★ 第 34 轮：「检查更新」原来只弹一句"已是最新版" —— 假话。
      它现在**真去读本机文件**，把这一版的构建时间算出来告诉你，
      你至少知道自己在跑哪一版（而不是一句空承诺）。
    """
    import os
    import time

    c = Card()
    c.body().addWidget(_t("关于与升级"))
    c.body().addWidget(KV("软件名称", "Taku · 拓客台"))
    c.body().addWidget(KV("版本", "v3.0"))

    # 真正的"这一版多重"：src 下最新改动的那个文件的修改时间
    newest, newest_f, n_files = 0, "—", 0
    src_dir = os.path.join(_data_root(), "src")
    for dirpath, _dirs, files in os.walk(src_dir):
        for fn in files:
            if fn.endswith(".py"):
                n_files += 1
                p = os.path.join(dirpath, fn)
                try:
                    m = os.path.getmtime(p)
                    if m > newest:
                        newest, newest_f = m, fn
                except Exception:
                    pass
    built = time.strftime("%Y-%m-%d %H:%M", time.localtime(newest)) if newest else "—"

    kv_build = KV("这一版的构建时间", built)
    kv_files = KV("源码文件", "%d 个 .py（最近改的是 %s）" % (n_files, newest_f))
    c.body().addWidget(kv_build)
    c.body().addWidget(kv_files)
    c.body().addWidget(KV("底子状态", "真机已打通（看屏 / 点屏 / 打字 / 发送）"))

    c.body().addWidget(_line())
    c.body().addWidget(_sub("★ 三个固定升级点（以后升级只动这三处）"))
    for x in ("换模型 API —— 在「模型设置」里改，不影响别的",
              "加新技能 —— 丢进技能目录，软件自己认出来",
              "软件升级 —— 换新版 exe，数据不动"):
        lb = QLabel("· " + x)
        lb.setObjectName("Sub")
        lb.setWordWrap(True)
        lb.setStyleSheet("font-size:11.5px;")
        c.body().addWidget(lb)

    row = QHBoxLayout()
    b1 = Btn("检查更新", "primary", icon_name="refresh")
    b2 = Btn("查看使用手册", "ghost", icon_name="help")
    row.addWidget(b1)
    row.addWidget(b2)
    row.addStretch(1)
    c.body().addLayout(row)

    def _check():
        # 没连升级服务器，就诚实说清楚：本地这一版是什么时候的
        ts = time.strftime("%Y-%m-%d %H:%M")
        kv_build.set_value(built + "（刚核对，%s）" % ts)
        kv_build.set_value_color(TH.cur()["green"])
        modal(c, "检查更新",
              "本地这一版：v3.0\n"
              "构建时间：%s\n"
              "源码：%d 个文件\n\n"
              "★ 说实话：现在还**没接升级服务器**（没做自动下载新版）。\n"
              "要升级就是换一个新版的文件夹/exe，你的数据（data/）不动。"
              % (built, n_files),
              [("知道了", None, "primary")])

    b1.clicked.connect(_check)
    b2.clicked.connect(lambda: modal(c, "这台软件怎么用？一句话：",
                                     "你插上手机，AI 替你聊，你看着就行。\n\n"
                                     "想再看一遍那 4 步引导，按 F1，"
                                     "或者点顶栏右上角那个 ? 按钮。",
                                     [("知道了", None, "primary")]))
    return c


# ============================================================
# 小工具
# ============================================================
def _t(s):
    lb = QLabel(s)
    lb.setStyleSheet("font-size:13.5px; font-weight:700;")
    return lb


def _sub(s):
    lb = QLabel(s)
    lb.setObjectName("Sub")
    lb.setWordWrap(True)
    lb.setStyleSheet("font-size:11.5px;")
    return lb


def _line():
    f = QFrame(); f.setFixedHeight(1)
    f.setStyleSheet("background:%s;" % TH.cur()["line"])
    return f


def _tip(s):
    f = QFrame()
    f.setObjectName("TipBox")
    l = QVBoxLayout(f)
    l.setContentsMargins(12, 9, 12, 9)
    lb = QLabel(s)
    lb.setObjectName("Sub")
    lb.setWordWrap(True)
    lb.setStyleSheet("font-size:11.5px;")
    l.addWidget(lb)
    return f


# ★ 左导航 10 项、4 组（照抄图纸第 1305~1320 行）
#   第 26 轮：第 2 列从 emoji 换成图纸原版 SVG 图标名
NAV_GROUPS = [
    ("连接", [
        ("account",    "phone",   "账号与设备", _panel_account),
        ("model",      "robot",   "模型设置",   _panel_model),
        ("appearance", "palette", "外观主题",   _panel_appearance),
    ]),
    ("内容", [
        ("persona", "user",  "人设管理",   _panel_persona),
        ("chat",    "chat",  "聊天策略",   _panel_chat),
        ("quota",   "chart", "平台与配额", _panel_quota),
    ]),
    ("运行", [
        ("goal",   "flame", "今日目标",   _panel_goal),
        ("notify", "bell",  "通知与告警", _panel_notify),
        ("data",   "save",  "数据与备份", _panel_data),
    ]),
    ("其他", [
        ("about",  "info",  "关于与升级", _panel_about),
    ]),
]


class SettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ---------- 左导航 ----------
        nav = QFrame()
        nav.setFixedWidth(198)
        nav.setStyleSheet("background:%s; border-right:1px solid %s;"
                          % (TH.cur()["panel"], TH.cur()["line"]))
        nl = QVBoxLayout(nav)
        nl.setContentsMargins(10, 12, 10, 12)
        nl.setSpacing(2)

        self._btns = []
        self._stack = QStackedWidget()
        self._key2idx = {}
        idx = 0

        for gname, items in NAV_GROUPS:
            g = QLabel(gname)
            g.setStyleSheet("font-size:10.5px; color:%s; padding:9px 10px 4px;"
                            "letter-spacing:.5px;" % TH.cur()["faint"])
            nl.addWidget(g)

            for key, icon_name, name, fn in items:
                b = QPushButton("  " + name)
                b.setCheckable(True)
                b.setCursor(Qt.PointingHandCursor)
                b.setIconSize(QSize(16, 16))
                b.setIcon(icons.make_icon(icon_name, 16,
                                          on=TH.cur()["blue"],
                                          off=TH.cur()["sub"]))
                b.setStyleSheet("""
                    QPushButton {{
                        background:transparent; border:none; border-radius:8px;
                        color:{sub}; text-align:left; padding:8px 10px; font-size:12px;
                    }}
                    QPushButton:hover  {{ background:{card}; color:{ink}; }}
                    QPushButton:checked {{
                        background:{bbg}; color:{blue}; font-weight:600;
                    }}
                """.format(sub=TH.cur()["sub"], card=TH.cur()["card"], ink=TH.cur()["ink"],
                           bbg=TH.cur()["blue_bg"], blue=TH.cur()["blue"]))
                b.clicked.connect(lambda _=False, i=idx: self._pick(i))
                nl.addWidget(b)
                self._btns.append(b)
                self._stack.addWidget(self._wrap(fn()))
                self._key2idx[key] = idx
                idx += 1

        nl.addStretch(1)
        lay.addWidget(nav)

        # ---------- 右内容 ----------
        # ★ 千万别给 QStackedWidget 单独设样式表（踩过坑）：
        #   Qt 里某个控件一旦 setStyleSheet，它的**整棵子树**会优先从这张
        #   局部表里找规则 —— 结果就是主窗口那张全局 QSS 对子树**部分失效**，
        #   按钮变成"白底浅蓝字"这种莫名其妙的样子。
        #   要背景色就靠全局 QSS 里的 `QWidget { background: ... }` 就够了。
        self._stack.setObjectName("SettingsStack")
        lay.addWidget(self._stack, 1)

        self._pick(0)

    def _wrap(self, inner):
        """
        给设置面板套上滚动 + **宽度上限**。

        ★ 为什么要限宽：表单类内容拉满整屏时，"标签"和"取值"会隔得很远，
          眼睛要横跨一整个屏幕才能对上。大厂（飞书 / Stripe 后台）的做法是
          把表单限制在 700~800px 内，其余留白。
        ★ 为什么用 setFixedWidth 而不是 setMaximumWidth：
          用"最大宽度"时，里面的 QLabel 换行后的高度算不准，
          提示条会被压扁。给个确定的宽度，布局才能一次性算对高度。
        """
        inner.setFixedWidth(760)

        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(18, 16, 18, 18)
        v.addWidget(inner, 0, Qt.AlignLeft)
        v.addStretch(1)

        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setWidget(w)

        outer = QWidget()
        o = QVBoxLayout(outer)
        o.setContentsMargins(0, 0, 0, 0)
        o.addWidget(sc)
        return outer

    def _pick(self, i):
        for j, b in enumerate(self._btns):
            b.setChecked(j == i)
        self._stack.setCurrentIndex(i)

    def goto_panel(self, key):
        if key in self._key2idx:
            self._pick(self._key2idx[key])

    def on_show(self):
        pass
