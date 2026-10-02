# -*- coding: utf-8 -*-
"""
Taku · 高清投屏（scrcpy 版）

★ 用户拍板的需求（2026-10-02）：
    「手机画面只能点不能拉…很鸡肋…去扒一扒人家成熟的手机控制电脑，
     人家那种点、拉…手机的声音也都能在客户端显示」

★ 为什么用 scrcpy（_tools/scrcpy/ 里本来就带着，之前一直没用上）：
    · 业界标准方案（GitHub 10 万+ star），画质好、延迟低；
    · 鼠标交互是**全套**的：单击 / 按住拖动=滑动 / 下拉状态栏 / 滚轮 / 打字；
    · scrcpy 2.0+ 支持**手机声音转发到电脑**（本项目手机安卓 16，支持）；
    · 它走自己的一条 socket 通道，**不占咱们的 adb 截图管道** ——
      老的「AI 干活时投屏让路」问题在它身上根本不存在。

★ 怎么嵌进界面：
    Windows 上用 SetParent 把 scrcpy 的窗口收进来当子窗口（成熟做法）。
    个别机器上收不进来 → 自动退回「独立置顶小窗」模式，点拉和声音一点不少。

★ 红线核对：scrcpy 只是**人眼看的投屏 + 人手操作**，跟用户拿手指头戳手机等价；
    AI 干活依然走自己的截图通道（screencap），不碰 scrcpy —— 不违反「只走视觉」。
"""
import os
import subprocess
import sys
import tempfile

from PySide6.QtCore import QObject, Signal, QTimer, QEvent

_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _project_root():
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return base
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    # __file__ = src/ui/scrcpy_mirror.py → 上跳三级才是项目根
    # ★ 坑 25 同款：每个文件自己算根就容易算岔，算岔了就找不到 scrcpy.exe
    here = os.path.dirname(os.path.abspath(__file__))            # src/ui
    return os.path.dirname(os.path.dirname(here))                # 项目根


def scrcpy_exe():
    """找 scrcpy.exe（跟 adb 一样，就住在 _tools/scrcpy/ 里）。"""
    p = os.path.join(_project_root(), "_tools", "scrcpy",
                     "scrcpy-win64-v4.1", "scrcpy.exe")
    return p if os.path.exists(p) else None


# ============================================================
# Windows 窗口嵌入（SetParent，失败就退回独立窗口）
# ============================================================
_WS_CHILD = 0x40000000
_WS_VISIBLE = 0x10000000
_WS_POPUP = 0x80000000
_WS_CAPTION = 0x00C00000
_WS_THICKFRAME = 0x00040000
_WS_SYSMENU = 0x00080000
_WS_MINMAXBOX = 0x00030000          # MINIMIZE|MAXIMIZE
_GWL_STYLE = -16


def _user32():
    import ctypes
    try:
        return ctypes.windll.user32
    except Exception:
        return None


def _find_window(title):
    u = _user32()
    if not u:
        return None
    try:
        import ctypes
        u.FindWindowW.restype = ctypes.c_void_p
        u.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        hwnd = u.FindWindowW(None, title)
        return int(hwnd) if hwnd else None
    except Exception:
        return None


def _embed_into(hwnd, container):
    """把 hwnd 变成 container 的子窗口。成功返回 True。"""
    u = _user32()
    if not u or not hwnd:
        return False
    try:
        import ctypes
        from ctypes import wintypes
        style = u.GetWindowLongW(hwnd, _GWL_STYLE)
        style = (style & ~(_WS_POPUP | _WS_CAPTION | _WS_THICKFRAME |
                           _WS_SYSMENU | _WS_MINMAXBOX))
        style |= (_WS_CHILD | _WS_VISIBLE)
        u.SetWindowLongW(hwnd, _GWL_STYLE, style)
        u.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
        u.SetParent.restype = wintypes.HWND
        parent = int(container.winId())
        if not u.SetParent(hwnd, parent):
            return False
        _fit(hwnd, container)
        return True
    except Exception:
        return False


def _fit(hwnd, container):
    """让 scrcpy 窗口铺满容器（按容器**客户区**的物理像素来，DPI 不慌）。"""
    u = _user32()
    if not u or not hwnd:
        return
    try:
        import ctypes
        from ctypes import wintypes
        rect = wintypes.RECT()
        if u.GetClientRect(int(container.winId()), ctypes.byref(rect)):
            u.MoveWindow(hwnd, 0, 0,
                         rect.right - rect.left,
                         rect.bottom - rect.top, True)
    except Exception:
        pass


