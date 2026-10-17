"""Rhythmos logic without the UI: settings, the schedule of breaks, water, meals and day end,
building breaks, and statistics. This is what the tests cover."""

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
STATS_PATH = os.path.join(DATA_DIR, "stats.json")  # before 2.16 all days in one file; now stats/<YYYY-MM>.json
STATE_PATH = os.path.join(DATA_DIR, "state.json")  # timer state, so a restart doesn't reset the day
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
    "water_profile": "custom",  # "female" / "male": goal and interval from the recommendation; "custom": manual
    "breakfast_enabled": False,  # breakfast and dinner are often away from the computer, so off by default
    "breakfast_at": 8 * 60,      # minutes from midnight
    "lunch_enabled": True,
    "lunch_at": 13 * 60,
    "dinner_enabled": False,
    "dinner_at": 18 * 60 + 30,
    "meal_pause_min": 45,    # how long "Going to eat" pauses breaks and water
    "meal_snooze_min": 15,   # "In 15 min" in the meal reminder and "15 more min" after the meal pause
    "water_later_min": 15,   # "Later" in the water reminder asks again in this many minutes
    "day_end_snooze_min": 30,  # "30 more min" at the day end; the work limit pushed out asks again too
    "day_end_enabled": True,     # the "workday is over" reminder
    "day_end_at": 18 * 60,
    "workdays": [0, 1, 2, 3, 4],  # weekdays (0 is Monday) with meal and day-end reminders
    "workday_start": 0,          # workday start, minutes from midnight; 0: from the first mouse/keyboard input
    "max_work_hours": 9,         # warn after this many hours at the computer; 0: off
    "intensity": 2,
    "workout_enabled": True,
    "sound": True,
    "language": "",  # "": the system language; the installer writes the language chosen during setup
    "check_updates": True,
    "sound_name": "",        # system notification sound; "": the first available one
    "group_buttons": True,   # muscle group buttons on the break screen; off: random exercises
    "kind_choice": True,     # "Short one instead" / "Long one instead" on the break warning and screen
    "notified_version": "",  # the new version a notification was already shown for
}
MAX_GLASSES = 30          # upper limit for manually entered water per day


# Settings sliders: key → (minimum, maximum, step, format); the label is t("s_<key>")
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
    "breakfast_at": (6 * 60, 11 * 60, 15, fmt_clock),
    "lunch_at": (11 * 60, 16 * 60, 15, fmt_clock),
    "dinner_at": (16 * 60, 22 * 60, 15, fmt_clock),
    "meal_pause_min": (15, 90, 15, fmt_minutes),
    "meal_snooze_min": (5, 60, 5, fmt_minutes),
    "water_later_min": (5, 60, 5, fmt_minutes),
    "day_end_snooze_min": (10, 120, 10, fmt_minutes),
    "day_end_at": (15 * 60, 23 * 60, 15, fmt_clock),
    "workday_start": (5 * 60 + 45, 12 * 60, 15, lambda v: t("auto") if v < 6 * 60 else fmt_clock(v)),
    "max_work_hours": (5, 12, 1, lambda v: t("off") if v < 6 else fmt_minutes(v * 60)),
}
# The leftmost position of these sliders means 0 in the settings: "auto" or "off"
SLIDER_ZERO = {"workday_start": 5 * 60 + 45, "max_work_hours": 5}


def slider_position(key, value):
    """Setting value → slider position."""
    return SLIDER_ZERO[key] if key in SLIDER_ZERO and not value else value


def setting_value(key, position):
    """Slider position → setting value."""
    return 0 if SLIDER_ZERO.get(key) == position else position

MEALS = ("breakfast", "lunch", "dinner")
MEAL_WINDOW_MIN = 60   # the computer woke up more than an hour after meal time: the reminder is pointless
WATER_MIN_PACE_MIN = 15   # sensible water pace: no more often than once in this many minutes
MORNING = dt.time(6, 0)         # when the "until morning" pause ends
EARLIEST_START = dt.time(4, 0)  # the workday starts with the first input no earlier than this; before is night
ACTIVE_IDLE_SEC = 60            # the person is at the computer if mouse or keyboard were used within a minute
MIN_AWAY_MIN = 2                # an absence is never shorter than this, even if the long break is shorter
FINISH_GRACE_MIN = 3            # after "Finish the day": working on longer than this asks whether the day goes on
BREAK_HOLD_MAX_MIN = 30         # a break held during a call or presentation waits no longer than this
STATE_MAX_AGE_H = 12            # an older saved timer state is not restored after a restart

# Recommended daily water goal in 250 ml glasses. EFSA: 2.0 L a day in total for women and 2.5 L for men,
# about 20% of it comes from food, so drink ≈1.6 and ≈2.0 L (rounded up to 7 glasses for women)
WATER_PROFILES = {"female": 7, "male": 8}
WORKDAY_MIN = 8 * 60  # workday length until the day's start and end are known
TYPICAL_START = 9 * 60  # day start when none has been detected yet
WORKDAY_LIMITS = (4 * 60, 14 * 60)  # sensible workday length limits for the water interval


def workday_span(start, end):
    """(start, end) of the workday in minutes: the end is "Workday ends at" from the settings
    (None when off, then 8 hours from the start); the length stays within sensible limits."""
    lo, hi = WORKDAY_LIMITS
    end = start + WORKDAY_MIN if end is None else end
    return start, start + min(max(end - start, lo), hi)


