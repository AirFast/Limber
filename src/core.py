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
STATE_PATH = os.path.join(DATA_DIR, "state.json")  # стан таймерів — щоб перезапуск не обнуляв день
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
    "workdays": [0, 1, 2, 3, 4],  # дні тижня (0 — понеділок), коли нагадувати про їжу й кінець дня
    "day_boundary_hour": 4,      # дії до цієї години ще належать учорашньому робочому дню
    "workday_start": 0,          # початок робочого дня, хвилини від півночі; 0 — за першою дією з мишею
    "max_work_hours": 9,         # після стількох годин за комп'ютером — попередження; 0 — вимкнено
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
    "workday_start": (5 * 60 + 45, 12 * 60, 15, lambda v: t("auto") if v < 6 * 60 else fmt_clock(v)),
    "max_work_hours": (5, 12, 1, lambda v: t("off") if v < 6 else fmt_minutes(v * 60)),
}
# Крайнє ліве положення цих повзунків означає 0 у налаштуваннях: «авто» чи «вимкнено»
SLIDER_ZERO = {"workday_start": 5 * 60 + 45, "max_work_hours": 5}


def slider_position(key, value):
    """Значення з налаштувань → положення повзунка."""
    return SLIDER_ZERO[key] if key in SLIDER_ZERO and not value else value


def setting_value(key, position):
    """Положення повзунка → значення для налаштувань."""
    return 0 if SLIDER_ZERO.get(key) == position else position

MEALS = ("breakfast", "lunch", "dinner")
MEAL_WINDOW_MIN = 60   # комп'ютер прокинувся пізніше, ніж на годину після часу їжі, — нагадування вже ні до чого
MEAL_SNOOZE_MIN = 15   # «Через 15 хв» і «Ще 15 хв»
DAY_END_SNOOZE_MIN = 30   # «Ще 30 хв» — людина ще працює, нагадаємо знову
WATER_LATER_MIN = 15      # «Пізніше» у нагадуванні про воду
WATER_MIN_PACE_MIN = 15   # розумний темп води: не частіше, ніж раз на стільки хвилин
MORNING_AFTER_BOUNDARY_H = 2    # пауза «до ранку» триває до межі доби + 2 год (за замовчуванням 06:00)
ACTIVE_IDLE_SEC = 60            # людина за комп'ютером, якщо миша чи клавіатура були не довше хвилини тому
MIN_AWAY_MIN = 2                # відсутність — не коротша за це, навіть якщо довга перерва коротша
FINISH_GRACE_MIN = 3            # після «Завершити день»: якщо людина працює далі довше — день триває
BREAK_HOLD_MAX_MIN = 30         # перерву під час дзвінка чи презентації тримаємо не довше за це
STATE_MAX_AGE_H = 12            # старіший збережений стан таймерів після перезапуску не відновлюємо

# Рекомендована денна мета води, склянок по 250 мл. EFSA: загалом 2,0 л на день жінкам і 2,5 л чоловікам,
# близько 20% з цього дає їжа — тож пити ≈1,6 і ≈2,0 л (жінкам округлено вгору до 7 склянок)
WATER_PROFILES = {"female": 7, "male": 8}
WORKDAY_MIN = 8 * 60  # тривалість робочого дня, поки її не видно з початку й кінця дня
TYPICAL_START = 9 * 60  # початок дня, коли ще немає жодного визначеного
WORKDAY_LIMITS = (4 * 60, 14 * 60)  # розумні межі тривалості робочого дня для розрахунку інтервалу води


def workday_span(start, end):
    """(початок, кінець) робочого дня в хвилинах: кінець — «Кінець робочого дня» з налаштувань
    (None — вимкнено, тоді 8 годин від початку); тривалість — у розумних межах."""
    lo, hi = WORKDAY_LIMITS
    end = start + WORKDAY_MIN if end is None else end
    return start, start + min(max(end - start, lo), hi)


