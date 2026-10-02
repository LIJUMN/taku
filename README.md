<div align="center">

# Taku · 拓客台

**纯视觉 AI 手机社交助手 —— 电脑看手机屏幕 → 大模型理解 → 操控手机 → 回读验证**

不root · 不注入 · 不读控件树 · 只用眼睛

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![PySide6](https://img.shields.io/badge/GUI-PySide6-green.svg)](https://doc.qt.io/qtforpython/)
[![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)]()
[![Status](https://img.shields.io/badge/%E7%8A%B6%E6%80%81-%E5%8D%8A%E6%88%90%E5%93%81-orange)](#-这版是半成品先说清楚)

</div>

---

## ⚠️ 这版是半成品（先说清楚）

> **这是一坨正在成型的半成品，不是成品。**
>
> - ✅ **已经真机跑通的**：AI 自动认路（打开 App → 找到人 → 进聊天页）、读消息、
>   按人设想回复、打字进输入框、回读验证——这条核心链路是真的能跑。
> - 🔧 **还没做成的**：拓客引擎（界面就绪没联调）、挂机长跑、通知感知、多手机。
> - 🎯 一句话：**它证明了"这条路能走通"，但它还不是"拿来就能用"的工具。**
>
> 欢迎下载来研究、改、骂、重写。
> 但别指望下载双击就能自动聊得飞起——做不到的部分在下面功能表里都用 🔧 标着，概不掩饰。

---

## 这是什么？

Taku 是一个跑在 Windows 电脑上的 AI 代理：它用数据线连接你的安卓手机，
**像人一样"看"手机屏幕**（截图 → 多模态大模型理解画面），
然后**像人一样"操作"手机**（网格定位 → adb 点击/输入），

- 自动打开目标 App、找到联系人、走进聊天页
- 读懂最近的对话，生成符合人设的回复
- 打字进输入框，回读验证，再由你决定是否发送

设计目标只有一个场景：**你不想再一条条回消息了，让 AI 替你把天聊热。**

## 界面一览（演示数据）

<div align="center">
<img src="docs/screenshots/customers.png" width="760" alt="客户页"/>
<p><sub>客户页：AI 已自主导航进微信聊天页 · 左侧客户列表 · 中栏对话与快捷指令 · 右侧手机投屏</sub></p>
</div>

<div align="center">
<table><tr>
<td><img src="docs/screenshots/overview.png" width="400" alt="总览"/></td>
<td><img src="docs/screenshots/messages.png" width="400" alt="消息"/></td>
</tr></table>
<p><sub>总览看板（漏斗/近7天/事件流，全部真数据） · 消息聚合页</sub></p>
</div>

## 为什么是"纯视觉"？（本项目的灵魂）

市面上的手机 Agent 大多依赖 Accessibility 或 `uiautomator dump` 读控件树——
**快，但在真实社交 App 上等于裸奔**：控件树里全是你的隐私，而且部分风控会盯无障碍服务。

Taku 反着来：

> **截图是唯一的输入，点击是唯一的输出。**

| | 控件树路线 | Taku 纯视觉路线 |
|---|---|---|
| App 感知 | 读 Accessibility 节点 | 截图 + 多模态大模型 |
| 风控面 | 无障碍服务可被检测 | 与人手操作无法区分 |
| 通用性 | 每个控件要适配 | 会看图就会用 |
| 隐私 | 控件树=全量隐私 | 只看当前屏幕 |

代价是难度：AndroidWorld 榜单上纯视觉路线只有 ~29%（读控件 91.4%）。
Taku 用了三件武器把这个差距打下来：

1. **网格定位法**：大模型"会看不会算"——让它报"第几行第几列"，坐标由代码换算；
   再叠加**领域锚点**（发送键永远贴右、放大镜永远在顶栏 x≈85%）直接干掉模型不确定性
2. **双模型分工**：判断/格式输出交给 glm-4v-flash（实测 autoglm 这类定位模型写小作文不守格式），
   精定位再裁小块复核——每个落点都过一道"裁图确认"闸门
3. **Reflection + 经验记忆**：每个动作后核验（还在不在目标 App？页面对不对？）；
   成功路径记入经验库，下次按经验走

## 功能一览

| 能力 | 状态 | 说明 |
|---|---|---|
| 🧭 **AI 自动认路** | ✅ | 桌面→拉起 App→列表直点/搜索→聊天页，全链路自主导航；成功路径自动记入经验库 |
| 💬 **读消息/想回复/打字** | ✅ | 8 步闭环全程可视化；人设+上下文生成回复；群聊自动排除 |
| 🛡️ **发送安全体系** | ✅ | 默认试跑模式（打完不发，你点头才发）· 高危词硬拦（验证码/转账）· 发送后回读验证 |
| 👥 **客户管理** | ✅ | 档案/阶段/热度/备注/回收站，SQLite 落库 |
| 📊 **数据看板** | ✅ | 今日新客/转化漏斗/近 7 天/事件流——全部真数据，量不出显示「—」不造假 |
| 🧪 **自检工具链** | ✅ | 逐按钮审计（90 项）/功能测试/结构检查/9 页渲染视检，一条命令一个 |
| 🧲 **拓客引擎** | 🔧 | 6 道安全锁策略就绪，真机联调中 |
| 🤖 **挂机模式** | 🔧 | 心跳+每日上限策略就绪，长跑稳定性实测中 |

## 工作原理

```
┌─────────────┐    截图     ┌──────────────┐   是非判断    ┌────────────────┐
│  安卓手机    │ ─────────> │  看图模型     │ ──────────>  │ 决策：点哪里/    │
│  (真机/USB)  │ <───────── │  (多模态LLM)  │              │ 说什么/下一步    │
└─────────────┘  adb 点击   └──────────────┘              └───────┬────────┘
      ▲                                                            │
      │      ┌──────────────┐    网格定位+锚点     ┌───────────────┐│
      └───── │  网格定位引擎  │ <──────────────── │  经验记忆库     │<┘
   adb 打字   │  (裁块复核)    │    成功路径沉淀      │ (data/*.json) │
             └──────────────┘                     └───────────────┘
```

一次完整对话的 8 步：**看手机 → 认清 App/认路 → 读对话 → 想回复 → 找输入框 →
打字 → （试跑暂停）→ 发送+回读验证**。每一步都在界面的「AI 视角」面板实时可见。

## 快速开始

```bash
# 1. 克隆 + 安装依赖
git clone https://github.com/LIJUMN/taku.git
cd taku
pip install -r requirements.txt

# 2. 配置大模型 Key（GLM-4V-Flash 免费额度即可跑通全链）
cp config/config.example.json config/config.json
#    编辑 config.json，填入你的 API Key

# 3. 手机开启 USB 调试，插上电脑
adb devices        # 确认能看到你的设备

# 4. 启动
python src/app.py
```

进入「客户」页 → 添加或选择一个联系人 → 点 **「让 AI 聊这一轮」** →
在「AI 视角」面板看它走完全程（默认试跑：字打进输入框但不发送）。

> ⚙️ 需要：Windows 10/11 · 一台开了 USB 调试的安卓手机 · adb（`_tools` 内已含）

## 目录结构

```
├── src/
│   ├── phone.py          # 眼睛+手：截图/点击/前台包名（系统级，不碰控件树）
│   ├── vision.py         # 脑子：App识别/页面判断/网格定位/是非问答
│   ├── tt_typing.py      # 嘴：ADB Keyboard 广播输入
│   ├── tt_navigate.py    # 认路：拉起App/列表直点/搜索/经验记忆
│   ├── tt_send.py        # 发送 + 回读验证
│   ├── tt_loop_chat.py   # 8 步聊天闭环
│   ├── tt_db.py          # SQLite（10 张表）
│   └── ui/               # PySide6 界面（9 页 / 深浅双主题 / 命令面板）
├── _tools/               # 自检工具链 + adb/scrcpy 便携版
├── config/config.example.json
└── README.md
```

## 自检工具链（本项目最引以为傲的部分之一）

"界面长得像"和"功能真的能用"是两回事。Taku 自带一整套**把自己当被告**的测试链：

```bash
python _tools/check_ui.py           # 结构：语法/引用/9 页齐全
python _tools/check_dup_methods.py  # 同名方法互相覆盖扫描（AST 级）
python _tools/test_all.py           # 逐功能点验：点了之后真的生效吗
python _tools/audit_buttons.py      # 逐按钮审计：点击前后状态 diff，90 项一个不落
python _tools/test_db_loop.py       # 数据闭环：删→回收站→恢复→永久删
python _tools/render_pages.py       # 9 页渲染成图，人眼视检设计
```

审计器自带**沙箱**：跑审计时备份/导出/弹窗全部接住，不污染桌面、不写垃圾文件。

## 定位：和 Mobile-Agent 等项目的区别

| | Mobile-Agent 系列 | Taku |
|---|---|---|
| 目标任务 | 通用任务基准测试 | **真实社交场景的长期对话** |
| 感知 | OCR/GroundingDINO/控件树 | 纯截图 + 多模态 API（无本地重模型） |
| 经验 | Self-Evolution（Tips/Shortcuts） | ✅ 已吸收（认路经验记忆） |
| Reflection | 截图对比分类 A/B/C | ✅ 已吸收（每步核验） |
| 风控视角 | 不考虑 | **核心设计约束**（纯视觉 = 不可检测） |
| 形态 | 命令行/研究框架 | Windows 桌面软件 + 完整 GUI |

经验库、Reflection、双模型分工等机制均吸收自
[Mobile-Agent](https://github.com/X-PLUG/MobileAgent) 系列与
[Open-AutoGLM](https://github.com/zai-org/Open-AutoGLM) 的公开设计，在此致谢。

## Roadmap

- [ ] 拓客引擎真机联调（6 道安全锁）
- [ ] 挂机模式 8 小时长跑压测
- [ ] 通知栏感知（跨 App 消息统一处理）
- [ ] Tips 自动沉淀（Mobile-Agent-E 式经验反射器）
- [ ] 多手机并发

## 免责声明（必读）

本工具**只能用于你自己的账号与你自己的社交关系**。它不提供任何绕过平台风控的能力——
恰恰相反，纯视觉设计就是为了尊重平台规则。请遵守所在平台用户协议与当地法律法规。
聊天内容生成自大模型，发出前请自行审阅（默认试跑模式就是为此设计的）。

## License

[MIT](LICENSE) © Taku Contributors
