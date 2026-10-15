"""Rhythmos: break reminders with exercises, water, meals and statistics (Windows, macOS).

The entry point and the app itself: tray, the per-second loop, the action queue, updates, the smoke test.
Logic lives in core.py, drawing in graphics.py, widgets in widgets.py,
windows over the work in popups.py, the main window in main_window.py."""
import datetime as dt
import importlib
import os
import queue
import sys
import threading
import time
import tkinter as tk
import traceback
import webbrowser

import system

if sys.stderr is None:  # a build without a console: import errors would otherwise vanish without a trace
    os.makedirs(system.data_dir(), exist_ok=True)
    sys.stderr = sys.stdout = open(os.path.join(system.data_dir(), "rhythmos.log"), "a", encoding="utf-8", buffering=1)

import pystray  # noqa: E402 — after redirecting stderr, so import errors reach the log

import i18n  # noqa: E402
import updates  # noqa: E402
from core import (APP_NAME, CONFIG_PATH, DATA_DIR, LOG_PATH, MEALS, PAUSE_KINDS,  # noqa: E402
                  STATE_PATH, TYPICAL_START, WORKING, Scheduler, Stats, absence_span, apply_water_profile,
                  at_workday_minute, average_minute, day_minute, fmt_time, load_config, load_json, minute_of_day,
                  save_config, save_json, set_language_setting, work_started, workday_date, workday_span)
from graphics import ensure_icon_file, make_icon  # noqa: E402
from i18n import t  # noqa: E402
from main_window import MainWindow  # noqa: E402
from popups import Popups  # noqa: E402

__version__ = "2.16.4"

UPDATE_CHECK_DELAY_MS = 30_000
UPDATE_CHECK_INTERVAL_MS = 60 * 60 * 1000   # hourly: with a daily check a new version could wait until tomorrow
UPDATE_RECHECK_ON_OPEN_SEC = 10 * 60        # opening the main window checks too, but no more often than this
STATE_SAVE_INTERVAL_SEC = 60                # timer state (state.json): every minute and on quit


