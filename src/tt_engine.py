# -*- coding: utf-8 -*-
"""
拓客台 · 引擎层（M2 事件闭环核心）
按《需求文档 v1.0》§23 接口清单实现，三大接口：
- ChatEngine.generate(persona, profile, history, incoming) -> 回复文本
  实现 B（GLM 系，智谱 API）：无需 DeepSeek Key，用 glm-5.3-flash
- VisionEngine.run_task(task) -> 子进程调 Open-AutoGLM main.py 执行手机操作
- NotifyListener（复用 notify_poll.py 的 Plan B 轮询）
"""
import json, os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CFG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "config", "config.json")
if getattr(sys, "frozen", False):
    # 打包模式：config 外置于 exe 所在目录
    CFG_PATH = os.path.join(os.path.dirname(os.path.abspath(sys.executable)),
                            "config", "config.json")
DEFAULT_PERSONA = (
    "你是拓客台的聊天引擎，替账号主人进行社交平台对话。"
    "人设：开朗、直接、会接梗，说话短句为主、偶尔带口头禅，不查户口、不舔不冷。"
    "规则：不暴露是自动回复；不主动要微信；对方问隐私问题就自然绕开。"
)

# ★ 第 52 轮隐私审查：默认人设改为演示值 —— 真实人设放 config.json 的
#   "persona_profile"（该文件在 .gitignore 里，永远不会进开源包）。
#   代码里不再出现任何真实姓名/城市/职业。
DEFAULT_PROFILE = {
    "姓名": "小周", "城市": "某市", "职业": "行政专员", "兴趣": "健身、徒步、摄影"
}


class ChatEngine:
    """聊天引擎（实现 B：GLM 系线上 API，OpenAI 兼容）"""

    def __init__(self, api_key=None, base_url=None, model="glm-5.3-flash"):
        cfg = self._load_cfg()
        self.api_key = api_key or cfg["zhipu"]["api_key"]
        self.base_url = base_url or cfg["zhipu"]["base_url"]
        self.model = model
        # ★ 第 52 轮：人设可从 config.json 注入（真实人设不进代码）
        self.persona = cfg.get("persona_text") or DEFAULT_PERSONA
        self.profile = cfg.get("persona_profile") or DEFAULT_PROFILE
        try:
            import requests
            self._requests = requests
        except ImportError:
            raise RuntimeError("需要 requests：pip install requests")

    @staticmethod
    def _load_cfg():
        with open(CFG_PATH, encoding="utf-8") as f:
            return json.load(f)

    def _chat(self, messages, max_tokens=600, temperature=0.8):
        r = self._requests.post(
            self.base_url + "/chat/completions",
            headers={"Authorization": "Bearer " + self.api_key},
            json={"model": self.model, "messages": messages,
                  "max_tokens": max_tokens, "temperature": temperature},
            timeout=90)
        if r.status_code != 200:
            raise RuntimeError(f"ChatEngine HTTP {r.status_code}: {r.text[:200]}")
        msg = r.json()["choices"][0]["message"]
        content = msg.get("content") or ""
        # 推理模型思考可能吃满 token 导致 content 为空 → 加大配额重试一次
        if not content.strip() and msg.get("reasoning_content"):
            r = self._requests.post(
                self.base_url + "/chat/completions",
                headers={"Authorization": "Bearer " + self.api_key},
                json={"model": self.model, "messages": messages,
                      "max_tokens": max_tokens + 600, "temperature": temperature},
                timeout=120)
            content = (r.json()["choices"][0]["message"].get("content") or "")
        return content

    def generate(self, persona=None, profile=None, history=None, incoming=""):
        """PRD §23: 生成回复（人设+记忆+上下文）"""
        persona = persona or self.persona
        profile = profile or self.profile
        history = history or []
        sys_msg = persona + "\n账号主人信息：" + json.dumps(profile, ensure_ascii=False)
        messages = [{"role": "system", "content": sys_msg}]
        for h in history[-12:]:  # 最近 12 条上下文
            role = "assistant" if h.get("sender") == "ai" else "user"
            messages.append({"role": role, "content": h.get("content", "")})
        messages.append({"role": "user", "content": incoming})
        return self._chat(messages)

    def is_handover_signal(self, conversation):
        """PRD §23: 命中信号判定（是否标记熟客）"""
        text = json.dumps(conversation, ensure_ascii=False)
        resp = self._chat(
            [{"role": "system",
              "content": "判断以下对话是否出现'熟客信号'（交换联系方式/约见面/提到工作生活细节/连续高频互动）。只回答 true 或 false。"},
             {"role": "user", "content": text}], max_tokens=200, temperature=0)
        return "true" in resp.lower()


class VisionEngine:
    """视觉引擎：子进程调 Open-AutoGLM main.py（实现 A 线上 autoglm-phone）"""

    def __init__(self, model="autoglm-phone"):
        cfg = ChatEngine._load_cfg()
        self.model = model
        self.api_key = cfg["zhipu"]["api_key"]
        self.base_url = cfg["zhipu"]["base_url"]
        self.main_py = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "Open-AutoGLM", "main.py")
        self.py = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "..", "Open-AutoGLM", "venv", "Scripts", "python.exe")

    def run_task(self, task, max_steps=30, timeout=1800):
        """把任务交给 AutoGLM 在手机上执行，返回 stdout"""
        cmd = [self.py, self.main_py,
               "--base-url", self.base_url,
               "--model", self.model,
               "--apikey", self.api_key,
               "--max-steps", str(max_steps),
               task]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout + r.stderr


if __name__ == "__main__":
    # 自检：生成一条测试回复
    ce = ChatEngine()
    reply = ce.generate(incoming="在吗 你是哪里人啊")
    print("REPLY:", reply)
