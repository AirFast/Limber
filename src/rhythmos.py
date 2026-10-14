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
from i18n import (content, fmt_after_minis, fmt_clock, fmt_days, fmt_glasses, fmt_intensity, fmt_minutes, fmt_seconds, fmt_times, fmt_volume,
                  fmt_warn, t)
from system import font

__version__ = "2.8.0"

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
    "day_end_enabled": True,     # нагадування «робочий день скінчився»
    "day_end_at": 18 * 60,
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
TIMELINE_HEIGHT = 76      # шкала дня в картці «Сьогодні»
TITLE_BAR = 32            # приблизна висота заголовка вікна ОС — щоб вікно вміщалося в робочу область
STATS_RANGES = (7, 30)    # перемикач періоду на графіку статистики
UPDATE_CHECK_DELAY_MS = 30_000
UPDATE_CHECK_INTERVAL_MS = 60 * 60 * 1000   # щогодини: раз на добу нова версія могла чекати до завтра
UPDATE_RECHECK_ON_OPEN_SEC = 10 * 60        # відкриття головного вікна теж перевіряє, але не частіше

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
    "meal": "#f2a65a",       # їжа — теплий бурштиновий, щоб не плутати з водою й перервами
    "on_meal": "#2e1803",
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
    "day_end_at": (15 * 60, 23 * 60, 15, fmt_clock),
}

MEALS = ("breakfast", "lunch", "dinner")
MEAL_WINDOW_MIN = 60   # комп'ютер прокинувся пізніше, ніж на годину після часу їжі, — нагадування вже ні до чого
MEAL_SNOOZE_MIN = 15   # «Через 15 хв» і «Ще 15 хв»
DAY_END_SNOOZE_MIN = 30  # «Ще 30 хв» — людина ще працює, нагадаємо знову

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
    # work_sec — час за комп'ютером (таймер іде: не пауза, не перерва, не їжа), active_sec — час на перервах,
    # meals — скільки разів поїли (сума ate_*), ate_<їжа> — 1, якщо цю їжу сьогодні з'їдено («Йду їсти»
    # або тарілка на «Стані»), day_end — о котрій (хв від півночі) натиснули «Завершити день»; 0 — не завершували
    KEYS = ("mini_done", "long_done", "skipped", "postponed", "water", "work_sec", "active_sec", "meals", "day_end",
            "ate_breakfast", "ate_lunch", "ate_dinner")

    def __init__(self):
        self.data = load_json(STATS_PATH, {})

    def add(self, key, amount=1):
        rec = self.data.setdefault(dt.date.today().isoformat(), {})
        rec[key] = rec.get(key, 0) + amount
        save_json(STATS_PATH, self.data)

    def set(self, key, value):
        """Ручне виправлення лічильника за сьогодні (наприклад, кількості склянок води)."""
        rec = self.data.setdefault(dt.date.today().isoformat(), {})
        rec[key] = max(0, int(value))
        save_json(STATS_PATH, self.data)

    def day(self, date):
        rec = self.data.get(date.isoformat(), {})
        return {k: rec.get(k, 0) for k in self.KEYS}

    def times(self, date, key):
        """Список моментів події за день (хвилини від півночі), наприклад water_at — коли пили воду."""
        return list(self.data.get(date.isoformat(), {}).get(key, []))

    def set_times(self, key, values):
        rec = self.data.setdefault(dt.date.today().isoformat(), {})
        rec[key] = list(values)
        save_json(STATS_PATH, self.data)


def split_balanced(heights, columns, gap=14):
    """Ділить картки (у заданому порядку) на `columns` послідовних груп так, щоб найвища колонка
    була якомога нижчою: порядок читання — згори вниз, зліва направо — зберігається.
    Повертає списки індексів карток для кожної колонки."""
    n = len(heights)
    columns = max(1, min(columns, n))

    def height(group):
        return sum(heights[i] for i in group) + gap * (len(group) - 1)

    best = None

    def search(start, left, groups):
        nonlocal best
        if left == 1:
            groups = groups + [list(range(start, n))]
            heights_now = [height(g) for g in groups]
            worst = max(heights_now)
            # Спершу — найнижча найвища колонка. Далі — найменше порожнього місця на одну картку:
            # коротші колонки розтягують свої картки до висоти найвищої, і краще, щоб запас ділили
            # кілька карток, ніж щоб одна картка стояла з великим порожнім низом
            slack = max((worst - h) / len(g) for h, g in zip(heights_now, groups))
            score = (worst, slack)
            if best is None or score < best[0]:
                best = (score, groups)
            return
        for end in range(start + 1, n - left + 2):
            search(end, left - 1, groups + [list(range(start, end))])

    search(0, columns, [])
    return best[1]


def main_layout(available_width):
    """Розкладка головного вікна під ширину робочої області екрана: скільки колонок у налаштуваннях,
    скільки карток статистики в ряд і бажана ширина вікна."""
    if available_width >= 1300:
        return {"columns": 4, "stat_cards": 6, "width": 1280}
    if available_width >= 1100:
        return {"columns": 3, "stat_cards": 6, "width": 1080}
    return {"columns": 2, "stat_cards": 3, "width": 900}


def completion_rate(rec):
    """Частка зроблених перерв серед зроблених і пропущених, %; None — перерв не було."""
    done = rec["mini_done"] + rec["long_done"]
    total = done + rec["skipped"]
    return round(100 * done / total) if total else None


def water_streak(stats, goal, today):
    """Скільки днів поспіль виконано норму води. Сьогодні ще не вечір — тож, якщо норми поки немає,
    рахуємо від учора."""
    day = today if stats.day(today)["water"] >= goal else today - dt.timedelta(days=1)
    streak = 0
    while stats.day(day)["water"] >= goal:
        streak += 1
        day -= dt.timedelta(days=1)
    return streak