# ============================================================
# 镜像本体
# ============================================================
class ScrcpyMirror(QObject):
    """
    一个手机的 scrcpy 投屏进程。

    信号 state(str)：
        "starting"   进程起了，正在找窗口
        "embedded"   已经嵌进界面（点/拉/滑/声音全都能用）
        "standalone" 没嵌进去，scrcpy 以独立置顶小窗运行（功能一样全）
        "stopped"    投屏结束（自己关的 / 手机拔了）
        "failed:…"   起不来
    """

    state = Signal(str)

    _FIND_TIMEOUT_MS = 9000     # 找窗口最多等这么久

    def __init__(self, parent=None):
        super().__init__(parent)
        self._proc = None
        self._hwnd = None
        self._container = None
        self._title = ""
        self._poll = QTimer(self)
        self._poll.setInterval(400)
        self._poll.timeout.connect(self._poll_once)
        self._tries = 0
        self._embedded = False
        self._retried_noaudio = False
        self._err_file = None
        self._watch = QTimer(self)
        self._watch.setInterval(2500)
        self._watch.timeout.connect(self._watch_proc)

    # --------------------------------------------------------
    def running(self):
        return self._proc is not None and self._proc.poll() is None

    def mode(self):
        """当前模式：off / starting / embedded / standalone"""
        if not self.running():
            return "off"
        return "embedded" if self._embedded else (
            "standalone" if self._hwnd is None and self._tries > 0 else "starting")

    def start(self, serial, container, with_audio=True):
        """起 scrcpy。container 是画面要嵌进去的那个 Qt 部件（可嵌失败）。"""
        self.stop()

        exe = scrcpy_exe()
        if not exe:
            self.state.emit("failed:没找到 _tools/scrcpy/ 里的 scrcpy.exe")
            return
        if not serial:
            self.state.emit("failed:手机没连上，先插数据线")
            return

        self._container = container
        self._title = "Taku投屏 %s" % (serial or "")
        args = [exe, "-s", str(serial),
                "--window-title", self._title,
                "--always-on-top",
                "--stay-awake"]
        if not with_audio:
            args.append("--no-audio")

        # stderr 落到临时文件：起不来的时候能捞两句原因，用户不用抓瞎
        try:
            fd, self._err_file = tempfile.mkstemp(suffix=".log", prefix="scrcpy_")
            self._err_f = os.fdopen(fd, "w")
        except Exception:
            self._err_file, self._err_f = None, None

        try:
            self._proc = subprocess.Popen(
                args, cwd=os.path.dirname(exe),
                stdout=subprocess.DEVNULL,
                stderr=(self._err_f if self._err_f else subprocess.DEVNULL),
                creationflags=_NO_WINDOW)
        except Exception as e:
            self.state.emit("failed:scrcpy 启动失败：%s" % str(e)[:80])
            return

        self.state.emit("starting")
        self._tries = 0
        self._embedded = False
        self._with_audio = with_audio
        self._poll.start()

    # --------------------------------------------------------
    def _poll_once(self):
        self._tries += 1

        # 进程起了又死了（大部分是音频初始化失败或手机没授权）
        if not self.running():
            self._poll.stop()
            why = self._read_err_tail()
            if self._with_audio and not self._retried_noaudio:
                self._retried_noaudio = True
                self._log("scrcpy 起挂了（%s）→ 关掉声音重试一次" % (why or "原因不明"))
                self.start(self._serial, self._container, with_audio=False)
                return
            self.state.emit("failed:scrcpy 起不来。%s" % (why or ""))
            return

        if self._hwnd is None:
            self._hwnd = _find_window(self._title)

        if self._hwnd is not None:
            if not self._embedded:
                if _embed_into(self._hwnd, self._container):
                    self._embedded = True
                    self._poll.stop()
                    self._watch.start()
                    self.state.emit("embedded")
                else:
                    # 嵌不进去 → 独立窗口模式（一样能点拉、有声音）
                    self._poll.stop()
                    self._watch.start()
                    self.state.emit("standalone")
            return

        if self._tries * 400 >= self._FIND_TIMEOUT_MS:
            self._poll.stop()
            if self.running():
                # 窗口标题没找到但进程活着 → 让它自己当独立窗口
                self._watch.start()
                self.state.emit("standalone")
            else:
                self.state.emit("failed:窗口没出来，进程也没了")

    # --------------------------------------------------------
    def _watch_proc(self):
        """运行中盯着进程：手机拔了 / 用户自己关了窗口 → 汇报一声。"""
        if not self.running():
            self._watch.stop()
            self._hwnd = None
            self._embedded = False
            self.state.emit("stopped")

    # --------------------------------------------------------
    def stop(self):
        if self._poll.isActive():
            self._poll.stop()
        if self._watch.isActive():
            self._watch.stop()
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:
                pass
            self._proc = None
        self._hwnd = None
        self._embedded = False
        self._try_close_err()

    def _read_err_tail(self):
        try:
            if self._err_f:
                self._err_f.flush()
            if self._err_file and os.path.exists(self._err_file):
                with open(self._err_file, "r", errors="replace") as f:
                    lines = [ln.strip() for ln in f.readlines()[-6:] if ln.strip()]
                return "；".join(lines)[-160:]
        except Exception:
            pass
        return ""

    def _try_close_err(self):
        try:
            if self._err_f:
                self._err_f.close()
        except Exception:
            pass
        self._err_f = None

    def _log(self, msg):
        print("[投屏] %s" % msg, flush=True)

    # --------------------------------------------------------
    # 容器大小变了 → scrcpy 窗口跟着铺满
    # --------------------------------------------------------
    def eventFilter(self, obj, ev):
        if obj is self._container and ev.type() == QEvent.Resize and self._hwnd:
            _fit(self._hwnd, self._container)
        return False

    def _set_container(self, container):
        if self._container is not None:
            try:
                self._container.removeEventFilter(self)
            except Exception:
                pass
        self._container = container
        if container is not None:
            container.installEventFilter(self)


# 原来直接赋值容器，这里补上挂事件过滤（_fit 要跟着容器缩放）
_orig_start = ScrcpyMirror.start


def _start(self, serial, container, with_audio=True):
    self._set_container(container)
    _orig_start(self, serial, container, with_audio)


ScrcpyMirror.start = _start


# ============================================================
# 单例
# ============================================================
_MIRROR = None


def get_mirror():
    global _MIRROR
    if _MIRROR is None:
        _MIRROR = ScrcpyMirror()
    return _MIRROR


def stop_mirror():
    global _MIRROR
    if _MIRROR is not None:
        _MIRROR.stop()
