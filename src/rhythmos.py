"""Rhythmos — нагадування про перерви з вправами, водою та статистикою (Windows, macOS)."""
import datetime as dt
import json
import math
import os
import queue
import random
import sys
import threading
import time
import tkinter as tk
import traceback
import webbrowser
from tkinter import messagebox

import system

if sys.stderr is None:  # збірка без консолі: помилки імпорту інакше зникли б безслідно
    os.makedirs(system.data_dir(), exist_ok=True)
    sys.stderr = sys.stdout = open(os.path.join(system.data_dir(), "rhythmos.log"), "a", encoding="utf-8", buffering=1)

import pystray
from PIL import Image, ImageDraw, ImageTk

import exercises
import i18n
import updates
from i18n import (content, fmt_clock, fmt_glasses, fmt_intensity, fmt_minutes, fmt_seconds, fmt_times, fmt_volume,
                  fmt_warn, t)
from system import font

__version__ = "2.2.0"

APP_NAME = "Rhythmos"
DATA_DIR = system.data_dir()
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
STATS_PATH = os.path.join(DATA_DIR, "stats.json")
ICON_PATH = os.path.join(DATA_DIR, "rhythmos.ico")
LOG_PATH = os.path.join(DATA_DIR, "rhythmos.log")

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
    "water_profile": "custom",  # "female" / "male" — мета й інтервал за рекомендацією; "custom" — вручну
    "breakfast_enabled": False,  # сніданок і вечеря часто не за комп'ютером — за замовчуванням вимкнені
    "breakfast_at": 8 * 60,      # хвилини від півночі
    "lunch_enabled": True,
    "lunch_at": 13 * 60,
    "dinner_enabled": False,
    "dinner_at": 18 * 60 + 30,
    "meal_pause_min": 45,    # на скільки «Йду їсти» ставить перерви й воду на паузу
    "pause_min": 30,         # тривалість паузи з кнопки «Пауза» (вкладка «Стан», попередження про перерву)
    "intensity": 2,
    "workout_enabled": True,
    "sound": True,
    "language": "",  # "" — за мовою системи; інсталятор записує мову, вибрану під час встановлення
    "check_updates": True,
    "sound_name": "",        # системний звук сповіщення; "" — перший доступний
    "group_buttons": True,   # кнопки груп м'язів на екрані перерви; вимкнено — вправи випадкові
    "notified_version": "",  # про яку нову версію вже показали сповіщення
}
MAX_GLASSES = 30          # верхня межа ручного введення води за день
MAX_GLASSES_SHOWN = 24    # більше — не малюємо (три ряди)
GLASSES_PER_ROW = 8       # далі склянки переносяться в наступний ряд
MAIN_MIN_WIDTH = 1080     # головне вікно: ширше й нижче — налаштування в три колонки
UPDATE_CHECK_DELAY_MS = 30_000
UPDATE_CHECK_INTERVAL_MS = 24 * 60 * 60 * 1000

C = {
    # Весняна зелень під іконку-листок; темне тло — з легким зеленим відтінком, вода — синя
    "bg": "#14261c",
    "card": "#1a3124",
    "panel": "#1f3a2b",
    "panel_hover": "#2a4d39",
    "track": "#2c4d38",
    "grid": "#1f3a2b",
    "accent": "#8fd477",
    "accent_dark": "#4fae5f",
    "on_accent": "#10301a",
    "text": "#eef7ec",
    "muted": "#a6c4a8",
    "dim": "#5f7b65",
    "water": "#4aa3df",
    "on_water": "#0b2233",
}


# Повзунки налаштувань: ключ → (мінімум, максимум, крок, формат); підпис — t("s_<ключ>")
SLIDERS = {
    "mini_interval_min": (5, 120, 5, fmt_minutes),
    "mini_duration_sec": (10, 300, 5, fmt_seconds),
    "long_every": (1, 10, 1, str),
    "long_duration_min": (1, 30, 1, fmt_minutes),
    "postpone_min": (1, 30, 1, fmt_minutes),
    "postpone_limit": (0, 5, 1, fmt_times),
    "warn_before_sec": (0, 120, 5, fmt_warn),
    "water_interval_min": (15, 240, 5, fmt_minutes),
    "water_goal": (4, 16, 1, fmt_glasses),
    "intensity": (1, 3, 1, fmt_intensity),
    "pause_min": (15, 240, 15, fmt_minutes),
    "breakfast_at": (6 * 60, 11 * 60, 15, fmt_clock),
    "lunch_at": (11 * 60, 16 * 60, 15, fmt_clock),
    "dinner_at": (16 * 60, 22 * 60, 15, fmt_clock),
    "meal_pause_min": (15, 90, 15, fmt_minutes),
}

MEALS = ("breakfast", "lunch", "dinner")
MEAL_WINDOW_MIN = 60   # комп'ютер прокинувся пізніше, ніж на годину після часу їжі, — нагадування вже ні до чого
MEAL_SNOOZE_MIN = 15   # «Через 15 хв» і «Ще 15 хв»

# Рекомендована денна мета води, склянок по 250 мл. EFSA: загалом 2,0 л на день жінкам і 2,5 л чоловікам,
# близько 20% з цього дає їжа — тож пити ≈1,6 і ≈2,0 л (жінкам округлено вгору до 7 склянок)
WATER_PROFILES = {"female": 7, "male": 8}
WORKDAY_MIN = 8 * 60  # нагадування розподіляють денну мету на 8 годин за комп'ютером