def water_interval_for(goal, workday=WORKDAY_MIN):
    """Найбільший інтервал (кратний кроку повзунка), з яким `goal` склянок встигаємо за робочий день."""
    lo, hi, step, _fmt = SLIDERS["water_interval_min"]
    return min(max(workday // goal // step * step, lo), hi)


def water_plan(profile, workday=WORKDAY_MIN):
    """(мета, інтервал у хв) для профілю або None, якщо налаштування ручні."""
    goal = WATER_PROFILES.get(profile)
    return (goal, water_interval_for(goal, workday)) if goal else None


def apply_water_profile(cfg, workday=WORKDAY_MIN):
    """Профіль «жінка»/«чоловік» перекриває мету й інтервал рекомендованими значеннями."""
    if cfg["water_profile"] not in WATER_PROFILES:
        cfg["water_profile"] = "custom"
    plan = water_plan(cfg["water_profile"], workday)
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


def migrate_config(saved):
    """Налаштування старих версій → нинішні ключі. «Їжа й кінець дня — лише в будні» (workdays_only)
    стало списком робочих днів: вимкнений перемикач означав «щодня»."""
    saved = dict(saved)
    if "workdays" not in saved and saved.get("workdays_only") is False:
        saved["workdays"] = list(range(7))
    days = saved.get("workdays")
    if days is not None:
        valid = isinstance(days, list) and all(isinstance(d, int) and 0 <= d <= 6 for d in days)
        saved["workdays"] = sorted(set(days)) if valid else list(DEFAULTS["workdays"])
    return saved


def load_config():
    cfg = dict(DEFAULTS)
    saved = migrate_config(load_json(CONFIG_PATH, {}))
    cfg.update({k: v for k, v in saved.items() if k in DEFAULTS})
    cfg["workdays"] = list(cfg["workdays"])  # власний список, а не спільний з DEFAULTS
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


def workday_date(moment, boundary_hour=DEFAULTS["day_boundary_hour"]):
    """Робочий день, до якого належить мить: до межі доби (04:00) — ще вчорашній.
    Саме ця дата — ключ статистики й «сьогодні» для нагадувань."""
    return (moment - dt.timedelta(hours=boundary_hour)).date()


def at_workday_minute(date, minutes, boundary_hour=DEFAULTS["day_boundary_hour"]):
    """Мить робочого дня `date` за хвилинами від півночі: час до межі доби — це вже наступна календарна дата."""
    moment = at_minute(date, minutes)
    return moment + dt.timedelta(days=1) if minutes < boundary_hour * 60 else moment


def work_started(now, idle_seconds, boundary_hour=DEFAULTS["day_boundary_hour"]):
    """Хвилина дня, коли почали працювати, або None: людина за комп'ютером (миша чи клавіатура щойно),
    і вже не ніч (до межі доби — це ще вчорашній день). Момент — остання дія, а не цей тік."""
    started = now - dt.timedelta(seconds=idle_seconds)
    if idle_seconds > ACTIVE_IDLE_SEC or started.hour < boundary_hour or started.date() != now.date():
        return None
    return minute_of_day(started)


def average_minute(minutes):
    """Середній час дня (хвилини від півночі) для днів, де він є; None — якщо таких днів немає."""
    minutes = [m for m in minutes if m]
    return round(sum(minutes) / len(minutes)) if minutes else None


def fmt_time(seconds):
    seconds = max(0, int(round(seconds)))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class Stats:
    # work_sec — час за комп'ютером (таймер іде: не пауза, не перерва, не їжа), active_sec — час на перервах,
    # meals — скільки разів поїли (сума ate_*), ate_<їжа> — 1, якщо цю їжу сьогодні з'їдено («Йду їсти»
    # або тарілка на «Стані»); day_start — коли почали працювати (перша дія з мишею чи клавіатурою),
    # day_end — коли завершили день; обидва — хвилини від півночі, 0 — ще не було
    KEYS = ("mini_done", "long_done", "skipped", "postponed", "water", "work_sec", "active_sec", "meals",
            "day_start", "day_end", "ate_breakfast", "ate_lunch", "ate_dinner")
    MOMENTS = ("day_start", "day_end")  # час дня, а не лічильник: не підсумовуються

    def __init__(self, today=None):
        self.data = load_json(STATS_PATH, {})
        self.today = today or dt.date.today  # поточний робочий день (App.today: з межею доби)

    def add(self, key, amount=1):
        rec = self.data.setdefault(self.today().isoformat(), {})
        rec[key] = rec.get(key, 0) + amount
        save_json(STATS_PATH, self.data)

    def set(self, key, value):
        """Ручне виправлення лічильника за сьогодні (наприклад, кількості склянок води)."""
        rec = self.data.setdefault(self.today().isoformat(), {})
        rec[key] = max(0, int(value))
        save_json(STATS_PATH, self.data)

    def day(self, date):
        rec = self.data.get(date.isoformat(), {})
        return {k: rec.get(k, 0) for k in self.KEYS}

    def times(self, date, key):
        """Список моментів події за день (хвилини від півночі), наприклад water_at — коли пили воду."""
        return list(self.data.get(date.isoformat(), {}).get(key, []))

    def set_times(self, key, values):
        rec = self.data.setdefault(self.today().isoformat(), {})
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


def _iso(value):
    return value.isoformat() if value else None


def _moment(text):
    return dt.datetime.fromisoformat(text) if text else None


def _date(text):
    return dt.date.fromisoformat(text) if text else None


# Стан людини (Scheduler.mode). AWAY ніхто не вибирає — його визначає бездіяльність, і він лише
# накладається на режим (Scheduler.state): пауза чи «до ранку» мають тривати й тоді, коли людина відійшла
WORKING, BREAK, EATING, PAUSED, FINISHED, AWAY = "working", "break", "eating", "paused", "finished", "away"
MODES = (WORKING, BREAK, EATING, PAUSED, FINISHED)

# Що стоїть у кожному стані: відлік до перерви, відлік до води, нагадування за годинником (їжа, кінець
# дня, переробка). Єдине місце, де це вирішується
BREAKS, WATER, CLOCK = "breaks", "water", "clock"
FREEZES = {
    WORKING: frozenset(),
    PAUSED: frozenset({BREAKS}),                  # звичайна пауза зупиняє лише перерви
    BREAK: frozenset({BREAKS, WATER, CLOCK}),
    EATING: frozenset({BREAKS, WATER, CLOCK}),    # до «Продовжити» після їжі
    FINISHED: frozenset({BREAKS, WATER, CLOCK}),  # «до ранку»: робочий день скінчився
    AWAY: frozenset({BREAKS, WATER, CLOCK}),      # нагадування не спливають у порожню кімнату
}
STATE_VERSION = 1
BREAK_RESUME_SEC = 60  # перерва, яку перервав вихід із програми, почнеться через хвилину після запуску


class Reminder:
    """Нагадування з однаковими для всіх правилами; Scheduler.tick щосекунди опитує їх по черзі (poll).

    Нагадування стоїть — ні відліку, ні показу, — якщо стан людини заморожує його ворота `gate`
    (FREEZES) або quiet(now): вимкнено, вихідний, уже відповіли, день завершено, мету досягнуто.
    Відкрите (open) чекає на відповідь і вдруге не спливає; нове спливає лише тоді, коли не висить
    нагадування з груп `waits` (кінець дня чекає, поки відповідять про їжу). Відкладене спрацьовує
    о snoozed_until, а застаріле (stale: комп'ютер спав) відкидається. Інакше — власний тригер
    triggered(now); shown — робочий день, коли воно вже спрацювало за власним часом.
    Відповідь "snooze" відкладає на snooze_min, будь-яка інша — остаточна до кінця робочого дня."""
    gate = CLOCK
    group = None
    waits = ()
    snooze_min = MEAL_SNOOZE_MIN

    def __init__(self, sched, name, event):
        self.sched, self.name, self.event = sched, name, event
        self.open = False
        self.snoozed_until = None
        self.shown = None
        self.answered = None  # (робочий день, відповідь)

    @property
    def cfg(self):
        return self.sched.cfg

    def answer_on(self, day):
        return self.answered[1] if self.answered and self.answered[0] == day else None

    def quiet(self, now):
        return False

    def triggered(self, now):
        return False

    def advance(self, seconds):
        """Відлік робочого часу — лише в нагадувань з відліком (вода)."""

    def poll(self, seconds, now, frozen):
        """Один тік; True — нагадування щойно спрацювало (тепер воно відкрите)."""
        if self.gate in frozen or self.quiet(now) or self.open:
            return False
        self.advance(seconds)
        if any(r.open for r in self.sched.reminders if r.group in self.waits):
            return False
        if self.snoozed_until is not None:
            if stale(self.snoozed_until, now):
                self.snoozed_until = None  # комп'ютер спав — відкладене вже ні до чого
            elif now >= self.snoozed_until:
                # Відкладене нагадує про той самий день — shown не перезаписуємо
                self.snoozed_until = None
                self.open = True
                return True
            else:
                return False
        if self.triggered(now):
            self.open = True
            self.shown = self.sched.workday(now)
            return True
        return False

    def answer(self, answer, now):
        self.open = False
        if answer == "snooze":
            self.snoozed_until = now + dt.timedelta(minutes=self.snooze_min)
        elif answer:
            self.answered = (self.sched.workday(now), answer)

    def cancel(self):
        """День завершено: відкрите й відкладене більше не потрібні (інакше спрацювали б уранці)."""
        self.open = False
        self.snoozed_until = None

    def snapshot(self):
        # Віконця після перезапуску вже немає — відкрите нагадування спливе знову
        return {"snoozed_until": _iso(self.snoozed_until), "shown": None if self.open else _iso(self.shown),
                "answered": [self.answered[0].isoformat(), self.answered[1]] if self.answered else None}

    def parse(self, data):
        """Збережене snapshot() → атрибути; зіпсовані дані — KeyError/TypeError/ValueError."""
        answered = data["answered"]
        return {"open": False, "snoozed_until": _moment(data["snoozed_until"]), "shown": _date(data["shown"]),
                "answered": (_date(answered[0]), str(answered[1])) if answered else None}


class WaterReminder(Reminder):
    """Вода: відлік робочого часу. «Випив» — наступна склянка в розумному темпі (Scheduler.water_interval),
    «Пізніше» — через WATER_LATER_MIN; мовчить, коли нагадування вимкнено чи денну мету досягнуто."""
    gate = WATER

    def __init__(self, sched):
        super().__init__(sched, "water", "water")
        self.remaining = sched.cfg["water_interval_min"] * 60

    def quiet(self, now):
        return not self.cfg["water_enabled"] or self.sched.water_done

    def advance(self, seconds):
        self.remaining -= seconds

    def triggered(self, now):
        return self.remaining <= 0

    def answer(self, drank, now):
        self.open = False
        self.remaining = self.sched.water_interval(now) if drank else WATER_LATER_MIN * 60

    def snapshot(self):
        return {"remaining": 0 if self.open else self.remaining}

    def parse(self, data):
        return {"open": False, "remaining": float(data["remaining"])}


class MealReminder(Reminder):
    """Сніданок, обід чи вечеря: о своїй годині, але не пізніше ніж за MEAL_WINDOW_MIN по ній
    (комп'ютер прокинувся пізніше — нагадування вже ні до чого). Відповіді: "eat", "skip", "snooze"."""
    group = "meal"
    waits = ("meal",)

    def quiet(self, now):
        return (not self.cfg[f"{self.name}_enabled"] or not self.sched.reminders_today(now)
                or self.answer_on(self.sched.workday(now)) is not None)

    def triggered(self, now):
        at = self.sched.moment(now, self.cfg[f"{self.name}_at"])
        return self.shown != self.sched.workday(now) and at <= now < at + dt.timedelta(minutes=MEAL_WINDOW_MIN)


class MealOverReminder(Reminder):
    """Пауза на їжу скінчилась — «Продовжуємо?». Питає один раз і чекає відповіді: пауза на їжу сама
    не закінчується. «Ще 15 хв» відсуває її кінець (Scheduler.extend_meal)."""
    gate = None
    group = "meal_over"

    def quiet(self, now):
        return self.sched.mode != EATING

    def triggered(self, now):
        return now >= self.sched.until


class DayEndReminder(Reminder):
    """Робочий день скінчився (у свій час чи після «Ще 30 хв»), а людина досі за комп'ютером.
    Відповіді: "snooze", "finish" (паузу «до ранку» ставить App)."""
    group = "day"
    waits = ("meal", "day")
    snooze_min = DAY_END_SNOOZE_MIN

    def quiet(self, now):
        return (not self.cfg["day_end_enabled"] or not self.sched.reminders_today(now)
                or self.sched.day_finished(now) or self.answer_on(self.sched.workday(now)) is not None)

    def triggered(self, now):
        return self.shown != self.sched.workday(now) and now >= self.sched.moment(now, self.cfg["day_end_at"])


class OverworkReminder(Reminder):
    """За комп'ютером сьогодні вже більше за денний ліміт (max_work_hours) — раз на день.
    Відповіді: "later", "finish" (паузу «до ранку» ставить App)."""
    group = "day"
    waits = ("meal", "day")

    def quiet(self, now):
        return (not self.cfg["max_work_hours"] or self.sched.day_finished(now)
                or self.answer_on(self.sched.workday(now)) is not None)

    def triggered(self, now):
        return (self.shown != self.sched.workday(now)
                and self.sched.worked >= self.cfg["max_work_hours"] * 3600)


class Scheduler:
    """Розклад дня: стан людини (mode), відлік робочого часу до перерви й нагадування (reminders).
    Відлік скидається лише після перерви, відсутності чи на вимогу — блокування екрана його не обнуляє.
    Переходи між станами — лише методами нижче; що заморожує кожен стан — FREEZES."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.mode = WORKING
        self.until = None          # кінець паузи, «до ранку» чи паузи на їжу
        self.meal = None           # яку їжу їдять (EATING)
        self.finished_at = None    # коли натиснули «Завершити день» (паузу «до ранку»)
        self.away = False          # людини немає за комп'ютером (див. away_after)
        self.away_idle = 0.0       # найдовша бездіяльність за цю відсутність
        self.breaks_taken = 0
        self.postpones = 0
        self.long_skipped = False  # довгу перерву пропустили — наступна знову довга (один раз)
        self.held = None           # скільки секунд перерву тримає зайнятість; None — не тримає
        # Що відомо App про сьогодні (update_day): для темпу води й ліміту роботи
        self.drunk = 0
        self.workday_end = None
        self.worked = 0
        self.water_done = False    # денну мету води досягнуто — до завтра без нагадувань
        self._set_countdown(self.cfg["mini_interval_min"] * 60)
        self.water = WaterReminder(self)
        self.meals = {meal: MealReminder(self, meal, "meal") for meal in MEALS}
        self.meal_over = MealOverReminder(self, "meal_over", "meal_over")
        self.day_end = DayEndReminder(self, "day_end", "day_end")
        self.overwork = OverworkReminder(self, "overwork", "overwork")
        # Порядок — пріоритет: з тих, що чекають одне на одного (waits), за тік спливає лише перше
        self.reminders = [self.water, *self.meals.values(), self.meal_over, self.day_end, self.overwork]

    def _set_countdown(self, seconds):
        self.remaining = self.period = seconds
        self.warned = False
        self.held = None

    # --- стан ---

    @property
    def state(self):
        """Режим, а якщо людини немає — AWAY."""
        return AWAY if self.away else self.mode

    def frozen(self):
        return FREEZES[self.state]

    # Властивості лише для читання — для інтерфейсу
    @property
    def in_break(self):
        return self.mode == BREAK

    @property
    def paused(self):
        return self.mode in (PAUSED, FINISHED)

    @property
    def paused_until(self):
        return self.until if self.paused else None

    @property
    def pause_water(self):
        """Пауза «до ранку» зупиняє й воду, звичайна — лише перерви."""
        return self.mode == FINISHED

    @property
    def eating(self):
        return self.meal if self.mode == EATING else None

    @property
    def eating_until(self):
        return self.until if self.mode == EATING else None

    @property
    def water_open(self):
        return self.water.open

    @property
    def water_remaining(self):
        return self.water.remaining

    @property
    def meal_open(self):
        """Про яку їжу зараз висить нагадування."""
        return next((meal for meal, r in self.meals.items() if r.open), None)

    @property
    def meal_snoozed(self):
        return {meal: r.snoozed_until for meal, r in self.meals.items() if r.snoozed_until}

    @property
    def day_end_open(self):
        return self.day_end.open

    @property
    def day_end_snoozed(self):
        return self.day_end.snoozed_until

    def workday(self, now):
        """Робочий день для миті `now` (з межею доби day_boundary_hour)."""
        return workday_date(now, self.cfg["day_boundary_hour"])

    def moment(self, now, minutes):
        """Мить сьогоднішнього робочого дня за хвилинами від півночі (час із налаштувань)."""
        return at_workday_minute(self.workday(now), minutes, self.cfg["day_boundary_hour"])

    def morning(self, now):
        """Кінець паузи «до ранку»: найближча година «межа доби + 2» (06:00) — після півночі це цей самий
        ранок, а не наступний (інакше пауза тривала б ~30 год)."""
        hour = (self.cfg["day_boundary_hour"] + MORNING_AFTER_BOUNDARY_H) % 24
        morning = dt.datetime.combine(now.date(), dt.time(hour))
        return morning if now < morning else morning + dt.timedelta(days=1)

    def away_after(self):
        """Скільки секунд без миші й клавіатури — це відсутність: як довга перерва, але не менше MIN_AWAY_MIN."""
        return max(MIN_AWAY_MIN, self.cfg["long_duration_min"]) * 60

    def reminders_today(self, now):
        """Чи нагадувати сьогодні про їжу й кінець дня: лише в робочі дні з налаштувань."""
        return self.workday(now).weekday() in self.cfg["workdays"]

    def day_finished(self, now):
        return self.finished_at is not None and self.workday(self.finished_at) == self.workday(now)

    def update_day(self, drunk, workday_end=None, worked=0):
        """Що App знає про сьогодні: склянок випито, кінець робочого дня (datetime чи None)
        і скільки секунд уже працювали."""
        self.drunk, self.workday_end, self.worked = drunk, workday_end, worked
        self.water_done = drunk >= self.cfg["water_goal"]

    # --- щосекундний відлік ---

    def tick(self, seconds, now=None, idle=0.0, busy=False):
        """Один крок. idle — скільки секунд не було миші й клавіатури (system.idle_seconds); busy — людина
        на дзвінку чи показує екран: перерва почекає (не довше BREAK_HOLD_MAX_MIN). Повертає події:
        "warn", "break", "break_held", "water", "meal", "meal_over", "day_end", "overwork",
        "day_continued", "back"."""
        now = now or dt.datetime.now()
        events = []
        if self.mode in (PAUSED, FINISHED) and now >= self.until:
            self.mode, self.until = WORKING, None  # пауза скінчилась сама
        # День завершили, а людина працює далі — день триває: таймери знову йдуть (без повторного питання)
        if (self.mode == FINISHED and idle < ACTIVE_IDLE_SEC and self.day_finished(now)
                and now - self.finished_at >= dt.timedelta(minutes=FINISH_GRACE_MIN)):
            self.mode, self.until = WORKING, None
            events.append("day_continued")
        # Людини немає довше за довгу перерву — це природна перерва: таймери стоять, а коли повернеться,
        # відлік до перерви почнеться з початку
        if idle >= self.away_after() and self.mode not in (BREAK, EATING):
            self.away = True
            self.away_idle = max(self.away_idle, idle)
        elif self.away:
            self.come_back()
            events.append("back")
        if BREAKS not in self.frozen():
            events += self._count_down(seconds, busy)
        frozen = self.frozen()  # перерва могла щойно початися
        events += [r.event for r in self.reminders if r.poll(seconds, now, frozen)]
        return events

    def _count_down(self, seconds, busy):
        """Відлік до перерви. Поки людина зайнята, попередження й перерва чекають (відлік стоїть на нулі),
        але не довше BREAK_HOLD_MAX_MIN; "break_held" — один раз, коли почали чекати."""
        self.remaining = max(0, self.remaining - seconds)
        warn = self.cfg["warn_before_sec"]
        warn_due = bool(warn) and not self.warned and 0 < self.remaining <= warn
        if not warn_due and self.remaining > 0:
            return []
        if self.held is not None:
            self.held += seconds
        if busy and (self.held or 0) < BREAK_HOLD_MAX_MIN * 60:
            if self.held is None:
                self.held = 0
                return ["break_held"]
            return []
        if warn_due:
            self.warned = True
            return ["warn"]
        self.mode = BREAK
        self.held = None
        return ["break"]

    def come_back(self):
        """Людина повернулася: відсутність була природною перервою — відлік до перерви з початку.
        Відсутність, удвічі довша за довгу перерву, — це й була довга перерва: до наступної — повний цикл."""
        self.away = False
        self.postpones = 0
        self._set_countdown(self.cfg["mini_interval_min"] * 60)
        if self.away_idle >= self.cfg["long_duration_min"] * 60 * 2:
            every = max(1, self.cfg["long_every"])
            self.breaks_taken = -(-self.breaks_taken // every) * every
            self.long_skipped = False
        self.away_idle = 0.0

    # --- перерви ---

    def breaks_until_long(self):
        """Скільки перерв лишилось до довгої, включно з нею: 1 — наступна перерва довга."""
        if self.long_skipped:
            return 1
        every = max(1, self.cfg["long_every"])
        return every - self.breaks_taken % every

    def next_kind(self):
        return "long" if self.breaks_until_long() == 1 else "mini"

    def start_break(self):
        """«Перерва зараз»: перерва важливіша за паузу чи їжу."""
        self.mode, self.until, self.meal = BREAK, None, None
        self.meal_over.open = False

    def finish_break(self, skipped=False):
        """Перерва скінчилась (зроблена, пропущена чи перервана паузою). Пропущена довга повертається:
        наступна перерва — знову довга, але лише раз; далі ритм іде своїм ходом."""
        long = self.next_kind() == "long"
        if self.mode == BREAK:
            self.mode = WORKING
        if skipped and long and not self.long_skipped:
            self.long_skipped = True
        else:
            self.long_skipped = False
            self.breaks_taken += 1
        self.postpones = 0
        self._set_countdown(self.cfg["mini_interval_min"] * 60)

    def can_postpone(self):
        return self.postpones < self.cfg["postpone_limit"]

    def postpone(self):
        if self.mode == BREAK:
            self.mode = WORKING
        self.postpones += 1
        self._set_countdown(self.cfg["postpone_min"] * 60)

    def reset(self):
        self.postpones = 0
        self._set_countdown(self.cfg["mini_interval_min"] * 60)

    # --- пауза й кінець дня ---

    def pause(self, minutes, now=None):
        """minutes=None — «до ранку»: день завершено, тож відкладені нагадування про їжу й кінець дня
        теж скасовуються, інакше вони спрацювали б уранці."""
        now = now or dt.datetime.now()
        self.meal = None
        self.meal_over.cancel()
        if minutes is None:
            self.mode, self.until, self.finished_at = FINISHED, self.morning(now), now
            for r in (*self.meals.values(), self.day_end, self.overwork):
                r.cancel()
            self.day_end.shown = self.workday(now)
        else:
            self.mode, self.until = PAUSED, now + dt.timedelta(minutes=minutes)

    def resume(self):
        if self.paused:
            self.mode, self.until = WORKING, None

    def day_end_answered(self, answer, now=None):
        """answer: "snooze" — нагадати через 30 хв, "finish" — день завершено (паузу ставить App)."""
        self.day_end.answer(answer, now or dt.datetime.now())

    def overwork_answered(self, answer, now=None):
        """answer: "later" — більше сьогодні не нагадувати, "finish" — день завершено (паузу ставить App)."""
        self.overwork.answer(answer, now or dt.datetime.now())

    # --- вода ---

    def water_interval(self, now):
        """Секунд до наступної склянки. Коли відомі мета й кінець робочого дня — розумний темп: решту часу
        ділимо на решту склянок (відстаємо — частіше, випереджаємо — рідше), у межах від
        WATER_MIN_PACE_MIN до подвоєного інтервалу з налаштувань."""
        base = self.cfg["water_interval_min"] * 60
        left = self.cfg["water_goal"] - self.drunk
        if self.workday_end is None or left <= 0 or now >= self.workday_end:
            return base
        pace = (self.workday_end - now).total_seconds() / left
        return int(min(max(pace, WATER_MIN_PACE_MIN * 60), 2 * base))

    def water_answered(self, drank, now=None):
        self.water.answer(drank, now or dt.datetime.now())

    # --- їжа ---

    def meal_answered(self, answer, now=None):
        """answer: "eat" — пауза на їжу, "snooze" — нагадати через 15 хв, "skip" — не нагадувати."""
        now = now or dt.datetime.now()
        meal = self.meal_open
        if not meal:
            return
        self.meals[meal].answer(answer, now)
        if answer == "eat":  # їжа важливіша за звичайну паузу
            self.mode, self.meal = EATING, meal
            self.until = now + dt.timedelta(minutes=self.cfg["meal_pause_min"])
            self.meal_over.cancel()

    def extend_meal(self, now=None):
        """«Ще 15 хв» після паузи на їжу."""
        if self.mode == EATING:
            self.until = (now or dt.datetime.now()) + dt.timedelta(minutes=MEAL_SNOOZE_MIN)
            self.meal_over.open = False

    def finish_meal(self, now=None):
        """«Продовжити»: їжа вже була довгою перервою, тож обидва таймери — з початку."""
        if self.mode != EATING:
            return
        self.mode, self.until, self.meal = WORKING, None, None
        self.meal_over.cancel()
        self.postpones = 0
        self._set_countdown(self.cfg["mini_interval_min"] * 60)
        self.water.remaining = self.water_interval(now or dt.datetime.now())

    def mark_meal(self, meal, eaten, now=None):
        """Тарілка на «Стані» чи «Йду їсти»: їжу сьогодні з'їдено (або позначку знято).
        True — висіло нагадування про цю їжу, і воно більше не потрібне."""
        reminder, day = self.meals[meal], self.workday(now or dt.datetime.now())
        if not eaten:
            if reminder.answer_on(day) == "eat":
                reminder.answered = None
            return False
        was_open = reminder.open
        reminder.answered, reminder.open, reminder.snoozed_until = (day, "eat"), False, None
        return was_open

    def meal_state(self, meal, now):
        """Стан їжі сьогодні для розкладу: (стан, час). Стани: "eating" (до часу), "eat", "skip",
        "snoozed" (нагадаю о), "open" (нагадування висить), "upcoming" (о), "due" (ось-ось), "missed"."""
        if self.eating == meal:
            return "eating", self.until
        reminder = self.meals[meal]
        result = reminder.answer_on(self.workday(now))
        if result:
            return result, None
        if reminder.snoozed_until and not stale(reminder.snoozed_until, now):
            return "snoozed", reminder.snoozed_until
        if reminder.open:
            return "open", None
        at = self.moment(now, self.cfg[f"{meal}_at"])
        if now < at:
            return "upcoming", at
        return ("due" if now < at + dt.timedelta(minutes=MEAL_WINDOW_MIN) else "missed"), at

    def next_meal(self, now):
        """Наступна їжа: (їжа, коли) або (їжа, None), якщо час їсти вже зараз; None — на сьогодні все."""
        if not self.reminders_today(now):
            return None
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

    # --- налаштування, статистика, перезапуск ---

    def apply_config(self, now=None):
        interval = self.cfg["mini_interval_min"] * 60
        if self.mode != BREAK and self.remaining > interval:
            self._set_countdown(interval)
        self.water.remaining = min(self.water.remaining, self.water_interval(now or dt.datetime.now()))

    def restore_day(self, day, eaten=(), finished_minute=0, day_end_asked=False):
        """Що про сьогодні вже записано в статистиці (на випадок, коли state.json немає): з'їдене
        не нагадуємо, завершений день і питання про кінець дня не повторюємо."""
        for meal in eaten:
            self.meals[meal].answered = (day, "eat")
        if finished_minute and not (self.finished_at and self.workday(self.finished_at) == day):
            self.finished_at = at_workday_minute(day, finished_minute, self.cfg["day_boundary_hour"])
        if finished_minute or day_end_asked:
            self.day_end.shown = day

    def snapshot(self, now):
        """Стан для state.json (лише JSON-типи): App зберігає його щохвилини й під час виходу."""
        return {
            "version": STATE_VERSION, "saved_at": now.isoformat(), "workday": self.workday(now).isoformat(),
            "mode": self.mode, "until": _iso(self.until), "meal": self.meal, "finished_at": _iso(self.finished_at),
            "remaining": self.remaining, "period": self.period, "warned": self.warned,
            "breaks_taken": self.breaks_taken, "postpones": self.postpones, "long_skipped": self.long_skipped,
            "reminders": {r.name: r.snapshot() for r in self.reminders},
        }

    def restore(self, data, now):
        """Відновлює snapshot() після перезапуску, якщо він з того самого робочого дня й не старший за
        STATE_MAX_AGE_H. Перерва, яку перервав вихід, почнеться за хвилину; довгий час без програми —
        як відсутність (come_back). True — відновлено; зіпсований файл просто ігнорується."""
        try:
            saved = _moment(data["saved_at"])
            if (data.get("version") != STATE_VERSION or _date(data["workday"]) != self.workday(now)
                    or not dt.timedelta(0) <= now - saved <= dt.timedelta(hours=STATE_MAX_AGE_H)):
                return False
            mode = data["mode"]
            values = {
                "mode": mode, "until": _moment(data["until"]), "meal": data["meal"] if mode == EATING else None,
                "finished_at": _moment(data["finished_at"]),
                "remaining": float(data["remaining"]), "period": float(data["period"]),
                "warned": bool(data["warned"]), "breaks_taken": int(data["breaks_taken"]),
                "postpones": int(data["postpones"]), "long_skipped": bool(data["long_skipped"]),
            }
            if (mode not in MODES or (mode == EATING and values["meal"] not in MEALS)
                    or (mode in (EATING, PAUSED, FINISHED) and values["until"] is None)):
                raise ValueError(mode)
            saved_reminders = data["reminders"]
            reminders = [(r, r.parse(saved_reminders[r.name])) for r in self.reminders if r.name in saved_reminders]
        except (KeyError, TypeError, ValueError, AttributeError):
            return False
        self.__dict__.update(values)
        for reminder, attrs in reminders:
            reminder.__dict__.update(attrs)
        self.held, self.away, self.away_idle = None, False, 0.0
        if self.mode == BREAK:
            self.mode = WORKING
            self.remaining, self.warned = BREAK_RESUME_SEC, False
        gap = (now - saved).total_seconds()
        if gap >= self.away_after():
            self.away_idle = gap
            self.come_back()
        return True