def water_interval_for(goal, workday=WORKDAY_MIN):
    """The longest interval (a multiple of the slider step) that fits `goal` glasses into the workday."""
    lo, hi, step, _fmt = SLIDERS["water_interval_min"]
    return min(max(workday // goal // step * step, lo), hi)


def water_plan(profile, workday=WORKDAY_MIN):
    """(goal, interval in min) for a profile, or None for manual settings."""
    goal = WATER_PROFILES.get(profile)
    return (goal, water_interval_for(goal, workday)) if goal else None


def apply_water_profile(cfg, workday=WORKDAY_MIN):
    """The female/male profile overrides the goal and interval with the recommended values."""
    if cfg["water_profile"] not in WATER_PROFILES:
        cfg["water_profile"] = "custom"
    plan = water_plan(cfg["water_profile"], workday)
    if plan:
        cfg["water_goal"], cfg["water_interval_min"] = plan

WORK_SEC, REST_SEC, WARMUP_SEC = 40, 15, 30


def step(title, text, secs, kind="exercise", phase=""):
    return {"title": title, "text": text, "secs": secs, "kind": kind, "phase": phase}


def pick_many(pool, count):
    """`count` exercises without repeats while the pool lasts."""
    picks = []
    while len(picks) < count:
        picks += random.sample(pool, min(len(pool), count - len(picks)))
    return picks


def link_rests(steps):
    """"Next: …" captions in rest steps, from the following exercise."""
    for i, s in enumerate(steps):
        if s["kind"] == "rest":
            upcoming = next((n for n in steps[i + 1:] if n["kind"] == "work"), None)
            if upcoming:
                s["text"] = t("rest_next", title=upcoming["title"])


def build_workout(total, level, group=None):
    """An interval workout of exactly `total` seconds: warm-up, work/rest, cool-down."""
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
    """Replaces the workout exercises from step `start` on with exercises of the chosen group."""
    targets = [s for s in steps[start:] if s["kind"] == "work"]
    for s, (title, text, _group) in zip(targets, pick_many(exercises.workout_pool(level, group), len(targets))):
        s["title"], s["text"] = title, text
    link_rests(steps)


def single_break_step(kind, cfg, group=None, avoid=None):
    """One step of a mini break or a long break without a workout."""
    if kind == "mini":
        pool = exercises.mini_pool(cfg["intensity"], group)
    else:
        pool = exercises.long_pool(group)
    fresh = [e for e in pool if e[0] != avoid] or pool  # choosing the group again gives another exercise
    title, body, _group = random.choice(fresh)
    if kind == "mini":
        return step(title, body, cfg["mini_duration_sec"], phase=t("phase_mini"))
    text = "\n".join(f"{i}.  {line}" for i, line in enumerate(body, 1))
    return step(title, text, cfg["long_duration_min"] * 60, "list", t("phase_long"))


def other_kind(kind):
    """The break kind offered instead: "Short one instead" on a long break, "Long one instead" on a mini one."""
    return "mini" if kind == "long" else "long"


def build_break(kind, cfg, group=None):
    """The list of break steps. A mini break and a plain long break are one step."""
    total = cfg["long_duration_min"] * 60
    if kind == "long" and cfg["workout_enabled"] and total >= 120:
        return build_workout(total, cfg["intensity"], group)
    return [single_break_step(kind, cfg, group)]


# ---------- data ----------

def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, data, compact=False):
    """Atomic write; compact (no indentation) for statistics, which are written often and only grow."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        if compact:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def migrate_config(saved):
    """Old settings → current keys. "Meals and day end on weekdays only" (workdays_only)
    became a list of workdays: the switch turned off meant "every day"."""
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
    cfg["workdays"] = list(cfg["workdays"])  # an own list, not the one shared with DEFAULTS
    apply_water_profile(cfg)
    i18n.set_language(cfg["language"] or system.system_language())
    return cfg


DERIVED_KEYS = ("water_goal", "water_interval_min")  # computed, not set, under the Female/Male norm


def save_config(cfg):
    """Saves the person's settings, and only them. The app never changes settings on their behalf:
    under the Female/Male norm the water goal and interval are derived (recomputed from the workday), so
    the file keeps the person's own Custom values, not the computed ones."""
    data = dict(cfg)
    if cfg.get("water_profile") in WATER_PROFILES:
        saved = load_json(CONFIG_PATH, {})
        for key in DERIVED_KEYS:
            data[key] = saved.get(key, DEFAULTS[key])
    save_json(CONFIG_PATH, data)


def restore_manual_water(cfg):
    """Switched to Custom: bring back the person's own values from the file, not the ones computed by the norm."""
    saved = load_json(CONFIG_PATH, {})
    for key in DERIVED_KEYS:
        cfg[key] = saved.get(key, DEFAULTS[key])


def set_language_setting(code):
    """--set-language: the installer saves the language chosen during setup."""
    cfg = load_json(CONFIG_PATH, {})
    cfg["language"] = code if code in i18n.LANGUAGES else ""
    save_json(CONFIG_PATH, cfg)


def minute_of_day(moment):
    """Minutes from midnight: 13:45 → 825. Times of day are stored like this in settings and statistics."""
    return moment.hour * 60 + moment.minute


def day_minute(date, moment):
    """Minutes from midnight of the workday `date`: after midnight, past 24:00 (00:30 → 1470).
    The event log stores time like this, so spans and order stay correct at night too."""
    return int((moment - dt.datetime.combine(date, dt.time())).total_seconds() // 60)


def at_minute(date, minutes):
    """The moment of day `date`, `minutes` minutes after midnight."""
    return dt.datetime.combine(date, dt.time()) + dt.timedelta(minutes=minutes)


def workday_date(moment):
    """The day a moment belongs to is the plain calendar date: from 00:00 to 24:00.
    This date is the statistics key and "today" for reminders."""
    return moment.date()


def at_workday_minute(date, minutes):
    """The moment of day `date` by minutes from midnight (a time from the settings)."""
    return at_minute(date, minutes)


def work_started(now, idle_seconds):
    """The minute of the day work started, or None: the person is at the computer (recent mouse or keyboard)
    and it is no longer night, the day starts no earlier than EARLIEST_START. The moment is the last input, not this tick."""
    started = now - dt.timedelta(seconds=idle_seconds)
    if idle_seconds > ACTIVE_IDLE_SEC or started.time() < EARLIEST_START or started.date() != now.date():
        return None
    return minute_of_day(started)


ACTIVITY_EVENTS = ("water", "meal", "break", "day_start")


def first_activity(rec):
    """The day starts with the earliest known activity: the recorded day_start, glasses, meals, logged breaks.
    First-input detection may have appeared mid-day (an update), and then earlier glasses or meals are more accurate.
    Night (before EARLIEST_START) is not a day start."""
    earliest = EARLIEST_START.hour * 60 + EARLIEST_START.minute
    times = [rec.get("day_start", 0)] + list(rec.get("water_at", []))
    times += [m for meal in MEALS for m in rec.get(f"ate_{meal}_at", [])]
    times += [e["at"] for e in rec.get("events", []) if e.get("type") in ACTIVITY_EVENTS]
    times = [m for m in times if m and earliest <= m < 24 * 60]
    return min(times) if times else 0


def average_minute(minutes):
    """Average time of day (minutes from midnight) over the days that have it; None if there are none."""
    minutes = [m for m in minutes if m]
    return round(sum(minutes) / len(minutes)) if minutes else None


def fmt_time(seconds):
    seconds = max(0, int(round(seconds)))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class Stats:
    # work_sec: time at the computer (the timer runs: no pause, break or meal), active_sec: time on breaks,
    # meals: how many meals were eaten (sum of ate_*), ate_<meal>: 1 if that meal was eaten today ("Going to eat"
    # or the plate on Status); day_start: when work started (first mouse or keyboard input),
    # day_end: when the day was finished; both in minutes from midnight, 0 when not yet
    KEYS = ("mini_done", "long_done", "skipped", "postponed", "water", "work_sec", "active_sec", "meals",
            "day_start", "day_end", "ate_breakfast", "ate_lunch", "ate_dinner")
    MOMENTS = ("day_start", "day_end")  # times of day, not counters: never summed

    # Stored one file per month (stats/2026-10.json): a change rewrites only its month, so a write
    # stays small however long the history is (it happens every minute and on every logged event)

    def __init__(self, today=None):
        self.folder = os.path.splitext(STATS_PATH)[0]
        self.data = self.load()
        self.today = today or dt.date.today  # the current workday (App.today)

    @staticmethod
    def month(key):
        return key[:7]  # "2026-10-14" → "2026-10"

    def load(self):
        """All days from the monthly files. The single stats.json of older versions is split into months
        once (into a temporary folder renamed at the end, so a crash halfway loses nothing) and kept as
        stats-before-2.16.json."""
        legacy = os.path.exists(STATS_PATH)
        if not os.path.isdir(self.folder) and legacy:
            data = load_json(STATS_PATH, {})
            tmp = self.folder + ".tmp"
            for month in {self.month(key) for key in data}:
                save_json(os.path.join(tmp, f"{month}.json"),
                          {k: v for k, v in data.items() if self.month(k) == month}, compact=True)
            if data:
                os.replace(tmp, self.folder)
        data = {}
        if os.path.isdir(self.folder):
            for name in sorted(os.listdir(self.folder)):
                if name.endswith(".json"):
                    data.update(load_json(os.path.join(self.folder, name), {}))
            if legacy:
                os.replace(STATS_PATH, os.path.join(os.path.dirname(STATS_PATH), "stats-before-2.16.json"))
        return data

    def save(self, key):
        """Writes the month of day `key`."""
        month = self.month(key)
        save_json(os.path.join(self.folder, f"{month}.json"),
                  {k: v for k, v in self.data.items() if self.month(k) == month}, compact=True)

    def add(self, key, amount=1):
        day = self.today().isoformat()
        rec = self.data.setdefault(day, {})
        rec[key] = rec.get(key, 0) + amount
        self.save(day)

    def set(self, key, value):
        """Manual correction of today's counter (for example, the number of water glasses)."""
        day = self.today().isoformat()
        rec = self.data.setdefault(day, {})
        rec[key] = max(0, int(value))
        self.save(day)

    def day(self, date):
        rec = self.data.get(date.isoformat(), {})
        day = {k: rec.get(k, 0) for k in self.KEYS}
        day["day_start"] = first_activity(rec)
        return day

    def times(self, date, key):
        """The day's list of event moments (minutes from midnight), e.g. water_at: when water was drunk."""
        return list(self.data.get(date.isoformat(), {}).get(key, []))

    def set_times(self, key, values):
        day = self.today().isoformat()
        rec = self.data.setdefault(day, {})
        rec[key] = list(values)
        self.save(day)

    # --- the day's event log ---
    # Besides counters, each day has an "events" list: it drives the day timeline and the regularity
    # facts. An event is a dict: "type" and "at" (minute of the workday, day_minute), then per type:
    #   break     kind (mini/long), result (done/skipped/postponed), sec: how long it lasted;
    #   away      to: the person was away from at to to;
    #   pause     to, kind (timed/eating/finished), meal: for eating;
    #   held      to, reason (fullscreen/camera/microphone): the break waited for a call or a presentation;
    #   water, meal (meal), day_start, day_end, overwork: moments.
    # A span still in progress (a pause, a held break) has to = None; close() ends it.
    # The counters above are still written: old days have no events, and the rest of the code reads them

    def events(self, date):
        return [dict(e) for e in self.data.get(date.isoformat(), {}).get("events", [])]

    def log(self, event_type, at, /, date=None, replace=None, **fields):
        """Logs `event_type` at minute `at` in the log of day `date` (today by default); one disk
        write. replace is a tuple of fields: an event of the same type with the same values of these fields
        is replaced (day end, an eaten meal) instead of adding another. Returns the event's index in the day's log."""
        day = (date or self.today()).isoformat()
        rec = self.data.setdefault(day, {})
        events = rec.setdefault("events", [])
        event = {"type": event_type, "at": int(at), **fields}
        index = len(events)
        if replace is not None:
            index = next((i for i, e in enumerate(events) if e.get("type") == event_type
                          and all(e.get(f) == fields.get(f) for f in replace)), index)
        if index < len(events):
            events[index] = event
        else:
            events.append(event)
        self.save(day)
        return index

    def close(self, date, index, to):
        """A span in progress (to = None) ended at minute `to`."""
        events = self.data.get(date.isoformat(), {}).get("events", [])
        if 0 <= index < len(events) and events[index].get("to") is None:
            events[index]["to"] = max(int(to), events[index]["at"])
            self.save(date.isoformat())

    def unlog(self, event_type, /, date=None, **match):
        """Removes `event_type` events with these fields (the "eaten" mark was taken off)."""
        day = (date or self.today()).isoformat()
        rec = self.data.get(day, {})
        events = rec.get("events", [])
        kept = [e for e in events if not (e.get("type") == event_type and all(e.get(k) == v for k, v in match.items()))]
        if len(kept) != len(events):
            rec["events"] = kept
            self.save(day)

    def open_spans(self, dates):
        """[(date, index, event)] of spans still in progress (to = None), to close them after a restart."""
        return [(date, i, e) for date in dates for i, e in enumerate(self.events(date))
                if e.get("type") in SPAN_TYPES and e.get("to") is None]

    def dates(self):
        """All days with statistics, in order."""
        found = []
        for key in self.data:
            try:
                found.append(dt.date.fromisoformat(key))
            except ValueError:
                pass
        return sorted(found)


SPAN_TYPES = ("away", "pause", "held")   # span events: they have an end "to"
PAUSE_KINDS = {"paused": "timed", "eating": "eating", "finished": "finished"}  # mode → pause kind in the log


def absence_span(date, now, seconds, day_start):
    """(from, to) of an absence in minutes of the workday `date` that ended at `now` and lasted `seconds`;
    None if the workday hasn't started yet (the night and the morning before the first input are not an absence).
    The start is no earlier than the day start: after an "until morning" pause the person is "away" since last evening."""
    if not day_start:
        return None
    end = day_minute(date, now)
    start = max(day_minute(date, now - dt.timedelta(seconds=seconds)), day_start)
    return (start, end) if end > start else None


def event_end(event, now=None, last=None):
    """End of a span: the recorded one, or "now" (now, for today), or the last known minute of the day."""
    if event.get("to") is not None:
        return event["to"]
    return max(event["at"], now if now is not None else (last if last is not None else event["at"]))


def event_spans(events, now=None):
    """The day's spans: [(type, from, to, event)]: absences, pauses and held breaks, in order.
    An open span lasts until now (today) or until the day's last event."""
    last = max((e.get("to") or e["at"] for e in events), default=None)
    spans = [(e["type"], e["at"], event_end(e, now, last), e) for e in events if e.get("type") in SPAN_TYPES]
    return sorted(spans, key=lambda s: s[1])


def day_bounds(events, now=None):
    """(start, end) of the workday from the log: day_start and day_end, or the first event and now/the last event."""
    if not events:
        return None
    start = next((e["at"] for e in events if e["type"] == "day_start"), None)
    end = next((e["at"] for e in events if e["type"] == "day_end"), None)
    first = min(e["at"] for e in events)
    last = max(max(e["at"], e.get("to") or 0) for e in events)
    return (start if start is not None else first,
            end if end is not None else (now if now is not None else last))


def regularity(events, now=None):
    """The day's regularity from the log (None without events): breaks on time (not postponed), after
    postponing, and skipped; how many times and minutes the person was away; the longest stretch of work
    without a break (a break, an absence, or a meal or plain pause is rest); how many times
    a break waited for a call to end."""
    if not events:
        return None
    result = {"on_time": 0, "late": 0, "skipped": 0, "postponed": 0, "away": 0, "away_min": 0,
              "held": 0, "longest_min": 0}
    rests = []
    postponed = False
    for e in sorted(events, key=lambda e: e["at"]):
        kind = e["type"]
        if kind == "break":
            if e.get("result") == "postponed":
                result["postponed"] += 1
                postponed = True
            elif e.get("result") == "skipped":
                result["skipped"] += 1
                postponed = False
            else:
                result["late" if postponed else "on_time"] += 1
                postponed = False
                rests.append((e["at"], e["at"] + -(-e.get("sec", 0) // 60)))
        elif kind == "held":
            result["held"] += 1
    for kind, start, end, e in event_spans(events, now):
        if kind == "away":
            result["away"] += 1
            result["away_min"] += end - start
            rests.append((start, end))
        elif kind == "pause":  # the "until morning" pause too: after "Finish the day" it's no longer work
            rests.append((start, end))
    result["longest_min"] = longest_work_stretch(day_bounds(events, now), rests)
    return result


def current_stretch(events, now):
    """How many minutes the person has been working in a row: since the end of the last rest (a done break,
    an absence, a pause) or since the day start; `now` is a minute of the day. 0 if the day hasn't started."""
    bounds = day_bounds(events, now)
    if not bounds:
        return 0
    rest_end = bounds[0]
    for e in events:
        if e["type"] == "break" and e.get("result") == "done" and e["at"] <= now:
            rest_end = max(rest_end, e["at"] + -(-e.get("sec", 0) // 60))
    for kind, _start, end, _e in event_spans(events, now):
        if kind in ("away", "pause") and end <= now:
            rest_end = max(rest_end, end)
    return max(0, now - rest_end)


def longest_work_stretch(bounds, rests):
    """The longest stretch between rests (minutes) within the workday `bounds`."""
    if not bounds:
        return 0
    start, end = bounds
    longest, cursor = 0, start
    for rest_from, rest_to in sorted(rests):
        if rest_from > cursor:
            longest = max(longest, min(rest_from, end) - cursor)
        cursor = max(cursor, rest_to)
        if cursor >= end:
            break
    return max(longest, end - cursor, 0)


DAY_COLUMNS = ("date",) + Stats.KEYS + ("breaks_on_time", "away_count", "away_min", "longest_without_break_min")
EVENT_COLUMNS = ("date", "time", "type", "until", "kind", "result", "seconds", "meal", "reason")


def export_csv(stats, path, now=None, today=None):
    """All statistics as CSV: `path` has a row per day (counters and regularity from the log),
    next to it `<name>-events.csv` has every logged event. Times are "HH:MM". Returns both paths.
    UTF-8 with BOM so Excel doesn't break Cyrillic."""
    import csv
    base, ext = os.path.splitext(path)
    events_path = f"{base}-events{ext or '.csv'}"
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(DAY_COLUMNS)
        for date in stats.dates():
            rec = stats.day(date)
            reg = regularity(stats.events(date), now if date == today else None) or {}
            writer.writerow([date.isoformat()]
                            + [(fmt_clock(rec[k]) if rec[k] else "") if k in Stats.MOMENTS else rec[k]
                               for k in Stats.KEYS]
                            + [reg.get("on_time", ""), reg.get("away", ""), reg.get("away_min", ""),
                               reg.get("longest_min", "")])
    with open(events_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(EVENT_COLUMNS)
        for date in stats.dates():
            for e in sorted(stats.events(date), key=lambda e: e["at"]):
                to = e.get("to")
                writer.writerow([date.isoformat(), fmt_clock(e["at"]), e["type"],
                                 fmt_clock(to) if to is not None else "", e.get("kind", ""), e.get("result", ""),
                                 e.get("sec", ""), e.get("meal", ""), e.get("reason", "")])
    return path, events_path


def split_balanced(heights, columns, gap=14):
    """Splits cards (in the given order) into `columns` consecutive groups so the tallest column
    is as short as possible: the reading order (top to bottom, left to right) is kept.
    Returns lists of card indices for each column."""
    return _best_split(heights, columns, gap)[1]


def split_orders(heights, orders, columns, gap=14):
    """The same for several allowed card orders (all grouped logically by theme): picks the order that
    gives the shortest and evenest columns. Returns groups of indices into `heights`, each in reading order."""
    best = min((_best_split([heights[i] for i in order], columns, gap), order) for order in orders)
    (_score, groups), order = best
    return [[order[i] for i in group] for group in groups]


def _best_split(heights, columns, gap):
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
            # First, the shortest tallest column. Then the least empty space per card:
            # shorter columns stretch their cards to the height of the tallest, and it's better when several
            # cards share the slack than when one card stands with a large empty bottom
            slack = max((worst - h) / len(g) for h, g in zip(heights_now, groups))
            score = (worst, slack)
            if best is None or score < best[0]:
                best = (score, groups)
            return
        for end in range(start + 1, n - left + 2):
            search(end, left - 1, groups + [list(range(start, end))])

    search(0, columns, [])
    return best


def main_layout(available_width):
    """Main window layout for the width of the screen's work area: settings columns,
    statistics cards per row, and the preferred window width."""
    if available_width >= 1300:
        return {"columns": 4, "stat_cards": 6, "width": 1280}
    if available_width >= 1100:
        return {"columns": 3, "stat_cards": 6, "width": 1080}
    return {"columns": 2, "stat_cards": 3, "width": 900}


def completion_rate(rec):
    """Share of done breaks among done and skipped ones, %; None if there were no breaks."""
    done = rec["mini_done"] + rec["long_done"]
    total = done + rec["skipped"]
    return round(100 * done / total) if total else None


def water_streak(stats, goal, today):
    """How many days in a row the water goal was met. Today isn't over yet, so if the goal isn't met
    so far, count from yesterday."""
    day = today if stats.day(today)["water"] >= goal else today - dt.timedelta(days=1)
    streak = 0
    while stats.day(day)["water"] >= goal:
        streak += 1
        day -= dt.timedelta(days=1)
    return streak


def fmt_hm(seconds):
    """Duration on a card: 6 h 5 min → "6:05"."""
    minutes = int(seconds) // 60
    return f"{minutes // 60}:{minutes % 60:02d}"


# ---------- timer ----------

def stale(due, now):
    """A snoozed reminder is stale: its time passed more than MEAL_WINDOW_MIN ago (the computer slept),
    and showing it now, in the morning or after lunch, no longer makes sense."""
    return now - due > dt.timedelta(minutes=MEAL_WINDOW_MIN)


def _iso(value):
    return value.isoformat() if value else None


def _moment(text):
    return dt.datetime.fromisoformat(text) if text else None


def _date(text):
    return dt.date.fromisoformat(text) if text else None


# The person's state (Scheduler.mode). Nobody chooses AWAY: idleness decides it, and it only
# overlays the mode (Scheduler.state): a pause or "until morning" must go on while the person is away
WORKING, BREAK, EATING, PAUSED, FINISHED, AWAY = "working", "break", "eating", "paused", "finished", "away"
MODES = (WORKING, BREAK, EATING, PAUSED, FINISHED)

# What each state stops: the break countdown, the water countdown, wall-clock reminders (meals, day
# end, overwork). The single place where this is decided
BREAKS, WATER, CLOCK = "breaks", "water", "clock"
FREEZES = {
    WORKING: frozenset(),
    PAUSED: frozenset({BREAKS}),                  # a plain pause stops only breaks
    BREAK: frozenset({BREAKS, WATER, CLOCK}),
    EATING: frozenset({BREAKS, WATER, CLOCK}),    # until "Continue" after the meal
    FINISHED: frozenset({BREAKS, WATER, CLOCK}),  # "until morning": the workday is over
    AWAY: frozenset({BREAKS, WATER, CLOCK}),      # reminders don't pop up into an empty room
}
STATE_VERSION = 1
BREAK_RESUME_SEC = 60  # a break interrupted by quitting the app starts a minute after launch


class Reminder:
    """A reminder with rules shared by all; Scheduler.tick polls them in turn every second (poll).

    A reminder stands still (no countdown, no popup) if the person's state freezes its gate `gate`
    (FREEZES) or quiet(now): disabled, a day off, already answered, the day finished, the goal reached.
    An open one waits for an answer and doesn't pop up twice; a new one pops up only when no
    reminder from the `waits` groups is open (day end waits for meal answers). A snoozed one fires
    at snoozed_until, a stale one (stale: the computer slept) is dropped. Otherwise its own trigger
    triggered(now); shown is the workday when it already fired at its own time.
    The answer "snooze" postpones by the setting snooze_key; any other answer is final until the end of the workday."""
    gate = CLOCK
    group = None
    waits = ()
    snooze_key = "meal_snooze_min"

    def __init__(self, sched, name, event):
        self.sched, self.name, self.event = sched, name, event
        self.open = False
        self.snoozed_until = None
        self.moved_to = None  # where "snooze" moved the reminder: still its time once it pops up again
        self.shown = None
        self.answered = None  # (workday, answer)

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
        """Work-time countdown, only for reminders with a countdown (water)."""

    def poll(self, seconds, now, frozen):
        """One tick; True if the reminder just fired (it is open now)."""
        if self.gate in frozen or self.quiet(now) or self.open:
            return False
        self.advance(seconds)
        if any(r.open for r in self.sched.reminders if r.group in self.waits):
            return False
        if self.snoozed_until is not None:
            if stale(self.snoozed_until, now):
                self.snoozed_until = None  # the computer slept: the snoozed reminder is pointless now
            elif now >= self.snoozed_until:
                # A snoozed reminder is about the same day: shown is not overwritten
                self.snoozed_until = None
                self.open = True
                return True
            else:
                return False
        if self.triggered(now):
            self.open = True
            self.shown = self.sched.workday(now)
            self.moved_to = None
            return True
        return False

    def answer(self, answer, now):
        self.open = False
        if answer == "snooze":
            self.snoozed_until = self.moved_to = now + dt.timedelta(minutes=self.cfg[self.snooze_key])
        elif answer:
            self.answered = (self.sched.workday(now), answer)
            self.moved_to = None

    def cancel(self):
        """The day is finished: open and snoozed reminders aren't needed (they would fire in the morning)."""
        self.open = False
        self.snoozed_until = self.moved_to = None

    def snapshot(self):
        # The popup is gone after a restart: an open reminder pops up again
        return {"snoozed_until": _iso(self.snoozed_until), "shown": None if self.open else _iso(self.shown),
                "answered": [self.answered[0].isoformat(), self.answered[1]] if self.answered else None}

    def parse(self, data):
        """Saved snapshot() → attributes; broken data raises KeyError/TypeError/ValueError."""
        answered = data["answered"]
        return {"open": False, "snoozed_until": _moment(data["snoozed_until"]), "shown": _date(data["shown"]),
                "answered": (_date(answered[0]), str(answered[1])) if answered else None}


class WaterReminder(Reminder):
    """Water: a work-time countdown. "Done" schedules the next glass at a sensible pace (Scheduler.water_interval),
    "Later" in water_later_min; silent when the reminder is off or the daily goal is reached."""
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
        self.remaining = self.sched.water_interval(now) if drank else self.cfg["water_later_min"] * 60

    def snapshot(self):
        return {"remaining": 0 if self.open else self.remaining}

    def parse(self, data):
        return {"open": False, "remaining": float(data["remaining"])}


class MealReminder(Reminder):
    """Breakfast, lunch or dinner: at its time, but no later than MEAL_WINDOW_MIN after it
    (the computer woke up later, so the reminder is pointless). Answers: "eat", "skip", "snooze"."""
    group = "meal"
    waits = ("meal",)

    def quiet(self, now):
        return (not self.cfg[f"{self.name}_enabled"] or not self.sched.reminders_today(now)
                or self.answer_on(self.sched.workday(now)) is not None)

    def triggered(self, now):
        at = self.sched.moment(now, self.cfg[f"{self.name}_at"])
        return self.shown != self.sched.workday(now) and at <= now < at + dt.timedelta(minutes=MEAL_WINDOW_MIN)


class MealOverReminder(Reminder):
    """The meal pause is over: "Continue?". Asks once and waits for the answer: the meal pause doesn't
    end by itself. "15 more min" moves its end (Scheduler.extend_meal)."""
    gate = None
    group = "meal_over"

    def quiet(self, now):
        return self.sched.mode != EATING

    def triggered(self, now):
        return now >= self.sched.until


class DayEndReminder(Reminder):
    """The workday is over (at its time or after "30 more min") and the person is still at the computer.
    Answers: "snooze", "finish" (App sets the "until morning" pause)."""
    group = "day"
    waits = ("meal", "day")
    snooze_key = "day_end_snooze_min"

    def quiet(self, now):
        return (not self.cfg["day_end_enabled"] or not self.sched.reminders_today(now)
                or self.sched.day_finished(now) or self.answer_on(self.sched.workday(now)) is not None)

    def triggered(self, now):
        return self.shown != self.sched.workday(now) and now >= self.sched.moment(now, self.cfg["day_end_at"])


class OverworkReminder(Reminder):
    """More than the daily limit (max_work_hours) at the computer today, once a day.
    Answers: "later", "finish" (App sets the "until morning" pause); "snooze" asks again (the window
    was pushed out by another notification before the person answered)."""
    group = "day"
    waits = ("meal", "day")
    snooze_key = "day_end_snooze_min"

    def quiet(self, now):
        return (not self.cfg["max_work_hours"] or self.sched.day_finished(now)
                or self.answer_on(self.sched.workday(now)) is not None)

    def triggered(self, now):
        return (self.shown != self.sched.workday(now)
                and self.sched.worked >= self.cfg["max_work_hours"] * 3600)


class Scheduler:
    """The day's schedule: the person's state (mode), the work-time countdown to a break, and reminders.
    The countdown resets only after a break, an absence or on request; locking the screen doesn't reset it.
    State changes happen only through the methods below; what each state freezes is FREEZES."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.mode = WORKING
        self.until = None          # end of a pause, "until morning" or a meal pause
        self.meal = None           # which meal is being eaten (EATING)
        self.finished_at = None    # when "Finish the day" was pressed (the "until morning" pause)
        self.active_since = None   # since when the person has worked continuously after "Finish the day"
        self.open_pause = False    # the Pause button's pause: until "Continue" (at the latest the morning)
        self.continue_asked = None  # "Still working?" after "Finish the day": None, "open" or "no" (until morning)
        self.away = False          # the person isn't at the computer (see away_after)
        self.away_idle = 0.0       # the longest idleness during this absence
        self.last_away = 0.0       # how many seconds the last absence lasted (logged on the "back" event)
        self.breaks_taken = 0
        self.postpones = 0
        self.long_skipped = False  # a long break was skipped: the next one is long again (once)
        self.chosen = None         # "mini"/"long" the person chose for the coming break instead of its kind
        self.held = None           # seconds the break has been held by busyness; None when not held
        # What App knows about today (update_day): for the water pace and the work limit
        self.drunk = 0
        self.workday_end = None
        self.worked = 0
        self.water_done = False    # the daily water goal is reached: no reminders until tomorrow
        self._set_countdown(self.cfg["mini_interval_min"] * 60)
        self.water = WaterReminder(self)
        self.meals = {meal: MealReminder(self, meal, "meal") for meal in MEALS}
        self.meal_over = MealOverReminder(self, "meal_over", "meal_over")
        self.day_end = DayEndReminder(self, "day_end", "day_end")
        self.overwork = OverworkReminder(self, "overwork", "overwork")
        # The order is the priority: of those waiting for each other (waits), only the first pops up per tick
        self.reminders = [self.water, *self.meals.values(), self.meal_over, self.day_end, self.overwork]

    def _set_countdown(self, seconds):
        self.remaining = self.period = seconds
        self.warned = False
        self.held = None

    # --- state ---

    @property
    def state(self):
        """The mode, or AWAY if the person is away."""
        return AWAY if self.away else self.mode

    def frozen(self):
        return FREEZES[self.state]

    # Read-only properties for the UI
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
        """The "until morning" pause stops water too, a plain one only breaks."""
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
        """Which meal has an open reminder now."""
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
        """The day of the moment `now`: the calendar date."""
        return workday_date(now)

    def moment(self, now, minutes):
        """A moment today by minutes from midnight (a time from the settings)."""
        return at_workday_minute(self.workday(now), minutes)

    def morning(self, now):
        """End of the "until morning" pause: the nearest MORNING (06:00); after midnight that is this same
        morning, not the next one (otherwise the pause would last ~30 h)."""
        morning = dt.datetime.combine(now.date(), MORNING)
        return morning if now < morning else morning + dt.timedelta(days=1)

    def away_after(self):
        """Seconds without mouse and keyboard that count as an absence: like a long break, but at least MIN_AWAY_MIN."""
        return max(MIN_AWAY_MIN, self.cfg["long_duration_min"]) * 60

    def reminders_today(self, now):
        """Whether to remind about meals and day end today: only on the workdays from the settings."""
        return self.workday(now).weekday() in self.cfg["workdays"]

    def day_finished(self, now):
        return self.finished_at is not None and self.workday(self.finished_at) == self.workday(now)

    def update_day(self, drunk, workday_end=None, worked=0):
        """What App knows about today: glasses drunk, the workday end (datetime or None)
        and how many seconds were already worked."""
        self.drunk, self.workday_end, self.worked = drunk, workday_end, worked
        self.water_done = drunk >= self.cfg["water_goal"]

    # --- per-second countdown ---

    def tick(self, seconds, now=None, idle=0.0, busy=False):
        """One step. idle: seconds without mouse and keyboard (system.idle_seconds); busy: the person
        is on a call or sharing the screen, so the break waits (no longer than BREAK_HOLD_MAX_MIN). Returns events:
        "warn", "break", "break_held", "water", "meal", "meal_over", "day_end", "overwork",
        "ask_continue", "back"."""
        now = now or dt.datetime.now()
        events = []
        if self.mode in (PAUSED, FINISHED) and now >= self.until:
            self.mode, self.until = WORKING, None  # the pause ended by itself
        # The day was finished but the person keeps using the computer (FINISH_GRACE_MIN of continuous input,
        # not a moment to glance at mail): "Still working?" is asked once. The day never goes on by itself —
        # until 2.18.0 it did, and an evening at the computer turned into work time with breaks and water.
        if (self.mode == FINISHED and self.day_finished(now) and self.continue_asked is None
                and idle < ACTIVE_IDLE_SEC):
            if self.active_since is None:
                self.active_since = now
            elif now - max(self.active_since, self.finished_at) >= dt.timedelta(minutes=FINISH_GRACE_MIN):
                self.continue_asked, self.active_since = "open", None
                events.append("ask_continue")
        else:
            self.active_since = None
        # Away for longer than a long break is a natural break: timers stand, and on return
        # the countdown to the break starts over
        if idle >= self.away_after() and self.mode not in (BREAK, EATING):
            self.away = True
            self.away_idle = max(self.away_idle, idle)
        elif self.away:
            self.come_back()
            events.append("back")
        if BREAKS not in self.frozen():
            events += self._count_down(seconds, busy)
        frozen = self.frozen()  # a break may have just started
        events += [r.event for r in self.reminders if r.poll(seconds, now, frozen)]
        return events

    def _count_down(self, seconds, busy):
        """Countdown to the break. While the person is busy, the warning and the break wait (the countdown stays at zero),
        but no longer than BREAK_HOLD_MAX_MIN; "break_held" fires once, when the waiting starts."""
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
        """The person is back: the absence was a natural break, the countdown starts over.
        An absence twice as long as the long break was the long break: a full cycle until the next one."""
        self.away = False
        self.postpones = 0
        self.chosen = None  # a choice made before the absence was for that moment
        self._set_countdown(self.cfg["mini_interval_min"] * 60)
        if self.away_idle >= self.cfg["long_duration_min"] * 60 * 2:
            every = max(1, self.cfg["long_every"])
            self.breaks_taken = -(-self.breaks_taken // every) * every
            self.long_skipped = False
        self.last_away = self.away_idle
        self.away_idle = 0.0

    # --- breaks ---

    def natural_until_long(self):
        """Breaks left until the long one by the rhythm alone, including it: 1 means the next break is long."""
        if self.long_skipped:
            return 1
        every = max(1, self.cfg["long_every"])
        return every - self.breaks_taken % every

    def breaks_until_long(self):
        """Breaks left until the long one, counting the person's choice for the coming break."""
        left = self.natural_until_long()
        if self.chosen == "long":
            return 1
        if self.chosen == "mini" and left == 1:
            return 2
        return left

    def natural_kind(self):
        return "long" if self.natural_until_long() == 1 else "mini"

    def next_kind(self):
        return self.chosen or self.natural_kind()

    @property
    def swapped(self):
        """The coming (or current) break is of the kind the person chose instead of the rhythm's one."""
        return self.chosen is not None and self.chosen != self.natural_kind()

    def choose_kind(self, kind):
        """"Short one instead" / "Long one instead": only this break, never the settings.
        None or the rhythm's own kind drops the choice."""
        self.chosen = kind if kind != self.natural_kind() else None

    def start_break(self):
        """"Break now": a break matters more than a pause or a meal."""
        self.mode, self.until, self.meal = BREAK, None, None
        self.meal_over.open = False

    def finish_break(self, skipped=False):
        """The break is over (done, skipped, or interrupted by a pause). A skipped long break comes back:
        the next break is long again, but only once; then the rhythm goes on as usual.
        A swapped break that was done: a mini one instead of the long one keeps the long one next;
        a long one instead of a mini one starts the count to the next long break over.
        A skipped swapped break is skipped by the rhythm's own kind."""
        swapped, chosen = self.swapped, self.chosen
        self.chosen = None
        if self.mode == BREAK:
            self.mode = WORKING
        self.postpones = 0
        self._set_countdown(self.cfg["mini_interval_min"] * 60)
        if swapped and not skipped:
            if chosen == "long":
                every = max(1, self.cfg["long_every"])
                self.breaks_taken = -(-(self.breaks_taken + 1) // every) * every
                self.long_skipped = False
            return
        long = self.natural_kind() == "long"
        if skipped and long and not self.long_skipped:
            self.long_skipped = True
        else:
            self.long_skipped = False
            self.breaks_taken += 1

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

    # --- pause and day end ---

    def pause(self, minutes=0, now=None):
        """minutes=0 is the Pause button: until "Continue", at the latest the morning, so a forgotten pause
        never carries into the next day. minutes=None means "until morning": the day is finished, so snoozed
        meal and day-end reminders are cancelled too, otherwise they would fire in the morning.
        Other minutes: a timed pause (no button offers it since 2.18.2)."""
        now = now or dt.datetime.now()
        self.meal = None
        self.meal_over.cancel()
        self.open_pause = minutes == 0
        if minutes is None:
            self.mode, self.until, self.finished_at = FINISHED, self.morning(now), now
            self.continue_asked, self.active_since = None, None
            for r in (*self.meals.values(), self.day_end, self.overwork):
                r.cancel()
            self.day_end.shown = self.workday(now)
        elif minutes == 0:
            self.mode, self.until = PAUSED, self.morning(now)
        else:
            self.mode, self.until = PAUSED, now + dt.timedelta(minutes=minutes)

    def resume(self, now=None):
        """The person ends the pause. After "Finish the day" that is their answer that the day goes on:
        it is no longer finished right away (no waiting for FINISH_GRACE_MIN). Returns True in that case.
        A day finished before its end time gets the day-end question back at that time; the person decides then."""
        if not self.paused:
            return False
        now = now or dt.datetime.now()
        continued = self.mode == FINISHED
        self.mode, self.until = WORKING, None
        if continued:
            self.finished_at, self.active_since, self.continue_asked = None, None, None
            if now < self.moment(now, self.cfg["day_end_at"]):
                self.day_end.shown = None
        return continued

    def continue_answered(self, answer, now=None):
        """"Still working?" after "Finish the day": "continue" goes on with the day (as "Continue", True is
        returned), "no" keeps it finished and doesn't ask again until morning, "snooze" (the window was pushed
        out before an answer) asks again after another FINISH_GRACE_MIN of work."""
        if answer == "continue":
            return self.resume(now)
        self.continue_asked = "no" if answer == "no" else None
        return False

    def day_end_answered(self, answer, now=None):
        """answer: "snooze" reminds again in 30 min, "finish" finishes the day (App sets the pause)."""
        self.day_end.answer(answer, now or dt.datetime.now())

    def overwork_answered(self, answer, now=None):
        """answer: "later" means no more reminders today, "finish" finishes the day (App sets the pause),
        "snooze" asks again in 30 min."""
        self.overwork.answer(answer, now or dt.datetime.now())

    # --- water ---

    def water_interval(self, now):
        """Seconds until the next glass. When the goal and the workday end are known, a sensible pace: the rest of
        the time is divided by the remaining glasses (behind: more often, ahead: less often), between
        WATER_MIN_PACE_MIN and twice the interval from the settings."""
        base = self.cfg["water_interval_min"] * 60
        left = self.cfg["water_goal"] - self.drunk
        if self.workday_end is None or left <= 0 or now >= self.workday_end:
            return base
        pace = (self.workday_end - now).total_seconds() / left
        return int(min(max(pace, WATER_MIN_PACE_MIN * 60), 2 * base))

    def water_answered(self, drank, now=None):
        self.water.answer(drank, now or dt.datetime.now())

    # --- meals ---

    def meal_answered(self, answer, now=None):
        """answer: "eat" starts the meal pause, "snooze" reminds in 15 min, "skip" doesn't remind."""
        now = now or dt.datetime.now()
        meal = self.meal_open
        if not meal:
            return
        self.meals[meal].answer(answer, now)
        if answer == "eat":  # a meal matters more than a plain pause
            self.mode, self.meal = EATING, meal
            self.until = now + dt.timedelta(minutes=self.cfg["meal_pause_min"])
            self.meal_over.cancel()

    def extend_meal(self, now=None):
        """"15 more min" after the meal pause (meal_snooze_min)."""
        if self.mode == EATING:
            self.until = (now or dt.datetime.now()) + dt.timedelta(minutes=self.cfg["meal_snooze_min"])
            self.meal_over.open = False

    def finish_meal(self, now=None):
        """"Continue": the meal was already a long break, so both timers start over."""
        if self.mode != EATING:
            return
        self.mode, self.until, self.meal = WORKING, None, None
        self.meal_over.cancel()
        self.postpones = 0
        self._set_countdown(self.cfg["mini_interval_min"] * 60)
        self.water.remaining = self.water_interval(now or dt.datetime.now())

    def mark_meal(self, meal, eaten, now=None):
        """The plate on Status or "Going to eat": the meal is eaten today (or the mark was removed).
        True if a reminder about this meal was open and is no longer needed."""
        reminder, day = self.meals[meal], self.workday(now or dt.datetime.now())
        if not eaten:
            if reminder.answer_on(day) == "eat":
                reminder.answered = None
            return False
        was_open = reminder.open
        reminder.answered, reminder.open, reminder.snoozed_until = (day, "eat"), False, None
        return was_open

    def meal_state(self, meal, now):
        """Today's meal state for the schedule: (state, time). States: "eating" (until), "eat", "skip",
        "snoozed" (remind at), "open" (reminder open; the time it was snoozed to, if it was), "upcoming" (at),
        "due" (any moment), "missed"."""
        if self.eating == meal:
            return "eating", self.until
        reminder = self.meals[meal]
        result = reminder.answer_on(self.workday(now))
        if result:
            return result, None
        if reminder.snoozed_until and not stale(reminder.snoozed_until, now):
            return "snoozed", reminder.snoozed_until
        if reminder.open:
            return "open", reminder.moved_to
        at = self.moment(now, self.cfg[f"{meal}_at"])
        if now < at:
            return "upcoming", at
        return ("due" if now < at + dt.timedelta(minutes=MEAL_WINDOW_MIN) else "missed"), at

    def next_meal(self, now):
        """The next meal: (meal, when) or (meal, None) if it's time to eat now; None when done for today."""
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

    # --- settings, statistics, restart ---

    def apply_config(self, now=None):
        interval = self.cfg["mini_interval_min"] * 60
        if self.mode != BREAK and self.remaining > interval:
            self._set_countdown(interval)
        self.water.remaining = min(self.water.remaining, self.water_interval(now or dt.datetime.now()))

    def restore_day(self, day, eaten=(), finished_minute=0, day_end_asked=False, now=None):
        """What statistics already recorded about today (in case there is no state.json): eaten meals
        aren't reminded, a finished day and the day-end question aren't repeated, and a finished day
        stays finished until morning (the person goes on with "Continue" or "Still working?")."""
        for meal in eaten:
            self.meals[meal].answered = (day, "eat")
        if finished_minute and not (self.finished_at and self.workday(self.finished_at) == day):
            self.finished_at = at_workday_minute(day, finished_minute)
            if self.mode == WORKING:
                self.mode, self.until = FINISHED, self.morning(now or dt.datetime.now())
        if finished_minute or day_end_asked:
            self.day_end.shown = day

    def snapshot(self, now):
        """State for state.json (JSON types only): App saves it every minute and on quit."""
        return {
            "version": STATE_VERSION, "saved_at": now.isoformat(), "workday": self.workday(now).isoformat(),
            "mode": self.mode, "until": _iso(self.until), "meal": self.meal, "finished_at": _iso(self.finished_at),
            "remaining": self.remaining, "period": self.period, "warned": self.warned,
            "breaks_taken": self.breaks_taken, "postpones": self.postpones, "long_skipped": self.long_skipped,
            "chosen": self.chosen, "open_pause": self.open_pause, "continue_declined": self.continue_asked == "no",
            "reminders": {r.name: r.snapshot() for r in self.reminders},
        }

    def restore(self, data, now):
        """Restores snapshot() after a restart if it's from the same workday and no older than
        STATE_MAX_AGE_H. A break interrupted by quitting starts in a minute; a long time without the app
        counts as an absence (come_back). True if restored; a broken file is simply ignored."""
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
                "chosen": data.get("chosen") if data.get("chosen") in ("mini", "long") else None,
                "continue_asked": "no" if data.get("continue_declined") else None,
                "open_pause": bool(data.get("open_pause")) and mode == PAUSED,
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
