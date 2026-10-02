# -*- coding: utf-8 -*-
"""
拓客台 · 可视化管理台（三栏布局，豆包式窗口）
左栏：客户会话列表（来自本地数据库）
中栏：聊天对话 + 输入区（AI 生成回复 / 发送到手机）
右栏：客户档案与备注编辑
顶栏：环境状态 + 设备
底部：AutoGLM 执行日志
Key 外置 config\\config.json；数据库 data\\tuoke.db
"""
import json
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import scrolledtext, simpledialog, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tt_db import TuokeDB
from tt_engine import ChatEngine

BG = "#f3f5f9"
CARD = "#ffffff"
ACCENT = "#2563eb"
FGC = "#111827"
SUB = "#6b7280"
MSG_BG = "#eef2f7"
AI_BLUE = "#1d4ed8"


def _base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _load_cfg():
    for base in (_base_dir(), os.path.dirname(_base_dir())):
        p = os.path.join(base, "config", "config.json")
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
    return {}


class QueueWriter:
    def __init__(self, q):
        self._q = q

    def write(self, s):
        if s:
            self._q.put(s)
        return len(s)

    def flush(self):
        pass


APP_NAMES = {"momo": "陌陌", "soul": "Soul", "wechat": "微信", "tantan": "探探"}


class TkGui:
    def __init__(self, root):
        self.root = root
        self.cfg = _load_cfg()
        self.z = self.cfg.get("zhipu", {})
        self.db = TuokeDB()
        self.engine = ChatEngine() if self.z.get("api_key") else None
        self.agent = None
        self.out_q = queue.Queue()
        self.current_cid = None
        self.busy = False
        root.title("拓客台 · AI 社交运营管理台")
        root.geometry("1180x720")
        root.minsize(1000, 640)
        root.configure(bg=BG)
        self._build()
        self._poll_queue()
        self.refresh_customers()
        threading.Thread(target=self._startup_check, daemon=True).start()

    # ================= 界面 =================
    def _build(self):
        self._build_topbar()
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        self._build_left(body)
        self._build_center(body)
        self._build_right(body)
        self._build_logbar(body)

    def _build_topbar(self):
        bar = tk.Frame(self.root, bg=CARD, height=48)
        bar.pack(fill=tk.X)
        tk.Label(bar, text="拓客台", bg=CARD, fg=ACCENT,
                 font=("Microsoft YaHei UI", 15, "bold")).pack(side=tk.LEFT, padx=16, pady=8)
        self.lbl_status = tk.Label(bar, text="正在检查环境…", bg=CARD, fg=SUB,
                                   font=("Microsoft YaHei UI", 10))
        self.lbl_status.pack(side=tk.LEFT, padx=(8, 0))
        self.lbl_device = tk.Label(bar, text="设备: --", bg=CARD, fg=SUB,
                                   font=("Microsoft YaHei UI", 10))
        self.lbl_device.pack(side=tk.RIGHT, padx=16)

    def _build_left(self, body):
        left = tk.Frame(body, bg=CARD, width=240)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 8))
        left.grid_propagate(False)
        head = tk.Frame(left, bg=CARD)
        head.pack(fill=tk.X, padx=10, pady=8)
        tk.Label(head, text="会话", bg=CARD, fg=FGC,
                 font=("Microsoft YaHei UI", 12, "bold")).pack(side=tk.LEFT)
        tk.Button(head, text="＋", command=self.add_customer, bg="#eef2ff", fg=ACCENT,
                  relief=tk.FLAT, width=2, font=("Microsoft YaHei UI", 11, "bold")
                  ).pack(side=tk.RIGHT)
        self.listbox = tk.Listbox(left, bg=CARD, fg=FGC, relief=tk.FLAT, bd=0,
                                  selectbackground="#dbe4ff", selectforeground=FGC,
                                  font=("Microsoft YaHei UI", 10), activestyle="none",
                                  highlightthickness=0)
        self.listbox.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

    def _build_center(self, body):
        center = tk.Frame(body, bg=CARD)
        center.grid(row=0, column=1, sticky="nsew", padx=(0, 8))
        tk.Label(center, text="对话", bg=CARD, fg=FGC,
                 font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w", padx=12, pady=(8, 4))
        self.msg = scrolledtext.ScrolledText(center, bg=MSG_BG, fg=FGC, wrap=tk.WORD,
                                             font=("Microsoft YaHei UI", 10), relief=tk.FLAT,
                                             borderwidth=0, padx=10, pady=10, state=tk.DISABLED)
        self.msg.pack(fill=tk.BOTH, expand=True, padx=10)
        self.msg.tag_configure("who", foreground=SUB, font=("Microsoft YaHei UI", 8))
        self.msg.tag_configure("ai", foreground=AI_BLUE)
        self.msg.tag_configure("me", foreground="#059669")
        self.msg.tag_configure("other", foreground=FGC)
        # 输入区
        inrow = tk.Frame(center, bg=CARD)
        inrow.pack(fill=tk.X, padx=10, pady=8)
        self.input = tk.Text(inrow, height=3, bg="#ffffff", fg=FGC, relief=tk.FLAT,
                             highlightthickness=1, highlightbackground="#e5e7eb",
                             font=("Microsoft YaHei UI", 11), wrap=tk.WORD)
        self.input.pack(fill=tk.X, pady=(0, 6))
        self.input.bind("<Control-Return>", lambda e: self.ai_reply())
        btns = tk.Frame(inrow, bg=CARD)
        btns.pack(fill=tk.X)
        self.btn_ai = tk.Button(btns, text="AI 生成回复", command=self.ai_reply,
                                bg=ACCENT, fg="white", activebackground="#1d4ed8",
                                relief=tk.FLAT, padx=14, font=("Microsoft YaHei UI", 10, "bold"))
        self.btn_ai.pack(side=tk.LEFT)
        self.btn_send = tk.Button(btns, text="发送到手机", command=self.send_to_phone,
                                  bg="#0ea5e9", fg="white", activebackground="#0284c7",
                                  relief=tk.FLAT, padx=14, font=("Microsoft YaHei UI", 10, "bold"))
        self.btn_send.pack(side=tk.LEFT, padx=8)
        self.btn_open = tk.Button(btns, text="打开应用", command=self.open_app,
                                  bg="#eef2ff", fg=ACCENT, activebackground="#dbe4ff",
                                  relief=tk.FLAT, padx=12, font=("Microsoft YaHei UI", 10))
        self.btn_open.pack(side=tk.LEFT, padx=8)

    def _build_right(self, body):
        right = tk.Frame(body, bg=CARD, width=250)
        right.grid(row=0, column=2, sticky="nse")
        right.grid_propagate(False)
        tk.Label(right, text="客户档案", bg=CARD, fg=FGC,
                 font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w", padx=12, pady=(8, 4))
        self.profile = tk.Frame(right, bg=CARD)
        self.profile.pack(fill=tk.X, padx=12)
        self.profile_labels = {}
        rows = [("nick", "昵称"), ("platform", "平台"), ("distance", "距离"),
                ("progress", "进度"), ("status", "状态"), ("last", "最后消息")]
        for key, label in rows:
            row = tk.Frame(self.profile, bg=CARD)
            row.pack(fill=tk.X, pady=1)
            tk.Label(row, text=label, bg=CARD, fg=SUB, width=7, anchor="w",
                     font=("Microsoft YaHei UI", 9)).pack(side=tk.LEFT)
            lbl = tk.Label(row, text="--", bg=CARD, fg=FGC, anchor="w",
                           font=("Microsoft YaHei UI", 10))
            lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.profile_labels[key] = lbl
        tk.Label(right, text="备注（可编辑）", bg=CARD, fg=SUB,
                 font=("Microsoft YaHei UI", 9)).pack(anchor="w", padx=12, pady=(10, 2))
        self.note = tk.Text(right, height=8, bg="#ffffff", fg=FGC, relief=tk.FLAT,
                            highlightthickness=1, highlightbackground="#e5e7eb",
                            font=("Microsoft YaHei UI", 9), wrap=tk.WORD)
        self.note.pack(fill=tk.X, padx=12)
        tk.Button(right, text="保存备注", command=self.save_note, bg="#eef2ff", fg=ACCENT,
                  relief=tk.FLAT, padx=10, font=("Microsoft YaHei UI", 9)
                  ).pack(anchor="w", padx=12, pady=6)
        tk.Label(right, text="客户信息", bg=CARD, fg=SUB,
                 font=("Microsoft YaHei UI", 9)).pack(anchor="w", padx=12, pady=(4, 2))
        self.info = tk.Text(right, height=6, bg="#fafafa", fg=FGC, relief=tk.FLAT,
                            font=("Microsoft YaHei UI", 9), wrap=tk.WORD, state=tk.DISABLED)
        self.info.pack(fill=tk.X, padx=12, pady=(0, 8))

    def _build_logbar(self, body):
        self.log = scrolledtext.ScrolledText(body, bg="#0f172a", fg="#cbd5e1", wrap=tk.WORD,
                                             height=7, font=("Consolas", 9), relief=tk.FLAT,
                                             borderwidth=0, state=tk.DISABLED)
        self.log.grid(row=1, column=0, columnspan=3, sticky="sew", pady=(10, 0))
        body.grid_rowconfigure(1, weight=0)

    # ================= 工具 =================
    def _log(self, text):
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, text)
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _poll_queue(self):
        try:
            while True:
                self._log(self.out_q.get_nowait())
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    # ================= 客户/对话 =================
    def refresh_customers(self):
        self.listbox.delete(0, tk.END)
        self._customers = self.db.list_customers()
        for c in self._customers:
            t = (c["last_msg_time"] or "")[5:16]
            self.listbox.insert(tk.END, f"{c['nickname'] or c['account_id']}（{c['platform']}） {t}")

    def add_customer(self):
        platform = simpledialog.askstring("添加客户", "平台（momo/soul/wechat）：", parent=self.root)
        if not platform:
            return
        nick = simpledialog.askstring("添加客户", "昵称：", parent=self.root)
        if not nick:
            return
        cid = self.db.upsert_customer(platform.strip(), nick.strip())
        self.refresh_customers()
        for i, c in enumerate(self._customers):
            if c["id"] == cid:
                self.listbox.selection_set(i)
                self._load_customer(cid)

    def _on_select(self, _evt):
        sel = self.listbox.curselection()
        if not sel:
            return
        cid = self._customers[sel[0]]["id"]
        self._load_customer(cid)

    def _load_customer(self, cid):
        self.current_cid = cid
        c = self.db.get_customer(cid)
        self._fill_profile(c)
        self._render_history(cid)

    def _fill_profile(self, c):
        self.profile_labels["nick"].configure(text=c["nickname"] or "--")
        self.profile_labels["platform"].configure(text=c["platform"] or "--")
        self.profile_labels["distance"].configure(text=c["distance"] or "--")
        self.profile_labels["progress"].configure(text=f"{c['progress']}/5")
        self.profile_labels["status"].configure(text=c["status"] or "--")
        self.profile_labels["last"].configure(text=(c["last_msg_time"] or "--")[:16])
        self.note.delete("1.0", tk.END)
        self.note.insert("1.0", c["summary"] or "")
        self.info.configure(state=tk.NORMAL)
        self.info.delete("1.0", tk.END)
        self.info.insert(tk.END, f"个人信息：{c['personal_info'] or '--'}\n"
                                 f"信号：{c['hit_signals'] or '--'}\n"
                                 f"下个话题：{c['next_topic'] or '--'}")
        self.info.configure(state=tk.DISABLED)

    def save_note(self):
        if not self.current_cid:
            return
        self.db.upsert_customer(
            self.db.get_customer(self.current_cid)["platform"],
            self.db.get_customer(self.current_cid)["nickname"],
            summary=self.note.get("1.0", "end").strip())

    def _render_history(self, cid):
        self.msg.configure(state=tk.NORMAL)
        self.msg.delete("1.0", tk.END)
        for m in reversed(self.db.history(cid)):
            who = {"ai": "AI", "other": "对方", "user": "我"}.get(m["sender"], m["sender"])
            tag = "ai" if m["sender"] == "ai" else ("me" if m["sender"] == "user" else "other")
            self.msg.insert(tk.END, f"{who}  {m['sent_at'][11:16]}\n", "who")
            self.msg.insert(tk.END, m["content"] + "\n\n", tag)
        self.msg.configure(state=tk.DISABLED)
        self.msg.see(tk.END)

    # ================= 业务动作 =================
    def _need_ready(self):
        if self.agent is None:
            self._log("尚未就绪（设备/API 检查未完成），请稍候…\n")
            return False
        return True

    def ai_reply(self):
        if not self.current_cid:
            self._log("请先在左侧选择一个客户\n")
            return
        if not self.engine:
            self._log("缺少 API Key，无法生成回复\n")
            return
        text = self.input.get("1.0", "end").strip()
        if not text:
            self._log("先输入客户发来的消息（或想聊的内容）\n")
            return
        self.input.delete("1.0", tk.END)
        self.db.add_message(self.current_cid, "other", text)
        self._render_history(self.current_cid)
        self._set_busy(True)
        threading.Thread(target=self._gen, args=(text,), daemon=True).start()

    def _gen(self, incoming):
        try:
            c = self.db.get_customer(self.current_cid)
            hist = [{"sender": m["sender"], "content": m["content"]}
                    for m in self.db.history(self.current_cid)]
            reply = self.engine.generate(history=hist, incoming=incoming)
            self.root.after(0, lambda: self._show_reply(reply))
        except Exception as e:
            self.root.after(0, lambda: self._gen_error(str(e)))
        finally:
            self.root.after(0, lambda: self._set_busy(False))

    def _show_reply(self, reply):
        if self.current_cid:
            self.db.add_message(self.current_cid, "ai", reply, verified=0)
            self._render_history(self.current_cid)
        self.input.delete("1.0", tk.END)
        self.input.insert("1.0", reply)
        self._log("AI 已生成回复，可点「发送到手机」让 AutoGLM 在手机上发出。\n")

    def _gen_error(self, err):
        self._log(f"生成失败：{err}\n")

    def send_to_phone(self):
        if not self._need_ready() or not self.current_cid:
            return
        c = self.db.get_customer(self.current_cid)
        app = APP_NAMES.get(c["platform"], c["platform"])
        text = self.input.get("1.0", "end").strip()
        if not text:
            self._log("输入框为空，先把要发的内容填进去（或先用 AI 生成）\n")
            return
        task = f"打开{app}，找到{c['nickname']}的对话，输入消息“{text}”，发送"
        self._set_busy(True)
        threading.Thread(target=self._exec_task, args=(task,), daemon=True).start()

    def open_app(self):
        if not self._need_ready() or not self.current_cid:
            return
        c = self.db.get_customer(self.current_cid)
        app = APP_NAMES.get(c["platform"], c["platform"])
        self._set_busy(True)
        threading.Thread(target=self._exec_task, args=(f"打开{app}",), daemon=True).start()

    def _exec_task(self, task):
        try:
            old = sys.stdout, sys.stderr
            sys.stdout = QueueWriter(self.out_q)
            sys.stderr = sys.stdout
            try:
                self.agent.run(task)
            finally:
                sys.stdout, sys.stderr = old
            self._log(f"\n>>> 任务完成：{task}\n")
        except Exception as e:
            self._log(f"\n>>> 任务出错：{e}\n")
        finally:
            self.root.after(0, lambda: self._set_busy(False))

    def _set_busy(self, busy):
        self.busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        for b in (self.btn_ai, self.btn_send, self.btn_open):
            b.configure(state=state)

    # ================= 环境自检 =================
    def _startup_check(self):
        z = self.z
        if not z.get("api_key"):
            self._log("错误：config\\config.json 缺少 zhipu.api_key（模板 config.example.json）\n")
            self.lbl_status.configure(text="缺少 API Key", fg="#dc2626")
            return
        import subprocess
        if getattr(sys, "frozen", False):
            sp = os.path.join(getattr(sys, "_MEIPASS", ""), "scrcpy")
            if os.path.isdir(sp):
                os.environ["PATH"] = sp + os.pathsep + os.environ.get("PATH", "")
        sp2 = os.path.join(os.path.dirname(_base_dir()), "_tools", "scrcpy", "scrcpy-win64-v4.1")
        if os.path.isdir(sp2):
            os.environ["PATH"] = sp2 + os.pathsep + os.environ.get("PATH", "")
        src = os.path.join(os.path.dirname(_base_dir()), "Open-AutoGLM")
        if os.path.isdir(src) and src not in sys.path:
            sys.path.insert(0, src)
        try:
            self._log("1/4 检查 ADB…\n")
            r = subprocess.run(["adb", "version"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=15)
            if not r.stdout.strip():
                self._log("未找到 adb，内置工具缺失\n")
                self.lbl_status.configure(text="环境异常", fg="#dc2626")
                return
            self._log("2/4 检查设备…\n")
            r = subprocess.run(["adb", "devices"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=15)
            devs = [ln.split()[0] for ln in r.stdout.splitlines()[1:]
                    if ln.strip() and "device" in ln]
            if not devs:
                self._log("未检测到手机：请 USB 连接并在手机端允许调试\n")
                self.lbl_status.configure(text="无设备", fg="#dc2626")
                return
            did = z.get("device_id") or devs[0]
            self.lbl_device.configure(text=f"设备: {did}")
            self._log("3/4 检查 ADB Keyboard…\n")
            r = subprocess.run(["adb", "-s", did, "shell", "pm", "path",
                                "com.android.adbkeyboard"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=15)
            if "package:" in (r.stdout or ""):
                self._log("ADB Keyboard 已安装\n")
            else:
                self._log("警告：ADB Keyboard 未安装（见手册安装）\n")
            self._log("4/4 检查模型 API…\n")
            import requests
            rr = requests.get(z["base_url"] + "/models",
                              headers={"Authorization": "Bearer " + z["api_key"]}, timeout=15)
            if rr.status_code != 200:
                self._log(f"API 连接失败 HTTP {rr.status_code}，请检查 Key/网络\n")
                self.lbl_status.configure(text="API 异常", fg="#dc2626")
                return
            self._log(f"API 连通（{z['model']}）\n")
            from phone_agent import PhoneAgent
            from phone_agent.agent import AgentConfig
            from phone_agent.device_factory import DeviceType, set_device_type
            from phone_agent.model import ModelConfig
            set_device_type(DeviceType.ADB)
            self.agent = PhoneAgent(
                ModelConfig(base_url=z["base_url"], model_name=z["model"],
                            api_key=z["api_key"], lang="cn"),
                AgentConfig(max_steps=z.get("max_steps", 100), device_id=did,
                            verbose=True, lang="cn"))
            self.lbl_status.configure(text="● 已就绪，选客户 → 输入消息 → AI 回复 → 发到手机",
                                      fg="#16a34a")
            self._log("环境就绪。\n")
        except Exception as e:
            self._log(f"启动检查失败：{e}\n")
            self.lbl_status.configure(text="启动失败", fg="#dc2626")


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        root = tk.Tk()
        TkGui(root)
        root.mainloop()
    except Exception:
        import traceback
        try:
            os.makedirs(os.path.join(_base_dir(), "logs"), exist_ok=True)
            with open(os.path.join(_base_dir(), "logs", "gui_error.log"), "w",
                      encoding="utf-8") as f:
                f.write(traceback.format_exc())
        except Exception:
            pass
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
