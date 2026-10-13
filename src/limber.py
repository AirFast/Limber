"""Limber — нагадування про перерви з вправами, водою та статистикою (Windows)."""
import ctypes
import datetime as dt
import json
import math
import os
import queue
import random
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import traceback
import winreg
import winsound
from tkinter import messagebox

if sys.stderr is None:  # pythonw: без консолі помилки імпорту інакше зникли б безслідно
    _log_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Limber")
    os.makedirs(_log_dir, exist_ok=True)
    sys.stderr = sys.stdout = open(os.path.join(_log_dir, "limber.log"), "a", encoding="utf-8", buffering=1)

import pystray
from PIL import Image, ImageDraw, ImageTk

__version__ = "1.0.0"

APP_NAME = "Limber"
APP_TAGLINE = "час розім'ятися"
APP_ID = "Limber.BreakReminder"
APPDATA = os.environ.get("APPDATA", os.path.expanduser("~"))
DATA_DIR = os.path.join(APPDATA, "Limber")
OLD_DATA_DIR = os.path.join(APPDATA, "Rozminka")  # дані з часів, коли програма звалася «Розминка»
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
STATS_PATH = os.path.join(DATA_DIR, "stats.json")
ICON_PATH = os.path.join(DATA_DIR, "limber.ico")
LOG_PATH = os.path.join(DATA_DIR, "limber.log")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
LEGACY_RUN_VALUES = ("Limber", "Rozminka")
STARTUP_LINK = os.path.join(APPDATA, r"Microsoft\Windows\Start Menu\Programs\Startup\Limber.lnk")
TASK_NAME = "Limber"
MUTEX_NAME = "Local\\LimberSingleInstance"
SHOW_EVENT_NAME = "Local\\LimberShowWindow"  # другий запуск просить уже запущений екземпляр показати вікно

DEFAULTS = {
    "mini_interval_min": 20,
    "mini_duration_sec": 30,
    "long_every": 3,
    "long_duration_min": 5,
    "postpone_min": 5,
    "postpone_limit": 2,
    "warn_before_sec": 30,
    "water_enabled": True,
    "water_interval_min": 60,
    "water_goal": 8,
    "intensity": 2,
    "workout_enabled": True,
    "sound": True,
}

C = {
    "bg": "#13292a",
    "card": "#1a3837",
    "panel": "#1f4241",
    "panel_hover": "#2a5654",
    "track": "#2c504e",
    "accent": "#5fc4b8",
    "accent_dark": "#3a8f86",
    "on_accent": "#0b2a28",
    "text": "#eef6f5",
    "muted": "#9dbcb8",
    "dim": "#5d7775",
    "water": "#4aa3df",
}


def fmt_minutes(v):
    h, m = divmod(v, 60)
    if not h:
        return f"{m} хв"
    return f"{h} год {m} хв" if m else f"{h} год"


def fmt_seconds(v):
    m, s = divmod(v, 60)
    if not m:
        return f"{s} с"
    return f"{m} хв {s} с" if s else f"{m} хв"


def fmt_times(v):
    if v == 0:
        return "не можна"
    word = "раз" if v % 10 == 1 and v % 100 != 11 else ("рази" if 2 <= v % 10 <= 4 and not 12 <= v % 100 <= 14 else "разів")
    return f"{v} {word}"


def fmt_warn(v):
    return "вимкнено" if v == 0 else fmt_seconds(v)


def glasses_word(v):
    if v % 10 == 1 and v % 100 != 11:
        return "склянка"
    return "склянки" if 2 <= v % 10 <= 4 and not 12 <= v % 100 <= 14 else "склянок"


def fmt_glasses(v):
    return f"{v} {glasses_word(v)} (≈{v * 0.25:g} л)".replace(".", ",")


# Повзунки налаштувань: (ключ, підпис, мінімум, максимум, крок, формат)
SLIDERS = {
    "mini_interval_min": ("Перерва кожні", 5, 120, 5, fmt_minutes),
    "mini_duration_sec": ("Тривалість міні-перерви", 10, 300, 5, fmt_seconds),
    "long_every": ("Кожна N-та перерва — довга", 1, 10, 1, str),
    "long_duration_min": ("Тривалість довгої перерви", 1, 30, 1, fmt_minutes),
    "postpone_min": ("Відкласти на", 1, 30, 1, fmt_minutes),
    "postpone_limit": ("Можна відкласти", 0, 5, 1, fmt_times),
    "warn_before_sec": ("Попередження перед перервою", 0, 120, 5, fmt_warn),
    "water_interval_min": ("Нагадувати кожні", 15, 240, 15, fmt_minutes),
    "water_goal": ("Мета на день", 4, 16, 1, fmt_glasses),
    "intensity": ("Інтенсивність вправ", 1, 3, 1, lambda v: fmt_intensity(v)),
}

MINI_EXERCISES = [
    ("Правило 20-20-20", "Знайдіть предмет щонайменше за 6 метрів і дивіться на нього 20 секунд."),
    ("Кліпання", "Часто покліпайте 10 секунд, потім заплющіть очі й розслабтеся."),
    ("Очі вгору-вниз", "Не повертаючи голови, повільно подивіться вгору, потім униз. Повторіть 5 разів."),
    ("Очі вліво-вправо", "Не повертаючи голови, повільно переведіть погляд уліво, потім управо. 5 разів."),
    ("Вісімка очима", "Повільно «намалюйте» очима велику вісімку: тричі в один бік і тричі в інший."),
    ("Ближче — далі", "Подивіться на палець перед носом, потім удалину за вікно. Повторіть 5 разів."),
    ("Пальмінг", "Розітріть долоні до тепла й накрийте ними заплющені очі. Посидьте в темряві."),
    ("Нахили голови", "Нахиліть голову до правого плеча, затримайтеся на 10 секунд. Потім до лівого."),
    ("Плечі", "Покрутіть плечима 10 разів назад, потім 10 разів уперед."),
    ("Кисті", "Стисніть кулаки, потім широко розчепірте пальці. Повторіть 10 разів."),
    ("Постава", "Сядьте рівно: стопи на підлозі, спина на спинці крісла, плечі опущені й розслаблені."),
    ("Дихання 4-4-6", "Вдих на 4 рахунки, затримка на 4, повільний видих на 6. Повторіть 3 рази."),
]

WATER_TIPS = [
    "Пийте невеликими ковтками — так вода засвоюється краще, ніж пів літра за раз.",
    "Тримайте пляшку чи графин на столі: що ближче вода, то частіше її п'єш.",
    "Колір сечі — найпростіший орієнтир: світло-солом'яний означає, що води досить.",
    "Здається, що хочеться перекусити? Іноді це насправді спрага — спершу випийте води.",
    "Кава й солодкі напої воду не замінюють. Краще — звичайна вода або трав'яний чай.",
    "Склянка води за пів години до їжі допомагає травленню і не дає переїсти.",
    "Втома й головний біль наприкінці дня часто бувають від нестачі води.",
    "Сходіть по воду пішки — це ще й маленька розминка для ніг.",
    "Якщо проста вода набридла, додайте скибочку лимона, огірка чи листок м'яти.",
    "У спеку, під час спорту чи хвороби води потрібно більше, ніж зазвичай.",
    "Почніть ранок зі склянки води — після сну організму її бракує.",
    "Сухість в очах і губах — теж сигнал, що час попити.",
]

