"""Everything that depends on the operating system: Windows and macOS.

The rest of the app only calls this module's functions, so platform libraries
(winreg, ctypes.windll, AppKit) are imported only inside the matching branches.
"""
import os
import plistlib
import subprocess
import sys

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
# Cursor over clickable things: Tk's "hand2" is an old X11 hand on macOS, "pointinghand" is the native one
HAND = "pointinghand" if IS_MAC else "hand2"

APP_NAME = "Rhythmos"
APP_ID = "Rhythmos.BreakReminder"            # Windows: AppUserModelID for our own taskbar icon
BUNDLE_ID = "com.airfast.rhythmos"           # macOS: the app and LaunchAgent identifier
TASK_NAME = "Rhythmos"                       # Windows: the Task Scheduler task
MUTEX_NAME = "Local\\RhythmosSingleInstance"
SHOW_EVENT_NAME = "Local\\RhythmosShowWindow"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def data_dir():
    """The folder for settings, statistics and the log."""
    if IS_MAC:
        return os.path.expanduser("~/Library/Application Support/Rhythmos")
    return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Rhythmos")


# ---------- fonts ----------

if IS_MAC:
    _FAMILY = "Helvetica Neue"
else:
    _FAMILY = "Segoe UI"


def font(size, style="regular"):
    """The UI font: regular, semibold or light."""
    if IS_MAC:
        return (_FAMILY, size, "bold") if style == "semibold" else (_FAMILY, size)
    family = {"semibold": "Segoe UI Semibold", "light": "Segoe UI Light"}.get(style, _FAMILY)
    return (family, size)


# ---------- process and windows ----------

def init_process():
    """Before creating windows: crisp fonts on Windows and our own taskbar icon."""
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
    """macOS counts fonts in points at 72 dpi; scale as on Windows (96 dpi)
    so window layouts look the same."""
    if IS_MAC:
        root.tk.call("tk", "scaling", 96 / 72)
        # On startup Tk turns the app into a regular one (Dock, the "File Edit…" menu), ignoring
        # LSUIElement from Info.plist. Switch back to a menu-bar app.
        try:
            from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
            NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        except Exception:
            pass


def style_window(win):
    """A dark window title bar to match the app's dark UI."""
    if IS_WINDOWS:
        import ctypes
        try:
            hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
            on = ctypes.c_int(1)
            for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (newer and older Windows 10 builds)
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
    """macOS: reopening the running app (Finder, Launchpad, Spotlight) doesn't start
    a second copy but sends the first one a "reopen" event; we show the window on it."""
    if IS_MAC:
        root.createcommand("::tk::mac::ReopenApplication", callback)


def activate_app():
    """macOS: a menu-bar app is inactive, so bring it to the front before a fullscreen break."""
    if IS_MAC:
        try:
            from AppKit import NSApplication
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        except Exception:
            pass


def keep_on_top(win, geometry):
    """Places a reminder window ("WxH+X+Y") and keeps it above the others, the app's own main window
    included. "-topmost" goes first: set after the place on a frameless window not yet on screen, it moves
    the window to the screen's top left corner (on Windows and macOS alike). On macOS "-topmost" given before
    the window is shown is also lost (the main window opened later covered a reminder), so there both are
    set again, in the same order, once the window is on screen."""
    win.attributes("-topmost", True)
    win.geometry(geometry)
    if IS_MAC:
        def again():
            if win.winfo_exists():
                win.attributes("-topmost", True)
                win.geometry(geometry)

        win.after_idle(again)
        win.after(250, again)


_display_assertion = None  # macOS: the IOPMAssertionID held while a break screen is shown