def water_interval_for(goal):
    """Найбільший інтервал (кратний кроку повзунка), з яким `goal` склянок встигаємо за робочий день."""
    lo, hi, step, _fmt = SLIDERS["water_interval_min"]
    return min(max(WORKDAY_MIN // goal // step * step, lo), hi)


def water_plan(profile):
    """(мета, інтервал у хв) для профілю або None, якщо налаштування ручні."""
    goal = WATER_PROFILES.get(profile)
    return (goal, water_interval_for(goal)) if goal else None


def apply_water_profile(cfg):
    """Профіль «жінка»/«чоловік» перекриває мету й інтервал рекомендованими значеннями."""
    if cfg["water_profile"] not in WATER_PROFILES:
        cfg["water_profile"] = "custom"
    plan = water_plan(cfg["water_profile"])
    if plan:
        cfg["water_goal"], cfg["water_interval_min"] = plan

WORK_SEC, REST_SEC, WARMUP_SEC = 40, 15, 30


def step(title, text, secs, kind="exercise", phase=""):
    return {"title": title, "text": text, "secs": secs, "kind": kind, "phase": phase}


def pick_many(pool, count):
    """`count` вправ без повторів, поки вистачає пулу."""
    picks = []
    while len(picks) < count:
        picks += random.sample(pool, min(len(pool), count - len(picks)))
    return picks


def link_rests(steps):
    """Підписи «Далі: …» у кроках відпочинку — за наступною вправою."""
    for i, s in enumerate(steps):
        if s["kind"] == "rest":
            upcoming = next((n for n in steps[i + 1:] if n["kind"] == "work"), None)
            if upcoming:
                s["text"] = t("rest_next", title=upcoming["title"])


def build_workout(total, level, group=None):
    """Інтервальне тренування рівно на `total` секунд: розминка, робота/відпочинок, заминка."""
    count = max(1, (total - 2 * WARMUP_SEC + REST_SEC) // (WORK_SEC + REST_SEC))
    while count > 1 and total - WARMUP_SEC - count * WORK_SEC - (count - 1) * REST_SEC < 20:
        count -= 1
    picks = pick_many(exercises.workout_pool(level, group), count)

    steps = [step(*content("warmup"), WARMUP_SEC, "warmup", t("phase_warmup"))]
    for i, (title, text, _group) in enumerate(picks):
        steps.append(step(title, text, WORK_SEC, "work", t("phase_work", n=i + 1, count=count)))
        if i < count - 1:
            steps.append(step(t("rest_title"), "", REST_SEC, "rest", t("phase_rest")))
    used = sum(s["secs"] for s in steps)
    steps.append(step(*content("cooldown"), max(total - used, 10), "cooldown", t("phase_cooldown")))
    link_rests(steps)
    return steps


def regroup_workout(steps, start, level, group):
    """Замінює вправи тренування, починаючи з кроку `start`, на вправи вибраної групи."""
    targets = [s for s in steps[start:] if s["kind"] == "work"]
    for s, (title, text, _group) in zip(targets, pick_many(exercises.workout_pool(level, group), len(targets))):
        s["title"], s["text"] = title, text
    link_rests(steps)


def single_break_step(kind, cfg, group=None, avoid=None):
    """Один крок міні-перерви або довгої перерви без тренування."""
    if kind == "mini":
        pool = exercises.mini_pool(cfg["intensity"], group)
    else:
        pool = exercises.long_pool(group)
    fresh = [e for e in pool if e[0] != avoid] or pool  # повторний вибір групи дає іншу вправу
    title, body, _group = random.choice(fresh)
    if kind == "mini":
        return step(title, body, cfg["mini_duration_sec"], phase=t("phase_mini"))
    text = "\n".join(f"{i}.  {line}" for i, line in enumerate(body, 1))
    return step(title, text, cfg["long_duration_min"] * 60, "list", t("phase_long"))


def build_break(kind, cfg, group=None):
    """Список кроків перерви. Міні та звичайна довга перерва — один крок."""
    total = cfg["long_duration_min"] * 60
    if kind == "long" and cfg["workout_enabled"] and total >= 120:
        return build_workout(total, cfg["intensity"], group)
    return [single_break_step(kind, cfg, group)]


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
    apply_water_profile(cfg)
    i18n.set_language(cfg["language"] or system.system_language())
    return cfg


def set_language_setting(code):
    """--set-language: інсталятор зберігає мову, вибрану під час встановлення."""
    cfg = load_json(CONFIG_PATH, {})
    cfg["language"] = code if code in i18n.LANGUAGES else ""
    save_json(CONFIG_PATH, cfg)


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

    def set(self, key, value):
        """Ручне виправлення лічильника за сьогодні (наприклад, кількості склянок води)."""
        rec = self.data.setdefault(dt.date.today().isoformat(), {})
        rec[key] = max(0, int(value))
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
        self.pause_water = False  # пауза «до ранку» зупиняє й нагадування про воду
        self.warned = False
        self.water_open = False
        self._set_countdown(self.cfg["mini_interval_min"] * 60)
        self.water_remaining = self.cfg["water_interval_min"] * 60
        self.meal_open = None       # про яку їжу зараз висить нагадування
        self.meals_shown = set()    # (дата, їжа), про які вже нагадали сьогодні
        self.meal_snoozed = {}      # їжа → коли нагадати знову («Через 15 хв»)
        self.eating = None          # «Йду їсти»: яка їжа; перерви й вода заморожені, поки не натиснуть «Продовжити»
        self.eating_until = None
        self.meal_over_asked = False

    def _set_countdown(self, seconds):
        self.remaining = self.period = seconds
        self.warned = False

    @property
    def paused(self):
        if self.paused_until and dt.datetime.now() >= self.paused_until:
            self.paused_until = None
            self.pause_water = False
        return self.paused_until is not None

    def next_kind(self):
        return "long" if (self.breaks_taken + 1) % max(1, self.cfg["long_every"]) == 0 else "mini"

    def tick(self, seconds, now=None):
        now = now or dt.datetime.now()
        events = []
        if self.eating:
            # Пауза на їжу не закінчується сама: після неї питаємо, чи продовжувати
            if not self.meal_over_asked and now >= self.eating_until:
                self.meal_over_asked = True
                events.append("meal_over")
            return events
        if self.in_break:
            return events
        paused = self.paused
        if not paused:
            self.remaining -= seconds
            warn = self.cfg["warn_before_sec"]
            if warn and not self.warned and 0 < self.remaining <= warn:
                self.warned = True
                events.append("warn")
            if self.remaining <= 0:
                self.in_break = True
                events.append("break")
        # Пауза зупиняє лише перерви; вода — тільки під час паузи «до ранку» (робочий день скінчився)
        water_paused = paused and self.pause_water
        if self.cfg["water_enabled"] and not self.water_open and not water_paused:
            self.water_remaining -= seconds
            if self.water_remaining <= 0 and not self.in_break:
                self.water_open = True
                events.append("water")
        meal = self.due_meal(now)
        if meal:
            self.meal_open = meal
            self.meals_shown.add((now.date(), meal))
            events.append("meal")
        return events

    def due_meal(self, now):
        """Їжа, про яку час нагадати: її година настала, але минуло не більше MEAL_WINDOW_MIN."""
        if self.meal_open or self.in_break or (self.paused and self.pause_water):
            return None
        minutes = now.hour * 60 + now.minute
        for meal in MEALS:
            if not self.cfg[f"{meal}_enabled"]:
                continue
            snoozed = self.meal_snoozed.get(meal)
            if snoozed:
                if now >= snoozed:
                    del self.meal_snoozed[meal]
                    return meal
                continue
            at = self.cfg[f"{meal}_at"]
            if (now.date(), meal) not in self.meals_shown and at <= minutes < at + MEAL_WINDOW_MIN:
                return meal
        return None

    def meal_answered(self, answer, now=None):
        """answer: "eat" — пауза на їжу, "snooze" — нагадати через 15 хв, "skip" — не нагадувати."""
        now = now or dt.datetime.now()
        meal, self.meal_open = self.meal_open, None
        if not meal:
            return
        if answer == "snooze":
            self.meal_snoozed[meal] = now + dt.timedelta(minutes=MEAL_SNOOZE_MIN)
        elif answer == "eat":
            self.paused_until = None  # їжа важливіша за звичайну паузу
            self.pause_water = False
            self.eating = meal
            self.eating_until = now + dt.timedelta(minutes=self.cfg["meal_pause_min"])
            self.meal_over_asked = False

    def extend_meal(self, now=None):
        """«Ще 15 хв» після паузи на їжу."""
        if self.eating:
            self.eating_until = (now or dt.datetime.now()) + dt.timedelta(minutes=MEAL_SNOOZE_MIN)
            self.meal_over_asked = False

    def finish_meal(self):
        """«Продовжити»: їжа вже була довгою перервою, тож обидва таймери — з початку."""
        self.eating = self.eating_until = None
        self.meal_over_asked = False
        self.postpones = 0
        self._set_countdown(self.cfg["mini_interval_min"] * 60)
        self.water_remaining = self.cfg["water_interval_min"] * 60

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
        self.eating = self.eating_until = None
        if minutes is None:  # до ранку
            tomorrow = dt.date.today() + dt.timedelta(days=1)
            self.paused_until = dt.datetime.combine(tomorrow, dt.time(6, 0))
        else:
            self.paused_until = dt.datetime.now() + dt.timedelta(minutes=minutes)
        self.pause_water = minutes is None

    def resume(self):
        self.paused_until = None
        self.pause_water = False

    def apply_config(self):
        interval = self.cfg["mini_interval_min"] * 60
        if not self.in_break and self.remaining > interval:
            self._set_countdown(interval)
        self.water_remaining = min(self.water_remaining, self.cfg["water_interval_min"] * 60)


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
    color = rgba(C["dim"]) if paused else rgba(C["accent"])

    def paint(d, s):
        draw_progress_ring(d, s, 64, 4, 9, 0 if paused else progress, rgba(C["track"]), color)
        if paused:
            d.rounded_rectangle((21 * s, 20 * s, 28 * s, 44 * s), radius=2 * s, fill=color)
            d.rounded_rectangle((36 * s, 20 * s, 43 * s, 44 * s), radius=2 * s, fill=color)
        else:
            d.ellipse((24 * s, 24 * s, 40 * s, 40 * s), fill=color)

    return smooth_image(64, 64, paint)


def _vertical_gradient(width, height, top, bottom):
    image = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        frac = y / max(height - 1, 1)
        draw.line([(0, y), (width, y)], fill=tuple(int(a + (b - a) * frac) for a, b in zip(top, bottom)) + (255,))
    return image


class _Leaf:
    """Геометрія листка вздовж осі base→tip: контур, хвиляста центральна жилка, точки на ній."""

    def __init__(self, base, tip, width):
        self.base, self.tip, self.width = base, tip, width
        dx, dy = tip[0] - base[0], tip[1] - base[1]
        self.length = math.hypot(dx, dy)
        self.ux, self.uy = dx / self.length, dy / self.length
        self.nx, self.ny = -self.uy, self.ux

    def half_width(self, t):
        return self.width * (math.sin(math.pi * t) ** 0.95) * (1 - 0.12 * t)

    def at(self, t, offset=0.0):
        return (self.base[0] + self.ux * self.length * t + self.nx * offset,
                self.base[1] + self.uy * self.length * t + self.ny * offset)

    def outline(self, steps=90):
        upper = [self.at(i / steps, self.half_width(i / steps)) for i in range(steps + 1)]
        lower = [self.at(i / steps, -self.half_width(i / steps)) for i in range(steps + 1)]
        return upper + lower[::-1]

    def wave(self, t, amplitude, start=0.06, end=0.86, waves=1.6):
        s = (t - start) / (end - start)
        return amplitude * math.sin(2 * math.pi * waves * s) * math.sin(math.pi * s)

    def vein(self, amplitude, start=0.06, end=0.86, steps=60):
        return [self.at(t, self.wave(t, amplitude, start, end))
                for t in (start + (end - start) * i / steps for i in range(steps + 1))]


def make_app_icon(size=256):
    """Іконка Rhythmos: листок (здоров'я) з хвилястою жилкою (ритм) на весняному градієнті.
    Дрібні деталі — бокові жилки, тінь, відблиск — лише у великих розмірах: у 16–32 px вони б розмилися."""
    from PIL import ImageFilter
    detailed = size >= 48
    big = size * SUPERSAMPLE
    u = big / 256

    background = _vertical_gradient(big, big, (0xb6, 0xec, 0x88), (0x3a, 0xa8, 0x64))
    if detailed:  # м'який відблиск угорі ліворуч
        glow = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        ImageDraw.Draw(glow).ellipse((-60 * u, -90 * u, 150 * u, 90 * u), fill=(255, 255, 255, 42))
        background.alpha_composite(glow.filter(ImageFilter.GaussianBlur(28 * u)))
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle((10 * u, 10 * u, big - 10 * u, big - 10 * u), radius=58 * u, fill=255)
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    img.paste(background, (0, 0), mask)

    leaf = _Leaf((76 * u, 184 * u), (198 * u, 62 * u), 58 * u)
    outline = leaf.outline()
    if detailed:  # тінь під листком
        shadow = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).polygon([(x + 5 * u, y + 9 * u) for x, y in outline], fill=(18, 88, 48, 120))
        img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(9 * u)))

    leaf_mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(leaf_mask).polygon(outline, fill=255)
    img.paste(_vertical_gradient(big, big, (0xff, 0xff, 0xff), (0xdf, 0xf4, 0xd2)), (0, 0), leaf_mask)

    d = ImageDraw.Draw(img)
    white = (255, 255, 255, 255)
    # черешок — плавно вигнутий
    stem = [leaf.at(0.02), (leaf.base[0] - 10 * u, leaf.base[1] + 14 * u), (leaf.base[0] - 22 * u, leaf.base[1] + 22 * u)]
    stem_width = 10 * u if detailed else 13 * u
    d.line(stem, fill=white, width=int(stem_width), joint="curve")
    r = stem_width / 2
    d.ellipse((stem[-1][0] - r, stem[-1][1] - r, stem[-1][0] + r, stem[-1][1] + r), fill=white)

    vein_color = (0x5f, 0xbd, 0x67, 255)
    amplitude = 9 * u
    if detailed:  # бокові жилки від хвилястої центральної до країв, трохи вигнуті до кінчика
        side = (0xb0, 0xe0, 0x9f, 255)
        for pos in (0.26, 0.46, 0.64):
            start = leaf.at(pos, leaf.wave(pos, amplitude))
            for sign in (1, -1):
                reach = leaf.half_width(pos + 0.15) * 0.68
                points = [start, leaf.at(pos + 0.05, sign * reach * 0.42), leaf.at(pos + 0.11, sign * reach * 0.78),
                          leaf.at(pos + 0.16, sign * reach)]
                d.line(points, fill=side, width=int(2.6 * u), joint="curve")
    d.line(leaf.vein(amplitude), fill=vein_color, width=int((7 if detailed else 11) * u), joint="curve")
    return img.resize((size, size), Image.LANCZOS)


def ensure_icon_file():
    """.ico для панелі завдань і ярликів."""
    if not os.path.exists(ICON_PATH):
        os.makedirs(DATA_DIR, exist_ok=True)
        make_app_icon(256).save(ICON_PATH, sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40),
                                                  (48, 48), (64, 64), (128, 128), (256, 256)])
    return ICON_PATH


# ---------- застосунок ----------

_glass_cache = {}


def blend(color, other, amount):
    """Змішування двох кольорів #rrggbb: amount = 0 → color, 1 → other."""
    a = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(other[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * amount) for x, y in zip(a, b))