LONG_EXERCISES = [
    ("Розтяжка спини", [
        "Встаньте, зчепіть руки в замок над головою.",
        "Потягніться вгору на 10 секунд.",
        "Нахиліться вліво, потім управо — по 10 секунд.",
        "Повторіть 3 рази.",
    ]),
    ("Шия та плечі", [
        "Повільно покрутіть головою по 5 разів у кожен бік.",
        "Зведіть лопатки й потримайте 5 секунд — 10 разів.",
        "Потягніть руку через груди іншою рукою — по 15 секунд.",
    ]),
    ("Ноги", [
        "Встаньте й зробіть 10 присідань.",
        "Нахиліться й потягніться до пальців ніг — 15 секунд.",
        "Підніміться на носки 15 разів.",
    ]),
    ("Прогулянка", [
        "Встаньте з-за столу.",
        "Пройдіться кімнатою чи коридором.",
        "Подивіться у вікно вдалину.",
        "Випийте склянку води.",
    ]),
    ("Віджимання від стіни", [
        "Встаньте на відстані витягнутих рук від стіни.",
        "Зробіть 10–15 віджимань.",
        "Покрутіть кистями й розімніть зап'ястя.",
    ]),
    ("Розкриття грудей", [
        "Станьте в дверному отворі, долоні на одвірках.",
        "Подайтеся вперед до легкого натягу в грудях — 20 секунд.",
        "Повторіть 3 рази, глибоко дихаючи.",
    ]),
    ("Повороти корпусу", [
        "Сядьте на край стільця, спина рівна.",
        "Поверніть корпус ліворуч і затримайтеся на 15 секунд.",
        "Те саме праворуч.",
        "Зробіть 3 підходи.",
    ]),
]


# Швидкі вправи для тіла — іноді замість вправ для очей на міні-перерві (рівень 2+)
MINI_ACTIVE = [
    ("10 присідань", "Встаньте й зробіть 10 спокійних присідань. Спина рівна, п'яти на підлозі."),
    ("Підйоми на носки", "Встаньте й 20 разів підніміться на носки, повільно опускаючись."),
    ("Віджимання від столу", "Зробіть 10 віджимань від краю стійкого столу."),
    ("Потягніться", "Встаньте на носки, потягніться руками вгору й затримайтеся на 10 секунд."),
    ("Пройдіться", "Встаньте й пройдіться кімнатою — сидіння теж треба перебивати."),
]

WORKOUT_WARMUP = ("Розминка", "Крокуйте на місці, високо піднімаючи коліна, і робіть кола руками.")
WORKOUT_COOLDOWN = ("Заминка", "Повільно потягніться вгору, потім нахиліться до носків. Дихайте глибоко й спокійно.")

# Вправи для тренування на довгій перерві за рівнем інтенсивності
WORKOUT_EXERCISES = {
    1: [
        ("Кола плечима", "Великі повільні кола плечима: половину часу вперед, половину — назад."),
        ("Нахили в боки", "Руки на поясі, повільно нахиляйтеся вліво й управо."),
        ("Повороти корпусу", "Стоячи, руки перед грудьми, плавно повертайте корпус уліво-вправо."),
        ("Підйоми на носки", "Тримаючись за стіл, піднімайтеся на носки й повільно опускайтеся."),
        ("Ходьба на місці", "Крокуйте на місці в спокійному темпі, розмахуючи руками."),
        ("Розкриття грудей", "Зчепіть руки за спиною, розправте плечі й потягніть руки назад і вниз."),
        ("Котик біля столу", "Руки на край столу, по черзі округлюйте й прогинайте спину."),
        ("Кола тазом", "Руки на поясі, повільні кола тазом в обидва боки."),
    ],
    2: [
        ("Присідання", "Ноги на ширині плечей, сідайте назад, ніби на стілець. Спина рівна."),
        ("Віджимання від столу", "Руки на край стійкого столу, тіло рівне, згинайте лікті."),
        ("Випади на місці", "Крок уперед, обидва коліна під кутом 90°. Чергуйте ноги."),
        ("Стільчик біля стіни", "Спиною до стіни, сповзіть до кута в колінах 90° і тримайте."),
        ("Планка на столі", "Передпліччя на стіл, тіло рівною лінією від голови до п'ят. Тримайте."),
        ("Махи ногою в бік", "Тримаючись за стіл, відводьте пряму ногу в бік. Половину часу — кожною."),
        ("Високі коліна", "Крокуйте на місці, піднімаючи коліна до рівня стегна."),
        ("Зворотні віджимання", "Руки на край стійкого стільця за спиною, згинайте лікті до 90°."),
    ],
    3: [
        ("Джампінг-джек", "Стрибок — ноги ширше, руки над головою; стрибок назад. У швидкому темпі."),
        ("Присідання зі стрибком", "Присід і вибуховий стрибок угору. Приземляйтеся м'яко, на зігнуті ноги."),
        ("Віджимання", "Від підлоги або з колін. Тіло рівне, опускайтеся грудьми до підлоги."),
        ("Біг на місці", "Швидко, коліна до рівня пояса, активно працюйте руками."),
        ("Альпініст", "Упор лежачи, по черзі швидко підтягуйте коліна до грудей."),
        ("Випади з чергуванням", "Глибокі випади вперед, по черзі кожною ногою."),
        ("Планка", "Упор на передпліччя, тіло рівне, живіт підтягнутий. Тримайте."),
        ("Берпі без стрибка", "Присід, руки на підлогу, ноги назад у планку, назад у присід і встати."),
        ("Присідання сумо", "Широко ноги, носки назовні, глибокий присід."),
    ],
}

INTENSITY_NAMES = {1: "легко", 2: "середньо", 3: "енергійно"}
WORK_SEC, REST_SEC, WARMUP_SEC = 40, 15, 30


def fmt_intensity(v):
    return INTENSITY_NAMES[v]


def step(title, text, secs, kind="exercise", phase=""):
    return {"title": title, "text": text, "secs": secs, "kind": kind, "phase": phase}