def keep_display_awake(on):
    """While a break screen is shown: no screen saver and no display sleep, like a video player. The person
    does the exercises without touching the mouse or keyboard, so the system took them for idle and started
    the screen saver over the break (#2). It doesn't fake input: idle and away detection keep working.
    Windows: SetThreadExecutionState (on the Tk thread); macOS: an IOKit PreventUserIdleDisplaySleep assertion."""
    global _display_assertion
    try:
        if IS_WINDOWS:
            import ctypes
            es_continuous, es_system, es_display = 0x80000000, 0x00000001, 0x00000002
            ctypes.windll.kernel32.SetThreadExecutionState(es_continuous | (es_system | es_display if on else 0))
        elif IS_MAC:
            import ctypes
            iokit = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/IOKit.framework/IOKit")
            if on and _display_assertion is None:
                cf = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
                cf.CFStringCreateWithCString.restype = ctypes.c_void_p
                cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
                cf.CFRelease.argtypes = [ctypes.c_void_p]
                utf8 = 0x08000100
                kind = cf.CFStringCreateWithCString(None, b"PreventUserIdleDisplaySleep", utf8)
                name = cf.CFStringCreateWithCString(None, b"Rhythmos break", utf8)
                iokit.IOPMAssertionCreateWithName.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p,
                                                              ctypes.POINTER(ctypes.c_uint32)]
                assertion = ctypes.c_uint32(0)
                result = iokit.IOPMAssertionCreateWithName(kind, 255, name, ctypes.byref(assertion))  # level On
                cf.CFRelease(kind)
                cf.CFRelease(name)
                if result == 0:
                    _display_assertion = assertion.value
                else:
                    print(f"display assertion failed: {result:#x}", file=sys.stderr)
            elif not on and _display_assertion is not None:
                iokit.IOPMAssertionRelease.argtypes = [ctypes.c_uint32]
                iokit.IOPMAssertionRelease(_display_assertion)
                _display_assertion = None
    except Exception as error:  # never let this break the break screen itself
        print(f"keep_display_awake({on}) failed: {error}", file=sys.stderr)


def display_assertions():
    """For the smoke test: whether the break's display assertion is held (macOS: pmset; Windows: our flag)."""
    if IS_MAC:
        out = subprocess.run(["pmset", "-g", "assertions"], capture_output=True, text=True).stdout
        return [line.strip() for line in out.splitlines() if "Rhythmos break" in line] or "none"
    return "n/a"


def monitors():
    """[(x, y, w, h, (work area l, t, r, b), primary?)], the primary monitor first."""
    if IS_MAC:
        return _monitors_mac()
    if IS_WINDOWS:
        return _monitors_windows()
    return []


def idle_seconds():
    """Seconds without mouse or keyboard. 0 if the OS didn't answer (then the person is assumed present)."""
    try:
        if IS_WINDOWS:
            import ctypes

            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

            info = LASTINPUTINFO()
            info.cbSize = ctypes.sizeof(info)
            if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
                return 0.0
            # Both counters are 32-bit milliseconds since system start, so the difference is modulo 2^32
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
    """The primary screen's work area (without the taskbar / menu bar and Dock): (l, t, r, b)."""
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
    """NSScreen counts y from the bottom up from the primary screen, Tk from the top down."""
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
    """A screenshot of the whole screen (for --smoke-test)."""
    if IS_MAC:
        subprocess.run(["screencapture", "-x", path], check=False)
    else:
        from PIL import ImageGrab
        ImageGrab.grab(all_screens=True).save(path)


# ---------- busyness: fullscreen apps and calls ----------

def busy_reason():
    """Whether the person shouldn't be interrupted by a fullscreen break right now.

    None means fine; otherwise a short reason: "fullscreen" (a game, video, fullscreen presentation),
    "camera" or "microphone" (most likely a call). Cheap (a few milliseconds), so it can be
    called even every second; on macOS from the main thread (NSScreen). Never raises:
    if the OS didn't answer, the person is assumed not busy."""
    if IS_WINDOWS:
        checks = (("fullscreen", _fullscreen_windows),
                  ("camera", lambda: _device_in_use(_consent_apps("webcam"))),
                  ("microphone", lambda: _device_in_use(_consent_apps("microphone"))))
    elif IS_MAC:
        checks = (("fullscreen", _fullscreen_mac), ("camera", _camera_in_use_mac),
                  ("microphone", _microphone_in_use_mac))
    else:
        return None
    for reason, check in checks:
        try:
            if check():
                return reason
        except Exception:
            pass
    return None


def _covers_monitor(window_rect, monitor_rect):
    """Whether a window covers the whole monitor. Both rectangles are (left, top, right, bottom).
    A maximized window doesn't count: it ends above the taskbar / Dock."""
    left, top, right, bottom = window_rect
    m_left, m_top, m_right, m_bottom = monitor_rect
    return (m_right > m_left and m_bottom > m_top
            and left <= m_left and top <= m_top and right >= m_right and bottom >= m_bottom)


# Windows: the desktop and the taskbar are "fullscreen windows" too; skip them
_SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}


def _is_fullscreen_window(class_name, pid, own_pid, rect, monitor, maximized_with_title=False):
    """Windows: whether the active window is a fullscreen app.
    Our own windows don't count: the Rhythmos break screen is fullscreen itself. A maximized window with
    a title bar and an auto-hidden taskbar covers the monitor too, but it isn't fullscreen."""
    if pid == own_pid or class_name in _SHELL_CLASSES or maximized_with_title:
        return False
    return _covers_monitor(rect, monitor)