def glass_picture(width, height, filled, bg):
    """Абстрактна склянка з рідиною: хвиляста поверхня й відблиск на гребені.
    Випита — синя вода й синій контур; ще не випита — сіра рідина й сірий контур."""
    if filled:
        edge, liquid, shine = lighten(C["water"], 0.35), C["water"], lighten(C["water"], 0.6)
    else:
        edge, liquid, shine = C["dim"], blend(C["dim"], bg, 0.55), blend(C["dim"], bg, 0.15)

    def paint(d, s):
        w, h = width * s, height * s
        stroke = max(1.5, width * 0.09) * s
        top, bottom = 0.1 * h, h - stroke / 2 - 0.5 * s
        left_top, right_top = stroke / 2 + 0.5 * s, w - stroke / 2 - 0.5 * s
        left_bottom, right_bottom = 0.2 * w, 0.8 * w

        def wall(y, x_top, x_bottom):
            return x_top + (x_bottom - x_top) * (y - top) / (bottom - top)

        # Поверхня рідини — синусоїда трохи більш ніж на півтора періоди
        level = top + (bottom - top) * 0.3
        amplitude = h * 0.045
        inset = stroke * 0.55
        x0, x1 = wall(level, left_top, left_bottom) + inset, wall(level, right_top, right_bottom) - inset
        steps = 28
        surface = [(x0 + (x1 - x0) * i / steps,
                    level + amplitude * math.sin(2 * math.pi * 1.6 * i / steps + 0.4)) for i in range(steps + 1)]
        d.polygon(surface + [(right_bottom - inset, bottom - inset), (left_bottom + inset, bottom - inset)],
                  fill=rgba(liquid))
        d.line(surface, fill=rgba(shine), width=max(1, int(stroke * 0.7)), joint="curve")

        d.line([(left_top, top), (left_bottom, bottom), (right_bottom, bottom), (right_top, top)],
               fill=rgba(edge), width=int(stroke), joint="curve")
        r = stroke / 2
        for x in (left_top, right_top):  # заокруглені верхні краї
            d.ellipse((x - r, top - r, x + r, top + r), fill=rgba(edge))

    return smooth_image(width, height, paint, bg)


def glass_image(width, height, filled, bg):
    key = (width, height, filled, bg)
    if key not in _glass_cache:
        _glass_cache[key] = ImageTk.PhotoImage(glass_picture(width, height, filled, bg))
    return _glass_cache[key]


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


def lighten(color, amount=0.14):
    """Колір, світліший на amount — для стану наведення будь-якої кнопки.
    (Раніше всім кнопкам задавався той самий темний колір наведення, і на бірюзовій
    «Перерва зараз» темний текст ставав нерозбірливим.)"""
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(round(c + (255 - c) * amount) for c in (r, g, b))


def flat_button(parent, text, command, bg=None, fg=None, size=13, hover=None, image=None):
    bg = bg or C["panel"]
    hover = hover or lighten(bg)
    fg = fg or C["text"]
    if image:
        # У Tk padx — це ще й проміжок між текстом і картинкою, тому збираємо кнопку з двох Label
        btn = tk.Frame(parent, bg=bg, padx=22, pady=10, cursor="hand2")
        parts = [tk.Label(btn, text=text, bg=bg, fg=fg, font=font(size), cursor="hand2"),
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
    # Label, а не tk.Button: на macOS кнопка Tk завжди системна біла й ігнорує кольори
    btn = tk.Label(parent, text=text, bg=bg, fg=fg, disabledforeground=C["dim"],
                   padx=22, pady=10, font=font(size), cursor="hand2")
    btn.bind("<Button-1>", lambda e: command() if btn["state"] == "normal" else None)
    btn.bind("<Enter>", lambda e: btn.configure(bg=hover) if btn["state"] == "normal" else None)
    btn.bind("<Leave>", lambda e: btn.configure(bg=bg))
    return btn


def card(parent, title=None):
    frame = tk.Frame(parent, bg=C["card"], padx=18, pady=14)
    if title:
        tk.Label(frame, text=title.upper(), bg=C["card"], fg=C["accent"],
                 font=font(9, "semibold")).pack(anchor="w", pady=(0, 8))
    return frame


class Slider(tk.Frame):
    """Повзунок: перетягування, клік по доріжці, коліщатко миші."""
    PAD = 11

    def __init__(self, parent, label, lo, hi, step, value, fmt, on_change):
        bg = parent["bg"]
        super().__init__(parent, bg=bg)
        self.lo, self.hi, self.step, self.fmt, self.on_change = lo, hi, step, fmt, on_change
        self.value = self.snap(value)
        self.enabled = True
        head = tk.Frame(self, bg=bg)
        head.pack(fill="x")
        tk.Label(head, text=label, bg=bg, fg=C["muted"], font=font(10)).pack(side="left")
        self.value_label = tk.Label(head, text=fmt(self.value), bg=bg, fg=C["text"],
                                    font=font(11, "semibold"))
        self.value_label.pack(side="right")
        # Явна мала ширина: інакше Canvas просить типові ~380 px і роздуває колонки налаштувань
        self.canvas = tk.Canvas(self, width=160, height=26, bg=bg, highlightthickness=0, cursor="hand2")
        self.canvas.pack(fill="x", pady=(2, 0))
        self.canvas.bind("<Configure>", lambda e: self.draw())
        self.canvas.bind("<Button-1>", self.drag)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", lambda e: self.on_change(self.value) if self.enabled else None)
        self.canvas.bind("<MouseWheel>", self.wheel)

    def snap(self, v):
        v = self.lo + round((v - self.lo) / self.step) * self.step
        return min(max(v, self.lo), self.hi)

    def drag(self, event):
        if not self.enabled:
            return
        width = max(self.canvas.winfo_width() - 2 * self.PAD, 1)
        self.set(self.snap(self.lo + (event.x - self.PAD) / width * (self.hi - self.lo)))

    def wheel(self, event):
        if not self.enabled:
            return
        self.set(self.snap(self.value + (self.step if event.delta > 0 else -self.step)))
        self.on_change(self.value)

    def set_enabled(self, enabled):
        """Заблокований повзунок лише показує значення (наприклад, розраховане за профілем води)."""
        if enabled != self.enabled:
            self.enabled = enabled
            self.canvas.configure(cursor="hand2" if enabled else "arrow")
            self.value_label.configure(fg=C["text"] if enabled else C["muted"])
            self.draw()

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
        fill = rgba(C["accent"] if self.enabled else C["dim"])
        knob = rgba(C["text"] if self.enabled else C["muted"])

        def paint(d, s):
            y, r = 13 * s, 3 * s
            d.rounded_rectangle((x0 * s - r, y - r, x1 * s + r, y + r), radius=r, fill=rgba(C["track"]))
            d.rounded_rectangle((x0 * s - r, y - r, xv * s + r, y + r), radius=r, fill=fill)
            d.ellipse(((xv - 10) * s, y - 10 * s, (xv + 10) * s, y + 10 * s), fill=fill)
            d.ellipse(((xv - 7) * s, y - 7 * s, (xv + 7) * s, y + 7 * s), fill=knob)

        self.photo = ImageTk.PhotoImage(smooth_image(width, 26, paint, self["bg"]))
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)