def build_workout(total, level):
    """Інтервальне тренування рівно на `total` секунд: розминка, робота/відпочинок, заминка."""
    pool = WORKOUT_EXERCISES[level] + (WORKOUT_EXERCISES[level - 1] if level > 1 else [])
    count = max(1, (total - 2 * WARMUP_SEC + REST_SEC) // (WORK_SEC + REST_SEC))
    while count > 1 and total - WARMUP_SEC - count * WORK_SEC - (count - 1) * REST_SEC < 20:
        count -= 1
    picks = []
    while len(picks) < count:
        picks += random.sample(pool, min(len(pool), count - len(picks)))

    steps = [step(*WORKOUT_WARMUP, WARMUP_SEC, "warmup", "РОЗМИНКА")]
    for i, (title, text) in enumerate(picks):
        steps.append(step(title, text, WORK_SEC, "work", f"ВПРАВА {i + 1} / {count}"))
        if i < count - 1:
            steps.append(step("Відпочинок", f"Далі: {picks[i + 1][0]}", REST_SEC, "rest", "ВІДПОЧИНОК"))
    used = sum(s["secs"] for s in steps)
    steps.append(step(*WORKOUT_COOLDOWN, max(total - used, 10), "cooldown", "ЗАМИНКА"))
    return steps


def build_break(kind, cfg):
    """Список кроків перерви. Міні та звичайна довга перерва — один крок."""
    level = cfg["intensity"]
    if kind == "mini":
        pool = MINI_ACTIVE if level >= 2 and random.random() < 0.4 else MINI_EXERCISES
        return [step(*random.choice(pool), cfg["mini_duration_sec"], phase="МІНІ-ПЕРЕРВА")]
    total = cfg["long_duration_min"] * 60
    if cfg["workout_enabled"] and total >= 120:
        return build_workout(total, level)
    title, lines = random.choice(LONG_EXERCISES)
    text = "\n".join(f"{i}.  {line}" for i, line in enumerate(lines, 1))
    return [step(title, text, total, "list", "ДОВГА ПЕРЕРВА")]


# ---------- дані ----------

def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_config():
    cfg = dict(DEFAULTS)
    saved = load_json(CONFIG_PATH, {})
    cfg.update({k: v for k, v in saved.items() if k in DEFAULTS})
    return cfg


def fmt_time(seconds):
    seconds = max(0, int(round(seconds)))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class Stats:
    KEYS = ("mini_done", "long_done", "skipped", "postponed", "water")

    def __init__(self):
        self.data = load_json(STATS_PATH, {})

    def add(self, key):
        rec = self.data.setdefault(dt.date.today().isoformat(), {})
        rec[key] = rec.get(key, 0) + 1
        save_json(STATS_PATH, self.data)

    def day(self, date):
        rec = self.data.get(date.isoformat(), {})
        return {k: rec.get(k, 0) for k in self.KEYS}


# ---------- таймер ----------

class Scheduler:
    """Відлік робочого часу. Скидається лише після перерви або на вимогу —
    неактивність і блокування екрана його не обнуляють."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.breaks_taken = 0
        self.postpones = 0
        self.in_break = False
        self.paused_until = None
        self.warned = False
        self.water_open = False
        self._set_countdown(self.cfg["mini_interval_min"] * 60)
        self.water_remaining = self.cfg["water_interval_min"] * 60

    def _set_countdown(self, seconds):
        self.remaining = self.period = seconds
        self.warned = False

    @property
    def paused(self):
        if self.paused_until and dt.datetime.now() >= self.paused_until:
            self.paused_until = None
        return self.paused_until is not None

    def next_kind(self):
        return "long" if (self.breaks_taken + 1) % max(1, self.cfg["long_every"]) == 0 else "mini"

    def tick(self, seconds):
        events = []
        if self.in_break or self.paused:
            return events
        self.remaining -= seconds
        warn = self.cfg["warn_before_sec"]
        if warn and not self.warned and 0 < self.remaining <= warn:
            self.warned = True
            events.append("warn")
        if self.remaining <= 0:
            self.in_break = True
            events.append("break")
        if self.cfg["water_enabled"] and not self.water_open:
            self.water_remaining -= seconds
            if self.water_remaining <= 0 and not self.in_break:
                self.water_open = True
                events.append("water")
        return events

    def start_break(self):
        self.in_break = True

    def finish_break(self):
        self.in_break = False
        self.breaks_taken += 1
        self.postpones = 0
        self._set_countdown(self.cfg["mini_interval_min"] * 60)

    def can_postpone(self):
        return self.postpones < self.cfg["postpone_limit"]

    def postpone(self):
        self.in_break = False
        self.postpones += 1
        self._set_countdown(self.cfg["postpone_min"] * 60)

    def reset(self):
        self.postpones = 0
        self._set_countdown(self.cfg["mini_interval_min"] * 60)

    def water_answered(self, drank):
        self.water_open = False
        self.water_remaining = self.cfg["water_interval_min"] * 60 if drank else 15 * 60

    def pause(self, minutes):
        if minutes is None:  # до ранку
            tomorrow = dt.date.today() + dt.timedelta(days=1)
            self.paused_until = dt.datetime.combine(tomorrow, dt.time(6, 0))
        else:
            self.paused_until = dt.datetime.now() + dt.timedelta(minutes=minutes)

    def resume(self):
        self.paused_until = None

    def apply_config(self):
        interval = self.cfg["mini_interval_min"] * 60
        if not self.in_break and self.remaining > interval:
            self._set_countdown(interval)
        self.water_remaining = min(self.water_remaining, self.cfg["water_interval_min"] * 60)


# ---------- Windows ----------

def monitors():
    """[(x, y, w, h, work_rect, is_primary)] для всіх моніторів, основний — першим."""
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


def launch_target():
    """(програма, аргументи) для запуску Limber без консолі."""
    if getattr(sys, "frozen", False):
        return sys.executable, ""
    exe = sys.executable
    pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pythonw):
        exe = pythonw
    return exe, f'"{os.path.abspath(__file__)}"'


def run_powershell(script, **env):
    """Скрипт отримує значення через змінні середовища — без проблем з лапками у шляхах."""
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                          env=dict(os.environ, **env), capture_output=True, stdin=subprocess.DEVNULL,
                          creationflags=subprocess.CREATE_NO_WINDOW, timeout=60)


def remove_legacy_autostart():
    """Ранні версії писали автозапуск у реєстр Run і в папку «Автозавантаження»."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            for name in LEGACY_RUN_VALUES:
                try:
                    winreg.DeleteValue(key, name)
                except FileNotFoundError:
                    pass
    except OSError:
        pass
    if os.path.exists(STARTUP_LINK):
        os.remove(STARTUP_LINK)


def get_autostart():
    return subprocess.run(["schtasks", "/query", "/tn", TASK_NAME], capture_output=True,
                          creationflags=subprocess.CREATE_NO_WINDOW).returncode == 0


def set_autostart(enabled):
    """Завдання Планувальника «під час входу» із затримкою — надійніше за реєстр Run."""
    remove_legacy_autostart()
    if not enabled:
        run_powershell("Unregister-ScheduledTask -TaskName $env:L_TASK -Confirm:$false -ErrorAction SilentlyContinue",
                       L_TASK=TASK_NAME)
        return
    target, arguments = launch_target()
    # Встановлений Limber.exe запускається без аргументів, а порожній -Argument PowerShell не приймає
    script = (
        "$a = if ($env:L_ARGS) { New-ScheduledTaskAction -Execute $env:L_EXE -Argument $env:L_ARGS "
        "-WorkingDirectory $env:L_DIR } else { New-ScheduledTaskAction -Execute $env:L_EXE -WorkingDirectory $env:L_DIR }; "
        "$t = New-ScheduledTaskTrigger -AtLogOn -User $env:L_USER; $t.Delay = 'PT20S'; "
        "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
        "-ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew; "
        "$p = New-ScheduledTaskPrincipal -UserId $env:L_USER -LogonType Interactive -RunLevel Limited; "
        "Register-ScheduledTask -TaskName $env:L_TASK -Action $a -Trigger $t -Settings $s -Principal $p "
        "-Description 'Limber: нагадування про перерви' -Force | Out-Null")
    result = run_powershell(script, L_EXE=target, L_ARGS=arguments, L_TASK=TASK_NAME,
                            L_DIR=os.path.dirname(target if getattr(sys, "frozen", False)
                                                  else os.path.abspath(__file__)),
                            L_USER=f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}")
    if result.returncode != 0:
        raise OSError(result.stderr.decode("utf-8", "replace").strip() or "Register-ScheduledTask failed")


SUPERSAMPLE = 4


def rgba(color):
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5)) + (255,)


def smooth_image(width, height, paint, bg=None):
    """Малює у збільшеному масштабі й зменшує — Tk сам згладжування не вміє."""
    s = SUPERSAMPLE
    img = Image.new("RGBA", (width * s, height * s), rgba(bg) if bg else (0, 0, 0, 0))
    paint(ImageDraw.Draw(img), s)
    return img.resize((width, height), Image.LANCZOS)


def draw_progress_ring(d, s, size, pad, thickness, fraction, track, color):
    """Кільце прогресу із заокругленими кінцями дуги (координати — у масштабі s)."""
    box = (pad * s, pad * s, (size - pad) * s, (size - pad) * s)
    d.ellipse(box, outline=track, width=thickness * s)
    fraction = min(max(fraction, 0), 1)
    if fraction <= 0.002:
        return
    end = -90 + 360 * fraction
    d.arc(box, start=-90, end=end, fill=color, width=thickness * s)
    center = size * s / 2
    radius = (size / 2 - pad - thickness / 2) * s
    cap = thickness * s / 2
    for angle in (-90, end):
        x = center + radius * math.cos(math.radians(angle))
        y = center + radius * math.sin(math.radians(angle))
        d.ellipse((x - cap, y - cap, x + cap, y + cap), fill=color)


def make_icon(progress, paused):
    """Кільце, що заповнюється в міру наближення перерви."""
    color = rgba("#96a0a0") if paused else rgba(C["accent"])

    def paint(d, s):
        draw_progress_ring(d, s, 64, 4, 9, 0 if paused else progress, rgba("#3c5a58"), color)
        if paused:
            d.rounded_rectangle((21 * s, 20 * s, 28 * s, 44 * s), radius=2 * s, fill=color)
            d.rounded_rectangle((36 * s, 20 * s, 43 * s, 44 * s), radius=2 * s, fill=color)
        else:
            d.ellipse((24 * s, 24 * s, 40 * s, 40 * s), fill=color)

    return smooth_image(64, 64, paint)