def _device_in_use(apps):
    """apps: the ConsentStore registry values for each app (dicts).
    The device is busy if some app started using it (LastUsedTimeStart ≠ 0)
    and hasn't finished yet (LastUsedTimeStop = 0)."""
    return any(app.get("LastUsedTimeStart") and app.get("LastUsedTimeStop") == 0 for app in apps)


# macOS: system windows that may cover the whole screen but don't mean the person is busy
_MAC_SYSTEM_OWNERS = {"Dock", "Window Server", "SystemUIServer", "Control Center", "Notification Center",
                      "WindowManager"}


def _fullscreen_in(windows, screens, own_pid):
    """macOS: whether the windows (CGWindowListCopyWindowInfo dicts) include a regular (layer 0) opaque
    window of another app that covers some screen. screens: [(left, top, right, bottom)] in
    Quartz coordinates (from the top left corner of the primary screen)."""
    for window in windows:
        if window.get("kCGWindowLayer") != 0 or window.get("kCGWindowOwnerPID") == own_pid:
            continue
        if window.get("kCGWindowOwnerName") in _MAC_SYSTEM_OWNERS or float(window.get("kCGWindowAlpha", 1)) <= 0:
            continue
        bounds = window.get("kCGWindowBounds") or {}
        x, y = float(bounds.get("X", 0)), float(bounds.get("Y", 0))
        rect = (x, y, x + float(bounds.get("Width", 0)), y + float(bounds.get("Height", 0)))
        if any(_covers_monitor(rect, screen) for screen in screens):
            return True
    return False


_user32 = None


def _user32_api():
    """A separate user32 instance with exact types (64-bit handles), so the shared
    ctypes.windll.user32 used by the rest of the module isn't changed."""
    global _user32
    if _user32 is None:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32")
        user32.GetForegroundWindow.restype = wintypes.HWND
        for fn in (user32.IsWindowVisible, user32.IsZoomed):
            fn.argtypes, fn.restype = [wintypes.HWND], wintypes.BOOL
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetWindowLongW.restype = ctypes.c_long
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.MonitorFromWindow.restype = wintypes.HMONITOR
        user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.c_void_p]
        _user32 = user32
    return _user32


def _fullscreen_windows():
    """Windows: the active window of another app covers its whole monitor (taskbar included)."""
    import ctypes
    from ctypes import wintypes

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD)]

    user32 = _user32_api()
    hwnd = user32.GetForegroundWindow()
    if not hwnd or not user32.IsWindowVisible(hwnd):
        return False  # a locked screen, window switching
    name = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(hwnd, name, 64)
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return False
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(info)
    monitor = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
    if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return False
    titled = (user32.GetWindowLongW(hwnd, -16) & 0x00C00000) == 0x00C00000  # GWL_STYLE, WS_CAPTION
    m = info.rcMonitor
    return _is_fullscreen_window(name.value, pid.value, os.getpid(), (rect.left, rect.top, rect.right, rect.bottom),
                                 (m.left, m.top, m.right, m.bottom),
                                 maximized_with_title=titled and bool(user32.IsZoomed(hwnd)))


_CONSENT_STORE = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore"


def _consent_apps(capability):
    """Windows: LastUsedTimeStart/Stop of each app that used the device
    (webcam or microphone): the same data Windows uses for the camera/microphone icon in the tray.
    Microsoft Store apps are right under the device key, regular ones under "NonPackaged".
    A generator: busy_reason stops at the first app that is using the device now."""
    import winreg
    for path in (rf"{_CONSENT_STORE}\{capability}", rf"{_CONSENT_STORE}\{capability}\NonPackaged"):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path)
        except OSError:
            continue
        with key:
            index = 0
            while True:
                try:
                    name = winreg.EnumKey(key, index)
                except OSError:
                    break
                index += 1
                values = {}
                try:
                    with winreg.OpenKey(key, name) as app:
                        for value in ("LastUsedTimeStop", "LastUsedTimeStart"):
                            try:
                                values[value] = winreg.QueryValueEx(app, value)[0]
                            except OSError:
                                pass
                except OSError:
                    continue
                yield values


def _fullscreen_mac():
    """macOS: another app's window is fullscreen (fullscreen mode, video, presentation).
    The window list and bounds are available without the Screen Recording permission; only window names need it."""
    from Quartz import (CGWindowListCopyWindowInfo, kCGNullWindowID, kCGWindowListExcludeDesktopElements,
                        kCGWindowListOptionOnScreenOnly)
    screens = [(x, y, x + w, y + h) for x, y, w, h, _work, _main in _monitors_mac()]
    windows = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
                                         kCGNullWindowID) or []
    return _fullscreen_in(windows, screens, os.getpid())