class App(Popups, MainWindow):
    def __init__(self):
        self.version = __version__
        self.cfg = load_config()
        self.stats = Stats(self.today)
        self.sched = Scheduler(self.cfg)
        self.last_state_save = time.monotonic()
        self.queue = queue.Queue()

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(APP_NAME)
        system.init_tk(self.root)
        if system.IS_WINDOWS:
            try:
                self.root.iconbitmap(default=ensure_icon_file())  # for all windows and the taskbar
            except (OSError, tk.TclError):
                pass

        self.main_win = None
        self.w = {}  # main window widgets; empty while the window isn't open
        self.break_wins = []
        self.break_state = None
        self.water_win = None
        self.water_demo = False
        self.meal_win = None
        self.meal_demo = False
        self.last_tick = time.monotonic()
        self.icon_key = None
        self.tooltip = None
        self.instance = None  # system.SingleInstance, so a second copy can ask to show the window
        self.update_info = None  # (version, release URL) if GitHub has a newer version
        self.last_update_check = None  # time.monotonic() of the last check
        self.stats_range = 7  # the statistics chart: 7 or 30 days
        self.work_pending = 0.0  # time at the computer not yet written to statistics (written once a minute)
        self.updating = False  # an update is downloading and installing
        self.busy = None  # why the break waits: "fullscreen" / "camera" / "microphone" (system.busy_reason)
        self.day_start_noted = None  # the date whose workday start is already recorded
        # Corner notifications (popups.show_toast): one at a time
        self.toast_win = self.toast_text = self.toast_kind = self.toast_after = self.toast_on_dismiss = None
        # The main window (main_window): pages, redraw caches, the "Saved" mark
        self.pages, self.page_frames, self.tab_buttons = {}, {}, {}
        self.current_page = None
        self.chart_info = None
        self._timeline_key = self._ring_key = None
        self.day_back = 0          # the day the Status day card shows: 0 today, 1 yesterday…
        self.timeline_points = []  # [(x, tooltip)] of unlabelled day timeline marks
        self.timeline_spans = []   # [(x0, x1, tooltip)] of spans on the day bar: absence, pause
        self.state_saved_at = None  # when state.json was last saved before this launch
        self.restore_state()
        self.restore_today()  # after the state above: recomputing water uses self.w
        self.adopt_open_spans()
        self.saved_check = self._saved_after = None

        self.icon = system.make_tray_icon(pystray, "Rhythmos", make_icon(0, False), APP_NAME, self.build_menu())
        system.start_tray(self.icon, self.root)
        system.on_reopen(self.root, self.open_main)

        self.root.after(1000, self.loop)
        self.root.after(100, self.process_queue)
        self.root.after(UPDATE_CHECK_DELAY_MS, self.check_updates)

    def today(self):
        """The current day is the calendar date (00:00 to 24:00). The statistics key."""
        return workday_date(dt.datetime.now())

    def restore_state(self):
        """Timer state from state.json (same workday, no older than 12 h): the countdown to the break,
        the long-break rhythm, water, a pause or a meal, answers to reminders."""
        data = load_json(STATE_PATH, None)
        try:
            self.state_saved_at = dt.datetime.fromisoformat(data["saved_at"])
        except (TypeError, KeyError, ValueError):
            self.state_saved_at = None
        if data and self.sched.restore(data, dt.datetime.now()):
            print(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} timer state restored ({self.sched.mode})",
                  file=sys.stderr)

    def save_state(self):
        self.last_state_save = time.monotonic()
        try:
            save_json(STATE_PATH, self.sched.snapshot(dt.datetime.now()))
        except OSError:
            traceback.print_exc()

    def restore_today(self):
        """What already happened today before the restart (from statistics, in case there is no state.json):
        eaten meals aren't reminded, a finished day and the day-end question aren't repeated."""
        today = self.today()
        rec = self.stats.day(today)
        self.sched.restore_day(today, eaten=[meal for meal in MEALS if rec[f"ate_{meal}"]],
                               finished_minute=rec["day_end"],
                               day_end_asked=bool(self.stats.times(today, "day_end_asked")))
        self.refresh_water_plan()

    def minute(self, moment=None):
        """The minute of today's workday (after midnight, past 24:00): the time of logged events."""
        return day_minute(self.today(), moment or dt.datetime.now())

    def adopt_open_spans(self):
        """After a restart: a pause or a held break still in progress goes on; those that ended
        while the app wasn't running are closed at the time of the last saved state."""
        self.open_spans = {}
        today = self.today()
        wanted = self.span_state()
        for date, index, event in self.stats.open_spans([today - dt.timedelta(days=1), today]):
            key = "held" if event["type"] == "held" else "pause"
            value = event.get("kind", "held")
            if event["type"] != "away" and wanted.get(key) == value and key not in self.open_spans:
                self.open_spans[key] = (date, index, value)
            else:
                end = self.state_saved_at or dt.datetime.now()
                self.stats.close(date, index, day_minute(date, end))  # close keeps it no earlier than the start

    def span_state(self):
        """Which spans are in progress: the pause kind (timed/eating/finished) and whether a break is held."""
        s = self.sched
        return {"pause": PAUSE_KINDS.get(s.mode), "held": "held" if s.held is not None else None}

    def track_spans(self):
        """Every second and after actions: log spans from the scheduler state. A pause, a meal, "until morning"
        or a held break started: an event with to = None; it ended: close it (the day is the one it started on)."""
        now = dt.datetime.now()
        for key, value in self.span_state().items():
            opened = self.open_spans.get(key)
            if opened and opened[2] == value:
                continue
            if opened:
                self.stats.close(opened[0], opened[1], day_minute(opened[0], now))
                self.open_spans.pop(key)
            if value:
                today = self.today()
                if key == "held":
                    index = self.stats.log("held", day_minute(today, now), to=None, reason=self.busy)
                else:
                    fields = {"meal": self.sched.eating} if value == "eating" else {}
                    index = self.stats.log("pause", day_minute(today, now), to=None, kind=value, **fields)
                self.open_spans[key] = (today, index, value)

    def log_away(self):
        """The person is back: log the absence (from the last input to the return)."""
        today = self.today()
        span = absence_span(today, dt.datetime.now(), self.sched.last_away, self.stats.day(today)["day_start"])
        if span:
            self.stats.log("away", span[0], to=span[1])

    def workday(self):
        """(start, end) of today's workday in minutes: the start from the settings ("Workday starts
        at"), or detected today, or the two-week average, or typical; the end is "Day end"."""
        today = self.today()
        start = (self.cfg["workday_start"] or self.stats.day(today)["day_start"]
                 or average_minute(self.stats.day(today - dt.timedelta(days=i))["day_start"] for i in range(1, 15))
                 or TYPICAL_START)
        return workday_span(start, self.cfg["day_end_at"] if self.cfg["day_end_enabled"] else None)

    def is_busy(self):
        """The person is on a call, sharing the screen or watching something fullscreen: the break waits
        (Scheduler.tick(busy=…)). The OS is asked only when it matters: a warning or a break is
        imminent, or a break is already waiting; on macOS the check queries the audio and video systems."""
        s = self.sched
        warn = self.cfg["warn_before_sec"]
        if not s.in_break and (s.held is not None or s.remaining <= max(warn, 0) + 2):
            self.busy = system.busy_reason()
        else:
            self.busy = None
        return self.busy is not None

    def sync_day(self):
        """Tells the scheduler what's known about today: glasses, the workday end, work time."""
        today = self.today()
        rec = self.stats.day(today)
        end = at_workday_minute(today, self.workday()[1])
        self.sched.update_day(rec["water"], end, rec["work_sec"] + int(self.work_pending))

    def ask_autostart(self):
        """macOS, first launch: open at login? The person decides."""
        def enable():
            try:
                system.set_autostart(True, __file__)
            except OSError:
                traceback.print_exc()

        self.show_toast(t("autostart_ask_title"), t("autostart_ask_text"),
                        [(t("no"), lambda: None, False), (t("yes"), enable, True)], timeout_ms=None)

    def refresh_water_plan(self):
        """The female/male norm: a water interval that meets the daily goal within the actual workday.
        Runtime only: the computed values aren't written to the settings file (save_config)."""
        start, end = self.workday()
        before = (self.cfg["water_goal"], self.cfg["water_interval_min"])
        apply_water_profile(self.cfg, end - start)
        if (self.cfg["water_goal"], self.cfg["water_interval_min"]) != before:
            self.sched.apply_config()
        if self.w.get("water_hint"):
            self.refresh_water_profile()

    # --- updates ---

    def check_updates(self, repeat=True):
        """Asks GitHub for the latest release every hour; the network runs in a background thread.
        repeat=False is an extra check (opening the main window), without rescheduling."""
        if self.cfg["check_updates"] and not self.updating:
            self.last_update_check = time.monotonic()
            threading.Thread(target=lambda: self.queue.put(("update", updates.fetch_latest())), daemon=True).start()
        if repeat:
            self.root.after(UPDATE_CHECK_INTERVAL_MS, self.check_updates)

    def recheck_updates_soon(self):
        """The main window opened: worth knowing about a new version without waiting for the hourly check."""
        last = self.last_update_check
        if last is not None and time.monotonic() - last >= UPDATE_RECHECK_ON_OPEN_SEC:
            self.check_updates(repeat=False)

    def on_update_result(self, result, install_now=False):
        if not result or not updates.is_newer(result[0], current_version()):
            return
        print(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} update available: {result[0]}", file=sys.stderr)
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
            save_config(self.cfg)
        self.refresh_main()

    def open_update(self):
        webbrowser.open(self.update_info[1] if self.update_info else updates.LATEST_PAGE)

    def start_update(self):
        """The Update button: download, verify and install the new version by itself.
        If that's impossible (running from source, no file for this system), open the release page."""
        if self.updating or not self.update_info:
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
            if self.toast_text:
                self.toast_text.configure(text=t("updating_progress", percent=value))
        elif kind == "update_ready":
            print(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} installing update from {value}", file=sys.stderr)
            if self.toast_text:
                self.toast_text.configure(text=t("updating_install"))
                self.root.update()
            updates.install(value, autostart=system.get_autostart(), language=i18n.get_language())
            self.handle("quit")  # the installer (Windows) or script (macOS) starts the new version
        elif kind == "update_failed":
            self.updating = False
            self.show_toast(t("update_failed_title"), t("update_failed_text"),
                            [(t("download"), self.open_update, True), (t("later"), lambda: None, False)],
                            timeout_ms=60_000)

    # --- tray ---

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
            # Quick actions, without the main window
            item(t("tray_drink"), post("drink"), visible=lambda i: self.cfg["water_enabled"]),
            item(t("day_end_finish"), post(("pause", None)),
                 visible=lambda i: not self.sched.day_finished(dt.datetime.now())),
            pystray.Menu.SEPARATOR,
            item(t("pause"), pystray.Menu(
                item(t("pause_30"), post(("pause", 30))),
                item(t("pause_60"), post(("pause", 60))),
                item(t("pause_120"), post(("pause", 120))),
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
        elif action == "drink":
            self.set_water(self.stats.day(self.today())["water"] + 1)
        elif action == "resume":
            if self.sched.eating:
                self.close_meal_window()  # "Continue?" isn't needed anymore
                self.sched.finish_meal()
            if self.sched.resume():  # "Continue" after "Finish the day": the day goes on
                self.continue_day()
            self.track_spans()
            self.icon.update_menu()
        elif isinstance(action, tuple) and action[0] == "pause":
            if self.break_state:
                self.close_break_windows()
                self.sched.finish_break()
            if action[1] is None:  # "until morning" is "Finish the day"
                self.finish_day()
            self.sched.pause(action[1])
            self.track_spans()
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
            self.save_state()
            if system.IS_MAC:
                self.icon.visible = False  # stop() would stop the NSApplication loop shared with Tk
            else:
                self.icon.stop()
            self.root.destroy()


    def finish_day(self):
        """The day is finished (with the button in the day-end window or the "until morning" pause): the time goes
        to statistics, windows waiting for an answer go away."""
        if not self.stats.day(self.today())["day_end"]:
            self.stats.set("day_end", minute_of_day(dt.datetime.now()))
            self.stats.log("day_end", self.minute(), replace=())
        if self.toast_kind == "day_end":  # both "The workday is over" and the work limit
            self.close_toast(dismissed=False)
        if not self.meal_demo:
            self.close_meal_window()

    def continue_day(self):
        """The day goes on, so it isn't finished: clear the finish time, the "Finish the day" button comes back."""
        self.stats.set("day_end", 0)
        self.stats.unlog("day_end")
        self.icon.update_menu()

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
        elif s.held is not None:  # the break is due but the person is busy: it waits
            title = t("tip_held", app=APP_NAME)
            key = ("run", 24)
        else:
            title = t(f"tip_next_{s.next_kind()}", app=APP_NAME, time=fmt_time(s.remaining))
            if self.cfg["water_enabled"] and not s.water_open and not s.water_done:
                title += "\n" + t("tip_water", time=fmt_time(s.water_remaining))
            key = ("run", int(24 * (1 - s.remaining / max(s.period, 1))))
        if title != self.tooltip:
            self.tooltip = title
            self.icon.title = title
        if key != self.icon_key:
            self.icon_key = key
            progress = 1 if key[0] == "break" else (key[1] / 24 if key[0] == "run" else 0)
            self.icon.icon = make_icon(progress, key[0] == "paused")

    # --- main loop ---

    def loop(self):
        now = time.monotonic()
        # No more than 5 s per step: the computer's sleep time doesn't count as work.
        delta = min(now - self.last_tick, 5.0)
        self.last_tick = now
        was_paused = self.sched.paused_until is not None
        idle = system.idle_seconds()
        self.sync_day()
        for event in self.sched.tick(delta, idle=idle, busy=self.is_busy()):
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
                self.stats.set_times("day_end_asked", [minute_of_day(dt.datetime.now())])  # don't ask after a restart
                self.show_day_end()
            elif event == "overwork":
                self.stats.log("overwork", self.minute())
                self.show_overwork()
            elif event == "day_continued":
                self.continue_day()
            elif event == "back":
                self.log_away()
            # "break_held" (the break waits for a call to end) and "back" (returned) have no window of their own;
            # the log sees a held break, like a pause, from the state (track_spans)
        self.track_spans()
        if was_paused and self.sched.paused_until is None:
            self.icon.update_menu()
        self.note_day_start(idle)
        if self.sched.state == WORKING:  # a break, a meal, a pause, an absence are not work
            self.work_pending += delta
            if self.work_pending >= 60:
                self.flush_work_time()
        if time.monotonic() - self.last_state_save >= STATE_SAVE_INTERVAL_SEC:
            self.save_state()
        self.update_break_warning()
        self.update_tray()
        self.refresh_main()
        self.root.after(1000, self.loop)

    def note_day_start(self, idle):
        """The first mouse or keyboard input today is the workday start (once a day)."""
        today = self.today()
        if self.day_start_noted == today:
            return
        if self.stats.day(today)["day_start"]:
            self.day_start_noted = today
            return
        minute = work_started(dt.datetime.now(), idle)
        if minute is not None:
            self.stats.set("day_start", minute)
            self.stats.log("day_start", minute, replace=())
            self.day_start_noted = today
            self.refresh_water_plan()  # a known day start gives a more accurate water interval

    def flush_work_time(self):
        seconds = int(self.work_pending)
        if seconds:
            self.stats.add("work_sec", seconds)
            self.work_pending -= seconds

    def beep(self):
        if self.cfg["sound"]:
            system.beep("info", self.sound_name())

def current_version():
    """The version to compare with releases. RHYTHMOS_VERSION_OVERRIDE is only for testing
    self-update in CI: the built app "pretends" to be an old version and updates to the latest release."""
    return os.environ.get("RHYTHMOS_VERSION_OVERRIDE") or __version__


def quartz_available():
    """For the smoke test: whether the build has Quartz (without it macOS can't see idleness)."""
    if not system.IS_MAC:
        return "n/a"
    try:
        importlib.import_module("Quartz")
        return "yes"
    except ImportError:
        return "MISSING"


def run_smoke_test(app, out_dir):
    """--smoke-test: walks through every window without a person and takes screenshots.
    Needed to check the build on the GitHub Actions macOS runner, where nobody can look."""
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
        """A line to the log and to info.txt next to the screenshots: on macOS the built app's stderr isn't kept."""
        print(f"smoke test: {text}", file=sys.stderr)
        with open(os.path.join(out_dir, "info.txt"), "a", encoding="utf-8") as f:
            f.write(text + "\n")

    steps = [
        (app.open_main, None),
        (lambda: note(f"main window {app.main_win.winfo_width()}x{app.main_win.winfo_height()}, "
                      f"screen {app.root.winfo_screenwidth()}x{app.root.winfo_screenheight()}"), None),
        # Idleness (for the workday start): on macOS through Quartz, which must be in the build
        (lambda: note(f"idle {system.idle_seconds():.1f} s, day start {app.stats.day(app.today())['day_start']}, "
                      f"quartz {quartz_available()}"), None),
        # Busyness (a call, fullscreen): on macOS real CoreAudio, CoreMediaIO and Quartz calls
        (lambda: note(f"busy {system.busy_reason()}"), None),
        (lambda: page("status"), "status"),
        (lambda: app.set_status_day(1), "status_yesterday"),
        (lambda: app.set_status_day(0), None),
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
        (lambda: app.show_overwork(demo=True), "overwork"),
        (app.close_toast, None),
        (lambda: app.show_toast(t("update_toast_title", version="9.9.9"), t("update_toast_text"),
                                [(t("download"), lambda: None, True), (t("later"), lambda: None, False)]), "toast"),
        (app.close_toast, None),
        (lambda: (setattr(app.sched, "warned", True), app.show_break_warning()), "break_warning"),
        (app.close_toast, None),
        # Network and certificates: on macOS HTTPS doesn't work in the built app without certifi
        (lambda: print(f"smoke test: update check -> {updates.fetch_latest()}", file=sys.stderr), None),
    ]

    def run(index=0):
        try:
            if index == len(steps):
                app.cfg["language"] = original_language
                save_config(app.cfg)
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
    # Installer commands: turn autostart on/off, set the language, and exit
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
        return  # the running copy shows the window itself

    smoke_dir = sys.argv[sys.argv.index("--smoke-test") + 1] if "--smoke-test" in sys.argv else None
    # macOS: there's no installer with a checkbox (the app is just dragged to Applications), so on the first
    # launch we ask about autostart and never turn it on ourselves: the person decides the settings
    ask_autostart = system.IS_MAC and getattr(sys, "frozen", False) and not smoke_dir and not os.path.exists(CONFIG_PATH)

    app = App()
    if ask_autostart:
        save_config(app.cfg)  # only so we don't ask twice; the values are the defaults
        app.root.after(3000, app.ask_autostart)
    app.instance = instance
    if smoke_dir:
        run_smoke_test(app, smoke_dir)
    if "--test-break" in sys.argv:
        app.root.after(1500, app.trigger_break)
    if "--test-water" in sys.argv:
        app.root.after(1500, lambda: (setattr(app.sched.water, "open", True), app.show_water()))
    if "--open" in sys.argv:
        app.root.after(500, app.open_main)
    if "--update-now" in sys.argv:  # self-update test: look for a release and update right away
        threading.Thread(target=lambda: app.queue.put(("update_now", updates.fetch_latest())), daemon=True).start()
    app.root.mainloop()
    if smoke_dir:
        sys.exit(app.exit_code)


def setup_logging():
    """pythonw has no console, so errors would otherwise vanish without a trace: write them to rhythmos.log."""
    if getattr(sys.stderr, "name", "") == LOG_PATH:
        log = sys.stderr  # already opened at the top of the file
    else:
        os.makedirs(DATA_DIR, exist_ok=True)
        log = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
    threading.excepthook = lambda a: traceback.print_exception(a.exc_type, a.exc_value, a.exc_traceback, file=log)
    print(f"--- {dt.datetime.now():%Y-%m-%d %H:%M:%S} start {sys.argv[1:]}", file=log)
    return log


if __name__ == "__main__":
    log = setup_logging()
    try:
        main()
    except Exception:
        # No raise: a build without a console would otherwise show an error window and wait for a click,
        # and during a silent install there's nobody to click it
        traceback.print_exc(file=log)
        sys.exit(1)