def make_app_icon(size=256):
    """Іконка програми: літера L — фігурка, що сидить і тягнеться до носків."""
    big = size * SUPERSAMPLE
    u = big / 256

    top, bottom = (0x72, 0xd9, 0xcb), (0x1c, 0x5f, 0x5b)
    gradient = Image.new("RGBA", (big, big))
    gd = ImageDraw.Draw(gradient)
    for y in range(big):
        t = y / (big - 1)
        gd.line([(0, y), (big, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,))
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle((10 * u, 10 * u, big - 10 * u, big - 10 * u), radius=58 * u, fill=255)
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    img.paste(gradient, (0, 0), mask)

    d = ImageDraw.Draw(img)

    def stroke(points, width, color):
        pts = [(x * u, y * u) for x, y in points]
        d.line(pts, fill=color, width=int(width * u), joint="curve")
        r = width * u / 2
        for x, y in (pts[0], pts[-1]):
            d.ellipse((x - r, y - r, x + r, y + r), fill=color)

    stroke([(78, 118), (78, 190), (180, 190)], 30, (255, 255, 255, 255))  # тулуб і ноги — літера L
    stroke([(88, 134), (170, 166)], 18, (214, 250, 244, 255))            # руки тягнуться до носків
    d.ellipse((70 * u, 62 * u, 108 * u, 100 * u), fill=(255, 255, 255, 255))  # голова
    return img.resize((size, size), Image.LANCZOS)


def ensure_icon_file():
    """.ico для панелі завдань і ярликів."""
    if not os.path.exists(ICON_PATH):
        os.makedirs(DATA_DIR, exist_ok=True)
        make_app_icon(256).save(ICON_PATH, sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40),
                                                  (48, 48), (64, 64), (128, 128), (256, 256)])
    return ICON_PATH


def migrate_old_data():
    if os.path.isdir(OLD_DATA_DIR) and not os.path.exists(DATA_DIR):
        os.replace(OLD_DATA_DIR, DATA_DIR)
    # Копії, запущені з-під застосунку Claude (пакет MSIX), писали дані в його приватне сховище
    packages = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Packages")
    if os.path.isdir(packages):
        for name in os.listdir(packages):
            cached = os.path.join(packages, name, "LocalCache", "Roaming", "Limber")
            if name.startswith("Claude_") and os.path.isdir(cached):
                os.makedirs(DATA_DIR, exist_ok=True)
                for file in ("config.json", "stats.json"):
                    src, dst = os.path.join(cached, file), os.path.join(DATA_DIR, file)
                    if os.path.exists(src) and not os.path.exists(dst):
                        shutil.copy2(src, dst)


# ---------- застосунок ----------

def check_mark(size, color):
    """Згладжена галочка на прозорому тлі."""
    def paint(d, s):
        width = max(2.0, size * 0.15) * s
        points = [(0.16 * size * s, 0.54 * size * s), (0.40 * size * s, 0.76 * size * s),
                  (0.84 * size * s, 0.26 * size * s)]
        d.line(points, fill=rgba(color), width=int(width), joint="curve")
        r = width / 2
        for x, y in (points[0], points[-1]):
            d.ellipse((x - r, y - r, x + r, y + r), fill=rgba(color))

    return ImageTk.PhotoImage(smooth_image(size, size, paint))


def flat_button(parent, text, command, bg=None, fg=None, size=13, hover=None, image=None):
    bg = bg or C["panel"]
    hover = hover or C["panel_hover"]
    fg = fg or C["text"]
    if image:
        # У Tk padx — це ще й проміжок між текстом і картинкою, тому збираємо кнопку з двох Label
        btn = tk.Frame(parent, bg=bg, padx=22, pady=10, cursor="hand2")
        parts = [tk.Label(btn, text=text, bg=bg, fg=fg, font=("Segoe UI", size), cursor="hand2"),
                 tk.Label(btn, image=image, bg=bg, cursor="hand2")]
        parts[0].pack(side="left")
        parts[1].pack(side="left", padx=(7, 0))
        btn.image = image

        def paint(color):
            for widget in (btn, *parts):
                widget.configure(bg=color)

        for widget in (btn, *parts):
            widget.bind("<Button-1>", lambda e: command())
            widget.bind("<Enter>", lambda e: paint(hover))
            widget.bind("<Leave>", lambda e: paint(bg))
        return btn
    else:
        btn = tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                        activebackground=hover, activeforeground=fg,
                        disabledforeground="#5d7775", relief="flat", bd=0, padx=22, pady=10,
                        font=("Segoe UI", size), cursor="hand2")
    btn.bind("<Enter>", lambda e: btn.configure(bg=hover) if btn["state"] == "normal" else None)
    btn.bind("<Leave>", lambda e: btn.configure(bg=bg))
    return btn


def card(parent, title=None):
    frame = tk.Frame(parent, bg=C["card"], padx=18, pady=14)
    if title:
        tk.Label(frame, text=title.upper(), bg=C["card"], fg=C["accent"],
                 font=("Segoe UI Semibold", 9)).pack(anchor="w", pady=(0, 8))
    return frame


def dark_title_bar(win):
    try:
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        on = ctypes.c_int(1)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (нові та старі збірки Windows 10)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(on), ctypes.sizeof(on)) == 0:
                break
    except (AttributeError, OSError):
        pass


class Slider(tk.Frame):
    """Повзунок: перетягування, клік по доріжці, коліщатко миші."""
    PAD = 11

    def __init__(self, parent, label, lo, hi, step, value, fmt, on_change):
        bg = parent["bg"]
        super().__init__(parent, bg=bg)
        self.lo, self.hi, self.step, self.fmt, self.on_change = lo, hi, step, fmt, on_change
        self.value = self.snap(value)
        head = tk.Frame(self, bg=bg)
        head.pack(fill="x")
        tk.Label(head, text=label, bg=bg, fg=C["muted"], font=("Segoe UI", 10)).pack(side="left")
        self.value_label = tk.Label(head, text=fmt(self.value), bg=bg, fg=C["text"],
                                    font=("Segoe UI Semibold", 11))
        self.value_label.pack(side="right")
        self.canvas = tk.Canvas(self, height=26, bg=bg, highlightthickness=0, cursor="hand2")
        self.canvas.pack(fill="x", pady=(2, 0))
        self.canvas.bind("<Configure>", lambda e: self.draw())
        self.canvas.bind("<Button-1>", self.drag)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", lambda e: self.on_change(self.value))
        self.canvas.bind("<MouseWheel>", self.wheel)

    def snap(self, v):
        v = self.lo + round((v - self.lo) / self.step) * self.step
        return min(max(v, self.lo), self.hi)

    def drag(self, event):
        width = max(self.canvas.winfo_width() - 2 * self.PAD, 1)
        self.set(self.snap(self.lo + (event.x - self.PAD) / width * (self.hi - self.lo)))

    def wheel(self, event):
        self.set(self.snap(self.value + (self.step if event.delta > 0 else -self.step)))
        self.on_change(self.value)

    def set(self, value):
        if value != self.value:
            self.value = value
            self.value_label.configure(text=self.fmt(value))
            self.draw()

    def draw(self):
        width = self.canvas.winfo_width()
        if width < 2 * self.PAD:
            return
        x0, x1 = self.PAD, width - self.PAD
        xv = x0 + (x1 - x0) * (self.value - self.lo) / (self.hi - self.lo)

        def paint(d, s):
            y, r = 13 * s, 3 * s
            d.rounded_rectangle((x0 * s - r, y - r, x1 * s + r, y + r), radius=r, fill=rgba(C["track"]))
            d.rounded_rectangle((x0 * s - r, y - r, xv * s + r, y + r), radius=r, fill=rgba(C["accent"]))
            d.ellipse(((xv - 10) * s, y - 10 * s, (xv + 10) * s, y + 10 * s), fill=rgba(C["accent"]))
            d.ellipse(((xv - 7) * s, y - 7 * s, (xv + 7) * s, y + 7 * s), fill=rgba(C["text"]))

        self.photo = ImageTk.PhotoImage(smooth_image(width, 26, paint, self["bg"]))
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)