# macOS: CoreAudio and CoreMediaIO are called through ctypes, without extra pyobjc packages
_mac_frameworks = {}


def _fourcc(code):
    """An Apple four-character code ('dIn ') → UInt32."""
    return int.from_bytes(code.encode("ascii"), "big")


def _mac_property_api(framework):
    """(GetPropertyDataSize, GetPropertyData, the property address struct) for CoreAudio or CoreMediaIO.
    Both share the same "object → property {selector, scope, element}" model."""
    if framework not in _mac_frameworks:
        import ctypes

        class PropertyAddress(ctypes.Structure):
            _fields_ = [("selector", ctypes.c_uint32), ("scope", ctypes.c_uint32), ("element", ctypes.c_uint32)]

        lib = ctypes.CDLL(f"/System/Library/Frameworks/{framework}.framework/{framework}")
        prefix = "AudioObject" if framework == "CoreAudio" else "CMIOObject"
        size_fn, data_fn = getattr(lib, prefix + "GetPropertyDataSize"), getattr(lib, prefix + "GetPropertyData")
        common = [ctypes.c_uint32, ctypes.POINTER(PropertyAddress), ctypes.c_uint32, ctypes.c_void_p]
        size_fn.argtypes = common + [ctypes.POINTER(ctypes.c_uint32)]
        if framework == "CoreAudio":  # (…, UInt32 *ioDataSize, void *outData)
            data_fn.argtypes = common + [ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p]
        else:  # CMIO: (…, UInt32 dataSize, UInt32 *dataUsed, void *data)
            data_fn.argtypes = common + [ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p]
        size_fn.restype = data_fn.restype = ctypes.c_int32
        _mac_frameworks[framework] = (size_fn, data_fn, PropertyAddress)
    return _mac_frameworks[framework]


