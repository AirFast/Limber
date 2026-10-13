"""Усе, що залежить від операційної системи: Windows і macOS.

Решта програми звертається лише до функцій цього модуля, тож платформні бібліотеки
(winreg, ctypes.windll, AppKit) імпортуються тільки всередині відповідних гілок.
"""
import os
import plistlib
import subprocess
import sys

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

APP_NAME = "Limber"
APP_ID = "Limber.BreakReminder"            # Windows: AppUserModelID для власної іконки в панелі завдань
BUNDLE_ID = "com.airfast.limber"           # macOS: ідентифікатор програми й LaunchAgent
TASK_NAME = "Limber"                       # Windows: завдання Планувальника
MUTEX_NAME = "Local\\LimberSingleInstance"
SHOW_EVENT_NAME = "Local\\LimberShowWindow"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
LEGACY_RUN_VALUES = ("Limber", "Rozminka")


def data_dir():
    """Папка налаштувань, статистики й журналу."""
    if IS_MAC:
        return os.path.expanduser("~/Library/Application Support/Limber")
    return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Limber")


# ---------- шрифти ----------

if IS_MAC:
    _FAMILY = "Helvetica Neue"
else:
    _FAMILY = "Segoe UI"


def font(size, style="regular"):
    """Шрифт інтерфейсу: regular, semibold або light."""
    if IS_MAC:
        return (_FAMILY, size, "bold") if style == "semibold" else (_FAMILY, size)
    family = {"semibold": "Segoe UI Semibold", "light": "Segoe UI Light"}.get(style, _FAMILY)
    return (family, size)


# ---------- процес і вікна ----------

def init_process():
    """До створення вікон: чіткі шрифти на Windows і власна іконка в панелі завдань."""
    if not IS_WINDOWS:
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except (AttributeError, OSError):
        pass


def init_tk(root):
    """macOS рахує шрифти в пунктах при 72 dpi — масштабуємо як на Windows (96 dpi),
    щоб розмітка вікон виглядала однаково."""
    if IS_MAC:
        root.tk.call("tk", "scaling", 96 / 72)


def style_window(win):
    """Темний заголовок вікна під темний інтерфейс програми."""
    if IS_WINDOWS:
        import ctypes
        try:
            hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
            on = ctypes.c_int(1)
            for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (нові та старі збірки Windows 10)
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(on), ctypes.sizeof(on)) == 0:
                    break
        except (AttributeError, OSError):
            pass
    elif IS_MAC:
        try:
            win.tk.call("::tk::unsupported::MacWindowStyle", "appearance", win._w, "darkaqua")
        except Exception:
            pass


def activate_app():
    """macOS: програма рядка меню неактивна, тож перед повноекранною перервою виводимо її наперед."""
    if IS_MAC:
        try:
            from AppKit import NSApplication
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        except Exception:
            pass


def monitors():
    """[(x, y, w, h, (робоча область l, t, r, b), основний?)] — основний монітор першим."""
    if IS_MAC:
        return _monitors_mac()
    if IS_WINDOWS:
        return _monitors_windows()
    return []


def _monitors_windows():
    import ctypes
    user32 = ctypes.windll.user32

    class RECT(ctypes.Structure):
        _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", RECT), ("rcWork", RECT), ("dwFlags", ctypes.c_ulong)]

    result = []
    proc_type = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
                                   ctypes.POINTER(RECT), ctypes.c_void_p)

    def callback(hmon, _hdc, _rect, _data):
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        user32.GetMonitorInfoW(ctypes.c_void_p(hmon), ctypes.byref(info))
        r, w = info.rcMonitor, info.rcWork
        result.append((r.l, r.t, r.r - r.l, r.b - r.t, (w.l, w.t, w.r, w.b), bool(info.dwFlags & 1)))
        return 1

    try:
        user32.EnumDisplayMonitors(None, None, proc_type(callback), 0)
    except OSError:
        return []
    result.sort(key=lambda m: not m[5])
    return result


def _monitors_mac():
    """NSScreen рахує y знизу вгору від основного екрана, Tk — згори вниз."""
    try:
        from AppKit import NSScreen
    except ImportError:
        return []
    screens = list(NSScreen.screens())
    if not screens:
        return []
    top = screens[0].frame().size.height
    result = []
    for i, screen in enumerate(screens):
        f, v = screen.frame(), screen.visibleFrame()
        x, w, h = int(f.origin.x), int(f.size.width), int(f.size.height)
        y = int(top - (f.origin.y + f.size.height))
        work = (int(v.origin.x), int(top - (v.origin.y + v.size.height)),
                int(v.origin.x + v.size.width), int(top - v.origin.y))
        result.append((x, y, w, h, work, i == 0))
    return result