class Toggle(tk.Frame):
    def __init__(self, parent, text, value, on_change):
        bg = parent["bg"]
        super().__init__(parent, bg=bg, cursor="hand2")
        self.value, self.on_change = value, on_change
        label = tk.Label(self, text=text, bg=bg, fg=C["text"], font=("Segoe UI", 11), cursor="hand2")
        label.pack(side="left")
        self.canvas = tk.Canvas(self, width=46, height=24, bg=bg, highlightthickness=0, cursor="hand2")
        self.canvas.pack(side="right")
        for widget in (self, label, self.canvas):
            widget.bind("<Button-1>", self.toggle)
        self.draw()

    def draw(self):
        color = rgba(C["accent"] if self.value else C["track"])
        knob = rgba("#ffffff" if self.value else C["muted"])
        x = 34 if self.value else 12

        def paint(d, s):
            d.rounded_rectangle((1 * s, 1 * s, 45 * s, 23 * s), radius=11 * s, fill=color)
            d.ellipse(((x - 8) * s, 4 * s, (x + 8) * s, 20 * s), fill=knob)

        self.photo = ImageTk.PhotoImage(smooth_image(46, 24, paint, self["bg"]))
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)

    def toggle(self, _event=None):
        self.value = not self.value
        self.draw()
        self.on_change(self.value)