def fmt_hm(seconds):
    """Тривалість у картці: 6 год 5 хв → «6:05»."""
    minutes = int(seconds) // 60
    return f"{minutes // 60}:{minutes % 60:02d}"


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
        self.meal_results = {}      # (дата, їжа) → "eat" / "skip" — для розкладу на вкладці «Стан»
        self.eating = None          # «Йду їсти»: яка їжа; перерви й вода заморожені, поки не натиснуть «Продовжити»
        self.eating_until = None
        self.meal_over_asked = False
        self.day_end_open = False   # висить нагадування «робочий день скінчився»
        self.day_end_shown = None   # дата, коли про кінець дня вже нагадали
        self.day_end_snoozed = None

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
        elif self.due_day_end(now):
            self.day_end_open = True
            self.day_end_shown = now.date()
            self.day_end_snoozed = None
            events.append("day_end")
        return events

    def due_day_end(self, now):
        """Час кінця робочого дня настав (або минуло «Ще 30 хв»), а людина досі за комп'ютером."""
        if (not self.cfg["day_end_enabled"] or self.day_end_open or self.meal_open or self.in_break
                or (self.paused and self.pause_water)):
            return False
        if self.day_end_snoozed:
            return now >= self.day_end_snoozed
        return self.day_end_shown != now.date() and now.hour * 60 + now.minute >= self.cfg["day_end_at"]

    def day_end_answered(self, answer, now=None):
        """answer: "snooze" — нагадати через 30 хв, "finish" — день завершено (паузу ставить App)."""
        self.day_end_open = False
        if answer == "snooze":
            self.day_end_snoozed = (now or dt.datetime.now()) + dt.timedelta(minutes=DAY_END_SNOOZE_MIN)

    def due_meal(self, now):
        """Їжа, про яку час нагадати: її година настала, але минуло не більше MEAL_WINDOW_MIN."""
        if self.meal_open or self.in_break or (self.paused and self.pause_water):
            return None
        minutes = now.hour * 60 + now.minute
        for meal in MEALS:
            if not self.cfg[f"{meal}_enabled"]:
                continue
            if (now.date(), meal) in self.meal_results:
                continue  # уже з'їли (позначили тарілку заздалегідь) чи пропустили
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
        if answer in ("eat", "skip"):
            self.meal_results[(now.date(), meal)] = answer
        if answer == "snooze":
            self.meal_snoozed[meal] = now + dt.timedelta(minutes=MEAL_SNOOZE_MIN)
        elif answer == "eat":
            self.paused_until = None  # їжа важливіша за звичайну паузу
            self.pause_water = False
            self.eating = meal
            self.eating_until = now + dt.timedelta(minutes=self.cfg["meal_pause_min"])
            self.meal_over_asked = False

    def meal_state(self, meal, now):
        """Стан їжі сьогодні для розкладу: (стан, час). Стани: "eating" (до часу), "eat", "skip",
        "snoozed" (нагадаю о), "open" (нагадування висить), "upcoming" (о), "due" (ось-ось), "missed"."""
        if self.eating == meal:
            return "eating", self.eating_until
        result = self.meal_results.get((now.date(), meal))
        if result:
            return result, None
        if meal in self.meal_snoozed:
            return "snoozed", self.meal_snoozed[meal]
        if self.meal_open == meal:
            return "open", None
        at = dt.datetime.combine(now.date(), dt.time()) + dt.timedelta(minutes=self.cfg[f"{meal}_at"])
        if now < at:
            return "upcoming", at
        return ("due" if now < at + dt.timedelta(minutes=MEAL_WINDOW_MIN) else "missed"), at

    def next_meal(self, now):
        """Наступна їжа: (їжа, коли) або (їжа, None), якщо час їсти вже зараз; None — на сьогодні все."""
        best = None
        for meal in MEALS:
            if not self.cfg[f"{meal}_enabled"]:
                continue
            state, when = self.meal_state(meal, now)
            if state in ("open", "due"):
                return meal, None
            if state in ("upcoming", "snoozed") and (best is None or when < best[1]):
                best = (meal, when)
        return best

    def breaks_until_long(self):
        """Скільки перерв лишилось до довгої, включно з нею: 1 — наступна перерва довга."""
        every = max(1, self.cfg["long_every"])
        return every - self.breaks_taken % every

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
    filled: True — випита (синя вода й синій контур), False — ще ні (сіра рідина й контур);
    при наведенні — що зробить клік: "add" — додасться (синій контур, бліда вода),
    "remove" — зніметься (сірий контур, ледь помітна вода)."""
    if filled == "add":
        edge, liquid, shine = lighten(C["water"], 0.35), blend(C["water"], bg, 0.6), blend(C["water"], bg, 0.3)
    elif filled == "remove":
        edge, liquid, shine = C["dim"], blend(C["water"], bg, 0.7), blend(C["water"], bg, 0.5)
    elif filled:
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


_dot_cache = {}
_plate_cache = {}

# Стан їжі (Scheduler.meal_state) → як малювати тарілку у віконці їжі
PLATE_STATES = {"eat": "done", "skip": "skip", "missed": "skip", "upcoming": "later", "snoozed": "later",
                "eating": "now", "open": "now", "due": "now"}


def plate_picture(size, state, bg):
    """Тарілка згори (два кола). "done" — з'їдено (заповнена), "now" — час їсти (яскравий контур),
    "later" — ще буде (сірий контур), "skip" — пропущено (сірий контур, перекреслено);
    при наведенні на «Стані»: "add" — клік позначить з'їденою (бліда заливка), "remove" — зніме позначку."""
    meal = C["meal"]

    def paint(d, s):
        w = size * s
        stroke = max(1.5, size * 0.07) * s
        pad = stroke / 2 + 0.5 * s
        outer = (pad, pad, w - pad, w - pad)
        inset = size * 0.24 * s
        inner = (inset, inset, w - inset, w - inset)
        if state == "done":
            d.ellipse(outer, fill=rgba(meal))
            d.ellipse(inner, outline=rgba(lighten(meal, 0.45)), width=int(stroke))
        elif state == "add":
            d.ellipse(outer, fill=rgba(blend(meal, bg, 0.55)), outline=rgba(lighten(meal, 0.3)), width=int(stroke))
            d.ellipse(inner, outline=rgba(blend(meal, bg, 0.2)), width=int(stroke * 0.8))
        elif state == "remove":
            d.ellipse(outer, fill=rgba(blend(meal, bg, 0.75)), outline=rgba(C["dim"]), width=int(stroke))
            d.ellipse(inner, outline=rgba(blend(meal, bg, 0.5)), width=int(stroke * 0.8))
        elif state == "now":
            d.ellipse(outer, fill=rgba(blend(meal, bg, 0.78)), outline=rgba(meal), width=int(stroke))
            d.ellipse(inner, outline=rgba(blend(meal, bg, 0.4)), width=int(stroke * 0.8))
        else:
            d.ellipse(outer, outline=rgba(C["dim"]), width=int(stroke))
            d.ellipse(inner, outline=rgba(blend(C["dim"], bg, 0.5)), width=int(stroke * 0.8))
            if state == "skip":
                d.line((w * 0.24, w * 0.76, w * 0.76, w * 0.24), fill=rgba(C["dim"]), width=int(stroke))

    return smooth_image(size, size, paint, bg)


def plate_image(size, state, bg):
    key = (size, state, bg)
    if key not in _plate_cache:
        _plate_cache[key] = ImageTk.PhotoImage(plate_picture(size, state, bg))
    return _plate_cache[key]


def dot_image(size, color, filled, bg):
    """Згладжений кружечок для canvas (create_oval у Tk — з «драбинкою» по краю):
    заповнений або кільце завтовшки ~1,6 px."""
    key = (size, color, filled, bg)
    if key not in _dot_cache:
        def paint(d, s):
            d.ellipse((0.5 * s, 0.5 * s, (size - 0.5) * s, (size - 0.5) * s), fill=rgba(color))
            if not filled:
                ring = 1.6 * s
                d.ellipse((0.5 * s + ring, 0.5 * s + ring, (size - 0.5) * s - ring, (size - 0.5) * s - ring),
                          fill=rgba(bg))

        _dot_cache[key] = ImageTk.PhotoImage(smooth_image(size, size, paint, bg))
    return _dot_cache[key]


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


def demo_badge(parent):
    """Однакова позначка «ДЕМО» для всіх демо-вікон: перерва, тренування, вода, їжа, кінець дня."""
    return tk.Label(parent, text=t("demo_tag").upper(), bg=C["dim"], fg=C["bg"], font=font(8, "semibold"),
                    padx=7, pady=1)


def wrap_to_width(label):
    """Перенос рядка за фактичною шириною мітки (pack з fill="x"): довгий текст не розпирає картку."""
    label.bind("<Configure>", lambda e: label.configure(wraplength=max(e.width, 1)))
    return label


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

    # Чи прокручується зараз сторінка з повзунком — тоді коліщатко гортає її, а не змінює значення
    # (інакше на малому екрані, гортаючи налаштування, легко випадково посунути повзунок)
    page_scrolls = staticmethod(lambda: False)

    def wheel(self, event):
        if not self.enabled or self.page_scrolls():
            return None  # подію обробить вікно — прокрутка сторінки
        self.set(self.snap(self.value + (self.step if event.delta > 0 else -self.step)))
        self.on_change(self.value)
        return "break"

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


class ScrollArea(tk.Frame):
    """Сторінка головного вікна з вертикальною прокруткою: якщо вміст вищий за вікно (малий екран),
    його гортають коліщатком або тонкою смугою праворуч; якщо нижчий — він розтягується на всю висоту."""
    BAR = 6

    def __init__(self, parent):
        bg = parent["bg"]
        super().__init__(parent, bg=bg)
        self.bar = tk.Canvas(self, width=self.BAR, bg=bg, highlightthickness=0)
        self.bar.pack(side="right", fill="y", padx=(8, 0))
        # width/height = 1: розмір полотна задає вікно, а не вміст
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, width=1, height=1, yscrollincrement=24)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.item = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.relayout())
        self.bar.bind("<Button-1>", self.drag)
        self.bar.bind("<B1-Motion>", self.drag)
        self._key = None

    def scrollable(self):
        return self.inner.winfo_reqheight() > self.canvas.winfo_height() + 1

    def relayout(self):
        """Ширина вмісту — як у полотна, висота — не менша за полотно; викликається й щосекунди,
        бо вміст може вирости (рядки розкладу, склянки)."""
        cw, ch, rh = self.canvas.winfo_width(), self.canvas.winfo_height(), self.inner.winfo_reqheight()
        if (cw, ch, rh) != self._key:
            self._key = (cw, ch, rh)
            self.canvas.itemconfigure(self.item, width=cw, height=max(ch, rh))
            self.canvas.configure(scrollregion=(0, 0, cw, max(ch, rh)))
        self.draw_bar()

    def draw_bar(self):
        self.bar.delete("all")
        if not self.scrollable():
            return
        top, bottom = self.canvas.yview()
        h = self.bar.winfo_height()
        self.bar.create_rectangle(0, 0, self.BAR, h, fill=C["card"], outline="")
        self.bar.create_rectangle(0, top * h, self.BAR, max(bottom * h, top * h + 24), fill=C["dim"], outline="")

    def scroll(self, units):
        if self.scrollable():
            self.canvas.yview_scroll(units, "units")
            self.draw_bar()

    def drag(self, event):
        if self.scrollable():
            top, bottom = self.canvas.yview()
            self.canvas.yview_moveto(event.y / max(self.bar.winfo_height(), 1) - (bottom - top) / 2)
            self.draw_bar()