def screenshot(path):
    """Знімок усього екрана (для --smoke-test)."""
    if IS_MAC:
        subprocess.run(["screencapture", "-x", path], check=False)
    else:
        from PIL import ImageGrab
        ImageGrab.grab(all_screens=True).save(path)


# ---------- звук і сповіщення ----------

def beep(kind="info"):
    """kind: info — початок/кінець перерви, step — зміна вправи."""
    if IS_WINDOWS:
        import winsound
        winsound.MessageBeep(winsound.MB_OK if kind == "step" else winsound.MB_ICONASTERISK)
    elif IS_MAC:
        sound = "Tink" if kind == "step" else "Glass"
        try:
            subprocess.Popen(["afplay", f"/System/Library/Sounds/{sound}.aiff"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass


def notify(icon, title, message):
    """Системне сповіщення. На macOS pystray їх не підтримує — використовуємо AppleScript."""
    try:
        if IS_MAC:
            def quote(s):
                return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
            subprocess.Popen(["osascript", "-e", f"display notification {quote(message)} with title {quote(title)}"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            icon.notify(message, title)
    except Exception:
        pass


def system_language():
    """Мова інтерфейсу системи: українська → uk, будь-яка інша → en."""
    if IS_WINDOWS:
        import ctypes
        try:
            return "uk" if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x22 else "en"
        except (AttributeError, OSError):
            return "uk"
    if IS_MAC:
        try:
            from Foundation import NSLocale
            preferred = NSLocale.preferredLanguages()
            return "uk" if preferred and str(preferred[0]).startswith("uk") else "en"
        except Exception:
            pass
    return "en"


# ---------- іконка в треї / рядку меню ----------

def start_tray(icon, root):
    """Windows: власний цикл pystray в окремому потоці.
    macOS: обидві бібліотеки мусять жити в головному потоці, тож pystray під'єднується
    до циклу NSApplication, який уже крутить Tk."""
    if IS_MAC:
        icon.run_detached(setup=lambda _icon: None)
        root.after(300, lambda: setattr(icon, "visible", True))
    else:
        import threading
        threading.Thread(target=icon.run, daemon=True).start()


def make_tray_icon(pystray, name, image, title, menu):
    if IS_MAC:
        from AppKit import NSApplication
        return pystray.Icon(name, image, title, menu, darwin_nsapplication=NSApplication.sharedApplication())
    return pystray.Icon(name, image, title, menu)


# ---------- одна копія програми ----------

class SingleInstance:
    """Друга копія не стартує, а просить першу показати вікно."""

    def __init__(self):
        self._handle = None
        self._event = None
        self._lock_file = None
        self._request = os.path.join(data_dir(), "show.request")

    def acquire(self):
        if IS_WINDOWS:
            return self._acquire_windows()
        return self._acquire_posix()

    def _acquire_windows(self):
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = ctypes.c_void_p
        for fn, args in ((kernel32.CreateMutexW, [handle, ctypes.c_bool, ctypes.c_wchar_p]),
                         (kernel32.CreateEventW, [handle, ctypes.c_bool, ctypes.c_bool, ctypes.c_wchar_p]),
                         (kernel32.OpenEventW, [ctypes.c_uint32, ctypes.c_bool, ctypes.c_wchar_p])):
            fn.argtypes, fn.restype = args, handle
        kernel32.SetEvent.argtypes = kernel32.CloseHandle.argtypes = [handle]
        kernel32.WaitForSingleObject.argtypes = [handle, ctypes.c_uint32]
        self._handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            event = kernel32.OpenEventW(0x0002, False, SHOW_EVENT_NAME)  # EVENT_MODIFY_STATE
            if event:
                kernel32.SetEvent(event)
                kernel32.CloseHandle(event)
            return False
        self._event = kernel32.CreateEventW(None, False, False, SHOW_EVENT_NAME)
        return True

    def _acquire_posix(self):
        import fcntl
        os.makedirs(data_dir(), exist_ok=True)
        self._lock_file = open(os.path.join(data_dir(), "limber.lock"), "w")
        try:
            fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            open(self._request, "w").close()
            return False
        if os.path.exists(self._request):
            os.remove(self._request)
        return True

    def show_requested(self):
        """Викликається з головного циклу: чи просила друга копія показати вікно."""
        if IS_WINDOWS:
            import ctypes
            return bool(self._event) and ctypes.windll.kernel32.WaitForSingleObject(self._event, 0) == 0
        if os.path.exists(self._request):
            os.remove(self._request)
            return True
        return False


# ---------- автозапуск ----------

def launch_target(script):
    """(програма, аргументи) для запуску Limber: зібраний exe/app або python + скрипт."""
    if getattr(sys, "frozen", False):
        return sys.executable, []
    exe = sys.executable
    if IS_WINDOWS:
        pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.exists(pythonw):
            exe = pythonw
    return exe, [os.path.abspath(script)]


def get_autostart():
    if IS_MAC:
        return os.path.exists(_launch_agent_path())
    return subprocess.run(["schtasks", "/query", "/tn", TASK_NAME], capture_output=True,
                          creationflags=subprocess.CREATE_NO_WINDOW).returncode == 0


def set_autostart(enabled, script):
    if IS_MAC:
        _set_autostart_mac(enabled, script)
    else:
        _set_autostart_windows(enabled, script)


def _launch_agent_path():
    return os.path.expanduser(f"~/Library/LaunchAgents/{BUNDLE_ID}.plist")


def _set_autostart_mac(enabled, script):
    """LaunchAgent запускає Limber під час входу в macOS."""
    path = _launch_agent_path()
    if not enabled:
        if os.path.exists(path):
            os.remove(path)
        return
    target, arguments = launch_target(script)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        plistlib.dump({
            "Label": BUNDLE_ID,
            "ProgramArguments": [target, *arguments],
            "RunAtLoad": True,
            "LimitLoadToSessionType": "Aqua",
        }, f)


def _run_powershell(script, **env):
    """Скрипт отримує значення через змінні середовища — без проблем з лапками у шляхах."""
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                          env=dict(os.environ, **env), capture_output=True, stdin=subprocess.DEVNULL,
                          creationflags=subprocess.CREATE_NO_WINDOW, timeout=60)


def _remove_legacy_autostart_windows():
    """Ранні версії писали автозапуск у реєстр Run і в папку «Автозавантаження»."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            for name in LEGACY_RUN_VALUES:
                try:
                    winreg.DeleteValue(key, name)
                except FileNotFoundError:
                    pass
    except OSError:
        pass
    link = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup\Limber.lnk")
    if os.path.exists(link):
        os.remove(link)


def _set_autostart_windows(enabled, script):
    """Завдання Планувальника «під час входу» із затримкою — надійніше за реєстр Run."""
    _remove_legacy_autostart_windows()
    if not enabled:
        _run_powershell("Unregister-ScheduledTask -TaskName $env:L_TASK -Confirm:$false -ErrorAction SilentlyContinue",
                        L_TASK=TASK_NAME)
        return
    target, arguments = launch_target(script)
    # Встановлений Limber.exe запускається без аргументів, а порожній -Argument PowerShell не приймає
    ps = (
        "$a = if ($env:L_ARGS) { New-ScheduledTaskAction -Execute $env:L_EXE -Argument $env:L_ARGS "
        "-WorkingDirectory $env:L_DIR } else { New-ScheduledTaskAction -Execute $env:L_EXE -WorkingDirectory $env:L_DIR }; "
        "$t = New-ScheduledTaskTrigger -AtLogOn -User $env:L_USER; $t.Delay = 'PT20S'; "
        "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
        "-ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew; "
        "$p = New-ScheduledTaskPrincipal -UserId $env:L_USER -LogonType Interactive -RunLevel Limited; "
        "Register-ScheduledTask -TaskName $env:L_TASK -Action $a -Trigger $t -Settings $s -Principal $p "
        "-Description 'Limber break reminder' -Force | Out-Null")
    result = _run_powershell(ps, L_EXE=target, L_ARGS=" ".join(f'"{a}"' for a in arguments), L_TASK=TASK_NAME,
                             L_DIR=os.path.dirname(target if getattr(sys, "frozen", False) else os.path.abspath(script)),
                             L_USER=f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}")
    if result.returncode != 0:
        raise OSError(result.stderr.decode("utf-8", "replace").strip() or "Register-ScheduledTask failed")


# ---------- перенесення старих даних ----------

def migrate_old_data(target_dir):
    """Windows: дані з часів «Розминки» та з копій, запущених з-під застосунку Claude (MSIX)."""
    if not IS_WINDOWS:
        return
    import shutil
    appdata = os.environ.get("APPDATA", "")
    old = os.path.join(appdata, "Rozminka")
    if os.path.isdir(old) and not os.path.exists(target_dir):
        os.replace(old, target_dir)
    packages = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Packages")
    if os.path.isdir(packages):
        for name in os.listdir(packages):
            cached = os.path.join(packages, name, "LocalCache", "Roaming", "Limber")
            if name.startswith("Claude_") and os.path.isdir(cached):
                os.makedirs(target_dir, exist_ok=True)
                for file in ("config.json", "stats.json"):
                    src, dst = os.path.join(cached, file), os.path.join(target_dir, file)
                    if os.path.exists(src) and not os.path.exists(dst):
                        shutil.copy2(src, dst)