def _mac_property(framework, obj, selector, as_list=False):
    """The value of an object's UInt32 property (or a list if as_list). None if the OS didn't answer
    (in particular, the property doesn't exist in this macOS version)."""
    import ctypes
    size_fn, data_fn, PropertyAddress = _mac_property_api(framework)
    address = PropertyAddress(_fourcc(selector), _fourcc("glob"), 0)  # scope global, element main
    size = ctypes.c_uint32(4)
    if as_list and size_fn(obj, ctypes.byref(address), 0, None, ctypes.byref(size)):
        return None
    data = (ctypes.c_uint32 * max(1, size.value // 4))()
    if framework == "CoreAudio":
        status = data_fn(obj, ctypes.byref(address), 0, None, ctypes.byref(size), data)
    else:
        status = data_fn(obj, ctypes.byref(address), 0, None, size.value, ctypes.byref(size), data)
    if status:
        return None
    return list(data[:size.value // 4]) if as_list else data[0]


def _microphone_in_use_mac():
    """macOS: someone is recording from the microphone, the same signal as the orange dot in the menu bar.
    macOS 14+: go through the audio processes (kAudioHardwarePropertyProcessObjectList) and check whether
    any of them (not us) has an active input. Older versions: whether the default input device is running
    (kAudioDevicePropertyDeviceIsRunningSomewhere), less precise: a USB headset with one device for
    input and output is "running" even when it's just playing music. No microphone permission needed."""
    processes = _mac_property("CoreAudio", 1, "prs#", as_list=True)  # 1 — kAudioObjectSystemObject
    if processes is not None:
        own = os.getpid()
        return any(_mac_property("CoreAudio", p, "piri") and _mac_property("CoreAudio", p, "ppid") != own
                   for p in processes)
    device = _mac_property("CoreAudio", 1, "dIn ")  # kAudioHardwarePropertyDefaultInputDevice
    return bool(device) and bool(_mac_property("CoreAudio", device, "gone"))


def _camera_in_use_mac():
    """macOS: some app is using the camera now (the green dot next to the camera).
    CoreMediaIO gives the camera list and kCMIODevicePropertyDeviceIsRunningSomewhere for each
    without camera permission; we never subscribe to the stream itself. Virtual cameras (OBS etc.) also
    count when someone uses them."""
    devices = _mac_property("CoreMediaIO", 1, "dev#", as_list=True)  # 1 — kCMIOObjectSystemObject
    return any(_mac_property("CoreMediaIO", d, "gone") for d in devices or [])


# ---------- sound and notifications ----------

# Windows: events of the standard sound scheme ("Control Panel → Sound → Sounds").
# The sound comes from the user's current scheme: if they change it in Windows, Rhythmos plays theirs.
# Identifier → event; the UI label is i18n "snd_<identifier>".
_WINDOWS_EVENTS = [
    ("notification", "Notification.Default"),
    ("reminder", "Notification.Reminder"),
    ("message", "Notification.IM"),
    ("mail", "Notification.Mail"),
    ("chime", "Notification.Proximity"),
    ("default", ".Default"),
]
# If the scheme has no sounds (e.g. "No Sounds"), the standard Windows files directly
_WINDOWS_FALLBACK = [
    ("notification", "Windows Notify System Generic.wav"), ("reminder", "Windows Notify Calendar.wav"),
    ("message", "Windows Notify Messaging.wav"), ("mail", "Windows Notify Email.wav"),
    ("chime", "Windows Proximity Notification.wav"), ("default", "Windows Background.wav"),
]
# Other standard Windows sounds (C:\Windows\Media) that work well as a break signal
_WINDOWS_EXTRA = [
    ("ding", "Windows Ding.wav"), ("nudge", "Windows Message Nudge.wav"), ("balloon", "Windows Balloon.wav"),
    ("classic", "Windows Notify.wav"), ("exclamation", "Windows Exclamation.wav"),
    ("device", "Windows Hardware Insert.wav"), ("unlock", "Windows Unlock.wav"),
    ("print", "Windows Print complete.wav"), ("logon", "Windows Logon.wav"),
    ("chimes", "chimes.wav"), ("chord", "chord.wav"), ("tada", "tada.wav"),
]
# macOS: standard notification sounds ("System Settings → Sound")
_MAC_SOUNDS = ["Glass", "Ping", "Hero", "Pop", "Purr", "Submarine", "Funk", "Bottle", "Blow", "Frog", "Morse",
               "Sosumi", "Tink", "Basso"]
# Newer macOS notification sounds (Sonoma and later): not in every version, used if found
_MAC_MODERN_DIR = "/System/Library/PrivateFrameworks/ToneLibrary.framework/Versions/A/Resources/AlertTones/Modern"


def _scheme_sound(event):
    """The file assigned to the event in the current Windows sound scheme, or None."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"AppEvents\Schemes\Apps\.Default\{event}\.Current") as key:
            path = os.path.expandvars(winreg.QueryValue(key, None) or "")
    except OSError:
        return None
    if path and not os.path.isabs(path):  # the scheme may hold just a file name from the Media folder
        path = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Media", path)
    return path if path and os.path.exists(path) else None


def available_sounds():
    """[(identifier, file path)] of the standard system sounds present on this computer."""
    if IS_WINDOWS:
        sounds, seen = [], set()
        for sound_id, event in _WINDOWS_EVENTS:
            path = _scheme_sound(event)
            if path and path.lower() not in seen:  # several events may share the same file
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
    """Plays a sound file without blocking the UI."""
    try:
        if IS_WINDOWS:
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        elif IS_MAC:
            subprocess.Popen(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, RuntimeError):
        pass


def beep(kind="info", sound=None):
    """kind: info is a break start/end (the user's chosen sound), step is an exercise change."""
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
    """The system UI language: Ukrainian → uk, anything else → en."""
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


# ---------- tray / menu bar icon ----------

def start_tray(icon, root):
    """Windows: pystray's own loop in a separate thread.
    macOS: both libraries must live on the main thread, so pystray attaches
    to the NSApplication loop that Tk already runs."""
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


# ---------- single instance ----------

class SingleInstance:
    """A second copy doesn't start but asks the first one to show the window."""

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
        """Called from the main loop: whether a second copy asked to show the window."""
        if IS_WINDOWS:
            import ctypes
            return bool(self._event) and ctypes.windll.kernel32.WaitForSingleObject(self._event, 0) == 0
        if os.path.exists(self._request):
            os.remove(self._request)
            return True
        return False


# ---------- autostart ----------

def launch_target(script):
    """(program, arguments) to launch Rhythmos: the built exe/app, or python + the script."""
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
    """A LaunchAgent starts Rhythmos at macOS login."""
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
    """The script gets values through environment variables, so quotes in paths are no problem."""
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                          env=dict(os.environ, **env), capture_output=True, stdin=subprocess.DEVNULL,
                          creationflags=subprocess.CREATE_NO_WINDOW, timeout=60)


def _set_autostart_windows(enabled, script):
    """A Task Scheduler "at logon" task with a delay, more reliable than the Run registry key."""
    if not enabled:
        _run_powershell("Unregister-ScheduledTask -TaskName $env:L_TASK -Confirm:$false -ErrorAction SilentlyContinue",
                        L_TASK=TASK_NAME)
        return
    target, arguments = launch_target(script)
    # The installed Rhythmos.exe starts without arguments, and PowerShell rejects an empty -Argument
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
