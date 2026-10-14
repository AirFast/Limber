"""Логіка Rhythmos без інтерфейсу: налаштування, розклад перерв, води, їжі й кінця дня,
збирання перерв і статистика. Саме це покривають тести."""

import datetime as dt
import json
import os
import random

import exercises
import i18n
import system
from i18n import (content, fmt_clock, fmt_glasses, fmt_intensity, fmt_minutes, fmt_seconds, fmt_times,
                  fmt_warn, t)


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
DAY_END_SNOOZE_MIN = 30
MORNING = dt.time(6, 0)  # до коли триває пауза «до ранку»  # «Ще 30 хв» — людина ще працює, нагадаємо знову

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


def minute_of_day(moment):
    """Хвилини від півночі: 13:45 → 825. Так у налаштуваннях і статистиці зберігається час дня."""
    return moment.hour * 60 + moment.minute


def at_minute(date, minutes):
    """Мить дня `date` через `minutes` хвилин від півночі."""
    return dt.datetime.combine(date, dt.time()) + dt.timedelta(minutes=minutes)


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

def stale(due, now):
    """Відкладене нагадування застаріло: його час минув понад MEAL_WINDOW_MIN тому (комп'ютер спав),
    і показувати його тепер — зранку чи після обіду — вже недоречно."""
    return now - due > dt.timedelta(minutes=MEAL_WINDOW_MIN)


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
            if not self.day_end_snoozed:  # «Ще 30 хв» нагадує про той самий день — дату не перезаписуємо
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
            if stale(self.day_end_snoozed, now):
                self.day_end_snoozed = None  # комп'ютер спав — «Ще 30 хв» уже ні до чого
            else:
                return now >= self.day_end_snoozed
        return self.day_end_shown != now.date() and minute_of_day(now) >= self.cfg["day_end_at"]

    def day_end_answered(self, answer, now=None):
        """answer: "snooze" — нагадати через 30 хв, "finish" — день завершено (паузу ставить App)."""
        self.day_end_open = False
        if answer == "snooze":
            self.day_end_snoozed = (now or dt.datetime.now()) + dt.timedelta(minutes=DAY_END_SNOOZE_MIN)

    def due_meal(self, now):
        """Їжа, про яку час нагадати: її година настала, але минуло не більше MEAL_WINDOW_MIN."""
        if self.meal_open or self.in_break or (self.paused and self.pause_water):
            return None
        minutes = minute_of_day(now)
        for meal in MEALS:
            if not self.cfg[f"{meal}_enabled"]:
                continue
            if (now.date(), meal) in self.meal_results:
                continue  # уже з'їли (позначили тарілку заздалегідь) чи пропустили
            snoozed = self.meal_snoozed.get(meal)
            if snoozed and stale(snoozed, now):
                del self.meal_snoozed[meal]  # комп'ютер спав — відкладене нагадування застаріло
                snoozed = None
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
        at = at_minute(now.date(), self.cfg[f"{meal}_at"])
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

    def pause(self, minutes, now=None):
        """minutes=None — «до ранку»: день завершено, тож відкладені нагадування про їжу й кінець дня
        теж скасовуються, інакше вони спрацювали б уранці."""
        now = now or dt.datetime.now()
        self.eating = self.eating_until = None
        if minutes is None:
            # До 06:00: після півночі — цього ж дня, а не наступного (інакше пауза тривала б ~30 год)
            morning = dt.datetime.combine(now.date(), MORNING)
            self.paused_until = morning if now < morning else morning + dt.timedelta(days=1)
            self.meal_snoozed.clear()
            self.meal_open = None
            self.day_end_open = False
            self.day_end_snoozed = None
            self.day_end_shown = now.date()
        else:
            self.paused_until = now + dt.timedelta(minutes=minutes)
        self.pause_water = minutes is None

    def resume(self):
        self.paused_until = None
        self.pause_water = False

    def apply_config(self):
        interval = self.cfg["mini_interval_min"] * 60
        if not self.in_break and self.remaining > interval:
            self._set_countdown(interval)
        self.water_remaining = min(self.water_remaining, self.cfg["water_interval_min"] * 60)