class Toggle(tk.Frame):
    def __init__(self, parent, text, value, on_change):
        bg = parent["bg"]
        super().__init__(parent, bg=bg, cursor="hand2")
        self.value, self.on_change = value, on_change
        # Перемикач — праворуч першим, підпис забирає решту й переноситься: у вузькій колонці
        # довгий підпис інакше виштовхував перемикач за край картки
        self.canvas = tk.Canvas(self, width=46, height=24, bg=bg, highlightthickness=0, cursor="hand2")
        self.canvas.pack(side="right", padx=(8, 0))
        label = wrap_to_width(tk.Label(self, text=text, bg=bg, fg=C["text"], font=font(11), cursor="hand2",
                                       anchor="w", justify="left", wraplength=180))
        label.pack(side="left", fill="x", expand=True)
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
        today = dt.date.today()
        for meal in MEALS:  # з'їдене сьогодні до перезапуску — без повторного нагадування
            if self.stats.day(today)[f"ate_{meal}"]:
                self.sched.meal_results[(today, meal)] = "eat"
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
        self.meal_win = None
        self.meal_demo = False
        self.last_tick = time.monotonic()
        self.icon_key = None
        self.tooltip = None
        self.instance = None  # system.SingleInstance — щоб друга копія могла попросити показати вікно
        self.update_info = None  # (версія, адреса релізу), якщо на GitHub є новіша версія
        self.last_update_check = None  # time.monotonic() останньої перевірки
        self.stats_range = 7  # графік статистики: 7 чи 30 днів
        self.work_pending = 0.0  # час за комп'ютером, ще не записаний у статистику (пишемо раз на хвилину)

        self.icon = system.make_tray_icon(pystray, "Rhythmos", make_icon(0, False), APP_NAME, self.build_menu())
        system.start_tray(self.icon, self.root)
        system.on_reopen(self.root, self.open_main)

        self.root.after(1000, self.loop)
        self.root.after(100, self.process_queue)
        self.root.after(UPDATE_CHECK_DELAY_MS, self.check_updates)

    # --- оновлення ---

    def check_updates(self, repeat=True):
        """Щогодини питає GitHub про останній реліз; мережа — у фоновому потоці.
        repeat=False — позачергова перевірка (відкриття головного вікна), без нового розкладу."""
        if self.cfg["check_updates"] and not getattr(self, "updating", False):
            self.last_update_check = time.monotonic()
            threading.Thread(target=lambda: self.queue.put(("update", updates.fetch_latest())), daemon=True).start()
        if repeat:
            self.root.after(UPDATE_CHECK_INTERVAL_MS, self.check_updates)

    def recheck_updates_soon(self):
        """Відкрили головне вікно — варто знати про нову версію, не чекаючи щогодинної перевірки."""
        last = self.last_update_check
        if last is not None and time.monotonic() - last >= UPDATE_RECHECK_ON_OPEN_SEC:
            self.check_updates(repeat=False)

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
                self.close_meal_window()  # «Продовжуємо?» більше не потрібне
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
            self.flush_work_time()
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
            elif event == "day_end":
                self.show_day_end()
        if was_paused and self.sched.paused_until is None:
            self.icon.update_menu()
        s = self.sched
        if not (s.in_break or s.eating or s.paused):
            self.work_pending += delta
            if self.work_pending >= 60:
                self.flush_work_time()
        self.update_break_warning()
        self.update_tray()
        self.refresh_main()
        self.root.after(1000, self.loop)

    def flush_work_time(self):
        seconds = int(self.work_pending)
        if seconds:
            self.stats.add("work_sec", seconds)
            self.work_pending -= seconds

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
                banner = tk.Frame(win, bg=C["bg"])
                banner.place(x=28, y=22)
                demo_badge(banner).pack(side="left")
                tk.Label(banner, text=t("demo_esc"), bg=C["bg"], fg=C["dim"], font=font(10)).pack(side="left", padx=8)
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
        state["elapsed"] = state.get("elapsed", 0) + 1
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
        elapsed = self.break_state.get("elapsed", 0) if self.break_state else 0
        self.close_break_windows()
        if demo:
            if self.main_win:
                self.main_win.focus_force()
            return
        if elapsed:
            self.stats.add("active_sec", elapsed)
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
        # Віконця живуть у тому самому куті: попередження про перерву, кінець дня й віконце їжі
        # лишаємо й ставимо воду над ними, решту сповіщень закриваємо
        keep = self.toast_win if getattr(self, "toast_kind", None) in ("warning", "day_end") else None
        if not keep:
            self.close_toast()
        right, bottom = self.corner(self.meal_win, keep)
        width = 420
        win = tk.Toplevel(self.root, bg=C["panel"], highlightthickness=2,
                         highlightbackground=C["water"], highlightcolor=C["water"])  # рамка однакова й у фокусі
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
            demo_badge(head).pack(side="right", padx=8)
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
        self.show_meal_window(meal, "remind", demo)

    def show_meal_over(self):
        """Пауза на їжу скінчилась — питаємо, чи продовжувати. Без відповіді перерви так і стоять."""
        self.show_meal_window(self.sched.eating, "over")

    def show_meal_window(self, meal, mode, demo=False):
        """Віконце їжі за зразком води: тарілки за день, текст, порада й кнопки.
        mode: "remind" — час їсти, "over" — «Продовжуємо?». Само не зникає: людина могла відійти."""
        if self.meal_win:
            if demo and not self.meal_demo:
                return  # справжнє нагадування важливіше за демо
            self.meal_win.destroy()
            self.meal_win = None
        self.meal_demo = demo
        keep = self.toast_win if getattr(self, "toast_kind", None) in ("warning", "day_end") else None
        if not keep:
            self.close_toast()
        right, bottom = self.corner(self.water_win, keep)
        width = 440
        win = tk.Toplevel(self.root, bg=C["panel"], highlightthickness=2,
                         highlightbackground=C["meal"], highlightcolor=C["meal"])  # рамка однакова й у фокусі
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        self.meal_win = win

        now = dt.datetime.now()
        meals = [m for m in MEALS if self.cfg[f"{m}_enabled"] or m == meal]
        head = tk.Frame(win, bg=C["panel"])
        head.pack(fill="x", padx=20, pady=(16, 0))
        title = t(f"meal_title_{meal}") if mode == "remind" else t("meal_over_title")
        tk.Label(head, text=title, bg=C["panel"], fg=C["meal"], font=font(16, "semibold")).pack(side="left")
        tk.Label(head, text=t("x_of_y", a=meals.index(meal) + 1, b=len(meals)), bg=C["panel"],
                 fg=C["muted"], font=font(11)).pack(side="right")
        if demo:
            demo_badge(head).pack(side="right", padx=8)
            win.bind("<Escape>", lambda e: self.close_meal_window())
        # Тарілки за день: з'їдено / зараз / ще буде / пропущено — як склянки у воді
        plates = tk.Frame(win, bg=C["panel"])
        plates.pack(anchor="w", padx=18, pady=(8, 10))
        for i, m in enumerate(meals):
            if m == meal:
                state = "done" if mode == "over" else "now"
            else:
                state = PLATE_STATES.get(self.sched.meal_state(m, now)[0], "later")
            cell = tk.Frame(plates, bg=C["panel"])
            cell.grid(row=0, column=i, padx=(2, 16))
            tk.Label(cell, image=plate_image(30, state, C["panel"]), bg=C["panel"]).pack()
            tk.Label(cell, text=t(f"meal_{m}"), bg=C["panel"], fg=C["text"] if m == meal else C["muted"],
                     font=font(9)).pack()
            tk.Label(cell, text=fmt_clock(self.cfg[f"{m}_at"]), bg=C["panel"], fg=C["dim"], font=font(8)).pack()
        if mode == "remind":
            text = t("meal_text", time=fmt_minutes(self.cfg["meal_pause_min"]))
        else:
            text = t("meal_over_text")
        tk.Label(win, text=text, bg=C["panel"], fg=C["text"], font=font(11),
                 wraplength=width - 44, justify="left").pack(anchor="w", padx=20)
        if mode == "remind":
            tk.Label(win, text=random.choice(content("meal_tips")), bg=C["panel"], fg=C["muted"], font=font(10),
                     wraplength=width - 44, justify="left").pack(anchor="w", padx=20, pady=(6, 0))
        buttons = tk.Frame(win, bg=C["panel"])
        buttons.pack(anchor="e", padx=16, pady=14)
        if mode == "remind":
            actions = ((t("skip"), "skip", False), (t("meal_snooze", min=MEAL_SNOOZE_MIN), "snooze", False),
                       (t("meal_go"), "eat", True))
        else:
            actions = ((t("meal_more", min=MEAL_SNOOZE_MIN), "more", False), (t("resume"), "continue", True))
        for label, answer, primary in actions:
            flat_button(buttons, label, lambda a=answer: self.answer_meal(a), size=11,
                        bg=C["meal"] if primary else C["bg"], fg=C["on_meal"] if primary else C["text"],
                        image=check_mark(16, C["on_meal"]) if primary else None).pack(side="left", padx=4)
        win.update_idletasks()
        width = max(width, win.winfo_reqwidth())
        height = win.winfo_reqheight()
        win.geometry(f"{width}x{height}+{right - width - 16}+{bottom - height - 16}")
        if demo:
            win.after(60_000, lambda: self.close_meal_window() if self.meal_win is win else None)
            win.focus_force()
        self.beep()

    def close_meal_window(self):
        if self.meal_win:
            self.meal_win.destroy()
            self.meal_win = None
        if self.meal_demo and self.main_win:
            self.main_win.focus_force()
        self.meal_demo = False

    def answer_meal(self, answer):
        demo = self.meal_demo
        self.close_meal_window()
        if demo:
            return
        if answer in ("skip", "snooze"):
            self.sched.meal_answered(answer)
        elif answer == "eat":
            self.go_eat()
        elif answer == "more":
            self.sched.extend_meal()
        elif answer == "continue":
            self.finish_meal()

    def go_eat(self):
        if self.break_state and not self.break_state["demo"]:  # перерва почалась, поки висіло нагадування
            self.close_break_windows()
            self.sched.finish_break()
        meal = self.sched.meal_open
        self.sched.meal_answered("eat")
        if meal:
            self.set_meal_eaten(meal, True)
        self.icon.update_menu()

    def set_meal_eaten(self, meal, eaten):
        """Позначка «з'їдено» для їжі за сьогодні: з нагадування («Йду їсти») або тарілкою на «Стані»."""
        today = dt.date.today()
        now = dt.datetime.now()
        self.stats.set(f"ate_{meal}", int(eaten))
        self.stats.set("meals", sum(self.stats.day(today)[f"ate_{m}"] for m in MEALS))
        # Коли насправді поїли — на шкалі дня тарілка стоїть у цей момент, а не в запланований
        self.stats.set_times(f"ate_{meal}_at", [now.hour * 60 + now.minute] if eaten else [])
        if eaten:
            self.sched.meal_results[(today, meal)] = "eat"
            self.sched.meal_snoozed.pop(meal, None)
            if self.sched.meal_open == meal and not self.meal_demo:  # нагадування більше не потрібне
                self.sched.meal_open = None
                self.close_meal_window()
        elif self.sched.meal_results.get((today, meal)) == "eat":
            del self.sched.meal_results[(today, meal)]
        self.refresh_main()

    def finish_meal(self):
        self.sched.finish_meal()
        self.icon.update_menu()

    # --- кінець робочого дня ---

    def show_day_end(self, demo=False):
        """«Робочий день скінчився» з підсумком дня. «Завершити день» — пауза до ранку."""
        today = self.stats.day(dt.date.today())
        text = t("day_end_text", breaks=today["mini_done"] + today["long_done"], volume=fmt_volume(today["water"]))
        answer = (lambda _answer: None) if demo else self.answer_day_end
        actions = [(t("day_end_snooze", min=DAY_END_SNOOZE_MIN), lambda: answer("snooze"), False),
                   (t("day_end_finish"), lambda: answer("finish"), True)]
        self.show_toast(t("day_end_title"), text, actions, timeout_ms=60_000 if demo else 3 * 60 * 60_000,
                        kind="day_end", on_dismiss=None if demo else lambda: answer("snooze"), demo=demo)
        self.beep()

    def answer_day_end(self, answer):
        self.sched.day_end_answered(answer)
        if answer == "finish":
            now = dt.datetime.now()
            self.stats.set("day_end", now.hour * 60 + now.minute)
            self.handle(("pause", None))

    # --- власні сповіщення ---

    def corner(self, *below):
        """Правий нижній кут робочої області (без панелі завдань) для нового віконця;
        якщо там уже стоять віконця з `below` — над ними."""
        screens = system.monitors()
        if screens:
            _l, _t, right, bottom = screens[0][4]
        else:
            right, bottom = self.root.winfo_screenwidth(), self.root.winfo_screenheight() - 48
        for win in below:
            if win:
                bottom = min(bottom, win.winfo_rooty())
        return right, bottom

    def show_toast(self, title, text, actions=(), timeout_ms=10_000, kind="info", on_dismiss=None, demo=False):
        """Спливаюче віконце в куті екрана. Не покладаємося на системні сповіщення:
        користувач міг їх вимкнути (на Windows вони тоді просто мовчки зникають),
        а на macOS вони ненадійні для програм без підпису Apple.
        actions: [(напис, функція, головна_кнопка?)]; on_dismiss — якщо віконце зникло без натискання кнопки
        (тайм-аут або його витіснило інше сповіщення)."""
        self.close_toast()
        right, bottom = self.corner(self.water_win, self.meal_win)  # не перекриваємо воду й їжу
        width = 380
        win = tk.Toplevel(self.root, bg=C["panel"], highlightthickness=2,
                         highlightbackground=C["accent"], highlightcolor=C["accent"])  # рамка однакова й у фокусі
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        head = tk.Frame(win, bg=C["panel"])
        head.pack(fill="x", padx=18, pady=(14, 2))
        tk.Label(head, text=title, bg=C["panel"], fg=C["accent"], font=font(13, "semibold")).pack(side="left")
        if demo:
            demo_badge(head).pack(side="right", padx=(8, 0))
            win.bind("<Escape>", lambda e: self.close_toast())
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
            self.log_water_times(1)
        self.sched.water_answered(drank)

    def log_water_times(self, delta):
        """Час кожної склянки — для шкали дня: додані склянки — «зараз», зняті — останні з кінця."""
        today = dt.date.today()
        times = self.stats.times(today, "water_at")
        if delta > 0:
            now = dt.datetime.now()
            times += [now.hour * 60 + now.minute] * delta
        else:
            times = times[:max(0, len(times) + delta)]
        self.stats.set_times("water_at", times)

    # --- головне вікно ---

    def open_main(self):
        system.activate_app()  # macOS: інакше вікно програми рядка меню відкривається позаду інших
        self.recheck_updates_soon()
        if self.main_win:
            self.main_win.deiconify()
            self.main_win.lift()
            self.main_win.focus_force()
            return
        win = tk.Toplevel(self.root, bg=C["bg"])
        # Приховане, доки не побудовані сторінки й не відомий розмір: на macOS розмір, заданий уже
        # показаному вікну, не застосовувався — лишалась сама шапка (2.2.0–2.5.0)
        win.withdraw()
        win.title(f"{APP_NAME} {__version__}")
        win.protocol("WM_DELETE_WINDOW", self.close_main)
        self.window_icon = ImageTk.PhotoImage(make_app_icon(64))
        win.iconphoto(False, self.window_icon)
        self.main_win = win
        self.w = {}
        # Розкладка під екран: колонки налаштувань, картки статистики в ряд
        work = self.work_area()
        self.layout = main_layout(work[2] - work[0] - 40)
        Slider.page_scrolls = staticmethod(self.page_scrolls)

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
        self.pages, self.page_frames, self.tab_buttons = {}, {}, {}
        self.current_page = None
        for key, builder in (("status", self.build_status_page),
                             ("stats", self.build_stats_page),
                             ("settings", self.build_settings_page)):
            area = ScrollArea(body)  # на малому екрані сторінка прокручується
            page = builder(area.inner)
            page.pack(fill="both", expand=True)
            self.pages[key], self.page_frames[key] = area, page
            btn = tk.Label(tabs, text=t(f"tab_{key}"), font=font(11), padx=16, pady=6, cursor="hand2")
            btn.pack(side="left", padx=2, pady=2)
            btn.bind("<Button-1>", lambda e, k=key: self.show_page(k))
            self.tab_buttons[key] = btn
        win.bind("<MouseWheel>", self.on_main_wheel)
        self.fit_main_window(header, work)
        win.deiconify()
        win.update()
        system.style_window(win)  # темний заголовок — уже для показаного вікна
        self.show_page("status")

    def work_area(self):
        """Робоча область основного екрана (без панелі завдань / рядка меню й Dock): (l, t, r, b)."""
        screens = system.monitors()
        if screens:
            return screens[0][4]
        return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight() - 48

    def fit_main_window(self, header, work):
        """Вікно під найбільшу сторінку, але не більше за робочу область екрана — тоді сторінки
        прокручуються. Розмір залежить від мови, шрифтів і масштабу екрана, тож не задаємо його числами."""
        win = self.main_win
        win.update_idletasks()  # розміри, що просять сторінки, рахуються й для прихованого вікна
        frames = self.page_frames.values()
        left, top, right, bottom = work
        # Відступи тіла (24 + 24), смуга прокрутки (6 + 8); заголовка (18 + 10) і тіла (4 + 20)
        width = max(self.layout["width"], *(page.winfo_reqwidth() + 48 + ScrollArea.BAR + 8 for page in frames))
        height = header.winfo_reqheight() + 28 + 24 + max(page.winfo_reqheight() for page in frames)
        width = min(width, right - left - 40)
        height = min(height, bottom - top - TITLE_BAR - 20)
        x = left + max(0, (right - left - width) // 2)
        y = top + max(0, (bottom - top - height - TITLE_BAR) // 2)
        win.geometry(f"{width}x{height}+{x}+{y}")
        # Лише після розміру: на macOS resizable(False, False) фіксує поточний розмір як мінімальний
        # і максимальний — увімкнене раніше, воно лишало вікно таким, яким його вперше показали (сама шапка)
        win.resizable(False, False)

    def close_main(self):
        self.main_win.destroy()
        self.main_win = None
        self.w = {}

    def page_scrolls(self):
        area = self.pages.get(self.current_page) if self.main_win else None
        return bool(area and area.scrollable())

    def on_main_wheel(self, event):
        """Коліщатко над будь-якою частиною головного вікна гортає поточну сторінку (якщо є куди)."""
        area = self.pages.get(self.current_page)
        if not area or not event.delta:
            return
        units = -int(event.delta / 120) if system.IS_WINDOWS else -event.delta  # macOS дає дрібні кроки
        area.scroll(units or (-1 if event.delta > 0 else 1))

    def show_page(self, key):
        for page in self.pages.values():
            page.pack_forget()
        self.current_page = key
        area = self.pages[key]
        area.pack(fill="both", expand=True)
        # Одразу розкласти вміст за справжнім розміром полотна: на macOS перша сторінка інакше
        # лишалась порожньою, доки не спрацює щосекундне оновлення
        self.main_win.update_idletasks()
        area.relayout()
        area.canvas.yview_moveto(0)
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
        # Розклад: довга перерва й кінець дня — рядок «назва … стан», оновлюється щосекунди
        tk.Label(left, text=t("card_schedule").upper(), bg=C["card"], fg=C["accent"],
                 font=font(9, "semibold")).pack(anchor="w", pady=(24, 6))
        self.w["schedule"] = tk.Frame(left, bg=C["card"])
        self.w["schedule"].pack(fill="x")
        self.w["schedule_rows"] = {}

        right = tk.Frame(page, bg=C["bg"])
        right.pack(side="left", fill="both", expand=True)

        # Вода й харчування — поруч, однакові за будовою: відлік, рядок стану, склянки чи тарілки
        top = tk.Frame(right, bg=C["bg"])
        top.pack(fill="x")
        water = card(top, t("card_water"))
        water.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        meals = card(top, t("card_meals"))
        meals.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        for column in (0, 1):
            top.columnconfigure(column, weight=1, uniform="top")
        self.build_meal_card(meals)
        self.w["water"] = tk.Label(water, bg=C["card"], fg=C["water"], font=font(28, "light"))
        self.w["water"].pack(anchor="w")
        self.w["water_sub"] = wrap_to_width(tk.Label(water, bg=C["card"], fg=C["muted"], font=font(10), height=2,
                                                     justify="left", anchor="nw", wraplength=260))
        self.w["water_sub"].pack(fill="x")
        # Склянки за сьогодні: клік по склянці виставляє кількість (як тарілки в картці «Їжа»)
        self.w["glasses"] = tk.Frame(water, bg=C["card"])
        self.w["glasses"].pack(anchor="w", pady=(4, 0))
        self.w["glasses_key"] = None

        today = card(right, t("card_today"))
        today.pack(fill="both", expand=True, pady=(14, 0))
        # Шкала дня внизу картки: від ранку до кінця робочого дня, їжа, кінець дня й «зараз»
        self.w["timeline"] = tk.Canvas(today, height=TIMELINE_HEIGHT, bg=C["card"], highlightthickness=0)
        self.w["timeline"].pack(side="bottom", fill="x", pady=(10, 0))
        self.w["timeline"].bind("<Configure>", lambda e: self.draw_timeline(force=True))
        grid = tk.Frame(today, bg=C["card"])
        grid.pack(fill="x")
        metrics = (("breaks", t("m_breaks"), C["accent"]), ("skipped", t("m_skipped"), C["muted"]),
                   ("postponed", t("m_postponed"), C["muted"]), ("active", t("m_active"), C["accent"]),
                   ("work", t("m_work"), C["text"]), ("meals", t("m_meals"), C["meal"]))
        for i, (key, caption, color) in enumerate(metrics):
            cell = tk.Frame(grid, bg=C["card"])
            cell.grid(row=i // 3, column=i % 3, sticky="nw", pady=(0 if i < 3 else 14, 0))
            grid.columnconfigure(i % 3, weight=1, uniform="today")
            self.w[f"today_{key}"] = tk.Label(cell, bg=C["card"], fg=color, font=font(28, "light"))
            self.w[f"today_{key}"].pack(anchor="w")
            tk.Label(cell, text=caption, bg=C["card"], fg=C["muted"], font=font(10)).pack(anchor="w")
            self.w[f"today_{key}_sub"] = tk.Label(cell, bg=C["card"], fg=C["dim"], font=font(9))
            self.w[f"today_{key}_sub"].pack(anchor="w")
        return page

    def build_meal_card(self, box):
        self.w["meal"] = tk.Label(box, bg=C["card"], fg=C["meal"], font=font(28, "light"))
        self.w["meal"].pack(anchor="w")
        self.w["meal_sub"] = wrap_to_width(tk.Label(box, bg=C["card"], fg=C["muted"], font=font(10), height=2,
                                                    justify="left", anchor="nw", wraplength=260))
        self.w["meal_sub"].pack(fill="x")
        self.w["plates"] = tk.Frame(box, bg=C["card"])
        self.w["plates"].pack(anchor="w", pady=(4, 0))
        self.w["plates_key"] = None

    def refresh_meal_card(self, now):
        """Картка «Їжа»: відлік до наступної їжі, «сьогодні 1 з 3» і тарілки увімкнених прийомів їжі."""
        s, today = self.sched, self.stats.day(now.date())
        enabled = [m for m in MEALS if self.cfg[f"{m}_enabled"]]
        eaten = sum(today[f"ate_{m}"] for m in enabled)
        progress = t("meals_today", n=eaten, total=len(enabled))
        hover = self.w.get("plate_hover")
        if hover is not None:  # курсор на тарілці — що буде після кліку
            progress += f"  →  {hover}"
        upcoming = s.next_meal(now)
        if not enabled:
            value, sub = "—", t("water_off")
        elif s.eating:
            value, sub = t("meal_enjoy"), t("sch_eating", time=f"{s.eating_until:%H:%M}") + "\n" + progress
        elif upcoming and upcoming[1] is None:
            value, sub = t("meal_now"), progress
        elif upcoming:
            value = fmt_time((upcoming[1] - now).total_seconds())
            sub = t(f"meal_next_{upcoming[0]}") + "\n" + progress  # два рядки: що далі й підсумок дня
        else:
            value, sub = t("meals_done"), progress
        self.w["meal"].configure(text=value)
        self.w["meal_sub"].configure(text=sub)
        self.render_plates(enabled, now)

    def render_plates(self, enabled, now):
        """Тарілки увімкнених прийомів їжі: клік позначає з'їденою чи знімає позначку, наведення — попередній вигляд."""
        today = self.stats.day(now.date())
        states = []
        for meal in enabled:
            state = PLATE_STATES.get(self.sched.meal_state(meal, now)[0], "later")
            states.append("done" if today[f"ate_{meal}"] else ("later" if state == "done" else state))
        key = (tuple(enabled), tuple(states), tuple(self.meal_time(m, now.date()) for m in enabled))
        if self.w.get("plates_key") == key:
            return
        self.w["plates_key"] = key
        self.w["plate_hover"] = None
        frame = self.w["plates"]
        for child in frame.winfo_children():
            child.destroy()
        plates = []
        eaten_count = sum(state == "done" for state in states)

        def preview(index):
            """None — звичайний вигляд; інакше показуємо, що зробить клік по тарілці index."""
            self.w["plate_hover"] = None if index is None else eaten_count + (-1 if states[index] == "done" else 1)
            for i, plate in enumerate(plates):
                state = states[i]
                if i == index:
                    state = "remove" if state == "done" else "add"
                plate.configure(image=plate_image(30, state, C["card"]))
            self.refresh_main()

        for i, (meal, state) in enumerate(zip(enabled, states)):
            cell = tk.Frame(frame, bg=C["card"], cursor="hand2")
            cell.grid(row=0, column=i, padx=(0, 14))
            plate = tk.Label(cell, image=plate_image(30, state, C["card"]), bg=C["card"], cursor="hand2")
            plate.pack()
            name = tk.Label(cell, text=t(f"meal_{meal}"), bg=C["card"], fg=C["muted"], font=font(9), cursor="hand2")
            name.pack()
            at = tk.Label(cell, text=fmt_clock(self.meal_time(meal, now.date())), bg=C["card"], fg=C["dim"],
                          font=font(8), cursor="hand2")
            at.pack()
            for widget in (cell, plate, name, at):
                widget.bind("<Button-1>", lambda e, m=meal, done=state == "done": self.set_meal_eaten(m, not done))
                widget.bind("<Enter>", lambda e, i=i: preview(i))
                widget.bind("<Leave>", lambda e: preview(None))
            plates.append(plate)

    def meal_time(self, meal, date):
        """Хвилина дня для їжі: коли насправді поїли (якщо позначено), інакше — запланований час."""
        if self.stats.day(date)[f"ate_{meal}"]:
            eaten_at = self.stats.times(date, f"ate_{meal}_at")
            if eaten_at:
                return eaten_at[0]
        return self.cfg[f"{meal}_at"]

    def timeline_marks(self, now):
        """Позначки шкали дня: (хвилина, назва, колір, стан) — їжа ("done"/"now"/"later"/"skip") і кінець дня.
        З'їдене стоїть у момент, коли поїли, — так на шкалі видно, наскільки регулярно це відбувається."""
        today = self.stats.day(now.date())
        marks = []
        for meal in MEALS:
            if self.cfg[f"{meal}_enabled"] or today[f"ate_{meal}"]:
                if today[f"ate_{meal}"]:
                    state = "done"
                else:
                    state = PLATE_STATES.get(self.sched.meal_state(meal, now)[0], "later")
                    state = "later" if state == "done" else state
                marks.append((self.meal_time(meal, now.date()), t(f"meal_{meal}"), C["meal"], state))
        if self.cfg["day_end_enabled"]:
            finished = today["day_end"]
            marks.append((finished or self.cfg["day_end_at"], t("sch_day_end"), C["accent"],
                          "done" if finished else "later"))
        return sorted(marks, key=lambda mark: mark[0])

    def draw_timeline(self, force=False):
        """Смуга дня: заповнена до «зараз»; кружечки їжі й кінця дня з підписами над смугою, сині точки —
        коли пили воду, синій кружечок — наступне нагадування; під смугою — години.
        Малюємо згладжено через Pillow і лише коли щось змінилося (раз на хвилину чи після кліку)."""
        c = self.w.get("timeline")
        if not c:
            return
        now = dt.datetime.now()
        width = c.winfo_width()
        if width < 100:
            return
        marks = self.timeline_marks(now)
        minute = now.hour * 60 + now.minute
        drinks = self.stats.times(now.date(), "water_at")
        s = self.sched
        next_water = None
        if self.cfg["water_enabled"] and not s.water_open and not (s.paused and s.pause_water):
            next_water = minute + round(s.water_remaining / 60)
        idle = s.paused or bool(s.eating)
        key = (width, minute, tuple(marks), tuple(drinks), next_water, idle)
        if not force and key == getattr(self, "_timeline_key", None):
            return
        self._timeline_key = key
        # Межі шкали: від ранку (не пізніше 8:00 чи першої події) до кінця дня (не раніше 18:00), по годинах
        times = [m[0] for m in marks] + drinks
        start = (min([8 * 60] + times) - 30) // 60 * 60
        end = -(-(max([18 * 60] + times) + 30) // 60) * 60
        pad, y = 16, 48

        def x_of(m):
            return pad + (width - 2 * pad) * (min(max(m, start), end) - start) / (end - start)

        xn = x_of(minute)

        def paint(d, sc):
            r = 3 * sc
            d.rounded_rectangle((pad * sc - r, y * sc - r, (width - pad) * sc + r, y * sc + r), radius=r,
                                fill=rgba(C["track"]))
            if minute > start:
                d.rounded_rectangle((pad * sc - r, y * sc - r, xn * sc + r, y * sc + r), radius=r,
                                    fill=rgba(C["dim"] if idle else C["accent_dark"]))
            # Усі позначки в одному стилі: кружечок з обідком кольору картки (відділяє від смуги й сусідів);
            # ring — товщина контуру для порожнього кружечка («ще буде»), None — заповнений
            halo = 1.5 * sc

            def dot(x, radius, color, ring=None):
                cx, cy, rr = x * sc, y * sc, radius * sc
                d.ellipse((cx - rr - halo, cy - rr - halo, cx + rr + halo, cy + rr + halo), fill=rgba(C["card"]))
                d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=rgba(color))
                if ring:
                    inner = rr - ring * sc
                    d.ellipse((cx - inner, cy - inner, cx + inner, cy + inner), fill=rgba(C["card"]))

            for m in drinks:  # склянки
                dot(x_of(m), 5, C["water"])
            # Наступне нагадування про воду — лише якщо не ховається за позначкою їжі чи кінця дня
            if (next_water is not None and next_water <= end
                    and all(abs(x_of(next_water) - x_of(m[0])) >= 14 for m in marks)):
                dot(x_of(next_water), 5, C["water"], ring=1.8)
            for m, _name, color, state in marks:  # їжа й кінець дня
                if state == "done":
                    dot(x_of(m), 7, color)
                else:
                    dot(x_of(m), 7, C["dim"] if state == "skip" else color, ring=2)
            dot(xn, 5, C["text"])  # «зараз»

        self.timeline_photo = ImageTk.PhotoImage(smooth_image(width, TIMELINE_HEIGHT, paint, C["card"]))
        c.delete("all")
        c.create_image(0, 0, anchor="nw", image=self.timeline_photo)

        def place(item, x):
            """Не даємо підпису вийти за краї полотна."""
            x0, _y0, x1, _y1 = c.bbox(item)
            shift = max(0, 2 - x0) - max(0, x1 - (width - 2))
            if shift:
                c.move(item, shift, 0)
            return c.bbox(item)

        # Години під смугою: крок такий, щоб підписи не злипались
        span = width - 2 * pad
        step = next((h for h in (1, 2, 3, 4, 6) if span * h * 60 / (end - start) >= 46), 6)
        for hour in range(-(-start // (60 * step)) * step, end // 60 + 1, step):
            place(c.create_text(x_of(hour * 60), y + 20, text=f"{hour}:00", fill=C["dim"], font=font(8)),
                  x_of(hour * 60))
        # Підписи позначок над смугою у два яруси: якщо підпис налазить на сусіда — вище
        placed = {0: [], 1: []}
        for m, name, color, state in marks:
            x = x_of(m)
            fill = color if state in ("now", "done") else C["muted"]
            for tier in (0, 1):
                item = c.create_text(x, y - 18 - tier * 16, text=f"{name} {fmt_clock(m)}", font=font(9), fill=fill)
                box = place(item, x)
                if tier == 1 or all(box[0] > b[2] + 8 or box[2] < b[0] - 8 for b in placed[0]):
                    placed[tier].append(box)
                    break
                c.delete(item)

    def schedule_rows(self, now):
        """Рядки розкладу на сьогодні: (ключ, назва, стан, підсвітити?). Їжа — у власній картці поруч з водою."""
        s, cfg = self.sched, self.cfg
        timed = []  # (хвилина дня, рядок) — події з часом ідуть за ним
        left = s.breaks_until_long()
        long_row = ("long", t("sch_long"), t("long_next") if left == 1 else fmt_after_minis(left - 1), left == 1)
        if cfg["day_end_enabled"]:
            finished = self.stats.day(now.date())["day_end"]
            at = dt.datetime.combine(now.date(), dt.time()) + dt.timedelta(minutes=cfg["day_end_at"])
            if finished:
                text, hot = t("sch_finished", time=fmt_clock(finished)), False
            elif s.day_end_snoozed:
                text, hot = t("sch_snoozed", time=f"{s.day_end_snoozed:%H:%M}"), True
            elif now < at:
                left_min = max(1, round((at - now).total_seconds() / 60))
                text, hot = t("sch_in", time=fmt_clock(cfg["day_end_at"]), left=fmt_minutes(left_min)), False
            else:
                text, hot = t("sch_rest", time=fmt_clock(cfg["day_end_at"])), True
            timed.append((cfg["day_end_at"], ("day_end", t("sch_day_end"), text, hot)))
        return [long_row] + [row for _minute, row in sorted(timed, key=lambda item: item[0])]

    def refresh_schedule(self):
        """Перебудовує рядки лише коли змінився їх набір; тексти оновлює щосекунди."""
        frame, widgets = self.w["schedule"], self.w["schedule_rows"]
        rows = self.schedule_rows(dt.datetime.now())
        if [r[0] for r in rows] != list(widgets):
            for child in frame.winfo_children():
                child.destroy()
            widgets.clear()
            for i, (key, name, _text, _hot) in enumerate(rows):
                tk.Label(frame, text=name, bg=C["card"], fg=C["muted"], font=font(10)).grid(
                    row=i, column=0, sticky="w", pady=3)
                widgets[key] = tk.Label(frame, bg=C["card"], font=font(10))
                widgets[key].grid(row=i, column=1, sticky="e", pady=3)
            frame.columnconfigure(1, weight=1)
        for key, _name, text, hot in rows:
            widgets[key].configure(text=text, fg=(C["meal"] if key in MEALS else C["accent"]) if hot else C["text"])

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
        """Картки нагорі — один день (сьогодні або той, на який наведено курсор на графіку);
        під ними графік за 7 або 30 днів і підсумки за цей період."""
        page = tk.Frame(parent, bg=C["bg"])
        self.w["stats_day"] = tk.Label(page, bg=C["bg"], fg=C["text"], font=font(12, "semibold"))
        self.w["stats_day"].pack(anchor="w", pady=(0, 8))
        summary = tk.Frame(page, bg=C["bg"])
        summary.pack(fill="x")
        # Порядок, як і всюди: перерви → рух → вода → їжа → робота
        cards = (("day_breaks", t("m_breaks"), C["accent"]), ("day_skipped", t("m_skipped"), C["muted"]),
                 ("day_active", t("m_active"), C["accent"]), ("day_water", t("m_water"), C["water"]),
                 ("day_meals", t("m_meals"), C["meal"]), ("day_work", t("m_work"), C["text"]))
        per_row = self.layout["stat_cards"]  # вузький екран — два ряди по три
        for i, (key, caption, color) in enumerate(cards):
            box = card(summary)
            column = i % per_row
            box.grid(row=i // per_row, column=column, sticky="nsew", pady=(0 if i < per_row else 10, 0),
                     padx=(0 if column == 0 else 5, 0 if column == per_row - 1 else 5))
            summary.columnconfigure(column, weight=1, uniform="sum")
            self.w[key] = tk.Label(box, bg=C["card"], fg=color, font=font(26, "light"))
            self.w[key].pack(anchor="w")
            tk.Label(box, text=caption, bg=C["card"], fg=C["muted"], font=font(10)).pack(anchor="w")
            # Додатковий рядок: % виконаних, відкладені, об'єм води, кінець дня
            self.w[f"{key}_sub"] = tk.Label(box, bg=C["card"], fg=color if key == "day_water" else C["dim"],
                                            font=font(9))
            self.w[f"{key}_sub"].pack(anchor="w")

        chart = card(page)
        chart.pack(fill="both", expand=True, pady=(14, 0))
        head = tk.Frame(chart, bg=C["card"])
        head.pack(fill="x", pady=(0, 4))
        self.w["chart_title"] = tk.Label(head, bg=C["card"], fg=C["accent"], font=font(9, "semibold"))
        self.w["chart_title"].pack(side="left")
        segments = tk.Frame(head, bg=C["panel"])
        segments.pack(side="right")
        self.w["range_buttons"] = {}
        for days in STATS_RANGES:
            btn = tk.Label(segments, text=t("range_days", n=days), font=font(9), padx=10, pady=2, cursor="hand2")
            btn.pack(side="left", padx=2, pady=2)
            btn.bind("<Button-1>", lambda e, d=days: self.set_stats_range(d))
            self.w["range_buttons"][days] = btn
        self.w["chart"] = tk.Canvas(chart, bg=C["card"], highlightthickness=0, height=262, cursor="hand2")
        self.w["chart"].pack(fill="both", expand=True)
        self.w["chart"].bind("<Motion>", self.on_chart_motion)
        self.w["chart"].bind("<Leave>", lambda e: self.highlight_day(None))
        bottom_row = tk.Frame(chart, bg=C["card"])
        bottom_row.pack(fill="x", pady=(6, 0))
        for text, color in ((t("lg_mini"), C["accent"]), (t("lg_long"), C["accent_dark"]),
                            (t("lg_skipped"), C["dim"]), (t("lg_water"), C["water"]), (t("lg_meals"), C["meal"])):
            tk.Label(bottom_row, text="●", bg=C["card"], fg=color, font=font(12)).pack(side="left")
            tk.Label(bottom_row, text=text, bg=C["card"], fg=C["muted"],
                     font=font(10)).pack(side="left", padx=(2, 14))
        for key in ("range_breaks", "range_water", "range_day"):
            self.w[key] = tk.Label(chart, bg=C["card"], fg=C["muted"], font=font(10), justify="left")
            self.w[key].pack(anchor="w", pady=(4, 0))
        return page

    def set_stats_range(self, days):
        if days != self.stats_range:
            self.stats_range = days
            self.draw_stats()

    def draw_stats(self):
        c = self.w.get("chart")
        if not c:
            return
        n = self.stats_range
        today = dt.date.today()
        days = [today - dt.timedelta(days=i) for i in range(n - 1, -1, -1)]
        records = [self.stats.day(d) for d in days]
        self.w["chart_title"].configure(text=t("card_last_n", n=n).upper())
        for d, btn in self.w["range_buttons"].items():
            active = d == n
            btn.configure(bg=C["accent"] if active else C["panel"], fg=C["on_accent"] if active else C["muted"])
        self.draw_range_totals(n, days, records)

        c.delete("all")
        width, height = max(c.winfo_width(), 600), max(c.winfo_height(), 210)
        top, bottom = 24, height - 66
        slot = width / n
        self.chart_info = {"days": days, "records": records, "slot": slot, "top": top, "bottom": bottom,
                           "width": width, "bar": min(44, slot * 0.6), "hover": None}
        peak = max([r["mini_done"] + r["long_done"] + r["skipped"] for r in records] + [4])
        for i in range(5):
            y = bottom - (bottom - top) * i / 4
            c.create_line(0, y, width, y, fill=C["track"] if i == 0 else C["grid"])
        bar = self.chart_info["bar"]
        week = n <= 7  # за тиждень — дні тижня й кількість склянок; за місяць — число кожного п'ятого дня
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
                c.create_text(cx, y - 10, text=total, fill=C["text"], font=font(10 if week else 8, "semibold"))
            if week:
                label = t("today") if day == today else t("weekdays").split()[day.weekday()]
            else:
                label = str(day.day) if (n - 1 - i) % 5 == 0 else ""
            c.create_text(cx, bottom + 14, text=label, fill=C["text"] if day == today else C["muted"],
                          font=font(10 if week else 9))
            # Вода й їжа: заповнений кружечок — норму / усі прийоми їжі виконано, порожній — ні;
            # за тиждень ще й кількість
            meals_planned = sum(self.cfg[f"{m}_enabled"] for m in MEALS)
            for row, (count, full, color) in enumerate((
                    (rec["water"], rec["water"] >= self.cfg["water_goal"], C["water"]),
                    (rec["meals"], meals_planned and rec["meals"] >= meals_planned, C["meal"]))):
                if not count:
                    continue
                ox, oy = (cx - 9 if week else cx), bottom + 33 + row * 18
                c.create_image(ox, oy, image=dot_image(9, color, bool(full), C["card"]))
                if week:
                    c.create_text(ox + 8, oy, text=count, anchor="w", fill=color, font=font(9))
        self.chart_info["bar_tops"] = bar_tops
        self.show_stats_day(n - 1)

    def draw_range_totals(self, n, days, records):
        """Підсумки за період трьома рядками: перерви й рух; вода; їжа й робота."""
        total = {k: sum(r[k] for r in records) for k in Stats.KEYS if k != "day_end"}
        rate = completion_rate(total)
        best = max(range(n), key=lambda i: records[i]["mini_done"] + records[i]["long_done"])
        best_breaks = records[best]["mini_done"] + records[best]["long_done"]
        best_text = t("best_day", day=f"{days[best]:%d.%m}", n=best_breaks) if best_breaks else ""
        self.w["range_breaks"].configure(text=t(
            "range_breaks", n=n, breaks=total["mini_done"] + total["long_done"], skipped=total["skipped"],
            rate=f"{rate}%" if rate is not None else "—", active=fmt_minutes(total["active_sec"] // 60)) + best_text)
        avg_liters = round(total["water"] * i18n.GLASS_LITERS / n, 1)
        self.w["range_water"].configure(text=t(
            "range_water", glasses=fmt_glasses(total["water"]), avg=fmt_volume(avg_liters / i18n.GLASS_LITERS),
            streak=fmt_days(water_streak(self.stats, self.cfg["water_goal"], dt.date.today()))))
        self.w["range_day"].configure(text=t(
            "range_day", meals=total["meals"], work=fmt_minutes(total["work_sec"] // 60)))

    def show_stats_day(self, index):
        """Картки нагорі: дані одного дня з графіка (останній — сьогодні)."""
        info = self.chart_info
        day, rec = info["days"][index], info["records"][index]
        date = f"{day:%d.%m}"
        if day == dt.date.today():
            title = t("stats_today", date=date)
        else:
            title = t("stats_day", weekday=t("weekdays").split()[day.weekday()], date=date)
        self.w["stats_day"].configure(text=title)
        rate = completion_rate(rec)
        values = {
            "day_breaks": (rec["mini_done"] + rec["long_done"], t("done_rate", pct=rate) if rate is not None else ""),
            "day_skipped": (rec["skipped"], t("postponed_n", n=rec["postponed"]) if rec["postponed"] else ""),
            "day_water": (rec["water"], fmt_volume(rec["water"])),
            "day_work": (fmt_hm(rec["work_sec"]),
                         t("day_end_at_tip", time=fmt_clock(rec["day_end"])) if rec["day_end"] else ""),
            "day_active": (rec["active_sec"] // 60, ""),
            "day_meals": (rec["meals"], ""),
        }
        for key, (value, sub) in values.items():
            self.w[key].configure(text=value)
            self.w[f"{key}_sub"].configure(text=sub)

    def on_chart_motion(self, event):
        info = getattr(self, "chart_info", None)
        if not info:
            return
        inside = info["top"] - 20 <= event.y <= info["bottom"] + 62
        self.highlight_day(min(len(info["days"]) - 1, max(0, int(event.x // info["slot"]))) if inside else None)

    def highlight_day(self, index):
        """Підсвітка стовпчика, підказка з деталями дня й картки нагорі для цього дня."""
        info = getattr(self, "chart_info", None)
        c = self.w.get("chart")
        if not info or not c or index == info["hover"]:
            return
        info["hover"] = index
        c.delete("hover")
        if index is None:
            self.show_stats_day(len(info["days"]) - 1)
            return
        slot, top, bottom = info["slot"], info["top"], info["bottom"]
        band = c.create_rectangle(slot * index + 4, top - 14, slot * (index + 1) - 4, bottom + 62,
                                  fill=C["grid"], outline="", tags="hover")
        c.tag_lower(band)
        rec = info["records"][index]
        lines = [
            f"{t('tip_mini')}: {rec['mini_done']}",
            f"{t('tip_long')}: {rec['long_done']}",
            f"{t('tip_skipped')}: {rec['skipped']}",
            f"{t('tip_postponed')}: {rec['postponed']}",
            f"{t('tip_active')}: {fmt_minutes(rec['active_sec'] // 60)}",
            f"{t('tip_day_water')}: {t('x_of_y', a=rec['water'], b=self.cfg['water_goal'])} ({fmt_volume(rec['water'])})",
            f"{t('tip_meals')}: {rec['meals']}",
            f"{t('tip_work')}: {fmt_minutes(rec['work_sec'] // 60)}",
        ]
        if rec["day_end"]:
            lines.append(f"{t('tip_day_end')}: {fmt_clock(rec['day_end'])}")
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
        """Картки в логічному порядку: перерви → довгі перерви → відкладання й пауза → вода → їжа →
        кінець дня → звук → інше. Колонок стільки, скільки вміщує екран; картки заповнюють їх по черзі
        згори вниз, межі підібрані так, щоб колонки були якомога рівнішими, а решту висоти картки
        колонки ділять порівну — усі колонки закінчуються на одній лінії. «Перегляд» — дія, а не
        налаштування: окремим рядком на всю ширину внизу."""
        page = tk.Frame(parent, bg=C["bg"])
        count = self.layout["columns"]
        # Колонки — раніше за картки: картки кладемо в них через pack(in_=…), а показується лише те,
        # що в порядку накладання вище за свою колонку
        columns = [tk.Frame(page, bg=C["bg"]) for _ in range(count)]
        for i, column in enumerate(columns):
            column.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 7, 0 if i == count - 1 else 7))
            page.columnconfigure(i, weight=1, uniform="settings")

        def sliders(title, keys):
            box = card(page, title)
            for key in keys:
                self.add_slider(box, key)
            return box

        def toggle(box, text, key, **pack):
            Toggle(box, text, self.cfg[key], lambda v: self.set_setting(key, v)).pack(fill="x", **pack)

        breaks = sliders(t("card_breaks"), ("mini_interval_min", "mini_duration_sec", "intensity"))
        toggle(breaks, t("group_buttons_toggle"), "group_buttons", pady=(2, 0))
        long_box = sliders(t("card_long"), ("long_every", "long_duration_min"))
        toggle(long_box, t("workout_toggle"), "workout_enabled", pady=(2, 0))
        postpone = sliders(t("card_postpone"), ("postpone_min", "postpone_limit", "warn_before_sec", "pause_min"))

        water = card(page, t("card_water"))
        toggle(water, t("water_toggle"), "water_enabled", pady=(0, 8))
        self.build_water_profile(water)
        meals = self.build_meals_card(page)

        day_end = card(page, t("card_day_end"))
        lo, hi, step, fmt = SLIDERS["day_end_at"]
        day_end_slider = Slider(day_end, t("s_day_end_at"), lo, hi, step, self.cfg["day_end_at"], fmt,
                                lambda v: self.set_setting("day_end_at", v))

        def toggle_day_end(value):
            self.set_setting("day_end_enabled", value)
            day_end_slider.set_enabled(value)

        Toggle(day_end, t("day_end_toggle"), self.cfg["day_end_enabled"], toggle_day_end).pack(fill="x", pady=(0, 6))
        day_end_slider.pack(fill="x")
        day_end_slider.set_enabled(self.cfg["day_end_enabled"])

        sound = card(page, t("card_sound"))
        toggle(sound, t("sound_toggle"), "sound", pady=(0, 8))
        self.add_sound_slider(sound)

        other = card(page, t("card_other"))
        self.build_language_switch(other).pack(fill="x", pady=(0, 6))
        Toggle(other, t("autostart_toggle_mac" if system.IS_MAC else "autostart_toggle"), system.get_autostart(),
               self.set_autostart_setting).pack(fill="x", pady=4)
        toggle(other, t("updates_toggle"), "check_updates", pady=4)

        cards = [breaks, long_box, postpone, water, meals, day_end, sound, other]
        page.update_idletasks()
        for column, group in zip(columns, split_balanced([c.winfo_reqheight() for c in cards], count)):
            for j, index in enumerate(group):
                # expand: коротша колонка розтягує свої картки до висоти найвищої
                cards[index].pack(in_=column, fill="both", expand=True, pady=(0 if j == 0 else 14, 0))

        # «Перегляд» — рядок на всю ширину: підказка й п'ять кнопок поруч
        preview = card(page)
        preview.grid(row=1, column=0, columnspan=count, sticky="ew", pady=(14, 0))
        head = tk.Frame(preview, bg=C["card"])
        head.pack(side="left", fill="y", padx=(0, 16))
        tk.Label(head, text=t("card_preview").upper(), bg=C["card"], fg=C["accent"],
                 font=font(9, "semibold")).pack(anchor="w")
        tk.Label(head, text=t("preview_hint"), bg=C["card"], fg=C["muted"], font=font(10)).pack(anchor="w")
        row = tk.Frame(preview, bg=C["card"])
        row.pack(side="left", fill="x", expand=True)
        previews = ((t("preview_mini"), lambda: self.show_demo_break("mini")),
                    (t("preview_long"), lambda: self.show_demo_break("long")),
                    (t("preview_water"), lambda: self.show_water(demo=True)),
                    (t("preview_meal"), lambda: self.show_meal("lunch", demo=True)),
                    (t("preview_day_end"), lambda: self.show_day_end(demo=True)))
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
        if self.pages.get(self.current_page):
            self.pages[self.current_page].relayout()
        s = self.sched
        self.draw_ring()
        self.w["update"].configure(text=t("update_banner", version=self.update_info[0]) if self.update_info else "")
        self.w["pause_btn"].configure(text=t("resume") if s.paused or s.eating else t("pause_btn", time=fmt_minutes(self.cfg["pause_min"])))
        today = self.stats.day(dt.date.today())
        progress = t("water_today", n=today["water"], goal=self.cfg["water_goal"], volume=fmt_volume(today["water"]))
        hover = self.w.get("glass_hover")
        if hover is not None:  # курсор на склянці — що буде після кліку
            progress += f"  →  {hover} · {fmt_volume(hover)}"
        if not self.cfg["water_enabled"]:
            self.w["water"].configure(text="—")
            self.w["water_sub"].configure(text=t("water_off"))
        elif s.water_open:
            self.w["water"].configure(text=t("water_now"))
            self.w["water_sub"].configure(text=progress)
        else:
            self.w["water"].configure(text=fmt_time(s.water_remaining))
            self.w["water_sub"].configure(text=t("water_next", progress=progress))
        rate = completion_rate(today)
        work = today["work_sec"] + int(self.work_pending)  # ще не записане теж показуємо — наживо
        values = {
            "breaks": (today["mini_done"] + today["long_done"],
                       t("breaks_split", mini=today["mini_done"], long=today["long_done"])),
            "skipped": (today["skipped"], t("done_rate", pct=rate) if rate is not None else ""),
            "postponed": (today["postponed"], ""),
            "work": (fmt_hm(work), ""),
            "active": (today["active_sec"] // 60, ""),
            "meals": (today["meals"], ""),
        }
        for key, (value, sub) in values.items():
            self.w[f"today_{key}"].configure(text=value)
            self.w[f"today_{key}_sub"].configure(text=sub)
        self.refresh_schedule()
        self.refresh_meal_card(dt.datetime.now())
        self.draw_timeline()
        self.render_glasses(today["water"])

    def render_glasses(self, drunk):
        """Ряд склянок у картці «Вода» — перемальовуємо лише коли щось змінилося."""
        goal = self.cfg["water_goal"]
        if self.w.get("glasses_key") == (drunk, goal):
            return
        self.w["glasses_key"] = (drunk, goal)
        self.w["glass_hover"] = None
        frame = self.w["glasses"]
        for child in frame.winfo_children():
            child.destroy()
        glasses = []

        def target(n):
            # Клік по останній випитій склянці знімає її, по будь-якій іншій — виставляє кількість до неї
            return n - 1 if n == drunk else n

        def preview(count):
            """Наведення: показуємо, які склянки клік додасть, а які зніме; None — звичайний вигляд."""
            self.w["glass_hover"] = count
            for i, glass in enumerate(glasses):
                was, will = i < drunk, count is not None and i < count
                state = was if count is None or was == will else ("add" if will else "remove")
                glass.configure(image=glass_image(22, 30, state, C["card"]))
            self.refresh_main()

        for i in range(min(max(goal, drunk), MAX_GLASSES_SHOWN)):
            glass = tk.Label(frame, image=glass_image(22, 30, i < drunk, C["card"]), bg=C["card"], cursor="hand2")
            glass.grid(row=i // GLASSES_PER_ROW, column=i % GLASSES_PER_ROW, padx=3, pady=2)
            glass.bind("<Button-1>", lambda e, n=i + 1: self.set_water(target(n)))
            glass.bind("<Enter>", lambda e, n=i + 1: preview(target(n)))
            glass.bind("<Leave>", lambda e: preview(None))
            glasses.append(glass)

    def set_water(self, count):
        """Ручна зміна кількості випитої води за сьогодні."""
        before = self.stats.day(dt.date.today())["water"]
        count = max(0, min(count, MAX_GLASSES))
        if count == before:
            return
        self.stats.set("water", count)
        self.log_water_times(count - before)
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
        area = app.pages[name]
        note(f"page {name}: canvas {area.canvas.winfo_width()}x{area.canvas.winfo_height()}, "
             f"content {area.inner.winfo_width()}x{area.inner.winfo_height()} "
             f"(asks {area.inner.winfo_reqwidth()}x{area.inner.winfo_reqheight()})")

    def note(text):
        """Рядок у журнал і в info.txt поруч зі знімками: на macOS stderr зібраної програми не зберігається."""
        print(f"smoke test: {text}", file=sys.stderr)
        with open(os.path.join(out_dir, "info.txt"), "a", encoding="utf-8") as f:
            f.write(text + "\n")

    steps = [
        (app.open_main, None),
        (lambda: note(f"main window {app.main_win.winfo_width()}x{app.main_win.winfo_height()}, "
                      f"screen {app.root.winfo_screenwidth()}x{app.root.winfo_screenheight()}"), None),
        (lambda: page("status"), "status"),
        (lambda: page("stats"), "stats"),
        (lambda: app.set_stats_range(30), "stats_30"),
        (lambda: app.set_stats_range(7), None),
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
        (app.close_meal_window, None),
        (lambda: app.show_day_end(demo=True), "day_end"),
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