class App:
    def __init__(self):
        self.cfg = load_config()
        self.stats = Stats()
        self.sched = Scheduler(self.cfg)
        self.queue = queue.Queue()

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(APP_NAME)
        try:
            self.root.iconbitmap(default=ensure_icon_file())  # для всіх вікон і панелі завдань
        except (OSError, tk.TclError):
            pass

        self.main_win = None
        self.break_wins = []
        self.break_state = None
        self.water_win = None
        self.water_demo = False
        self.last_tick = time.monotonic()
        self.icon_key = None
        self.tooltip = None
        self.show_event = None

        self.icon = pystray.Icon("Limber", make_icon(0, False), APP_NAME, self.build_menu())
        threading.Thread(target=self.icon.run, daemon=True).start()

        self.root.after(1000, self.loop)
        self.root.after(100, self.process_queue)

    # --- трей ---

    def build_menu(self):
        def post(action):
            return lambda icon, item: self.queue.put(action)

        item = pystray.MenuItem
        return pystray.Menu(
            item("Відкрити", post("open"), default=True),
            item("Перерва зараз", post("break_now")),
            item("Скинути таймер", post("reset")),
            pystray.Menu.SEPARATOR,
            item("Пауза", pystray.Menu(
                item("30 хвилин", post(("pause", 30))),
                item("1 година", post(("pause", 60))),
                item("2 години", post(("pause", 120))),
                item("До ранку", post(("pause", None))),
            )),
            item("Продовжити", post("resume"), visible=lambda i: self.sched.paused_until is not None),
            pystray.Menu.SEPARATOR,
            item("Вихід", post("quit")),
        )

    def process_queue(self):
        while True:
            try:
                action = self.queue.get_nowait()
            except queue.Empty:
                break
            self.handle(action)
        if self.show_event and ctypes.windll.kernel32.WaitForSingleObject(self.show_event, 0) == 0:
            self.open_main()
        self.root.after(100, self.process_queue)

    def handle(self, action):
        if action == "open":
            self.open_main()
        elif action == "break_now":
            self.trigger_break()
        elif action == "reset":
            self.sched.reset()
        elif action == "resume":
            self.sched.resume()
            self.icon.update_menu()
        elif isinstance(action, tuple) and action[0] == "pause":
            if self.break_state:
                self.close_break_windows()
                self.sched.finish_break()
            self.sched.pause(action[1])
            self.icon.update_menu()
        elif action == "quit":
            self.icon.stop()
            self.root.destroy()

    def notify(self, message):
        try:
            self.icon.notify(message, APP_NAME)
        except Exception:
            pass

    def update_tray(self):
        s = self.sched
        if s.paused:
            title = f"{APP_NAME}: пауза до {s.paused_until:%H:%M}"
            key = ("paused",)
        elif s.in_break:
            title = f"{APP_NAME}: перерва"
            key = ("break",)
        else:
            kind = "довга" if s.next_kind() == "long" else "міні"
            title = f"{APP_NAME}: перерва ({kind}) через {fmt_time(s.remaining)}"
            if self.cfg["water_enabled"] and not s.water_open:
                title += f"\nВода через {fmt_time(s.water_remaining)}"
            key = ("run", int(24 * (1 - s.remaining / max(s.period, 1))))
        if title != self.tooltip:
            self.tooltip = title
            self.icon.title = title
        if key != self.icon_key:
            self.icon_key = key
            progress = 1 if key[0] == "break" else (key[1] / 24 if key[0] == "run" else 0)
            self.icon.icon = make_icon(progress, key[0] == "paused")

    # --- головний цикл ---

    def loop(self):
        now = time.monotonic()
        # Не більше 5 с за крок: час сну комп'ютера не зараховується як робота.
        delta = min(now - self.last_tick, 5.0)
        self.last_tick = now
        was_paused = self.sched.paused_until is not None
        for event in self.sched.tick(delta):
            if event == "warn":
                kind = "Довга перерва" if self.sched.next_kind() == "long" else "Міні-перерва"
                self.notify(f"{kind} через {int(self.sched.remaining)} с")
            elif event == "break":
                self.show_break(self.sched.next_kind())
            elif event == "water":
                self.show_water()
        if was_paused and self.sched.paused_until is None:
            self.icon.update_menu()
        self.update_tray()
        self.refresh_main()
        self.root.after(1000, self.loop)

    def beep(self):
        if self.cfg["sound"]:
            winsound.MessageBeep(winsound.MB_ICONASTERISK)

    # --- перерва ---

    def trigger_break(self):
        if self.break_state:
            return
        self.sched.start_break()
        self.show_break(self.sched.next_kind())

    def show_demo_break(self, kind):
        """Перегляд вікна перерви з поточними налаштуваннями — без впливу на таймер і статистику."""
        if self.break_state and not self.break_state["demo"]:
            return
        self.show_break(kind, demo=True)

    def show_break(self, kind, demo=False):
        self.close_break_windows()
        steps = build_break(kind, self.cfg)
        multi = len(steps) > 1
        self.break_state = {"kind": kind, "steps": steps, "index": 0, "left": steps[0]["secs"],
                            "after": None, "widgets": None, "demo": demo}
        self.beep()

        screens = monitors() or [(0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight(), None, True)]
        for x, y, w, h, _work, primary in screens:
            win = tk.Toplevel(self.root, bg=C["bg"])
            win.overrideredirect(True)
            win.geometry(f"{w}x{h}+{x}+{y}")
            win.attributes("-topmost", True)
            win.protocol("WM_DELETE_WINDOW", lambda: None)
            self.break_wins.append(win)
            if demo:
                win.bind("<Escape>", lambda e: self.end_break("skip"))
                tk.Label(win, text="ДЕМО-ПЕРЕГЛЯД  ·  Esc — закрити", bg=C["bg"], fg=C["dim"],
                         font=("Segoe UI Semibold", 11)).place(x=28, y=22)
            if not primary:
                tk.Label(win, text="Перерва", bg=C["bg"], fg=C["muted"],
                         font=("Segoe UI Light", 40)).place(relx=0.5, rely=0.5, anchor="center")
                continue

            frame = tk.Frame(win, bg=C["bg"])
            frame.place(relx=0.5, rely=0.5, anchor="center")
            wrap = int(min(w * 0.6, 900))
            widgets = {
                "phase": tk.Label(frame, bg=C["bg"], fg=C["accent"], font=("Segoe UI Semibold", 14)),
                "title": tk.Label(frame, bg=C["bg"], fg=C["text"], font=("Segoe UI Semibold", 36)),
                "text": tk.Label(frame, bg=C["bg"], fg=C["text"], font=("Segoe UI", 18), wraplength=wrap),
                "timer": tk.Label(frame, bg=C["bg"], font=("Segoe UI Light", 72)),
                "info": tk.Label(frame, bg=C["bg"], fg=C["muted"], font=("Segoe UI", 12)),
            }
            widgets["phase"].pack()
            widgets["title"].pack(pady=(8, 24))
            widgets["text"].pack()
            widgets["timer"].pack(pady=(30, 4))
            widgets["info"].pack(pady=(0, 26))
            self.break_state["widgets"] = widgets

            buttons = tk.Frame(frame, bg=C["bg"])
            buttons.pack()
            left = self.cfg["postpone_limit"] - self.sched.postpones
            postpone = flat_button(buttons, f"Відкласти на {self.cfg['postpone_min']} хв (ще {max(left, 0)})",
                                   lambda: self.end_break("postpone"))
            if not self.sched.can_postpone():
                postpone.configure(state="disabled")
            postpone.pack(side="left", padx=8)
            if multi:
                flat_button(buttons, "Наступна вправа →", self.next_break_step).pack(side="left", padx=8)
            flat_button(buttons, "Пропустити", lambda: self.end_break("skip")).pack(side="left", padx=8)
            if multi:
                tk.Label(frame, text="Слухайте своє тіло: якщо вправа викликає біль — пропустіть її.",
                         bg=C["bg"], fg=C["dim"], font=("Segoe UI", 11)).pack(pady=(28, 0))
            win.focus_force()

        self.update_break_view()
        self.break_state["after"] = self.root.after(1000, self.break_tick)

    def update_break_view(self):
        state = self.break_state
        widgets = state and state["widgets"]
        if not widgets:
            return
        steps, index = state["steps"], state["index"]
        current = steps[index]
        widgets["phase"].configure(text=current["phase"])
        widgets["title"].configure(text=current["title"])
        widgets["text"].configure(text=current["text"], justify="left" if current["kind"] == "list" else "center")
        widgets["timer"].configure(text=fmt_time(state["left"]),
                                   fg=C["muted"] if current["kind"] == "rest" else C["accent"])
        if len(steps) > 1:
            total_left = state["left"] + sum(s["secs"] for s in steps[index + 1:])
            info = f"Крок {index + 1} з {len(steps)}  ·  усього залишилось {fmt_time(total_left)}"
            if current["kind"] == "work" and index + 1 < len(steps):
                upcoming = next((s for s in steps[index + 1:] if s["kind"] != "rest"), None)
                if upcoming:
                    info += f"  ·  далі: {upcoming['title']}"
            widgets["info"].configure(text=info)

    def next_break_step(self):
        state = self.break_state
        if not state:
            return
        state["index"] += 1
        if state["index"] >= len(state["steps"]):
            self.end_break("done")
            return
        state["left"] = state["steps"][state["index"]]["secs"]
        if self.cfg["sound"]:
            winsound.MessageBeep(winsound.MB_OK)
        self.update_break_view()

    def break_tick(self):
        state = self.break_state
        if not state:
            return
        state["left"] -= 1
        if state["left"] <= 0:
            self.next_break_step()
        else:
            self.update_break_view()
        if self.break_state is state:
            state["after"] = self.root.after(1000, self.break_tick)

    def close_break_windows(self):
        if self.break_state and self.break_state["after"]:
            self.root.after_cancel(self.break_state["after"])
        for win in self.break_wins:
            win.destroy()
        self.break_wins = []
        self.break_state = None

    def end_break(self, result):
        kind = self.break_state["kind"] if self.break_state else "mini"
        demo = bool(self.break_state and self.break_state["demo"])
        self.close_break_windows()
        if demo:
            if self.main_win:
                self.main_win.focus_force()
            return
        if result == "done":
            self.stats.add(f"{kind}_done")
            self.sched.finish_break()
            self.beep()
        elif result == "skip":
            self.stats.add("skipped")
            self.sched.finish_break()
        elif result == "postpone":
            self.stats.add("postponed")
            self.sched.postpone()

    # --- вода ---

    def show_water(self, demo=False):
        if self.water_win:
            if not self.water_demo or demo:
                return
            self.water_win.destroy()  # справжнє нагадування важливіше за демо
            self.water_win = None
        self.water_demo = demo
        screens = monitors()
        if screens:
            _l, _t, right, bottom = screens[0][4]
        else:
            right, bottom = self.root.winfo_screenwidth(), self.root.winfo_screenheight() - 48
        width = 420
        win = tk.Toplevel(self.root, bg=C["panel"], highlightthickness=2, highlightbackground=C["water"])
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        self.water_win = win

        drunk = self.stats.day(dt.date.today())["water"]
        goal = self.cfg["water_goal"]
        done = drunk >= goal
        head = tk.Frame(win, bg=C["panel"])
        head.pack(fill="x", padx=20, pady=(16, 0))
        tk.Label(head, text="Час випити води", bg=C["panel"], fg=C["water"],
                 font=("Segoe UI Semibold", 16)).pack(side="left")
        tk.Label(head, text=f"{min(drunk + 1, goal) if not done else drunk} з {goal}", bg=C["panel"],
                 fg=C["muted"], font=("Segoe UI", 11)).pack(side="right")
        if demo:
            tk.Label(head, text="демо", bg=C["panel"], fg=C["dim"],
                     font=("Segoe UI Semibold", 9)).pack(side="right", padx=8)
            win.bind("<Escape>", lambda e: self.end_water(False))
        dots = tk.Frame(win, bg=C["panel"])
        dots.pack(anchor="w", padx=18, pady=(2, 8))
        for i in range(goal):
            tk.Label(dots, text="●" if i < drunk else "○", bg=C["panel"],
                     fg=C["water"] if i < drunk else C["dim"], font=("Segoe UI", 12)).pack(side="left", padx=1)
        if done:
            tip = "Денну мету виконано! Пити можна й далі — особливо в спеку чи після руху."
        else:
            tip = random.choice(WATER_TIPS)
        tk.Label(win, text=tip, bg=C["panel"], fg=C["text"], font=("Segoe UI", 11),
                 wraplength=width - 44, justify="left").pack(anchor="w", padx=20)
        buttons = tk.Frame(win, bg=C["panel"])
        buttons.pack(anchor="e", padx=16, pady=14)
        flat_button(buttons, "Пізніше", lambda: self.end_water(False), bg=C["bg"], size=11).pack(side="left", padx=4)
        flat_button(buttons, "Випив", lambda: self.end_water(True), bg=C["water"], fg="#0b2233",
                    size=11, hover="#6bb8ea", image=check_mark(16, "#0b2233")).pack(side="left", padx=4)
        win.update_idletasks()
        height = win.winfo_reqheight()
        win.geometry(f"{width}x{height}+{right - width - 16}+{bottom - height - 16}")
        win.after(120_000, lambda: self.end_water(False) if self.water_win is win else None)
        if demo:
            win.focus_force()
        self.beep()

    def end_water(self, drank):
        if self.water_win:
            self.water_win.destroy()
            self.water_win = None
        if self.water_demo:
            self.water_demo = False
            return
        if drank:
            self.stats.add("water")
        self.sched.water_answered(drank)

    # --- головне вікно ---

    def open_main(self):
        if self.main_win:
            self.main_win.deiconify()
            self.main_win.lift()
            self.main_win.focus_force()
            return
        win = tk.Toplevel(self.root, bg=C["bg"])
        win.title(f"{APP_NAME} {__version__}")
        win.geometry("800x745")
        win.resizable(False, False)
        win.protocol("WM_DELETE_WINDOW", self.close_main)
        self.window_icon = ImageTk.PhotoImage(make_app_icon(64))
        win.iconphoto(False, self.window_icon)
        self.main_win = win
        self.w = {}
        win.update()
        dark_title_bar(win)

        header = tk.Frame(win, bg=C["bg"])
        header.pack(fill="x", padx=24, pady=(18, 10))
        self.header_icon = ImageTk.PhotoImage(make_app_icon(40))
        tk.Label(header, image=self.header_icon, bg=C["bg"]).pack(side="left", padx=(0, 10))
        title = tk.Frame(header, bg=C["bg"])
        title.pack(side="left")
        tk.Label(title, text=APP_NAME, bg=C["bg"], fg=C["text"],
                 font=("Segoe UI Semibold", 18)).pack(anchor="w")
        tk.Label(title, text=APP_TAGLINE, bg=C["bg"], fg=C["muted"],
                 font=("Segoe UI", 9)).pack(anchor="w")
        self.w["saved"] = tk.Label(header, text="", bg=C["bg"], fg=C["accent"], font=("Segoe UI", 10))
        self.w["saved"].pack(side="left", padx=14, pady=(6, 0))
        tabs = tk.Frame(header, bg=C["panel"])
        tabs.pack(side="right")

        body = tk.Frame(win, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=24, pady=(4, 20))
        self.pages, self.tab_buttons = {}, {}
        for key, text, builder in (("status", "Стан", self.build_status_page),
                                   ("stats", "Статистика", self.build_stats_page),
                                   ("settings", "Налаштування", self.build_settings_page)):
            self.pages[key] = builder(body)
            btn = tk.Label(tabs, text=text, font=("Segoe UI", 11), padx=16, pady=6, cursor="hand2")
            btn.pack(side="left", padx=2, pady=2)
            btn.bind("<Button-1>", lambda e, k=key: self.show_page(k))
            self.tab_buttons[key] = btn
        self.show_page("status")

    def close_main(self):
        self.main_win.destroy()
        self.main_win = None
        self.w = {}

    def show_page(self, key):
        for page in self.pages.values():
            page.pack_forget()
        self.pages[key].pack(fill="both", expand=True)
        for k, btn in self.tab_buttons.items():
            active = k == key
            btn.configure(bg=C["accent"] if active else C["panel"], fg=C["on_accent"] if active else C["muted"])
        if key == "stats":
            self.main_win.update_idletasks()
            self.draw_stats()
        self.refresh_main()

    def flash_saved(self):
        label = self.w.get("saved")
        if not label:
            return
        if not getattr(self, "saved_check", None):
            self.saved_check = check_mark(14, C["accent"])
        label.configure(text="Збережено ", image=self.saved_check, compound="right")
        if getattr(self, "_saved_after", None):
            self.root.after_cancel(self._saved_after)
        self._saved_after = self.root.after(
            1500, lambda: self.w.get("saved") and self.w["saved"].configure(text="", image=""))

    # стан

    def build_status_page(self, parent):
        page = tk.Frame(parent, bg=C["bg"])
        left = card(page)
        left.pack(side="left", fill="y", padx=(0, 14))
        self.w["ring"] = tk.Canvas(left, width=270, height=270, bg=C["card"], highlightthickness=0)
        self.w["ring"].pack(pady=(4, 12))
        flat_button(left, "Перерва зараз", self.trigger_break, bg=C["accent"], fg=C["on_accent"],
                    size=11).pack(fill="x", pady=3)
        self.w["pause_btn"] = flat_button(left, "Пауза 30 хв", self.toggle_pause, size=11)
        self.w["pause_btn"].pack(fill="x", pady=3)
        flat_button(left, "Скинути таймер", self.sched.reset, size=11).pack(fill="x", pady=3)

        right = tk.Frame(page, bg=C["bg"])
        right.pack(side="left", fill="both", expand=True)

        water = card(right, "Вода")
        water.pack(fill="x")
        self.w["water"] = tk.Label(water, bg=C["card"], fg=C["water"], font=("Segoe UI Light", 28))
        self.w["water"].pack(anchor="w")
        self.w["water_sub"] = tk.Label(water, bg=C["card"], fg=C["muted"], font=("Segoe UI", 10))
        self.w["water_sub"].pack(anchor="w")

        today = card(right, "Сьогодні")
        today.pack(fill="both", expand=True, pady=(14, 0))
        grid = tk.Frame(today, bg=C["card"])
        grid.pack(fill="both", expand=True)
        metrics = (("mini_done", "міні-перерв", C["accent"]), ("long_done", "довгих перерв", C["accent"]),
                   ("skipped", "пропущено", C["muted"]), ("water", "склянок води", C["water"]))
        for i, (key, caption, color) in enumerate(metrics):
            cell = tk.Frame(grid, bg=C["card"])
            cell.grid(row=i // 2, column=i % 2, sticky="nw", padx=(0, 30), pady=8)
            self.w[f"today_{key}"] = tk.Label(cell, bg=C["card"], fg=color, font=("Segoe UI Light", 34))
            self.w[f"today_{key}"].pack(anchor="w")
            tk.Label(cell, text=caption, bg=C["card"], fg=C["muted"], font=("Segoe UI", 10)).pack(anchor="w")
        return page

    def toggle_pause(self):
        self.handle("resume" if self.sched.paused else ("pause", 30))

    def draw_ring(self):
        c, s = self.w["ring"], self.sched
        c.delete("all")
        size = 270
        fraction = 1 - s.remaining / max(s.period, 1)
        color = rgba(C["dim"] if s.paused else C["accent"])
        key = (round(fraction, 3), s.paused)
        if key != getattr(self, "_ring_key", None):
            self._ring_key = key
            self.ring_photo = ImageTk.PhotoImage(smooth_image(
                size, size, lambda d, k: draw_progress_ring(d, k, size, 18, 14, fraction, rgba(C["track"]), color),
                C["card"]))
        c.create_image(0, 0, anchor="nw", image=self.ring_photo)
        if s.paused:
            subtitle = f"пауза до {s.paused_until:%H:%M}"
        elif s.in_break:
            subtitle = "зараз перерва"
        else:
            subtitle = "до довгої перерви" if s.next_kind() == "long" else "до міні-перерви"
        c.create_text(size / 2, size / 2 - 10, text=fmt_time(s.remaining), fill=C["text"],
                      font=("Segoe UI Light", 40))
        c.create_text(size / 2, size / 2 + 38, text=subtitle, fill=C["muted"], font=("Segoe UI", 11))

    # статистика

    def build_stats_page(self, parent):
        page = tk.Frame(parent, bg=C["bg"])
        summary = tk.Frame(page, bg=C["bg"])
        summary.pack(fill="x")
        for i, (key, caption, color) in enumerate((("sum_done", "перерв за 7 днів", C["accent"]),
                                                   ("sum_skipped", "пропущено", C["muted"]),
                                                   ("sum_water", "склянок води", C["water"]))):
            box = card(summary)
            box.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 7, 0 if i == 2 else 7))
            summary.columnconfigure(i, weight=1, uniform="sum")
            self.w[key] = tk.Label(box, bg=C["card"], fg=color, font=("Segoe UI Light", 30))
            self.w[key].pack(anchor="w")
            tk.Label(box, text=caption, bg=C["card"], fg=C["muted"], font=("Segoe UI", 10)).pack(anchor="w")

        chart = card(page, "Останні 7 днів")
        chart.pack(fill="both", expand=True, pady=(14, 0))
        self.w["chart"] = tk.Canvas(chart, bg=C["card"], highlightthickness=0, height=290)
        self.w["chart"].pack(fill="both", expand=True)
        legend = tk.Frame(chart, bg=C["card"])
        legend.pack(anchor="w", pady=(6, 0))
        for text, color in (("міні", C["accent"]), ("довгі", C["accent_dark"]),
                            ("пропущені", C["dim"]), ("вода", C["water"])):
            tk.Label(legend, text="●", bg=C["card"], fg=color, font=("Segoe UI", 12)).pack(side="left")
            tk.Label(legend, text=text, bg=C["card"], fg=C["muted"],
                     font=("Segoe UI", 10)).pack(side="left", padx=(2, 14))
        return page

    def draw_stats(self):
        c = self.w.get("chart")
        if not c:
            return
        today = dt.date.today()
        days = [today - dt.timedelta(days=i) for i in range(6, -1, -1)]
        records = [self.stats.day(d) for d in days]
        self.w["sum_done"].configure(text=sum(r["mini_done"] + r["long_done"] for r in records))
        self.w["sum_skipped"].configure(text=sum(r["skipped"] for r in records))
        self.w["sum_water"].configure(text=sum(r["water"] for r in records))

        c.delete("all")
        width, height = max(c.winfo_width(), 600), max(c.winfo_height(), 250)
        top, bottom = 24, height - 48
        peak = max([r["mini_done"] + r["long_done"] + r["skipped"] for r in records] + [4])
        for i in range(5):
            y = bottom - (bottom - top) * i / 4
            c.create_line(0, y, width, y, fill=C["track"] if i == 0 else "#20403f")
        slot = width / 7
        bar = min(44, slot * 0.5)
        for i, (day, rec) in enumerate(zip(days, records)):
            cx = slot * i + slot / 2
            y = bottom
            for key, color in (("mini_done", C["accent"]), ("long_done", C["accent_dark"]), ("skipped", C["dim"])):
                h = (bottom - top) * rec[key] / peak
                if h:
                    c.create_rectangle(cx - bar / 2, y - h, cx + bar / 2, y, fill=color, outline="")
                    y -= h
            total = rec["mini_done"] + rec["long_done"] + rec["skipped"]
            if total:
                c.create_text(cx, y - 10, text=total, fill=C["text"], font=("Segoe UI Semibold", 10))
            label = "сьогодні" if day == today else ["пн", "вт", "ср", "чт", "пт", "сб", "нд"][day.weekday()]
            c.create_text(cx, bottom + 14, text=label, fill=C["text"] if day == today else C["muted"],
                          font=("Segoe UI", 10))
            c.create_text(cx, bottom + 33, text=f"● {rec['water']}" if rec["water"] else "",
                          fill=C["water"], font=("Segoe UI", 9))

    # налаштування

    def build_settings_page(self, parent):
        page = tk.Frame(parent, bg=C["bg"])
        left = tk.Frame(page, bg=C["bg"])
        right = tk.Frame(page, bg=C["bg"])
        left.pack(side="left", fill="both", expand=True, padx=(0, 7))
        right.pack(side="left", fill="both", expand=True, padx=(7, 0))

        def group(column, title, keys):
            box = card(column, title)
            box.pack(fill="x", pady=(0, 14))
            for key in keys:
                self.add_slider(box, key)

        group(left, "Перерви", ("mini_interval_min", "mini_duration_sec", "intensity"))
        long_box = card(left, "Довгі перерви")
        long_box.pack(fill="x", pady=(0, 14))
        self.add_slider(long_box, "long_every")
        self.add_slider(long_box, "long_duration_min")
        Toggle(long_box, "Інтервальне тренування", self.cfg["workout_enabled"],
               lambda v: self.set_setting("workout_enabled", v)).pack(fill="x", pady=(2, 0))
        other = card(left, "Інше")
        other.pack(fill="x")
        Toggle(other, "Звук на початку й наприкінці", self.cfg["sound"],
               lambda v: self.set_setting("sound", v)).pack(fill="x", pady=4)
        Toggle(other, "Запускати разом з Windows", get_autostart(),
               self.set_autostart_setting).pack(fill="x", pady=4)

        group(right, "Відкладання", ("postpone_min", "postpone_limit", "warn_before_sec"))
        water = card(right, "Вода")
        water.pack(fill="x")
        Toggle(water, "Нагадувати пити воду", self.cfg["water_enabled"],
               lambda v: self.set_setting("water_enabled", v)).pack(fill="x", pady=(0, 8))
        self.add_slider(water, "water_interval_min")
        self.add_slider(water, "water_goal")

        preview = card(right, "Перегляд")
        preview.pack(fill="x", pady=(14, 0))
        tk.Label(preview, text="Спробуйте з поточними налаштуваннями:", bg=C["card"],
                 fg=C["muted"], font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 8))
        row = tk.Frame(preview, bg=C["card"])
        row.pack(fill="x")
        for i, (text, action) in enumerate((("Міні", lambda: self.show_demo_break("mini")),
                                            ("Довга", lambda: self.show_demo_break("long")),
                                            ("Вода", lambda: self.show_water(demo=True)))):
            btn = flat_button(row, text, action, size=10)
            btn.configure(padx=6, pady=7)
            btn.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 4, 0 if i == 2 else 4))
            row.columnconfigure(i, weight=1, uniform="preview")
        return page

    def add_slider(self, parent, key):
        label, lo, hi, step, fmt = SLIDERS[key]
        Slider(parent, label, lo, hi, step, self.cfg[key], fmt,
               lambda v, k=key: self.set_setting(k, v)).pack(fill="x", pady=(0, 10))

    def set_setting(self, key, value):
        if self.cfg.get(key) == value:
            return
        self.cfg[key] = value
        save_json(CONFIG_PATH, self.cfg)
        self.sched.apply_config()
        self.flash_saved()

    def set_autostart_setting(self, enabled):
        try:
            set_autostart(enabled)
            self.flash_saved()
        except OSError as e:
            messagebox.showerror(APP_NAME, f"Не вдалося змінити автозапуск: {e}", parent=self.main_win)

    def refresh_main(self):
        if not self.main_win or "ring" not in self.w:
            return
        s = self.sched
        self.draw_ring()
        self.w["pause_btn"].configure(text="Продовжити" if s.paused else "Пауза 30 хв")
        today = self.stats.day(dt.date.today())
        progress = f"сьогодні {today['water']} з {self.cfg['water_goal']}"
        if not self.cfg["water_enabled"]:
            self.w["water"].configure(text="—")
            self.w["water_sub"].configure(text="нагадування вимкнено")
        elif s.water_open:
            self.w["water"].configure(text="Час пити!")
            self.w["water_sub"].configure(text=progress)
        else:
            self.w["water"].configure(text=fmt_time(s.water_remaining))
            self.w["water_sub"].configure(text=f"до наступної склянки  ·  {progress}")
        for key in ("mini_done", "long_done", "skipped", "water"):
            self.w[f"today_{key}"].configure(text=today[key])


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    try:
        # Власна іконка в панелі завдань замість іконки Python
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except (AttributeError, OSError):
        pass
    # Команди для інсталятора: увімкнути/вимкнути автозапуск і вийти
    for arg in sys.argv[1:]:
        if arg.startswith("--set-autostart="):
            set_autostart(arg.split("=", 1)[1] == "on")
            return

    kernel32 = ctypes.windll.kernel32
    handle = ctypes.c_void_p
    for fn, args in ((kernel32.CreateMutexW, [handle, ctypes.c_bool, ctypes.c_wchar_p]),
                     (kernel32.CreateEventW, [handle, ctypes.c_bool, ctypes.c_bool, ctypes.c_wchar_p]),
                     (kernel32.OpenEventW, [ctypes.c_uint32, ctypes.c_bool, ctypes.c_wchar_p])):
        fn.argtypes, fn.restype = args, handle
    kernel32.SetEvent.argtypes = kernel32.CloseHandle.argtypes = [handle]
    kernel32.WaitForSingleObject.argtypes = [handle, ctypes.c_uint32]
    _mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS: просимо запущений екземпляр показати вікно
        event = kernel32.OpenEventW(0x0002, False, SHOW_EVENT_NAME)  # EVENT_MODIFY_STATE
        if event:
            kernel32.SetEvent(event)
            kernel32.CloseHandle(event)
        return

    migrate_old_data()
    app = App()
    app.show_event = kernel32.CreateEventW(None, False, False, SHOW_EVENT_NAME)
    if "--test-break" in sys.argv:
        app.root.after(1500, app.trigger_break)
    if "--test-water" in sys.argv:
        app.root.after(1500, lambda: (setattr(app.sched, "water_open", True), app.show_water()))
    if "--open" in sys.argv:
        app.root.after(500, app.open_main)
    app.root.mainloop()


def setup_logging():
    """pythonw не має консолі, тож помилки інакше зникають безслідно — пишемо їх у limber.log."""
    if getattr(sys.stderr, "name", "") == LOG_PATH:
        log = sys.stderr  # вже відкрито на початку файлу
    else:
        os.makedirs(DATA_DIR, exist_ok=True)
        log = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
    threading.excepthook = lambda a: traceback.print_exception(a.exc_type, a.exc_value, a.exc_traceback, file=log)
    print(f"--- {dt.datetime.now():%Y-%m-%d %H:%M:%S} старт {sys.argv[1:]}", file=log)
    return log


if __name__ == "__main__":
    log = setup_logging()
    try:
        main()
    except Exception:
        # Без raise: збірка без консолі інакше показує вікно з помилкою й чекає на клік —
        # під час тихого встановлення натиснути його нікому
        traceback.print_exc(file=log)
        sys.exit(1)
