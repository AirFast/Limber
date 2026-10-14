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

APP_NAME = "Rhythmos"
APP_ID = "Rhythmos.BreakReminder"            # Windows: AppUserModelID для власної іконки в панелі завдань
BUNDLE_ID = "com.airfast.rhythmos"           # macOS: ідентифікатор програми й LaunchAgent
TASK_NAME = "Rhythmos"                       # Windows: завдання Планувальника
MUTEX_NAME = "Local\\RhythmosSingleInstance"
SHOW_EVENT_NAME = "Local\\RhythmosShowWindow"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def data_dir():
    """Папка налаштувань, статистики й журналу."""
    if IS_MAC:
        return os.path.expanduser("~/Library/Application Support/Rhythmos")
    return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Rhythmos")


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
        # Tk під час старту робить програму звичайною (Dock, меню «File Edit…»), ігноруючи
        # LSUIElement з Info.plist. Повертаємо режим програми рядка меню.
        try:
            from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
            NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        except Exception:
            pass


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


def on_reopen(root, callback):
    """macOS: повторне відкриття вже запущеної програми (Finder, Launchpad, Spotlight) не стартує
    другу копію, а надсилає першій подію «reopen» — показуємо на неї вікно."""
    if IS_MAC:
        root.createcommand("::tk::mac::ReopenApplication", callback)


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


