# src/ui —— 界面模块说明

> **这一层是干什么的**：把图纸 `管理台界面原型-v3.html` **1:1 抄成 Qt 原生界面**。
> 用户电脑上双击 exe 就能开，**不出现浏览器痕迹**（规格书第 17 章拍板）。

---

## 三条硬约束（规格书 17.4，改代码前必须守住）

1. **9 页一个不少** —— 不许合并、不许删页
2. **深色浅色双主题** —— 两套都要能用
3. **布局文案照抄图纸** —— 不许自己发挥、不许改文案

---

## 文件清单

| 文件 | 干什么 |
|---|---|
| `theme.py` | **色板**（深/浅两套，1:1 抄图纸 CSS 变量）+ 全局 QSS + **`cur()` 取当前主题色** |
| `icons.py` | **图标库**：44 个矢量线条图标（1:1 抄图纸 SVG，用 QtSvg 渲染） |
| `overlays.py` | **弹层系统**：遮罩 / toast / 统一弹层 / 命令面板 / 新手引导 / 自定义卡片 |
| `device_hub.py` | **设备管家**：后台投屏 + 遥控（命令队列）+ 设备信息 |
| `agent_runner.py` | **AI 干活的编排者**：跑一轮 8 步，每步报进度；`SendWorker` 负责真发 |
| `ai_panel.py` | **AI 过程面板**：8 步实时显示 + 试跑停下问用户 |
| `widgets.py` | 通用小控件：Card / Btn / IconBtn / Chip / NavItem / LinkLabel / Empty / KV / MiniBar 等 |
| `main_window.py` | **主窗口**：顶部栏 + 左导航 9 项 + 页面容器 + 底部状态栏 + 快捷键 |
| `pages_overview.py` | ① 总览 |
| `pages_customers.py` | ② 客户（三栏工作区 + 手机画面/遥控） |
| `pages_messages.py` | ③ 消息 |
| `pages_strategy.py` | ④ 策略 |
| `pages_skills.py` | ⑤ 技能库 |
| `pages_tuoke.py` | ⑥ 拓客 |
| `pages_stats.py` | ⑦ 统计 |
| `pages_trash.py` | ⑧ 回收站 |
| `pages_settings.py` | ⑨ 设置（左导航 10 项 / 4 组） |

**入口**：`src/app.py`

---

## 常用命令

```bash
# 只查环境（不开窗口）
python src/app.py --check

# 开窗口
python src/app.py

# 离线自检（语法 / 名字引用 / 9 页齐全性）—— 不依赖 PySide6
python _tools/check_ui.py

# 把 9 页 × 双主题拍成图，存 _shots_ui/
python _tools/shot_ui.py
```

---

## 加一页 / 改一页的规矩

**加一页**要动两处：
1. 新建 `pages_xxx.py`，里面写一个 `XxxPage(QWidget)` 类
2. 在 `main_window.py` 的 `NAV` 表里加一项（`(key, 图标, 名字, 角标数)`），
   并在 `_install_pages()` 的 `pages` 列表里挂上

**改一页**只需动它自己那个文件，不会碰坏别页 —— 这是每页单独一个文件的目的。

**每页建议实现 `on_show()`**：切到这一页时会被调一次，用来刷新数据。
现在是空的，以后接真数据挂这儿。

---

## 主题是怎么切换的

```
main_window.apply_theme("dark" / "light")
  ├─ theme.get(name)      → 拿到色板 dict
  ├─ theme.to_qss(色板)   → 渲染成 QSS 字符串 → self.setStyleSheet()
  └─ 遍历所有子控件，凡是实现了 set_theme(name) / apply_theme(name) 的都通知一遍
```

**自绘控件**（`AreaChart` / `HeatGrid` / `MiniBar` / `Avatar`）必须实现
`set_theme(name)`，否则切主题时它的颜色不会跟着变。

---

## 已经在代码里落实的规格书条目

| 规格书条 | 落在哪 |
|---|---|
| 17.4 三条硬约束 | 整个 `ui/` 层 |
| 4.8.4 拓客 6 道锁 | `pages_tuoke.py` |
| 4.9 客户 6 级阶段（4 页签） | `pages_customers.py::_rt_arc` |
| 4.11 跨平台同人识别 | `pages_customers.py::_rt_acct` |
| 4.9.3 AI 判放弃 + 回收站 | `pages_trash.py` |
| 1.10.6 投屏与截图分工 | `pages_customers.py::_rt_phone` |
| 4.8.1 微信只承接不拓客 | `pages_settings.py::_panel_quota` |
| 第 12 章 只填一个模型 API | `pages_settings.py::_panel_model` |
| 第 11 章 人格全局统一 | `pages_settings.py::_panel_persona` |
| 4.5 回复延迟随机区间 | `pages_settings.py::_panel_chat` |
| 1.10.1 暂停（1 秒内停手） | `pages_overview.py::_toggle_pause` |
| 4.3 人工接管 | `pages_customers.py::_toggle_takeover` |
| 5.5 数据来源约束 | 各页数字旁的标注 |
| 13.1.6 AI 自己学 App | `pages_skills.py` |
| 第 16 章 只显示最高优先级黄条 | `main_window.py` 顶部栏 |
| V4.10 全站只有两种弹层 | `overlays.py` |

---

## ★ 改这一层必须遵守的三条规矩（第 26 轮定）

**① 颜色一律写 `TH.cur()[...]`，不许写 `TH.DARK[...]`**

```python
# ✗ 错的 —— 浅色主题下这里还是深色
lb.setStyleSheet("color:%s;" % TH.DARK["sub"])

# ✓ 对的 —— 跟着当前主题走
lb.setStyleSheet("color:%s;" % TH.cur()["sub"])
```

原因：写死深色的后果是切浅色时那一处不跟着变，一页里深浅混着看着"花"。
（第 26 轮一次揪出 **109 处**这种情况。）

**② 切主题会重建所有页面**

因为颜色是**构造时**写进样式字符串的，光换 QSS 不够。
`main_window.apply_theme()` 里会调 `_rebuild_pages()`。
→ 所以**页面的构造必须无副作用**（不要在 `__init__` 里写数据库、发网络请求）。

**③ 加一页要动两处**

1. 新建 `pages_xxx.py`，里面写 `XxxPage(QWidget)`
2. 在 `main_window.py` 的 `NAV` 表加一项，并在 `_install_pages()` 的
   `pages` 列表里挂上

---

## 快捷键

| 键 | 作用 |
|---|---|
| `Ctrl+K` / `Ctrl+P` | 命令面板 |
| `Ctrl+1` ~ `Ctrl+9` | 直达 9 页 |
| `F1` | 使用引导 |
| `Ctrl+T` | 切深色 / 浅色 |
| `Esc` | 关掉弹层 |

---

## 还没做的（下一步）

- [ ] **装 PySide6 后开窗口跑一遍**，逐页对图纸
- [ ] 拍 18 张图（9 页 × 双主题）存 `_shots_ui/`，给用户过目
- [ ] 修细节：间距 / 字号 / 圆角跟图纸对齐
- [ ] 把页面上的假数据换成真数据（接 `tt_db.py`）
- [ ] 打包 exe（PyInstaller，零依赖）