class Toggle(tk.Frame):
    def __init__(self, parent, text, value, on_change):
        bg = parent["bg"]
        super().__init__(parent, bg=bg, cursor="hand2")
        self.value, self.on_change = value, on_change
        label = tk.Label(self, text=text, bg=bg, fg=C["text"], font=font(11), cursor="hand2")
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
        system.init_tk(self.root)
        if system.IS_WINDOWS:
            try:
                self.root.iconbitmap(default=ensure_icon_file())  # для всіх вікон і панелі завдань
            except (OSError, tk.TclError):
                pass

        self.main_win = None
        self.w = {}  # віджети головного вікна; порожній, поки вікно не відкрите
        self.break_wins = []
        self.break_state = None
        self.water_win = None
        self.water_demo = False
        self.last_tick = time.monotonic()
        self.icon_key = None
        self.tooltip = None
        self.instance = None  # system.SingleInstance — щоб друга копія могла попросити показати вікно
        self.update_info = None  # (версія, адреса релізу), якщо на GitHub є новіша версія

        self.icon = system.make_tray_icon(pystray, "Rhythmos", make_icon(0, False), APP_NAME, self.build_menu())
        system.start_tray(self.icon, self.root)
        system.on_reopen(self.root, self.open_main)

        self.root.after(1000, self.loop)
        self.root.after(100, self.process_queue)
        self.root.after(UPDATE_CHECK_DELAY_MS, self.check_updates)

    # --- оновлення ---

    def check_updates(self):
        """Раз на добу питає GitHub про останній реліз; мережа — у фоновому потоці."""
        if self.cfg["check_updates"]:
            threading.Thread(target=lambda: self.queue.put(("update", updates.fetch_latest())), daemon=True).start()
        self.root.after(UPDATE_CHECK_INTERVAL_MS, self.check_updates)

    def on_update_result(self, result, install_now=False):
        if not result or not updates.is_newer(result[0], current_version()):
            return
        print(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} доступне оновлення {result[0]}", file=sys.stderr)
        self.update_info = result
        self.icon.menu = self.build_menu()
        self.icon.update_menu()
        if install_now:
            self.start_update()
        elif self.cfg["notified_version"] != result[0]:
            self.show_toast(t("update_toast_title", version=result[0]), t("update_toast_text"),
                            [(t("update_now"), self.start_update, True), (t("later"), lambda: None, False)],
                            timeout_ms=60_000)
            self.cfg["notified_version"] = result[0]
            save_json(CONFIG_PATH, self.cfg)
        self.refresh_main()

    def open_update(self):
        webbrowser.open(self.update_info[1] if self.update_info else updates.LATEST_PAGE)

    def start_update(self):
        """Кнопка «Оновити»: завантажити, перевірити й встановити нову версію самостійно.
        Якщо це неможливо (запуск із коду, немає файлу для цієї системи) — відкрити сторінку релізу."""
        if getattr(self, "updating", False) or not self.update_info:
            return
        asset = updates.pick_asset(self.update_info[2])
        if not updates.can_self_update() or not asset:
            self.open_update()
            return
        self.updating = True
        version = self.update_info[0]
        self.show_toast(t("updating_title", version=version), t("updating_progress", percent=0),
                        timeout_ms=30 * 60_000)

        def work():
            try:
                path = updates.download(asset, progress=lambda p: self.queue.put(("update_progress", p)))
                self.queue.put(("update_ready", path))
            except Exception as error:
                traceback.print_exc()
                self.queue.put(("update_failed", str(error)))

        threading.Thread(target=work, daemon=True).start()

    def on_update_event(self, kind, value):
        if kind == "update_progress":
            if getattr(self, "toast_text", None):
                self.toast_text.configure(text=t("updating_progress", percent=value))
        elif kind == "update_ready":
            print(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} встановлюю оновлення з {value}", file=sys.stderr)
            if getattr(self, "toast_text", None):
                self.toast_text.configure(text=t("updating_install"))
                self.root.update()
            updates.install(value, autostart=system.get_autostart(), language=i18n.get_language())
            self.handle("quit")  # інсталятор (Windows) чи скрипт (macOS) запустить нову версію
        elif kind == "update_failed":
            self.updating = False
            self.show_toast(t("update_failed_title"), t("update_failed_text"),
                            [(t("download"), self.open_update, True), (t("later"), lambda: None, False)],
                            timeout_ms=60_000)

    # --- трей ---

    def build_menu(self):
        def post(action):
            return lambda icon, item: self.queue.put(action)

        item = pystray.MenuItem
        return pystray.Menu(
            item(lambda i: t("update_menu", version=self.update_info[0]) if self.update_info else "",
                 post("start_update"), visible=lambda i: self.update_info is not None),
            item(t("open"), post("open"), default=True),
            item(t("break_now"), post("break_now")),
            item(t("reset"), post("reset")),
            pystray.Menu.SEPARATOR,
            item(t("pause"), pystray.Menu(
                item(t("pause_30"), post(("pause", 30))),
                item(t("pause_60"), post(("pause", 60))),
                item(t("pause_120"), post(("pause", 120))),
                item(t("pause_morning"), post(("pause", None))),
            )),
            item(t("resume"), post("resume"),
                 visible=lambda i: self.sched.paused_until is not None or bool(self.sched.eating)),
            pystray.Menu.SEPARATOR,
            item(t("quit"), post("quit")),
        )

    def process_queue(self):
        while True:
            try:
                action = self.queue.get_nowait()
            except queue.Empty:
                break
            self.handle(action)
        if self.instance and self.instance.show_requested():
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
            if self.sched.eating:
                if getattr(self, "toast_kind", None) == "meal":
                    self.close_toast(dismissed=False)
                self.sched.finish_meal()
            self.sched.resume()
            self.icon.update_menu()
        elif isinstance(action, tuple) and action[0] == "pause":
            if self.break_state:
                self.close_break_windows()
                self.sched.finish_break()
            self.sched.pause(action[1])
            self.icon.update_menu()
        elif action == "start_update":
            self.start_update()
        elif isinstance(action, tuple) and action[0] in ("update_progress", "update_ready", "update_failed"):
            self.on_update_event(*action)
        elif isinstance(action, tuple) and action[0] == "update_now":
            self.on_update_result(action[1], install_now=True)
        elif isinstance(action, tuple) and action[0] == "update":
            self.on_update_result(action[1])
        elif action == "quit":
            if system.IS_MAC:
                self.icon.visible = False  # stop() зупинив би спільний з Tk цикл NSApplication
            else:
                self.icon.stop()
            self.root.destroy()


    def update_tray(self):
        s = self.sched
        if s.eating:
            title = f"{APP_NAME}: " + t(f"meal_until_{s.eating}", time=f"{s.eating_until:%H:%M}")
            key = ("paused",)
        elif s.paused:
            title = t("tip_paused", app=APP_NAME, time=f"{s.paused_until:%H:%M}")
            key = ("paused",)
        elif s.in_break:
            title = t("tip_break", app=APP_NAME)
            key = ("break",)
        else:
            title = t(f"tip_next_{s.next_kind()}", app=APP_NAME, time=fmt_time(s.remaining))
            if self.cfg["water_enabled"] and not s.water_open:
                title += "\n" + t("tip_water", time=fmt_time(s.water_remaining))
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
                self.show_break_warning()
            elif event == "break":
                self.show_break(self.sched.next_kind())
            elif event == "water":
                self.show_water()
            elif event == "meal":
                self.show_meal(self.sched.meal_open)
            elif event == "meal_over":
                self.show_meal_over()
        if was_paused and self.sched.paused_until is None:
            self.icon.update_menu()
        self.update_break_warning()
        self.update_tray()
        self.refresh_main()
        self.root.after(1000, self.loop)

    def beep(self):
        if self.cfg["sound"]:
            system.beep("info", self.sound_name())

    # --- попередження перед перервою ---

    def show_break_warning(self):
        """Віконце «Скоро перерва» з живим відліком. Тримається до самого початку перерви;
        «Відкласти» переносить її (з тим самим лімітом, що й на екрані перерви), «Ок» лише ховає віконце."""
        kind = self.sched.next_kind()
        if kind == "long" and self.cfg["workout_enabled"] and self.cfg["long_duration_min"] >= 2:
            title = t("warn_title_workout")
        else:
            title = t(f"warn_title_{kind}")
        pause = self.cfg["pause_min"]
        actions = [(t("pause_btn", time=fmt_minutes(pause)), lambda: self.handle(("pause", pause)), False)]
        if self.sched.can_postpone():
            left = self.cfg["postpone_limit"] - self.sched.postpones
            actions.append((t("postpone_btn", min=self.cfg["postpone_min"], left=left), self.postpone_from_warning, False))
        actions.append((t("ok"), lambda: None, True))
        self.show_toast(title, t("warn_countdown", time=fmt_time(self.sched.remaining)), actions,
                        timeout_ms=int(self.sched.remaining * 1000) + 15_000, kind="warning")

    def update_break_warning(self):
        """Щосекунди: оновлює відлік або прибирає віконце, якщо перерва почалась чи програма на паузі."""
        if getattr(self, "toast_kind", None) != "warning":
            return
        s = self.sched
        if s.in_break or s.paused or s.remaining <= 0:
            self.close_toast()
        elif self.toast_text:
            self.toast_text.configure(text=t("warn_countdown", time=fmt_time(s.remaining)))

    def postpone_from_warning(self):
        if self.sched.in_break or not self.sched.can_postpone():
            return
        self.stats.add("postponed")
        self.sched.postpone()

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
        if getattr(self, "toast_kind", None) == "warning" and not demo:
            self.close_toast()  # перерва почалась — попередження більше не потрібне
        self.close_break_windows()
        steps = build_break(kind, self.cfg)
        multi = len(steps) > 1
        self.break_state = {"kind": kind, "steps": steps, "index": 0, "left": steps[0]["secs"],
                            "after": None, "widgets": None, "demo": demo, "group": None}
        self.beep()

        system.activate_app()
        screens = system.monitors() or [(0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight(), None, True)]
        for x, y, w, h, _work, primary in screens:
            win = tk.Toplevel(self.root, bg=C["bg"])
            win.overrideredirect(True)
            win.geometry(f"{w}x{h}+{x}+{y}")
            win.attributes("-topmost", True)
            win.protocol("WM_DELETE_WINDOW", lambda: None)
            self.break_wins.append(win)
            if demo:
                win.bind("<Escape>", lambda e: self.end_break("skip"))
                tk.Label(win, text=t("demo_banner"), bg=C["bg"], fg=C["dim"],
                         font=font(11, "semibold")).place(x=28, y=22)
            if not primary:
                tk.Label(win, text=t("break_other_screen"), bg=C["bg"], fg=C["muted"],
                         font=font(40, "light")).place(relx=0.5, rely=0.5, anchor="center")
                continue

            frame = tk.Frame(win, bg=C["bg"])
            frame.place(relx=0.5, rely=0.5, anchor="center")
            wrap = int(min(w * 0.6, 900))
            widgets = {
                "phase": tk.Label(frame, bg=C["bg"], fg=C["accent"], font=font(14, "semibold")),
                "title": tk.Label(frame, bg=C["bg"], fg=C["text"], font=font(36, "semibold")),
                "text": tk.Label(frame, bg=C["bg"], fg=C["text"], font=font(18), wraplength=wrap),
                "timer": tk.Label(frame, bg=C["bg"], font=font(72, "light")),
                "info": tk.Label(frame, bg=C["bg"], fg=C["muted"], font=font(12)),
            }
            widgets["phase"].pack()
            widgets["title"].pack(pady=(8, 24))
            widgets["text"].pack()
            widgets["timer"].pack(pady=(30, 4))
            widgets["info"].pack(pady=(0, 18))
            # Вибір групи м'язів: замінює поточну (і наступні) вправи
            chips = tk.Frame(frame, bg=C["bg"])
            chips.pack(pady=(0, 22 if self.cfg["group_buttons"] else 8))
            widgets["chips"] = {}
            for group in (None, *exercises.GROUPS) if self.cfg["group_buttons"] else ():
                chip = tk.Label(chips, text=t(f"group_{group or 'any'}"), font=font(10),
                                padx=12, pady=5, cursor="hand2")
                chip.pack(side="left", padx=3)
                chip.bind("<Button-1>", lambda e, g=group: self.choose_group(g))
                widgets["chips"][group] = chip
            self.break_state["widgets"] = widgets

            buttons = tk.Frame(frame, bg=C["bg"])
            buttons.pack()
            left = self.cfg["postpone_limit"] - self.sched.postpones
            postpone = flat_button(buttons, t("postpone_btn", min=self.cfg["postpone_min"], left=max(left, 0)),
                                   lambda: self.end_break("postpone"))
            if not self.sched.can_postpone():
                postpone.configure(state="disabled")
            postpone.pack(side="left", padx=8)
            if multi:
                flat_button(buttons, t("next_exercise"), self.next_break_step).pack(side="left", padx=8)
            flat_button(buttons, t("skip"), lambda: self.end_break("skip")).pack(side="left", padx=8)
            if multi:
                tk.Label(frame, text=t("body_note"),
                         bg=C["bg"], fg=C["dim"], font=font(11)).pack(pady=(28, 0))
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
        for group, chip in widgets["chips"].items():
            active = group == state["group"]
            chip.configure(bg=C["accent"] if active else C["panel"], fg=C["on_accent"] if active else C["muted"])
        if len(steps) > 1:
            total_left = state["left"] + sum(s["secs"] for s in steps[index + 1:])
            info = t("step_info", n=index + 1, total=len(steps), time=fmt_time(total_left))
            if current["kind"] == "work" and index + 1 < len(steps):
                upcoming = next((s for s in steps[index + 1:] if s["kind"] != "rest"), None)
                if upcoming:
                    info += t("up_next", title=upcoming["title"])
            widgets["info"].configure(text=info)

    def choose_group(self, group):
        """Кнопка групи м'язів на екрані перерви. Повторне натискання дає іншу вправу тієї ж групи."""
        state = self.break_state
        if not state:
            return
        steps, index = state["steps"], state["index"]
        current = steps[index]
        if len(steps) == 1:
            new = single_break_step(state["kind"], self.cfg, group, avoid=current["title"])
            new["secs"] = current["secs"]
            steps[0] = new
            if state["kind"] == "mini":
                state["left"] = new["secs"]  # нова міні-вправа — на повний час
        else:
            regroup_workout(steps, index if current["kind"] == "work" else index + 1, self.cfg["intensity"], group)
            if current["kind"] == "work":
                state["left"] = current["secs"]
        state["group"] = group
        self.update_break_view()

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
            system.beep("step")
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
        screens = system.monitors()
        if screens:
            _l, _t, right, bottom = screens[0][4]
        else:
            right, bottom = self.root.winfo_screenwidth(), self.root.winfo_screenheight() - 48
        # Обидва віконця живуть у тому самому куті: попередження про перерву й нагадування
        # про їжу лишаємо й ставимо воду над ними, решту сповіщень закриваємо
        if getattr(self, "toast_kind", None) in ("warning", "meal") and self.toast_win:
            bottom = self.toast_win.winfo_rooty()
        else:
            self.close_toast()
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
        tk.Label(head, text=t("water_title"), bg=C["panel"], fg=C["water"],
                 font=font(16, "semibold")).pack(side="left")
        tk.Label(head, text=t("x_of_y", a=min(drunk + 1, goal) if not done else drunk, b=goal), bg=C["panel"],
                 fg=C["muted"], font=font(11)).pack(side="right")
        if demo:
            tk.Label(head, text=t("demo_tag"), bg=C["panel"], fg=C["dim"],
                     font=font(9, "semibold")).pack(side="right", padx=8)
            win.bind("<Escape>", lambda e: self.end_water(False))
        glasses = tk.Frame(win, bg=C["panel"])
        glasses.pack(anchor="w", padx=18, pady=(6, 10))
        for i in range(min(max(goal, drunk), MAX_GLASSES_SHOWN)):
            tk.Label(glasses, image=glass_image(18, 24, i < drunk, C["panel"]), bg=C["panel"]).grid(
                row=i // GLASSES_PER_ROW, column=i % GLASSES_PER_ROW, padx=2, pady=2)
        if done:
            tip = t("water_goal_done")
        else:
            tip = random.choice(content("water_tips"))
        tk.Label(win, text=tip, bg=C["panel"], fg=C["text"], font=font(11),
                 wraplength=width - 44, justify="left").pack(anchor="w", padx=20)
        buttons = tk.Frame(win, bg=C["panel"])
        buttons.pack(anchor="e", padx=16, pady=14)
        flat_button(buttons, t("later"), lambda: self.end_water(False), bg=C["bg"], size=11).pack(side="left", padx=4)
        drank = t(f"drank_{self.cfg['water_profile']}")  # «Випила» / «Випив» / нейтральне «Готово»
        flat_button(buttons, drank, lambda: self.end_water(True), bg=C["water"], fg=C["on_water"], size=11,
                    image=check_mark(16, C["on_water"])).pack(side="left", padx=4)
        win.update_idletasks()
        height = win.winfo_reqheight()
        win.geometry(f"{width}x{height}+{right - width - 16}+{bottom - height - 16}")
        win.after(120_000, lambda: self.end_water(False) if self.water_win is win else None)
        if demo:
            win.focus_force()
        self.beep()

    # --- харчування ---

    def show_meal(self, meal, demo=False):
        """«Час обідати»: «Йду їсти» ставить перерви й воду на паузу, «Через 15 хв» — нагадає ще раз."""
        answer = (lambda _answer: None) if demo else self.sched.meal_answered
        actions = [(t("skip"), lambda: answer("skip"), False),
                   (t("meal_snooze", min=MEAL_SNOOZE_MIN), lambda: answer("snooze"), False),
                   (t("meal_go"), (lambda: None) if demo else self.go_eat, True)]
        title = t(f"meal_title_{meal}") + (f"  ·  {t('demo_tag')}" if demo else "")
        # Без тайм-ауту: людина могла відійти; якщо віконце витіснить інше сповіщення — нагадаємо пізніше
        self.show_toast(title, t("meal_text", time=fmt_minutes(self.cfg["meal_pause_min"])), actions,
                        timeout_ms=60_000 if demo else 3 * 60 * 60_000, kind="meal",
                        on_dismiss=None if demo else lambda: answer("snooze"))
        self.beep()

    def show_meal_over(self):
        """Пауза на їжу скінчилась — питаємо, чи продовжувати. Без відповіді перерви так і стоять."""
        actions = [(t("meal_more", min=MEAL_SNOOZE_MIN), self.sched.extend_meal, False),
                   (t("resume"), self.finish_meal, True)]
        self.show_toast(t("meal_over_title"), t("meal_over_text"), actions, timeout_ms=3 * 60 * 60_000,
                        kind="meal", on_dismiss=self.sched.extend_meal)
        self.beep()

    def go_eat(self):
        if self.break_state and not self.break_state["demo"]:  # перерва почалась, поки висіло нагадування
            self.close_break_windows()
            self.sched.finish_break()
        self.sched.meal_answered("eat")
        self.icon.update_menu()

    def finish_meal(self):
        self.sched.finish_meal()
        self.icon.update_menu()

    # --- власні сповіщення ---

    def show_toast(self, title, text, actions=(), timeout_ms=10_000, kind="info", on_dismiss=None):
        """Спливаюче віконце в куті екрана. Не покладаємося на системні сповіщення:
        користувач міг їх вимкнути (на Windows вони тоді просто мовчки зникають),
        а на macOS вони ненадійні для програм без підпису Apple.
        actions: [(напис, функція, головна_кнопка?)]; on_dismiss — якщо віконце зникло без натискання кнопки
        (тайм-аут або його витіснило інше сповіщення)."""
        self.close_toast()
        screens = system.monitors()
        if screens:
            _l, _t, right, bottom = screens[0][4]
        else:
            right, bottom = self.root.winfo_screenwidth(), self.root.winfo_screenheight() - 48
        if self.water_win:  # не перекриваємо нагадування про воду
            bottom = self.water_win.winfo_rooty()
        width = 380
        win = tk.Toplevel(self.root, bg=C["panel"], highlightthickness=2, highlightbackground=C["accent"])
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        tk.Label(win, text=title, bg=C["panel"], fg=C["accent"],
                 font=font(13, "semibold")).pack(anchor="w", padx=18, pady=(14, 2))
        self.toast_text = tk.Label(win, text=text, bg=C["panel"], fg=C["text"], font=font(10),
                                   wraplength=width - 40, justify="left")
        self.toast_text.pack(anchor="w", padx=18, pady=(0, 0 if actions else 14))
        if actions:
            row = tk.Frame(win, bg=C["panel"])
            row.pack(anchor="e", padx=14, pady=12)
            for label, command, primary in actions:
                btn = flat_button(row, label, lambda c=command: (self.close_toast(dismissed=False), c()), size=10,
                                  bg=C["accent"] if primary else C["bg"], fg=C["on_accent"] if primary else C["text"])
                btn.configure(padx=14)
                btn.pack(side="left", padx=3)
        else:
            for widget in (win, *win.winfo_children()):
                widget.bind("<Button-1>", lambda e: self.close_toast())
        win.update_idletasks()
        width = max(width, win.winfo_reqwidth())  # три кнопки можуть не вміститися в стандартну ширину
        height = win.winfo_reqheight()
        win.geometry(f"{width}x{height}+{right - width - 16}+{bottom - height - 16}")
        self.toast_win = win
        self.toast_kind = kind
        self.toast_on_dismiss = on_dismiss
        self.toast_after = self.root.after(timeout_ms, self.close_toast)

    def close_toast(self, dismissed=True):
        if getattr(self, "toast_after", None):
            self.root.after_cancel(self.toast_after)
            self.toast_after = None
        if getattr(self, "toast_win", None):
            on_dismiss = self.toast_on_dismiss if dismissed else None
            self.toast_win.destroy()
            self.toast_win = None
            self.toast_text = None
            self.toast_kind = None
            self.toast_on_dismiss = None
            if on_dismiss:
                on_dismiss()

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
        system.activate_app()  # macOS: інакше вікно програми рядка меню відкривається позаду інших
        if self.main_win:
            self.main_win.deiconify()
            self.main_win.lift()
            self.main_win.focus_force()
            return
        win = tk.Toplevel(self.root, bg=C["bg"])
        win.title(f"{APP_NAME} {__version__}")
        win.resizable(False, False)
        win.protocol("WM_DELETE_WINDOW", self.close_main)
        self.window_icon = ImageTk.PhotoImage(make_app_icon(64))
        win.iconphoto(False, self.window_icon)
        self.main_win = win
        self.w = {}
        win.update()
        system.style_window(win)

        header = tk.Frame(win, bg=C["bg"])
        header.pack(fill="x", padx=24, pady=(18, 10))
        self.header_icon = ImageTk.PhotoImage(make_app_icon(40))
        tk.Label(header, image=self.header_icon, bg=C["bg"]).pack(side="left", padx=(0, 10))
        title = tk.Frame(header, bg=C["bg"])
        title.pack(side="left")
        tk.Label(title, text=APP_NAME, bg=C["bg"], fg=C["text"],
                 font=font(18, "semibold")).pack(anchor="w")
        tk.Label(title, text=t("tagline"), bg=C["bg"], fg=C["muted"],
                 font=font(9)).pack(anchor="w")
        self.w["saved"] = tk.Label(header, text="", bg=C["bg"], fg=C["accent"], font=font(10))
        self.w["saved"].pack(side="left", padx=14, pady=(6, 0))
        self.w["update"] = tk.Label(header, text="", bg=C["bg"], fg=C["water"], font=font(10, "semibold"),
                                    cursor="hand2")
        self.w["update"].pack(side="left", pady=(6, 0))
        self.w["update"].bind("<Button-1>", lambda e: self.start_update())
        tabs = tk.Frame(header, bg=C["panel"])
        tabs.pack(side="right")

        body = tk.Frame(win, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=24, pady=(4, 20))
        self.pages, self.tab_buttons = {}, {}
        for key, builder in (("status", self.build_status_page),
                             ("stats", self.build_stats_page),
                             ("settings", self.build_settings_page)):
            self.pages[key] = builder(body)
            btn = tk.Label(tabs, text=t(f"tab_{key}"), font=font(11), padx=16, pady=6, cursor="hand2")
            btn.pack(side="left", padx=2, pady=2)
            btn.bind("<Button-1>", lambda e, k=key: self.show_page(k))
            self.tab_buttons[key] = btn
        self.fit_main_window(header)
        self.show_page("status")

    def fit_main_window(self, header):
        """Вікно під найбільшу сторінку (зазвичай «Налаштування»): розмір залежить від мови, шрифтів
        і масштабу екрана, тому не задаємо його числами."""
        win = self.main_win
        win.update_idletasks()
        width = max(MAIN_MIN_WIDTH, *(page.winfo_reqwidth() + 48 for page in self.pages.values()))
        # Відступи заголовка (18 + 10) і тіла (4 + 20). Підказки до розкладки переносяться вужче, ніж потім,
        # тож висота з запасом — нічого не обріжеться
        height = header.winfo_reqheight() + 28 + 24 + max(page.winfo_reqheight() for page in self.pages.values())
        win.geometry(f"{width}x{height}")

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
        label.configure(text=t("saved"), image=self.saved_check, compound="right")
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
        flat_button(left, t("break_now"), self.trigger_break, bg=C["accent"], fg=C["on_accent"],
                    size=11).pack(fill="x", pady=3)
        self.w["pause_btn"] = flat_button(left, t("pause_btn", time=fmt_minutes(self.cfg["pause_min"])), self.toggle_pause, size=11)
        self.w["pause_btn"].pack(fill="x", pady=3)
        flat_button(left, t("reset"), self.sched.reset, size=11).pack(fill="x", pady=3)

        right = tk.Frame(page, bg=C["bg"])
        right.pack(side="left", fill="both", expand=True)

        water = card(right, t("card_water"))
        water.pack(fill="x")
        self.w["water"] = tk.Label(water, bg=C["card"], fg=C["water"], font=font(28, "light"))
        self.w["water"].pack(anchor="w")
        self.w["water_sub"] = tk.Label(water, bg=C["card"], fg=C["muted"], font=font(10))
        self.w["water_sub"].pack(anchor="w")
        # Склянки за сьогодні: клік по склянці виставляє кількість, «−»/«+» — по одній
        row = tk.Frame(water, bg=C["card"])
        row.pack(fill="x", pady=(10, 0))
        self.w["glasses"] = tk.Frame(row, bg=C["card"])
        self.w["glasses"].pack(side="left")
        self.w["glasses_key"] = None
        for text, delta in (("+", 1), ("−", -1)):
            btn = flat_button(row, text, lambda d=delta: self.change_water(d), size=12)
            btn.configure(padx=10, pady=0)
            btn.pack(side="right", anchor="n", padx=(4, 0), pady=(4, 0))

        today = card(right, t("card_today"))
        today.pack(fill="both", expand=True, pady=(14, 0))
        grid = tk.Frame(today, bg=C["card"])
        grid.pack(fill="both", expand=True)
        metrics = (("mini_done", t("m_mini"), C["accent"]), ("long_done", t("m_long"), C["accent"]),
                   ("skipped", t("m_skipped"), C["muted"]), ("water", t("m_water"), C["water"]))
        for i, (key, caption, color) in enumerate(metrics):
            cell = tk.Frame(grid, bg=C["card"])
            cell.grid(row=i // 2, column=i % 2, sticky="nw", padx=(0, 30), pady=8)
            self.w[f"today_{key}"] = tk.Label(cell, bg=C["card"], fg=color, font=font(34, "light"))
            self.w[f"today_{key}"].pack(anchor="w")
            self.w[f"today_{key}_caption"] = tk.Label(cell, text=caption, bg=C["card"], fg=C["muted"], font=font(10))
            self.w[f"today_{key}_caption"].pack(anchor="w")
        return page

    def toggle_pause(self):
        busy = self.sched.paused or self.sched.eating
        self.handle("resume" if busy else ("pause", self.cfg["pause_min"]))

    def draw_ring(self):
        c, s = self.w["ring"], self.sched
        c.delete("all")
        size = 270
        fraction = 1 - s.remaining / max(s.period, 1)
        idle = s.paused or bool(s.eating)
        color = rgba(C["dim"] if idle else C["accent"])
        key = (round(fraction, 3), idle)
        if key != getattr(self, "_ring_key", None):
            self._ring_key = key
            self.ring_photo = ImageTk.PhotoImage(smooth_image(
                size, size, lambda d, k: draw_progress_ring(d, k, size, 18, 14, fraction, rgba(C["track"]), color),
                C["card"]))
        c.create_image(0, 0, anchor="nw", image=self.ring_photo)
        if s.eating:
            subtitle = t(f"meal_until_{s.eating}", time=f"{s.eating_until:%H:%M}")
        elif s.paused:
            subtitle = t("ring_paused", time=f"{s.paused_until:%H:%M}")
        elif s.in_break:
            subtitle = t("ring_break")
        else:
            subtitle = t(f"ring_{s.next_kind()}")
        c.create_text(size / 2, size / 2 - 10, text=fmt_time(s.remaining), fill=C["text"],
                      font=font(40, "light"))
        c.create_text(size / 2, size / 2 + 38, text=subtitle, fill=C["muted"], font=font(11))

    # статистика

    def build_stats_page(self, parent):
        """Картки нагорі — один день (сьогодні або той, на який наведено курсор на графіку)."""
        page = tk.Frame(parent, bg=C["bg"])
        self.w["stats_day"] = tk.Label(page, bg=C["bg"], fg=C["text"], font=font(12, "semibold"))
        self.w["stats_day"].pack(anchor="w", pady=(0, 8))
        summary = tk.Frame(page, bg=C["bg"])
        summary.pack(fill="x")
        cards = (("day_breaks", t("m_breaks"), C["accent"]), ("day_skipped", t("m_skipped"), C["muted"]),
                 ("day_postponed", t("m_postponed"), C["muted"]), ("day_water", t("m_water"), C["water"]))
        for i, (key, caption, color) in enumerate(cards):
            box = card(summary)
            box.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 6, 0 if i == len(cards) - 1 else 6))
            summary.columnconfigure(i, weight=1, uniform="sum")
            self.w[key] = tk.Label(box, bg=C["card"], fg=color, font=font(28, "light"))
            self.w[key].pack(anchor="w")
            tk.Label(box, text=caption, bg=C["card"], fg=C["muted"], font=font(10)).pack(anchor="w")
        # Об'єм — окремим рядком: у вузькій картці «glasses of water · ≈2.25 L» не вміщається
        self.w["day_water_volume"] = tk.Label(self.w["day_water"].master, bg=C["card"], fg=C["water"], font=font(10))
        self.w["day_water_volume"].pack(anchor="w")

        chart = card(page, t("card_last7"))
        chart.pack(fill="both", expand=True, pady=(14, 0))
        self.w["chart"] = tk.Canvas(chart, bg=C["card"], highlightthickness=0, height=270, cursor="hand2")
        self.w["chart"].pack(fill="both", expand=True)
        self.w["chart"].bind("<Motion>", self.on_chart_motion)
        self.w["chart"].bind("<Leave>", lambda e: self.highlight_day(None))
        bottom_row = tk.Frame(chart, bg=C["card"])
        bottom_row.pack(fill="x", pady=(6, 0))
        for text, color in ((t("lg_mini"), C["accent"]), (t("lg_long"), C["accent_dark"]),
                            (t("lg_skipped"), C["dim"]), (t("lg_water"), C["water"])):
            tk.Label(bottom_row, text="●", bg=C["card"], fg=color, font=font(12)).pack(side="left")
            tk.Label(bottom_row, text=text, bg=C["card"], fg=C["muted"],
                     font=font(10)).pack(side="left", padx=(2, 14))
        self.w["week_total"] = tk.Label(chart, bg=C["card"], fg=C["muted"], font=font(10))
        self.w["week_total"].pack(anchor="w", pady=(4, 0))
        return page

    def draw_stats(self):
        c = self.w.get("chart")
        if not c:
            return
        today = dt.date.today()
        days = [today - dt.timedelta(days=i) for i in range(6, -1, -1)]
        records = [self.stats.day(d) for d in days]
        week_water = sum(r["water"] for r in records)
        self.w["week_total"].configure(text=t(
            "week_total", breaks=sum(r["mini_done"] + r["long_done"] for r in records),
            skipped=sum(r["skipped"] for r in records), water=week_water, volume=fmt_volume(week_water)))

        c.delete("all")
        width, height = max(c.winfo_width(), 600), max(c.winfo_height(), 230)
        top, bottom = 24, height - 48
        slot = width / 7
        self.chart_info = {"days": days, "records": records, "slot": slot, "top": top, "bottom": bottom,
                           "width": width, "bar": min(44, slot * 0.5), "hover": None}
        peak = max([r["mini_done"] + r["long_done"] + r["skipped"] for r in records] + [4])
        for i in range(5):
            y = bottom - (bottom - top) * i / 4
            c.create_line(0, y, width, y, fill=C["track"] if i == 0 else C["grid"])
        bar = self.chart_info["bar"]
        bar_tops = []
        for i, (day, rec) in enumerate(zip(days, records)):
            cx = slot * i + slot / 2
            y = bottom
            for key, color in (("mini_done", C["accent"]), ("long_done", C["accent_dark"]), ("skipped", C["dim"])):
                h = (bottom - top) * rec[key] / peak
                if h:
                    c.create_rectangle(cx - bar / 2, y - h, cx + bar / 2, y, fill=color, outline="")
                    y -= h
            bar_tops.append(y)
            total = rec["mini_done"] + rec["long_done"] + rec["skipped"]
            if total:
                c.create_text(cx, y - 10, text=total, fill=C["text"], font=font(10, "semibold"))
            label = t("today") if day == today else t("weekdays").split()[day.weekday()]
            c.create_text(cx, bottom + 14, text=label, fill=C["text"] if day == today else C["muted"],
                          font=font(10))
            c.create_text(cx, bottom + 33, text=f"● {rec['water']}" if rec["water"] else "",
                          fill=C["water"], font=font(9))
        self.chart_info["bar_tops"] = bar_tops
        self.show_stats_day(6)

    def show_stats_day(self, index):
        """Картки нагорі: дані одного дня з графіка (6 — сьогодні)."""
        info = self.chart_info
        day, rec = info["days"][index], info["records"][index]
        date = f"{day:%d.%m}"
        if day == dt.date.today():
            title = t("stats_today", date=date)
        else:
            title = t("stats_day", weekday=t("weekdays").split()[day.weekday()], date=date)
        self.w["stats_day"].configure(text=title)
        self.w["day_breaks"].configure(text=rec["mini_done"] + rec["long_done"])
        self.w["day_skipped"].configure(text=rec["skipped"])
        self.w["day_water_volume"].configure(text=fmt_volume(rec["water"]))
        self.w["day_postponed"].configure(text=rec["postponed"])
        self.w["day_water"].configure(text=rec["water"])

    def on_chart_motion(self, event):
        info = getattr(self, "chart_info", None)
        if not info:
            return
        inside = info["top"] - 20 <= event.y <= info["bottom"] + 44
        self.highlight_day(min(6, max(0, int(event.x // info["slot"]))) if inside else None)

    def highlight_day(self, index):
        """Підсвітка стовпчика, підказка з деталями дня й картки нагорі для цього дня."""
        info = getattr(self, "chart_info", None)
        c = self.w.get("chart")
        if not info or not c or index == info["hover"]:
            return
        info["hover"] = index
        c.delete("hover")
        if index is None:
            self.show_stats_day(6)
            return
        slot, top, bottom = info["slot"], info["top"], info["bottom"]
        band = c.create_rectangle(slot * index + 4, top - 14, slot * (index + 1) - 4, bottom + 44,
                                  fill=C["grid"], outline="", tags="hover")
        c.tag_lower(band)
        rec = info["records"][index]
        lines = [
            f"{t('tip_mini')}: {rec['mini_done']}",
            f"{t('tip_long')}: {rec['long_done']}",
            f"{t('tip_skipped')}: {rec['skipped']}",
            f"{t('tip_postponed')}: {rec['postponed']}",
            f"{t('tip_day_water')}: {t('x_of_y', a=rec['water'], b=self.cfg['water_goal'])} ({fmt_volume(rec['water'])})",
        ]
        text = c.create_text(0, 0, text="\n".join(lines), anchor="nw", fill=C["text"], font=font(10), tags="hover")
        x0, y0, x1, y1 = c.bbox(text)
        box_w, box_h = x1 - x0 + 24, y1 - y0 + 18
        cx, bar = slot * index + slot / 2, info["bar"]
        x = cx + bar / 2 + 10
        if x + box_w > info["width"] - 4:  # біля правого краю — підказка ліворуч від стовпчика
            x = cx - bar / 2 - 10 - box_w
        y = max(4, min(info["bar_tops"][index] - box_h / 2, bottom - box_h))
        box = c.create_rectangle(x, y, x + box_w, y + box_h, fill=C["panel"], outline=C["accent"], tags="hover")
        c.coords(text, x + 12, y + 9)
        c.tag_raise(text, box)
        self.show_stats_day(index)

    # налаштування

    def build_settings_page(self, parent):
        page = tk.Frame(parent, bg=C["bg"])
        # Три однакові колонки: перерви · довгі перерви й вода · їжа та загальне
        left, middle, right = (tk.Frame(page, bg=C["bg"]) for _ in range(3))
        for i, column in enumerate((left, middle, right)):
            column.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 7, 0 if i == 2 else 7))
            page.columnconfigure(i, weight=1, uniform="settings")

        def group(column, title, keys):
            box = card(column, title)
            box.pack(fill="x", pady=(0, 14))
            for key in keys:
                self.add_slider(box, key)

        breaks = card(left, t("card_breaks"))
        breaks.pack(fill="x", pady=(0, 14))
        for key in ("mini_interval_min", "mini_duration_sec", "intensity"):
            self.add_slider(breaks, key)
        Toggle(breaks, t("group_buttons_toggle"), self.cfg["group_buttons"],
               lambda v: self.set_setting("group_buttons", v)).pack(fill="x", pady=(2, 0))
        group(left, t("card_postpone"), ("postpone_min", "postpone_limit", "warn_before_sec", "pause_min"))

        long_box = card(middle, t("card_long"))
        long_box.pack(fill="x", pady=(0, 14))
        self.add_slider(long_box, "long_every")
        self.add_slider(long_box, "long_duration_min")
        Toggle(long_box, t("workout_toggle"), self.cfg["workout_enabled"],
               lambda v: self.set_setting("workout_enabled", v)).pack(fill="x", pady=(2, 0))
        water = card(middle, t("card_water"))
        water.pack(fill="x")
        Toggle(water, t("water_toggle"), self.cfg["water_enabled"],
               lambda v: self.set_setting("water_enabled", v)).pack(fill="x", pady=(0, 8))
        self.build_water_profile(water)
        sound = card(middle, t("card_sound"))
        sound.pack(fill="x", pady=(14, 0))
        Toggle(sound, t("sound_toggle"), self.cfg["sound"],
               lambda v: self.set_setting("sound", v)).pack(fill="x", pady=(0, 8))
        self.add_sound_slider(sound)

        self.build_meals_card(right).pack(fill="x")
        other = card(right, t("card_other"))
        other.pack(fill="x", pady=(14, 0))
        self.build_language_switch(other).pack(fill="x", pady=(0, 6))
        Toggle(other, t("autostart_toggle_mac" if system.IS_MAC else "autostart_toggle"), system.get_autostart(),
               self.set_autostart_setting).pack(fill="x", pady=4)
        Toggle(other, t("updates_toggle"), self.cfg["check_updates"],
               lambda v: self.set_setting("check_updates", v)).pack(fill="x", pady=4)

        preview = card(right, t("card_preview"))
        preview.pack(fill="x", pady=(14, 0))
        tk.Label(preview, text=t("preview_hint"), bg=C["card"],
                 fg=C["muted"], font=font(10)).pack(anchor="w", pady=(0, 8))
        row = tk.Frame(preview, bg=C["card"])
        row.pack(fill="x")
        previews = ((t("preview_mini"), lambda: self.show_demo_break("mini")),
                    (t("preview_long"), lambda: self.show_demo_break("long")),
                    (t("preview_water"), lambda: self.show_water(demo=True)),
                    (t("preview_meal"), lambda: self.show_meal("lunch", demo=True)))
        for i, (text, action) in enumerate(previews):
            btn = flat_button(row, text, action, size=10)
            btn.configure(padx=4, pady=7)
            btn.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 3, 0 if i == len(previews) - 1 else 3))
            row.columnconfigure(i, weight=1, uniform="preview")
        return page

    def build_meals_card(self, parent):
        """Сніданок, обід, вечеря: перемикач і час для кожного; повзунок часу неактивний, поки їжу вимкнено."""
        box = card(parent, t("card_meals"))
        for meal in MEALS:
            lo, hi, step, fmt = SLIDERS[f"{meal}_at"]
            slider = Slider(box, t(f"s_{meal}_at"), lo, hi, step, self.cfg[f"{meal}_at"], fmt,
                            lambda v, k=f"{meal}_at": self.set_setting(k, v))

            def toggle(value, meal=meal, slider=slider):
                self.set_setting(f"{meal}_enabled", value)
                slider.set_enabled(value)

            Toggle(box, t(f"meal_{meal}"), self.cfg[f"{meal}_enabled"], toggle).pack(fill="x", pady=(0, 2))
            slider.pack(fill="x", pady=(0, 8))
            slider.set_enabled(self.cfg[f"{meal}_enabled"])
        self.add_slider(box, "meal_pause_min")
        return box

    def build_language_switch(self, parent):
        """Рядок «Мова» з перемикачем-сегментом між мовами."""
        row = tk.Frame(parent, bg=parent["bg"])
        tk.Label(row, text=t("language"), bg=parent["bg"], fg=C["text"], font=font(11)).pack(side="left")
        segments = tk.Frame(row, bg=C["panel"])
        segments.pack(side="right")
        for code, name in i18n.LANGUAGES.items():
            active = code == i18n.get_language()
            btn = tk.Label(segments, text=name, font=font(10), padx=12, pady=3, cursor="hand2",
                           bg=C["accent"] if active else C["panel"], fg=C["on_accent"] if active else C["muted"])
            btn.pack(side="left", padx=2, pady=2)
            btn.bind("<Button-1>", lambda e, c=code: self.change_language(c))
        return row

    def build_water_profile(self, parent):
        """Перемикач «Норма: жінка / чоловік / вручну», підказка-рекомендація і повзунки води."""
        row = tk.Frame(parent, bg=parent["bg"])
        row.pack(fill="x", pady=(0, 4))
        tk.Label(row, text=t("water_profile"), bg=parent["bg"], fg=C["text"], font=font(11)).pack(side="left")
        segments = tk.Frame(row, bg=C["panel"])
        segments.pack(side="right")
        self.w["water_profile"] = {}
        for code in (*WATER_PROFILES, "custom"):
            btn = tk.Label(segments, text=t(f"water_profile_{code}"), font=font(10), padx=10, pady=3, cursor="hand2")
            btn.pack(side="left", padx=2, pady=2)
            btn.bind("<Button-1>", lambda e, c=code: self.set_water_profile(c))
            self.w["water_profile"][code] = btn
        # Початковий перенос — вужчий за колонку, щоб довгий рядок не роздував вікно; далі — за шириною
        hint = tk.Label(parent, bg=parent["bg"], fg=C["muted"], font=font(9), justify="left", anchor="w",
                        wraplength=240)
        hint.pack(fill="x", pady=(0, 10))
        hint.bind("<Configure>", lambda e: hint.configure(wraplength=e.width))
        self.w["water_hint"] = hint
        self.w["water_sliders"] = {}
        for key in ("water_interval_min", "water_goal"):
            lo, hi, step, fmt = SLIDERS[key]

            def change(v, k=key):
                self.set_setting(k, v)
                self.refresh_water_profile()  # підказка для ручного режиму залежить від мети

            slider = Slider(parent, t(f"s_{key}"), lo, hi, step, self.cfg[key], fmt, change)
            slider.pack(fill="x", pady=(0, 10))
            self.w["water_sliders"][key] = slider
        self.refresh_water_profile()

    def refresh_water_profile(self):
        profile = self.cfg["water_profile"]
        for code, btn in self.w["water_profile"].items():
            active = code == profile
            btn.configure(bg=C["water"] if active else C["panel"], fg=C["on_water"] if active else C["muted"])
        for key, slider in self.w["water_sliders"].items():
            slider.set(self.cfg[key])
            slider.set_enabled(profile == "custom")
        goal = self.cfg["water_goal"]
        if profile == "custom":
            text = t("water_hint_custom", female=fmt_volume(WATER_PROFILES["female"]),
                     male=fmt_volume(WATER_PROFILES["male"]), goal=fmt_glasses(goal),
                     interval=fmt_minutes(water_interval_for(goal)))
        else:
            text = t("water_hint_auto", volume=fmt_volume(goal), interval=fmt_minutes(self.cfg["water_interval_min"]))
        self.w["water_hint"].configure(text=text)

    def set_water_profile(self, profile):
        if profile == self.cfg["water_profile"]:
            return
        self.cfg["water_profile"] = profile
        apply_water_profile(self.cfg)
        save_json(CONFIG_PATH, self.cfg)
        self.sched.apply_config()
        self.flash_saved()
        self.refresh_water_profile()

    def change_language(self, code):
        if code == i18n.get_language():
            return
        self.cfg["language"] = code
        save_json(CONFIG_PATH, self.cfg)
        i18n.set_language(code)
        self.icon.menu = self.build_menu()
        self.icon.update_menu()
        self.tooltip = None
        # Вікно перебудовуємо поза обробником кліку, бо кнопка, що його викликала, теж зникне
        self.root.after(10, self.reopen_main_on_settings)

    def reopen_main_on_settings(self):
        if self.main_win:
            self.close_main()
        self.open_main()
        self.show_page("settings")
        self.flash_saved()

    def sound_name(self):
        """Вибраний звук сповіщення або перший доступний на цьому комп'ютері."""
        names = [name for name, _path in system.available_sounds()]
        return self.cfg["sound_name"] if self.cfg["sound_name"] in names else (names[0] if names else "")

    def add_sound_slider(self, parent):
        """Повзунок перебирає системні звуки й одразу програє вибраний — для прослуховування."""
        sounds = system.available_sounds()
        if len(sounds) < 2:
            return
        names = [name for name, _path in sounds]

        def choose(index):
            self.set_setting("sound_name", names[index])
            system.play_sound(sounds[index][1])

        def label(index):  # Windows: перекладені назви подій; macOS: власні назви звуків (Glass, Ping…)
            key = f"snd_{names[index]}"
            return t(key) if key in i18n.STRINGS[i18n.get_language()] else names[index]

        Slider(parent, t("sound_name_label"), 0, len(names) - 1, 1, names.index(self.sound_name()),
               label, choose).pack(fill="x", pady=(0, 6))

    def add_slider(self, parent, key):
        lo, hi, step, fmt = SLIDERS[key]
        Slider(parent, t(f"s_{key}"), lo, hi, step, self.cfg[key], fmt,
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
            system.set_autostart(enabled, __file__)
            self.flash_saved()
        except OSError as e:
            messagebox.showerror(APP_NAME, t("autostart_error", e=e), parent=self.main_win)

    def refresh_main(self):
        if not self.main_win or "ring" not in self.w:
            return
        s = self.sched
        self.draw_ring()
        self.w["update"].configure(text=t("update_banner", version=self.update_info[0]) if self.update_info else "")
        self.w["pause_btn"].configure(text=t("resume") if s.paused or s.eating else t("pause_btn", time=fmt_minutes(self.cfg["pause_min"])))
        today = self.stats.day(dt.date.today())
        progress = t("water_today", n=today["water"], goal=self.cfg["water_goal"], volume=fmt_volume(today["water"]))
        self.w["today_water_caption"].configure(text=f"{t('m_water')} · {fmt_volume(today['water'])}")
        if not self.cfg["water_enabled"]:
            self.w["water"].configure(text="—")
            self.w["water_sub"].configure(text=t("water_off"))
        elif s.water_open:
            self.w["water"].configure(text=t("water_now"))
            self.w["water_sub"].configure(text=progress)
        else:
            self.w["water"].configure(text=fmt_time(s.water_remaining))
            self.w["water_sub"].configure(text=t("water_next", progress=progress))
        for key in ("mini_done", "long_done", "skipped", "water"):
            self.w[f"today_{key}"].configure(text=today[key])
        self.render_glasses(today["water"])

    def render_glasses(self, drunk):
        """Ряд склянок у картці «Вода» — перемальовуємо лише коли щось змінилося."""
        goal = self.cfg["water_goal"]
        if self.w.get("glasses_key") == (drunk, goal):
            return
        self.w["glasses_key"] = (drunk, goal)
        frame = self.w["glasses"]
        for child in frame.winfo_children():
            child.destroy()
        for i in range(min(max(goal, drunk), MAX_GLASSES_SHOWN)):
            glass = tk.Label(frame, image=glass_image(22, 30, i < drunk, C["card"]), bg=C["card"], cursor="hand2")
            glass.grid(row=i // GLASSES_PER_ROW, column=i % GLASSES_PER_ROW, padx=3, pady=2)
            # Клік по останній випитій склянці знімає її, по будь-якій іншій — виставляє кількість до неї
            glass.bind("<Button-1>", lambda e, n=i + 1: self.set_water(n - 1 if n == drunk else n))

    def change_water(self, delta):
        self.set_water(self.stats.day(dt.date.today())["water"] + delta)

    def set_water(self, count):
        """Ручна зміна кількості випитої води за сьогодні."""
        before = self.stats.day(dt.date.today())["water"]
        count = max(0, min(count, MAX_GLASSES))
        if count == before:
            return
        self.stats.set("water", count)
        if count > before:
            # Щойно випив — наступне нагадування відраховується заново; відкрите нагадування вже зайве
            if self.water_win and not self.water_demo:
                self.water_win.destroy()
                self.water_win = None
            self.sched.water_answered(True)
        self.refresh_main()
        if self.w.get("chart") and self.w["chart"].winfo_ismapped():
            self.draw_stats()


def current_version():
    """Версія для порівняння з релізами. RHYTHMOS_VERSION_OVERRIDE — лише для перевірки
    самооновлення в CI: зібрана програма «вдає» стару версію й оновлюється до останнього релізу."""
    return os.environ.get("RHYTHMOS_VERSION_OVERRIDE") or __version__


def run_smoke_test(app, out_dir):
    """--smoke-test: проходить усі вікна без участі людини й робить знімки екрана.
    Потрібен для перевірки збірки на macOS-сервері GitHub Actions, де немає кому дивитися."""
    os.makedirs(out_dir, exist_ok=True)
    original_language = app.cfg["language"]
    counter = [0]

    def shot(name):
        app.root.update()
        counter[0] += 1
        system.screenshot(os.path.join(out_dir, f"{counter[0]:02d}_{name}.png"))

    def page(name):
        app.show_page(name)
        app.main_win.lift()

    steps = [
        (app.open_main, None),
        (lambda: page("status"), "status"),
        (lambda: page("stats"), "stats"),
        (lambda: page("settings"), "settings"),
        (lambda: app.change_language("en" if i18n.get_language() == "uk" else "uk"), None),
        (lambda: None, "settings_other_language"),
        (lambda: app.show_demo_break("mini"), None),
        (lambda: app.choose_group("back"), "mini_break_back"),
        (lambda: app.end_break("skip"), None),
        (lambda: (app.show_demo_break("long"), app.next_break_step()), "workout"),
        (lambda: app.end_break("skip"), None),
        (lambda: app.show_water(demo=True), "water"),
        (lambda: app.end_water(False), None),
        (lambda: app.show_meal("lunch", demo=True), "meal"),
        (app.close_toast, None),
        (lambda: app.show_toast(t("update_toast_title", version="9.9.9"), t("update_toast_text"),
                                [(t("download"), lambda: None, True), (t("later"), lambda: None, False)]), "toast"),
        (app.close_toast, None),
        (lambda: (setattr(app.sched, "warned", True), app.show_break_warning()), "break_warning"),
        (app.close_toast, None),
        # Мережа й сертифікати: на macOS без certifi HTTPS у зібраній програмі не працює
        (lambda: print(f"smoke test: update check -> {updates.fetch_latest()}", file=sys.stderr), None),
    ]

    def run(index=0):
        try:
            if index == len(steps):
                app.cfg["language"] = original_language
                save_json(CONFIG_PATH, app.cfg)
                print("smoke test: OK", file=sys.stderr)
                app.exit_code = 0
                app.handle("quit")
                return
            action, name = steps[index]
            action()
            if name:
                app.root.after(900, lambda: (shot(name), run(index + 1)))
            else:
                app.root.after(500, lambda: run(index + 1))
        except Exception:
            traceback.print_exc()
            app.exit_code = 1
            app.handle("quit")

    app.exit_code = 1
    app.root.after(1500, run)


def main():
    system.init_process()
    # Команди для інсталятора: увімкнути/вимкнути автозапуск, задати мову — і вийти
    commands = [arg for arg in sys.argv[1:] if arg.startswith(("--set-autostart=", "--set-language="))]
    for arg in commands:
        name, value = arg[2:].split("=", 1)
        if name == "set-language":
            set_language_setting(value)
        else:
            system.set_autostart(value == "on", __file__)
    if commands:
        return

    instance = system.SingleInstance()
    if not instance.acquire():
        return  # уже запущена копія сама покаже вікно

    old_autostart = system.migrate_old_data(DATA_DIR)
    smoke_dir = sys.argv[sys.argv.index("--smoke-test") + 1] if "--smoke-test" in sys.argv else None
    if old_autostart and not smoke_dir:  # автозапуск зі старою назвою (Limber) — перереєструємо під новою
        try:
            system.set_autostart(True, __file__)
        except OSError:
            traceback.print_exc()
    # macOS: інсталятора немає (програму просто перетягують у «Програми»),
    # тож автозапуск вмикаємо під час першого запуску; вимкнути можна в налаштуваннях
    if system.IS_MAC and getattr(sys, "frozen", False) and not smoke_dir and not os.path.exists(CONFIG_PATH):
        try:
            system.set_autostart(True, __file__)
        except OSError:
            traceback.print_exc()
        save_json(CONFIG_PATH, load_json(CONFIG_PATH, {}))

    app = App()
    app.instance = instance
    if smoke_dir:
        run_smoke_test(app, smoke_dir)
    if "--test-break" in sys.argv:
        app.root.after(1500, app.trigger_break)
    if "--test-water" in sys.argv:
        app.root.after(1500, lambda: (setattr(app.sched, "water_open", True), app.show_water()))
    if "--open" in sys.argv:
        app.root.after(500, app.open_main)
    if "--update-now" in sys.argv:  # перевірка самооновлення: одразу шукаємо реліз і оновлюємося
        threading.Thread(target=lambda: app.queue.put(("update_now", updates.fetch_latest())), daemon=True).start()
    app.root.mainloop()
    if smoke_dir:
        sys.exit(app.exit_code)


def setup_logging():
    """pythonw не має консолі, тож помилки інакше зникають безслідно — пишемо їх у rhythmos.log."""
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