def idle_seconds():
    """Скільки секунд не було ні миші, ні клавіатури. 0 — якщо ОС не відповіла (тоді вважаємо, що людина тут)."""
    try:
        if IS_WINDOWS:
            import ctypes

            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

            info = LASTINPUTINFO()
            info.cbSize = ctypes.sizeof(info)
            if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
                return 0.0
            # Обидва лічильники — 32-бітні мілісекунди від старту системи, тож різниця — по модулю 2^32
            return ((ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000
        if IS_MAC:
            from Quartz import (CGEventSourceSecondsSinceLastEventType, kCGAnyInputEventType,
                                kCGEventSourceStateCombinedSessionState)
            return float(CGEventSourceSecondsSinceLastEventType(kCGEventSourceStateCombinedSessionState,
                                                                kCGAnyInputEventType))
    except Exception:
        pass
    return 0.0


def work_area(root):
    """Робоча область основного екрана (без панелі завдань / рядка меню й Dock): (l, t, r, b)."""
    screens = monitors()
    if screens:
        return screens[0][4]
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight() - 48


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

# Windows: події стандартної звукової схеми («Панель керування → Звук → Звуки»).
# Звук беремо з поточної схеми користувача — якщо він змінить його у Windows, Rhythmos зіграє його ж.
# Ідентифікатор → подія; підпис для інтерфейсу — i18n "snd_<ідентифікатор>".
_WINDOWS_EVENTS = [
    ("notification", "Notification.Default"),
    ("reminder", "Notification.Reminder"),
    ("message", "Notification.IM"),
    ("mail", "Notification.Mail"),
    ("chime", "Notification.Proximity"),
    ("default", ".Default"),
]
# Якщо у схемі звуків немає (наприклад, «Без звуків») — стандартні файли Windows напряму
_WINDOWS_FALLBACK = [
    ("notification", "Windows Notify System Generic.wav"), ("reminder", "Windows Notify Calendar.wav"),
    ("message", "Windows Notify Messaging.wav"), ("mail", "Windows Notify Email.wav"),
    ("chime", "Windows Proximity Notification.wav"), ("default", "Windows Background.wav"),
]
# Інші стандартні звуки Windows (C:\Windows\Media), приємні як сигнал перерви
_WINDOWS_EXTRA = [
    ("ding", "Windows Ding.wav"), ("nudge", "Windows Message Nudge.wav"), ("balloon", "Windows Balloon.wav"),
    ("classic", "Windows Notify.wav"), ("exclamation", "Windows Exclamation.wav"),
    ("device", "Windows Hardware Insert.wav"), ("unlock", "Windows Unlock.wav"),
    ("print", "Windows Print complete.wav"), ("logon", "Windows Logon.wav"),
    ("chimes", "chimes.wav"), ("chord", "chord.wav"), ("tada", "tada.wav"),
]
# macOS: стандартні звуки сповіщень («Системні параметри → Звук»)
_MAC_SOUNDS = ["Glass", "Ping", "Hero", "Pop", "Purr", "Submarine", "Funk", "Bottle", "Blow", "Frog", "Morse",
               "Sosumi", "Tink", "Basso"]
# Новіші звуки сповіщень macOS (Sonoma і пізніші): є не в усіх версіях — беремо, якщо знайдуться
_MAC_MODERN_DIR = "/System/Library/PrivateFrameworks/ToneLibrary.framework/Versions/A/Resources/AlertTones/Modern"


def _scheme_sound(event):
    """Файл, призначений події в поточній звуковій схемі Windows, або None."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"AppEvents\Schemes\Apps\.Default\{event}\.Current") as key:
            path = os.path.expandvars(winreg.QueryValue(key, None) or "")
    except OSError:
        return None
    if path and not os.path.isabs(path):  # схема може містити лише ім'я файлу з папки Media
        path = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Media", path)
    return path if path and os.path.exists(path) else None


def available_sounds():
    """[(ідентифікатор, шлях до файлу)] стандартних системних звуків, які є на цьому комп'ютері."""
    if IS_WINDOWS:
        sounds, seen = [], set()
        for sound_id, event in _WINDOWS_EVENTS:
            path = _scheme_sound(event)
            if path and path.lower() not in seen:  # кілька подій можуть мати той самий файл
                seen.add(path.lower())
                sounds.append((sound_id, path))
        media = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Media")
        if len(sounds) < 2:
            sounds = [(sound_id, os.path.join(media, file)) for sound_id, file in _WINDOWS_FALLBACK
                      if os.path.exists(os.path.join(media, file))]
            seen = {path.lower() for _id, path in sounds}
        for sound_id, file in _WINDOWS_EXTRA:
            path = os.path.join(media, file)
            if os.path.exists(path) and path.lower() not in seen:
                seen.add(path.lower())
                sounds.append((sound_id, path))
        return sounds
    if IS_MAC:
        sounds = [(name, f"/System/Library/Sounds/{name}.aiff") for name in _MAC_SOUNDS
                  if os.path.exists(f"/System/Library/Sounds/{name}.aiff")]
        if os.path.isdir(_MAC_MODERN_DIR):
            for file in sorted(os.listdir(_MAC_MODERN_DIR)):
                name, ext = os.path.splitext(file)
                if ext.lower() in (".m4r", ".caf", ".aiff", ".m4a") and name not in dict(sounds):
                    sounds.append((name, os.path.join(_MAC_MODERN_DIR, file)))
        return sounds
    return []


def play_sound(path):
    """Програє файл звуку, не блокуючи інтерфейс."""
    try:
        if IS_WINDOWS:
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        elif IS_MAC:
            subprocess.Popen(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, RuntimeError):
        pass


def beep(kind="info", sound=None):
    """kind: info — початок/кінець перерви (звук на вибір користувача), step — зміна вправи."""
    if kind == "info" and sound:
        path = dict(available_sounds()).get(sound)
        if path:
            play_sound(path)
            return
    if IS_WINDOWS:
        import winsound
        winsound.MessageBeep(winsound.MB_OK if kind == "step" else winsound.MB_ICONASTERISK)
    elif IS_MAC:
        play_sound(f"/System/Library/Sounds/{'Tink' if kind == 'step' else 'Glass'}.aiff")


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
        self._lock_file = open(os.path.join(data_dir(), "rhythmos.lock"), "w")
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
    """(програма, аргументи) для запуску Rhythmos: зібраний exe/app або python + скрипт."""
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
    """LaunchAgent запускає Rhythmos під час входу в macOS."""
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


def _set_autostart_windows(enabled, script):
    """Завдання Планувальника «під час входу» із затримкою — надійніше за реєстр Run."""
    if not enabled:
        _run_powershell("Unregister-ScheduledTask -TaskName $env:L_TASK -Confirm:$false -ErrorAction SilentlyContinue",
                        L_TASK=TASK_NAME)
        return
    target, arguments = launch_target(script)
    # Встановлений Rhythmos.exe запускається без аргументів, а порожній -Argument PowerShell не приймає
    ps = (
        "$a = if ($env:L_ARGS) { New-ScheduledTaskAction -Execute $env:L_EXE -Argument $env:L_ARGS "
        "-WorkingDirectory $env:L_DIR } else { New-ScheduledTaskAction -Execute $env:L_EXE -WorkingDirectory $env:L_DIR }; "
        "$t = New-ScheduledTaskTrigger -AtLogOn -User $env:L_USER; $t.Delay = 'PT20S'; "
        "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
        "-ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew; "
        "$p = New-ScheduledTaskPrincipal -UserId $env:L_USER -LogonType Interactive -RunLevel Limited; "
        "Register-ScheduledTask -TaskName $env:L_TASK -Action $a -Trigger $t -Settings $s -Principal $p "
        "-Description 'Rhythmos break reminder' -Force | Out-Null")
    result = _run_powershell(ps, L_EXE=target, L_ARGS=" ".join(f'"{a}"' for a in arguments), L_TASK=TASK_NAME,
                             L_DIR=os.path.dirname(target if getattr(sys, "frozen", False) else os.path.abspath(script)),
                             L_USER=f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}")
    if result.returncode != 0:
        raise OSError(result.stderr.decode("utf-8", "replace").strip() or "Register-ScheduledTask failed")
