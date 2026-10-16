"""The main window: the Status, Statistics and Settings tabs, and the layout for the screen."""

import datetime as dt
import os
import tkinter as tk
from tkinter import filedialog, messagebox

from PIL import ImageTk

import i18n
import system
from core import (APP_NAME, MAX_GLASSES, MEALS, SLIDERS, WATER_PROFILES, Stats, average_minute, completion_rate,
                  current_stretch, day_bounds, event_spans, export_csv, fmt_hm, fmt_time, main_layout, regularity,
                  restore_manual_water, save_config, setting_value, slider_position, split_orders,
                  water_interval_for, water_streak)
from graphics import (C, GLASSES_PER_ROW, MAX_GLASSES_SHOWN, PLATE_STATES, blend, check_mark, dot_image,
                      draw_progress_ring, glass_image, make_app_icon, plate_image, rgba, smooth_image)
from i18n import (SEP, fmt_after_minis, fmt_clock, fmt_days, fmt_glasses, fmt_minutes, fmt_times,
                  fmt_volume, t)
from system import HAND, font
from widgets import CARD, HEAD_GAP, ITEM, TIGHT, UNIT, ScrollArea, Slider, Toggle, card, flat_button, wrap_to_width


TIMELINE_HEIGHT = 100     # the day timeline in the Today card
STATUS_DAYS = 7           # the day switch of the day card: today and the six days before
TIMELINE_MIN_H = 4        # the day timeline is at least this many hours long (early morning, a short day)
TIMELINE_Y = 62           # where the bar is: labels above it in two tiers, hours below it (with air)
TITLE_BAR = 32            # approximate OS title bar height, so the window fits the work area
STATS_RANGES = (7, 30)    # the period switch on the statistics chart


class MainWindow:
    """Part of App: the main window and its pages."""

    # --- main window ---

    def open_main(self):
        system.activate_app()  # macOS: otherwise a menu-bar app's window opens behind the others
        self.recheck_updates_soon()
        if self.main_win:
            self.main_win.deiconify()
            self.main_win.lift()
            self.main_win.focus_force()
            return
        win = tk.Toplevel(self.root, bg=C["bg"])
        # Hidden until the pages are built and the size is known: on macOS a size set on an already
        # shown window wasn't applied, leaving just the header (2.2.0–2.5.0)
        win.withdraw()
        win.title(f"{APP_NAME} {self.version}")
        win.protocol("WM_DELETE_WINDOW", self.close_main)
        self.window_icon = ImageTk.PhotoImage(make_app_icon(64))
        win.iconphoto(False, self.window_icon)
        self.main_win = win
        self.w = {}
        # Layout for the screen: settings columns, statistics cards per row
        work = self.work_area()
        self.layout = main_layout(work[2] - work[0] - 40)
        Slider.page_scrolls = staticmethod(self.page_scrolls)

        header = tk.Frame(win, bg=C["bg"])
        header.pack(fill="x", padx=6 * UNIT, pady=(5 * UNIT, 2 * UNIT))
        self.header_icon = ImageTk.PhotoImage(make_app_icon(40))
        tk.Label(header, image=self.header_icon, bg=C["bg"]).pack(side="left", padx=(0, 3 * UNIT))
        title = tk.Frame(header, bg=C["bg"])
        title.pack(side="left")
        tk.Label(title, text=APP_NAME, bg=C["bg"], fg=C["text"],
                 font=font(18, "semibold")).pack(anchor="w")
        tk.Label(title, text=t("tagline"), bg=C["bg"], fg=C["muted"],
                 font=font(9)).pack(anchor="w")
        self.w["saved"] = tk.Label(header, text="", bg=C["bg"], fg=C["accent"], font=font(10))
        self.w["saved"].pack(side="left", padx=4 * UNIT, pady=(2 * UNIT, 0))
        self.w["update"] = tk.Label(header, text="", bg=C["bg"], fg=C["water"], font=font(10, "semibold"),
                                    cursor=HAND)
        self.w["update"].pack(side="left", pady=(2 * UNIT, 0))
        self.w["update"].bind("<Button-1>", lambda e: self.start_update())
        tabs = tk.Frame(header, bg=C["panel"])
        tabs.pack(side="right")

        body = tk.Frame(win, bg=C["bg"])
        # The scroll bar (6 + 8 px) lives in the right margin: the right edge of the content lines up
        # with the right edge of the tab buttons (24 px from the window edge)
        body.pack(fill="both", expand=True, padx=(6 * UNIT, 6 * UNIT - ScrollArea.BAR - 2 * UNIT), pady=(TIGHT, 5 * UNIT))
        self.pages, self.page_frames, self.tab_buttons = {}, {}, {}
        self.current_page = None
        for key, builder in (("status", self.build_status_page),
                             ("stats", self.build_stats_page),
                             ("settings", self.build_settings_page)):
            area = ScrollArea(body)  # on a small screen the page scrolls
            page = builder(area.inner)
            page.pack(fill="both", expand=True)
            self.pages[key], self.page_frames[key] = area, page
            btn = tk.Label(tabs, text=t(f"tab_{key}"), font=font(11), padx=16, pady=6, cursor=HAND)
            btn.pack(side="left", padx=2, pady=2)
            btn.bind("<Button-1>", lambda e, k=key: self.show_page(k))
            self.tab_buttons[key] = btn
        win.bind("<MouseWheel>", self.on_main_wheel)
        # No win.update() here: on macOS it could keep servicing redraw events and never return, leaving
        # the window with no tab chosen and no content (every reopen nested another such update)
        self.fit_main_window(header, work)
        self.show_page("status")
        win.deiconify()
        win.update_idletasks()
        win.after(50, lambda: self.main_shown(win))

    def main_shown(self, win):
        """Once the window is on screen: the dark title bar and the page laid out for the real size."""
        if win is not self.main_win:  # closed meanwhile
            return
        system.style_window(win)
        self.show_page(self.current_page or "status")

    def work_area(self):
        return system.work_area(self.root)

    def fit_main_window(self, header, work):
        """The window fits the largest page, but no larger than the screen's work area; then pages
        scroll. The size depends on the language, fonts and display scaling, so it isn't set in numbers."""
        win = self.main_win
        win.update_idletasks()  # the sizes pages ask for are computed for a hidden window too
        frames = self.page_frames.values()
        left, top, right, bottom = work
        # Body margins together with the scroll bar, 24 + 24; header (20 + 8) and body (4 + 20)
        width = max(self.layout["width"], *(page.winfo_reqwidth() + 48 for page in frames))
        height = header.winfo_reqheight() + 28 + 24 + max(page.winfo_reqheight() for page in frames)
        width = min(width, right - left - 40)
        height = min(height, bottom - top - TITLE_BAR - 20)
        x = left + max(0, (right - left - width) // 2)
        y = top + max(0, (bottom - top - height - TITLE_BAR) // 2)
        win.geometry(f"{width}x{height}+{x}+{y}")
        # Only after the size: on macOS resizable(False, False) fixes the current size as both minimum
        # and maximum; set earlier, it kept the window as first shown (just the header)
        win.resizable(False, False)

    def close_main(self):
        self.main_win.destroy()
        self.main_win = None
        self.w = {}

    def page_scrolls(self):
        area = self.pages.get(self.current_page) if self.main_win else None
        return bool(area and area.scrollable())

    def on_main_wheel(self, event):
        """The mouse wheel over any part of the main window scrolls the current page (if it can)."""
        area = self.pages.get(self.current_page)
        if not area or not event.delta:
            return
        units = -int(event.delta / 120) if system.IS_WINDOWS else -event.delta  # macOS gives small steps
        area.scroll(units or (-1 if event.delta > 0 else 1))

    def show_page(self, key):
        for page in self.pages.values():
            page.pack_forget()
        self.current_page = key
        area = self.pages[key]
        area.pack(fill="both", expand=True)
        # Lay out the content for the real canvas size right away: on macOS the first page otherwise
        # stayed empty until the per-second refresh
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
        if not self.saved_check:
            self.saved_check = check_mark(14, C["accent"])
        label.configure(text=t("saved"), image=self.saved_check, compound="right")
        if self._saved_after:
            self.root.after_cancel(self._saved_after)
        self._saved_after = self.root.after(
            1500, lambda: self.w.get("saved") and self.w["saved"].configure(text="", image=""))

    # status

    def build_status_page(self, parent):
        page = tk.Frame(parent, bg=C["bg"])
        left = card(page)
        left.pack(side="left", fill="y", padx=(0, CARD))
        self.w["ring"] = tk.Canvas(left, width=270, height=270, bg=C["card"], highlightthickness=0)
        self.w["ring"].pack(pady=(TIGHT, 4 * UNIT))
        flat_button(left, t("break_now"), self.trigger_break, bg=C["accent"], fg=C["on_accent"],
                    size=11).pack(fill="x", pady=UNIT)
        self.w["pause_btn"] = flat_button(left, t("pause_btn", time=fmt_minutes(self.cfg["pause_min"])), self.toggle_pause, size=11)
        self.w["pause_btn"].pack(fill="x", pady=UNIT)
        self.w["reset_btn"] = flat_button(left, t("reset"), self.sched.reset, size=11)
        self.w["reset_btn"].pack(fill="x", pady=UNIT)
        # "Finish the day": only once the day end from the settings has come and the day isn't finished
        self.w["finish_btn"] = flat_button(left, t("day_end_finish"), lambda: self.handle(("pause", None)),
                                           bg=C["accent"], fg=C["on_accent"], size=11)
        # Schedule: long break and day end, a "name … state" row refreshed every second
        tk.Label(left, text=t("card_schedule").upper(), bg=C["card"], fg=C["accent"],
                 font=font(9, "semibold")).pack(anchor="w", pady=(6 * UNIT, 2 * UNIT))
        self.w["schedule"] = tk.Frame(left, bg=C["card"])
        self.w["schedule"].pack(fill="x")
        self.w["schedule_rows"] = {}

        right = tk.Frame(page, bg=C["bg"])
        right.pack(side="left", fill="both", expand=True)

        # Water and meals side by side, built the same way: countdown, status line, glasses or plates
        top = tk.Frame(right, bg=C["bg"])
        top.pack(fill="x")
        water = card(top, t("card_water"))
        water.grid(row=0, column=0, sticky="nsew", padx=(0, CARD // 2))
        meals = card(top, t("card_meals"))
        meals.grid(row=0, column=1, sticky="nsew", padx=(CARD // 2, 0))
        for column in (0, 1):
            top.columnconfigure(column, weight=1, uniform="top")
        self.build_meal_card(meals)
        self.w["water"] = tk.Label(water, bg=C["card"], fg=C["water"], font=font(28, "light"))
        self.w["water"].pack(anchor="w")
        self.w["water_sub"] = wrap_to_width(tk.Label(water, bg=C["card"], fg=C["muted"], font=font(10), height=2,
                                                     justify="left", anchor="nw", wraplength=260))
        self.w["water_sub"].pack(fill="x")
        # Today's glasses: clicking a glass sets the count (like the plates in the Meals card)
        self.w["glasses"] = tk.Frame(water, bg=C["card"])
        self.w["glasses"].pack(anchor="w", pady=(TIGHT, 0))
        self.w["glasses_key"] = None

        # The day card: a day switch instead of a heading (today and the days before it, to compare how days
        # went); the metrics and the timeline show the chosen day
        today = card(right)
        today.pack(fill="both", expand=True, pady=(CARD, 0))
        self.day_back, self.w["day_chips_date"] = 0, self.today()
        days = tk.Frame(today, bg=C["panel"])
        days.pack(fill="x", pady=(0, HEAD_GAP))
        self.w["day_chips"] = []
        for back in range(STATUS_DAYS - 1, -1, -1):
            chip = tk.Label(days, font=font(9), padx=4, pady=2, cursor=HAND)
            chip.pack(side="left", fill="x", expand=True, padx=2, pady=2)
            chip.bind("<Button-1>", lambda e, b=back: self.set_status_day(b))
            self.w["day_chips"].append((back, chip))
        # The day timeline at the bottom of the card: from morning to the workday end, meals, day end and "now"
        self.w["timeline"] = tk.Canvas(today, height=TIMELINE_HEIGHT, bg=C["card"], highlightthickness=0)
        self.w["timeline"].pack(side="bottom", fill="x", pady=(3 * UNIT, 0))
        self.w["timeline"].bind("<Configure>", lambda e: self.draw_timeline(force=True))
        self.w["timeline"].bind("<Motion>", self.timeline_hover)
        self.w["timeline"].bind("<Leave>", lambda e: self.timeline_leave())
        grid = tk.Frame(today, bg=C["card"])
        grid.pack(fill="x")
        # Breaks and rest on top; work, continuous work and absence below
        metrics = (("breaks", t("m_breaks"), C["accent"]), ("skipped", t("m_skipped"), C["muted"]),
                   ("active", t("m_active"), C["accent"]), ("work", t("m_work"), C["text"]),
                   ("stretch", t("m_stretch"), C["text"]), ("away", t("m_away"), C["muted"]))
        for i, (key, caption, color) in enumerate(metrics):
            cell = tk.Frame(grid, bg=C["card"])
            cell.grid(row=i // 3, column=i % 3, sticky="nw", pady=(0 if i < 3 else ITEM, 0))
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
        self.w["plates"].pack(anchor="w", pady=(TIGHT, 0))
        self.w["plates_key"] = None

    def set_headline(self, key, text, countdown=False):
        """The big caption of the Water or Meals card: a countdown in a large font, a text message
        ("Time to drink!", "No more reminders") smaller, so it fits a narrow card too."""
        self.w[key].configure(text=text, font=font(28 if countdown else 20, "light"))

    def refresh_meal_card(self, now):
        """The Meals card: countdown to the next meal, "today 1 of 3" and plates of the enabled meals."""
        s, today = self.sched, self.stats.day(self.today())
        enabled = [m for m in MEALS if self.cfg[f"{m}_enabled"]]
        eaten = sum(today[f"ate_{m}"] for m in enabled)
        progress = t("meals_today", n=eaten, total=len(enabled))
        hover = self.w.get("plate_hover")
        if hover is not None:  # the cursor is on a plate: what a click will do
            progress += f"  →  {hover}"
        upcoming = s.next_meal(now)
        if not enabled:
            value, sub = "—", t("water_off")
        elif not s.reminders_today(now) and not s.eating:
            value, sub = "—", t("weekend_off") + "\n" + progress
        elif s.eating:
            value, sub = t("meal_enjoy"), t("sch_eating", time=f"{s.eating_until:%H:%M}") + "\n" + progress
        elif upcoming and upcoming[1] is None:
            value, sub = t("meal_now"), progress
        elif upcoming:
            value = fmt_time((upcoming[1] - now).total_seconds())
            sub = t(f"meal_next_{upcoming[0]}") + "\n" + progress  # two lines: what's next and the day's total
        else:
            # No more reminders today: "all" only if everything was really eaten
            value, sub = t("meals_done" if eaten >= len(enabled) else "meals_no_more"), progress
        self.set_headline("meal", value, countdown=bool(upcoming and upcoming[1]) and not s.eating)
        self.w["meal_sub"].configure(text=sub)
        self.render_plates(enabled, now)

    def render_plates(self, enabled, now):
        """Plates of the enabled meals: a click marks one eaten, hover shows a preview."""
        today = self.stats.day(self.today())
        states = []
        for meal in enabled:
            state = PLATE_STATES.get(self.sched.meal_state(meal, now)[0], "later")
            states.append("done" if today[f"ate_{meal}"] else ("later" if state == "done" else state))
        key = (tuple(enabled), tuple(states), tuple(self.meal_time(m, self.today()) for m in enabled))
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
            """Hover over a meal not yet eaten: a click marks it eaten; None is the normal look."""
            self.w["plate_hover"] = None if index is None else eaten_count + 1
            for i, plate in enumerate(plates):
                plate.configure(image=plate_image(30, "add" if i == index else states[i], C["card"]))
            self.refresh_main()

        # Eaten can't be undone: only plates not yet eaten are clickable
        for i, (meal, state) in enumerate(zip(enabled, states)):
            done = state == "done"
            cursor = "arrow" if done else HAND
            cell = tk.Frame(frame, bg=C["card"], cursor=cursor)
            cell.grid(row=0, column=i, padx=(0, 4 * UNIT))
            plate = tk.Label(cell, image=plate_image(30, state, C["card"]), bg=C["card"], cursor=cursor)
            plate.pack()
            name = tk.Label(cell, text=t(f"meal_{meal}"), bg=C["card"], fg=C["muted"], font=font(9), cursor=cursor)
            name.pack()
            at = tk.Label(cell, text=fmt_clock(self.meal_time(meal, self.today())), bg=C["card"], fg=C["dim"],
                          font=font(8), cursor=cursor)
            at.pack()
            if not done:
                for widget in (cell, plate, name, at):
                    widget.bind("<Button-1>", lambda e, m=meal: self.set_meal_eaten(m, True))
                    widget.bind("<Enter>", lambda e, i=i: preview(i))
                    widget.bind("<Leave>", lambda e: preview(None))
            plates.append(plate)

    def meal_time(self, meal, date):
        """The minute of the day for a meal: when it was actually eaten (the log, or ate_<meal>_at in old days),
        today when it was snoozed ("In 15 min") the time it will be reminded at, otherwise the planned time."""
        if self.stats.day(date)[f"ate_{meal}"]:
            logged = [e["at"] for e in self.stats.events(date) if e["type"] == "meal" and e.get("meal") == meal]
            eaten_at = logged or self.stats.times(date, f"ate_{meal}_at")
            if eaten_at:
                return eaten_at[0]
        if date == self.today():
            state, when = self.sched.meal_state(meal, dt.datetime.now())
            if state in ("snoozed", "open") and when:
                return self.minute(when)
        return self.cfg[f"{meal}_at"]

    def timeline_marks(self, now, events, date):
        """Day timeline marks: (minute, name, colour, state, kind). Meals ("done"/"now"/"later"/"skip") stand
        at the moment they were eaten, so the regularity shows; kind "day" is the day start and end (labelled).
        Start and end come from the event log (where times after midnight go past 24:00), in old days from counters.
        A past date shows only what happened: no planned meals or day end."""
        rec = self.stats.day(date)
        # on days off and past days, only what really happened
        planned = date == self.today() and self.sched.reminders_today(now)
        logged = {e["type"]: e["at"] for e in events if e["type"] in ("day_start", "day_end")}
        marks = []
        for meal in MEALS:
            if rec[f"ate_{meal}"]:
                marks.append((self.meal_time(meal, date), t(f"meal_{meal}"), C["meal"], "done", "meal"))
            elif self.cfg[f"{meal}_enabled"] and planned:
                state = PLATE_STATES.get(self.sched.meal_state(meal, now)[0], "later")
                marks.append((self.meal_time(meal, date), t(f"meal_{meal}"), C["meal"],
                              "later" if state == "done" else state, "meal"))
        start = logged.get("day_start") or rec["day_start"]
        if start:
            marks.append((start, t("sch_day_start"), C["accent"], "done", "day"))
        # The planned day end (from the settings) stays in place: before it, a hollow dot;
        # after it, if the day goes on, dimmed as "skipped". The actual finish is a separate filled mark
        if self.cfg["day_end_enabled"] and planned:
            passed = self.minute(now) >= self.cfg["day_end_at"]
            marks.append((self.cfg["day_end_at"], t("sch_day_end"), C["accent"], "skip" if passed else "later", "day"))
        end = logged.get("day_end") or rec["day_end"]
        if end:
            marks.append((end, t("tl_day_finished"), C["accent"], "done", "day"))
        return sorted(marks, key=lambda mark: mark[0])

    def set_status_day(self, back):
        """A day switch chip: the day card (metrics and timeline) shows today or a day before it."""
        self.day_back = back
        self.timeline_leave()
        self.refresh_status()
        self.draw_timeline(force=True)

    def refresh_day_chips(self):
        """Chip captions follow the date ("Mo 13", the last one "Today"); days without a record are dimmed.
        A new day brings the card back to today."""
        today = self.today()
        if self.w.get("day_chips_date") != today:
            self.w["day_chips_date"], self.day_back = today, 0
        weekdays = t("weekdays").split()
        for back, chip in self.w.get("day_chips", ()):
            date = today - dt.timedelta(days=back)
            active = back == self.day_back
            known = not back or date.isoformat() in self.stats.data
            chip.configure(text=f"{weekdays[date.weekday()]} {date.day}" if back else t("today"),
                           bg=C["accent"] if active else C["panel"],
                           fg=C["on_accent"] if active else C["muted"] if known else C["dim"])

    def draw_timeline(self, force=False):
        """The day bar: filled up to "now"; on it, spans from the log (absence, pause, meal pause,
        held break), small green dots for breaks (hollow when skipped), blue ones for glasses, circles
        for meals and day end, a blue circle for the next water reminder; labels only for the day start
        and end, hours under the bar. Drawn anti-aliased with Pillow, and only when something changed.
        A past day from the day switch is filled from its start to its end, without "now" or plans."""
        c = self.w.get("timeline")
        if not c:
            return
        now = dt.datetime.now()
        width = c.winfo_width()
        if width < 100:
            return
        today = self.today() - dt.timedelta(days=self.day_back)
        live = not self.day_back
        events = self.stats.events(today)
        minute = self.minute(now) if live else None
        marks = self.timeline_marks(now, events, today)
        drinks = [e["at"] for e in events if e["type"] == "water"] or self.stats.times(today, "water_at")
        missed = [e["at"] for e in events if e["type"] == "water_missed"]  # reminders without a glass
        breaks = [e for e in events if e["type"] == "break" and e.get("result") in ("done", "skipped")]
        spans = event_spans(events, minute)
        s = self.sched
        next_water = None
        if (live and self.cfg["water_enabled"] and not s.water_open and not s.water_done
                and not (s.paused and s.pause_water)):
            next_water = minute + round(s.water_remaining / 60)
        idle = live and (s.paused or bool(s.eating))
        # The filled (worked) part: from the day start to "now"; a past day from its start to its end
        rec = self.stats.day(today)
        if live:
            fill_from, fill_to = rec["day_start"], minute
        else:
            # the same start and end as the labelled marks; without a finish, up to the day's last event
            logged = {e["type"]: e["at"] for e in events if e["type"] in ("day_start", "day_end")}
            fill_from = logged.get("day_start") or rec["day_start"]
            fill_to = logged.get("day_end") or rec["day_end"] or (day_bounds(events) or (None, None))[1]
        key = (width, today, minute, tuple(marks), tuple(drinks), tuple(missed), next_water, idle,
               tuple(tuple(sorted(e.items())) for e in events))
        if not force and key == self._timeline_key:
            return
        self._timeline_key = key
        # Timeline bounds: only the hours that have something on them (marks, spans, "now", the next glass),
        # in whole hours with half an hour of margin and at least TIMELINE_MIN_H long (stretched forward);
        # a day with nothing on it shows 8:00-18:00. The "until morning" pause after the day end is left out:
        # it looks like the empty bar, and it stretched a finished day to the evening
        times = ([m[0] for m in marks] + drinks + missed + [e["at"] for e in breaks]
                 + ([minute] if live else []) + ([next_water] if next_water is not None else [])
                 + [m for kind, a, b, e in spans if e.get("kind") != "finished" for m in (a, b)]
                 + [m for m in (fill_from, fill_to) if m])
        start = (min(times or [8 * 60]) - 30) // 60 * 60
        end = -(-(max(times or [18 * 60]) + 30) // 60) * 60
        end = max(end, start + TIMELINE_MIN_H * 60)
        pad, y = 16, TIMELINE_Y

        def x_of(m):
            return pad + (width - 2 * pad) * (min(max(m, start), end) - start) / (end - start)

        xn = x_of(fill_to) if fill_to else None
        # Absence is faint, a pause muted, a meal amber, "until morning" like the not yet lived bar,
        # a held break lighter than the green, so it shows on the filled bar
        span_colors = {"away": C["dim"], "timed": C["muted"], "eating": C["meal"], "finished": C["track"],
                       "held": blend(C["accent"], C["text"], 0.5)}

        def paint(d, sc):
            r = 3 * sc
            d.rounded_rectangle((pad * sc - r, y * sc - r, (width - pad) * sc + r, y * sc + r), radius=r,
                                fill=rgba(C["track"]))
            # Green is the working time: from the day start (once known) to "now" or to a past day's end
            x0 = x_of(fill_from) if fill_from else pad
            if xn is not None and (live or fill_from) and fill_to > start and xn > x0:
                d.rounded_rectangle((x0 * sc - r, y * sc - r, xn * sc + r, y * sc + r), radius=r,
                                    fill=rgba(C["dim"] if idle else C["accent_dark"]))
            # Spans are thin strips on the bar itself (at least 3 px, so short ones show too)
            for kind, a, b, event in spans:
                color = span_colors.get(event.get("kind") if kind == "pause" else kind, C["muted"])
                x0, x1 = x_of(a), max(x_of(b), x_of(a) + 3)
                h = 2.2 * sc
                d.rounded_rectangle((x0 * sc, y * sc - h, x1 * sc, y * sc + h), radius=h, fill=rgba(color))
            # All marks in one style: a dot with a card-coloured halo (sets it off from the bar and neighbours);
            # ring is the outline width for a hollow dot ("still to come", skipped), None means filled
            halo = 1.5 * sc

            def dot(x, radius, color, ring=None):
                cx, cy, rr = x * sc, y * sc, radius * sc
                d.ellipse((cx - rr - halo, cy - rr - halo, cx + rr + halo, cy + rr + halo), fill=rgba(C["card"]))
                d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=rgba(color))
                if ring:
                    inner = rr - ring * sc
                    d.ellipse((cx - inner, cy - inner, cx + inner, cy + inner), fill=rgba(C["card"]))

            for e in breaks:  # breaks are the smallest, below glasses and meals
                if e["result"] == "done":
                    dot(x_of(e["at"]), 3.5, C["accent"])
                else:
                    dot(x_of(e["at"]), 3.5, C["dim"], ring=1.4)
            for m in missed:  # missed glasses: hollow and dimmed, like skipped breaks
                dot(x_of(m), 5, C["dim"], ring=1.8)
            for m in drinks:  # drunk glasses, at the moment they were marked
                dot(x_of(m), 5, C["water"])
            # The next water reminder, only if it isn't hidden behind a meal or day-end mark
            if (next_water is not None and next_water <= end
                    and all(abs(x_of(next_water) - x_of(m[0])) >= 14 for m in marks)):
                dot(x_of(next_water), 5, C["water"], ring=1.8)
            for m, _name, color, state, _kind in marks:  # meals, day start and end
                if state == "done":
                    dot(x_of(m), 7, color)
                else:
                    dot(x_of(m), 7, C["dim"] if state == "skip" else color, ring=2)
            if live:
                dot(xn, 5, C["text"])  # "now"

        self.timeline_photo = ImageTk.PhotoImage(smooth_image(width, TIMELINE_HEIGHT, paint, C["card"]))
        c.delete("all")
        c.create_image(0, 0, anchor="nw", image=self.timeline_photo)

        def place(item, x):
            """Keeps a label within the canvas edges."""
            x0, _y0, x1, _y1 = c.bbox(item)
            shift = max(0, 2 - x0) - max(0, x1 - (width - 2))
            if shift:
                c.move(item, shift, 0)
            return c.bbox(item)

        # Hours under the bar: a step that keeps labels apart; after midnight again from 0:00
        span = width - 2 * pad
        step = next((h for h in (1, 2, 3, 4, 6) if span * h * 60 / (end - start) >= 46), 6)
        for hour in range(-(-start // (60 * step)) * step, end // 60 + 1, step):
            place(c.create_text(x_of(hour * 60), y + 28, text=f"{hour % 24}:00", fill=C["dim"], font=font(8)),
                  x_of(hour * 60))
        # Labels only for the day start and end (in two tiers if tight, otherwise shifted past the neighbour);
        # other marks get a hover tooltip (timeline_hover)
        placed = {0: [], 1: []}

        def clash(box, tier):
            return [b for b in placed[tier] if not (box[0] > b[2] + 8 or box[2] < b[0] - 8)]

        self.timeline_points = self.timeline_tips(marks, drinks, breaks, next_water, now if live else None, x_of,
                                                  end, missed)
        self.timeline_spans = self.timeline_span_tips(spans, x_of)
        for m, name, color, state, kind in marks:
            if kind != "day":
                continue
            x = x_of(m)
            fill = color if state in ("now", "done") else C["muted"]
            item, tier = None, 0
            for tier in (0, 1):
                item = c.create_text(x, y - 24 - tier * 18, text=f"{name} {fmt_clock(m)}", font=font(9), fill=fill,
                                     tags="label")
                box = place(item, x)
                if not clash(box, tier):
                    break
                if tier == 0:
                    c.delete(item)
            others = clash(box, tier)
            if others:
                c.move(item, max(b[2] for b in others) + 8 - box[0], 0)
                box = place(item, x)
            placed[tier].append(box)

    @staticmethod
    def grouped(items, x_of, gap=10):
        """Marks close on the timeline (no more than gap px apart) go together: one tooltip per group.
        items are tuples whose first element is a minute of the day."""
        groups = []
        for item in sorted(items, key=lambda i: i[0]):
            if groups and x_of(item[0]) - x_of(groups[-1][-1][0]) <= gap:
                groups[-1].append(item)
            else:
                groups.append([item])
        return groups

    def timeline_tips(self, marks, drinks, breaks, next_water, now, x_of, end, missed=()):
        """[(x, tooltip text)] for unlabelled marks, simply "Name: time": "Dinner: 18:37",
        "Water: 17:19", "Long break: 10:30". The state (eaten, skipped) shows on the mark itself;
        close glasses and breaks share one tooltip with several times."""
        points = [(x_of(m), f"{name}: {fmt_clock(m)}") for m, name, _color, _state, kind in marks if kind == "meal"]
        for times, name in ((drinks, t("tl_water")), (missed, t("tl_water_missed"))):
            for group in self.grouped([(m,) for m in times], x_of):
                points.append((x_of(group[0][0]), f"{name}: {', '.join(fmt_clock(g[0]) for g in group)}"))
        for group in self.grouped([(e["at"], e) for e in breaks], x_of):
            x = sum(x_of(m) for m, _e in group) / len(group)
            if len(group) == 1:
                e = group[0][1]
                if e["result"] != "done":
                    name = t("tl_break_skipped")
                else:
                    name = t("tl_break_long" if e.get("kind") == "long" else "tl_break")
                    if e.get("swapped"):
                        name += t("tl_swapped")
                points.append((x, f"{name}: {fmt_clock(e['at'])}"))
            else:
                points.append((x, f"{t('tl_breaks')}: {', '.join(fmt_clock(m) for m, _e in group)}"))
        if next_water is not None and next_water <= end:
            points.append((x_of(next_water), f"{t('tl_next_water')}: {fmt_clock(next_water)}"))
        if now is not None:  # None for a past day
            points.append((x_of(self.minute(now)), f"{t('tl_now')}: {now:%H:%M}"))
        return points

    def timeline_span_tips(self, spans, x_of):
        """[(x0, x1, text)] for spans, "Name: from–to": "You were away: 12:05–12:40", "Lunch: 13:05–13:50"."""
        names = {"timed": t("tl_pause"), "eating": t("tl_eating"), "finished": t("tl_finished")}
        tips = []
        for kind, a, b, event in spans:
            if kind == "away":
                name = t("tl_away")
            elif kind == "held":
                name = t("tl_held")
            elif event.get("kind") == "eating" and event.get("meal") in MEALS:
                name = t(f"meal_{event['meal']}")
            else:
                name = names.get(event.get("kind"), t("tl_pause"))
            tips.append((x_of(a), max(x_of(b), x_of(a) + 3), f"{name}: {fmt_clock(a)}–{fmt_clock(b)}"))
        return tips

    def timeline_hover(self, event):
        """A tooltip above the timeline mark nearest to the cursor (within 9 px), or, if the cursor is on a span
        and no mark is right there (further than 4 px), above the span (the shortest, if several).
        Day start and end labels the tooltip would cover are hidden meanwhile."""
        c = self.w.get("timeline")
        if not c:
            return
        self.timeline_leave()
        if abs(event.y - TIMELINE_Y) > 18:
            return
        near = [p for p in self.timeline_points if abs(p[0] - event.x) <= 9]
        point = min(near, key=lambda p: abs(p[0] - event.x)) if near else None
        under = [s for s in self.timeline_spans if s[0] - 2 <= event.x <= s[1] + 2]
        if under and (point is None or abs(point[0] - event.x) > 4):
            x0, x1, text = min(under, key=lambda s: s[1] - s[0])
            x = min(max(event.x, x0), x1)
        elif point:
            x, text = point
        else:
            return
        item = c.create_text(x, TIMELINE_Y - 42, text=text, font=font(9), fill=C["text"], tags="tip")
        x0, y0, x1, y1 = c.bbox(item)
        shift = max(0, 8 - x0) - max(0, x1 - (c.winfo_width() - 8))
        c.move(item, shift, 0)
        x0, y0, x1, y1 = c.bbox(item)
        box = c.create_rectangle(x0 - 8, y0 - 4, x1 + 8, y1 + 4, fill=C["panel"], outline=C["accent"], tags="tip")
        c.tag_raise(item, box)
        for label in c.find_withtag("label"):
            lx0, ly0, lx1, ly1 = c.bbox(label)
            if lx0 < x1 + 8 and lx1 > x0 - 8 and ly0 < y1 + 4:
                c.itemconfigure(label, state="hidden")

    def timeline_leave(self):
        """The cursor left the timeline (or the tooltip changes): remove the tooltip and bring the labels back."""
        c = self.w.get("timeline")
        if c:
            c.delete("tip")
            c.itemconfigure("label", state="normal")

    def schedule_rows(self, now):
        """Today's schedule rows: (key, name, state, highlight?). Meals have their own card next to water."""
        s, cfg = self.sched, self.cfg
        timed = []  # (minute of the day, row): events with a time are sorted by it
        left = s.breaks_until_long()
        long_row = ("long", t("sch_long"), t("long_next") if left == 1 else fmt_after_minis(left - 1), left == 1)
        started = self.stats.day(self.today())["day_start"]
        if started:
            timed.append((started, ("day_start", t("sch_day_start"), fmt_clock(started), False)))
        if cfg["day_end_enabled"] and (s.reminders_today(now) or self.stats.day(self.today())["day_end"]):
            finished = self.stats.day(self.today())["day_end"]
            at = s.moment(now, cfg["day_end_at"])
            if finished:
                text, hot = t("sch_finished", time=fmt_clock(finished)), False
            elif s.day_end_snoozed:
                text, hot = t("sch_snoozed", time=f"{s.day_end_snoozed:%H:%M}"), True
            elif now < at:
                left_min = max(1, round((at - now).total_seconds() / 60))
                text, hot = t("sch_in", time=fmt_clock(cfg["day_end_at"]), left=fmt_minutes(left_min)), False
            else:
                text, hot = t("sch_rest", time=fmt_clock(cfg["day_end_at"])), True
            timed.append((finished or cfg["day_end_at"], ("day_end", t("sch_day_end"), text, hot)))
        return [long_row] + [row for _minute, row in sorted(timed, key=lambda item: item[0])]

    def refresh_schedule(self):
        """Rebuilds the rows only when their set changed; texts are refreshed every second."""
        frame, widgets = self.w["schedule"], self.w["schedule_rows"]
        rows = self.schedule_rows(dt.datetime.now())
        if [r[0] for r in rows] != list(widgets):
            for child in frame.winfo_children():
                child.destroy()
            widgets.clear()
            for i, (key, name, _text, _hot) in enumerate(rows):
                tk.Label(frame, text=name, bg=C["card"], fg=C["muted"], font=font(10)).grid(
                    row=i, column=0, sticky="w", pady=UNIT)
                widgets[key] = tk.Label(frame, bg=C["card"], font=font(10))
                widgets[key].grid(row=i, column=1, sticky="e", pady=UNIT)
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
        key = (round(fraction * 500), idle)  # steps of 0.2% (under 2 px of the arc): no redraws nobody sees
        if key != self._ring_key:
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
        elif s.held is not None:
            subtitle = t("ring_held")  # the break is due but waits while the person is busy
        else:
            subtitle = t(f"ring_{s.next_kind()}")
        c.create_text(size / 2, size / 2 - 10, text=fmt_time(s.remaining), fill=C["text"],
                      font=font(40, "light"))
        c.create_text(size / 2, size / 2 + 38, text=subtitle, fill=C["muted"], font=font(11))

    # statistics

    def build_stats_page(self, parent):
        """Cards on top show one day (today, or the one hovered on the chart);
        below them, a 7- or 30-day chart and the totals for that period."""
        page = tk.Frame(parent, bg=C["bg"])
        self.w["stats_day"] = tk.Label(page, bg=C["bg"], fg=C["text"], font=font(12, "semibold"))
        self.w["stats_day"].pack(anchor="w", pady=(0, 2 * UNIT))
        summary = tk.Frame(page, bg=C["bg"])
        summary.pack(fill="x")
        # The order, as everywhere: breaks → movement → water → meals → work
        cards = (("day_breaks", t("m_breaks"), C["accent"]), ("day_skipped", t("m_skipped"), C["muted"]),
                 ("day_active", t("m_active"), C["accent"]), ("day_water", t("m_water"), C["water"]),
                 ("day_meals", t("m_meals"), C["meal"]), ("day_work", t("m_work"), C["text"]))
        per_row = self.layout["stat_cards"]  # a narrow screen: two rows of three
        for i, (key, caption, color) in enumerate(cards):
            box = card(summary)
            column = i % per_row
            box.grid(row=i // per_row, column=column, sticky="nsew", pady=(0 if i < per_row else CARD, 0),
                     padx=(0 if column == 0 else CARD // 2, 0 if column == per_row - 1 else CARD // 2))
            summary.columnconfigure(column, weight=1, uniform="sum")
            self.w[key] = tk.Label(box, bg=C["card"], fg=color, font=font(26, "light"))
            self.w[key].pack(anchor="w")
            tk.Label(box, text=caption, bg=C["card"], fg=C["muted"], font=font(10)).pack(anchor="w")
            # An extra line: % done, postponed, water volume, day end
            self.w[f"{key}_sub"] = tk.Label(box, bg=C["card"], fg=color if key == "day_water" else C["dim"],
                                            font=font(9))
            self.w[f"{key}_sub"].pack(anchor="w")

        chart = card(page)
        chart.pack(fill="both", expand=True, pady=(CARD, 0))
        head = tk.Frame(chart, bg=C["card"])
        head.pack(fill="x", pady=(0, TIGHT))
        self.w["chart_title"] = tk.Label(head, bg=C["card"], fg=C["accent"], font=font(9, "semibold"))
        self.w["chart_title"].pack(side="left")
        segments = tk.Frame(head, bg=C["panel"])
        segments.pack(side="right")
        # Export all statistics to CSV: a link next to the period switch
        export = tk.Label(head, text=t("export_link"), bg=C["card"], fg=C["accent"], font=font(9), cursor=HAND)
        export.pack(side="right", padx=(0, 4 * UNIT))
        export.bind("<Button-1>", lambda e: self.export_stats())
        self.w["range_buttons"] = {}
        for days in STATS_RANGES:
            btn = tk.Label(segments, text=t("range_days", n=days), font=font(9), padx=10, pady=2, cursor=HAND)
            btn.pack(side="left", padx=2, pady=2)
            btn.bind("<Button-1>", lambda e, d=days: self.set_stats_range(d))
            self.w["range_buttons"][days] = btn
        self.w["chart"] = tk.Canvas(chart, bg=C["card"], highlightthickness=0, height=262, cursor=HAND)
        self.w["chart"].pack(fill="both", expand=True)
        self.w["chart"].bind("<Motion>", self.on_chart_motion)
        self.w["chart"].bind("<Leave>", lambda e: self.highlight_day(None))
        bottom_row = tk.Frame(chart, bg=C["card"])
        bottom_row.pack(fill="x", pady=(2 * UNIT, 0))
        for text, color in ((t("lg_mini"), C["accent"]), (t("lg_long"), C["accent_dark"]),
                            (t("lg_skipped"), C["dim"]), (t("lg_water"), C["water"]), (t("lg_meals"), C["meal"])):
            tk.Label(bottom_row, text="●", bg=C["card"], fg=color, font=font(12)).pack(side="left")
            tk.Label(bottom_row, text=text, bg=C["card"], fg=C["muted"],
                     font=font(10)).pack(side="left", padx=(0, 4 * UNIT))
        for key in ("range_breaks", "range_water", "range_day"):
            # Wrap to the card width: on a narrow screen the totals line is longer than the card
            self.w[key] = wrap_to_width(tk.Label(chart, bg=C["card"], fg=C["muted"], font=font(10), justify="left",
                                                 anchor="w", wraplength=400))
            self.w[key].pack(fill="x", pady=(TIGHT, 0))
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
        today = self.today()
        days = [today - dt.timedelta(days=i) for i in range(n - 1, -1, -1)]
        records = [self.stats.day(d) for d in days]
        now = self.minute()
        regular = [regularity(self.stats.events(d), now if d == today else None) for d in days]
        self.w["chart_title"].configure(text=t("card_last_n", n=n).upper())
        for d, btn in self.w["range_buttons"].items():
            active = d == n
            btn.configure(bg=C["accent"] if active else C["panel"], fg=C["on_accent"] if active else C["muted"])
        self.draw_range_totals(n, days, records)

        c.delete("all")
        width, height = max(c.winfo_width(), 600), max(c.winfo_height(), 210)
        top, bottom = 24, height - 66
        slot = width / n
        self.chart_info = {"days": days, "records": records, "regular": regular, "slot": slot, "top": top, "bottom": bottom,
                           "width": width, "bar": min(44, slot * 0.6), "hover": None}
        peak = max([r["mini_done"] + r["long_done"] + r["skipped"] for r in records] + [4])
        for i in range(5):
            y = bottom - (bottom - top) * i / 4
            c.create_line(0, y, width, y, fill=C["track"] if i == 0 else C["grid"])
        bar = self.chart_info["bar"]
        week = n <= 7  # a week: weekdays and glass counts; a month: the date of every fifth day
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
            # Water and meals: a filled dot when the goal / all meals were met, hollow when not;
            # for a week, the count too
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
        """Period totals in three lines: breaks and movement; water; meals and work."""
        total = {k: sum(r[k] for r in records) for k in Stats.KEYS if k not in Stats.MOMENTS}
        rate = completion_rate(total)
        best = max(range(n), key=lambda i: records[i]["mini_done"] + records[i]["long_done"])
        best_breaks = records[best]["mini_done"] + records[best]["long_done"]
        best_text = t("best_day", day=f"{days[best]:%d.%m}", n=best_breaks) if best_breaks else ""
        self.w["range_breaks"].configure(text=t(
            "range_breaks", n=n, breaks=total["mini_done"] + total["long_done"], skipped=total["skipped"],
            rate=f"{rate}%" if rate is not None else "—") + best_text
            + t("range_active", active=fmt_minutes(total["active_sec"] // 60)))
        avg_liters = round(total["water"] * i18n.GLASS_LITERS / n, 1)
        self.w["range_water"].configure(text=t(
            "range_water", glasses=fmt_glasses(total["water"]), avg=fmt_volume(avg_liters / i18n.GLASS_LITERS),
            streak=fmt_days(water_streak(self.stats, self.cfg["water_goal"], self.today()))))
        start = average_minute(r["day_start"] for r in records)
        self.w["range_day"].configure(text=t(
            "range_day", meals=total["meals"], work=fmt_minutes(total["work_sec"] // 60))
            + (t("range_start", time=fmt_clock(start)) if start is not None else ""))

    def show_stats_day(self, index):
        """Cards on top: one chart day's data (the last one is today)."""
        info = self.chart_info
        day, rec = info["days"][index], info["records"][index]
        date = f"{day:%d.%m}"
        if day == self.today():
            title = t("stats_today", date=date)
        else:
            title = t("stats_day", weekday=t("weekdays").split()[day.weekday()], date=date)
        self.w["stats_day"].configure(text=title)
        rate = completion_rate(rec)
        values = {
            "day_breaks": (rec["mini_done"] + rec["long_done"], t("done_rate", pct=rate) if rate is not None else ""),
            "day_skipped": (rec["skipped"], t("postponed_n", n=rec["postponed"]) if rec["postponed"] else ""),
            "day_water": (rec["water"], fmt_volume(rec["water"])),
            "day_work": (fmt_hm(rec["work_sec"]), self.work_span(rec)),
            "day_active": (rec["active_sec"] // 60, ""),
            "day_meals": (rec["meals"], ""),
        }
        for key, (value, sub) in values.items():
            self.w[key].configure(text=value)
            self.w[f"{key}_sub"].configure(text=sub)

    @staticmethod
    def regularity_lines(reg):
        """The day's regularity from the log for the chart tooltip (old days have no log: nothing)."""
        if not reg:
            return []
        lines = []
        if reg["on_time"] or reg["late"]:
            line = f"{t('tip_on_time')}: {reg['on_time']}"
            if reg["late"]:
                line += f"{SEP}{t('tip_late')}: {reg['late']}"
            lines.append(line)
        if reg["away"]:
            lines.append(f"{t('tip_away')}: {fmt_times(reg['away'])}{SEP}{t('tip_away_total')}: "
                         f"{fmt_minutes(reg['away_min'])}")
        if reg["longest_min"]:
            lines.append(f"{t('tip_longest')}: {fmt_minutes(reg['longest_min'])}")
        if reg["held"]:
            lines.append(f"{t('tip_held_n')}: {fmt_times(reg['held'])}")
        return lines

    def export_stats(self):
        """"Export CSV": all statistics, a row per day, and a file with every logged event next to it."""
        path = filedialog.asksaveasfilename(
            parent=self.main_win, title=t("export_dialog"), defaultextension=".csv",
            initialfile=f"rhythmos-{self.today():%Y-%m-%d}.csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            days, events = export_csv(self.stats, path, now=self.minute(), today=self.today())
        except OSError as e:
            messagebox.showerror(APP_NAME, t("export_failed", e=e), parent=self.main_win)
            return
        self.show_toast(t("export_done"), t("export_done_text", days=os.path.basename(days),
                                                               events=os.path.basename(events)))

    def work_span(self, rec):
        """"08:42 – 18:05" (day start and end), "from 08:42" if the day goes on, or "" without data."""
        start, end = rec["day_start"], rec["day_end"]
        if start and end:
            return t("work_span", start=fmt_clock(start), end=fmt_clock(end))
        if start:
            return t("work_from", start=fmt_clock(start))
        return t("day_end_at_tip", time=fmt_clock(end)) if end else ""

    def on_chart_motion(self, event):
        info = self.chart_info
        if not info:
            return
        inside = info["top"] - 20 <= event.y <= info["bottom"] + 62
        self.highlight_day(min(len(info["days"]) - 1, max(0, int(event.x // info["slot"]))) if inside else None)

    def highlight_day(self, index):
        """Highlights the bar, shows a tooltip with the day's details and that day in the cards on top."""
        info = self.chart_info
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
        if rec["day_start"] and rec["day_end"]:
            lines.append(f"{t('tip_workday')}: {self.work_span(rec)}")
        elif rec["day_start"]:
            lines.append(f"{t('tip_day_start')}: {fmt_clock(rec['day_start'])}")
        elif rec["day_end"]:
            lines.append(f"{t('tip_day_end')}: {fmt_clock(rec['day_end'])}")
        lines += self.regularity_lines(info["regular"][index])
        text = c.create_text(0, 0, text="\n".join(lines), anchor="nw", fill=C["text"], font=font(10), tags="hover")
        x0, y0, x1, y1 = c.bbox(text)
        box_w, box_h = x1 - x0 + 24, y1 - y0 + 18
        cx, bar = slot * index + slot / 2, info["bar"]
        x = cx + bar / 2 + 10
        if x + box_w > info["width"] - 4:  # near the right edge, the tooltip goes left of the bar
            x = cx - bar / 2 - 10 - box_w
        y = max(4, min(info["bar_tops"][index] - box_h / 2, bottom - box_h))
        box = c.create_rectangle(x, y, x + box_w, y + box_h, fill=C["panel"], outline=C["accent"], tags="hover")
        c.coords(text, x + 12, y + 9)
        c.tag_raise(text, box)
        self.show_stats_day(index)

    # settings

    def build_settings_page(self, parent):
        """Cards grouped by theme: breaks first (mini → long → postpone & pause), then the day
        (workday → meals → water); Sound either closes the breaks (it plays at their start and end) or
        sits next to Other, whichever gives evener columns. As many columns as the screen fits; cards fill
        them top to bottom, split so the columns are as even as possible, and a shorter column shares the
        remaining height among its cards, so all columns end on one line. In four columns the rows read
        logically too: the main card of each theme on top (breaks, postpone, workday, water), its
        companions below. "Try it" sits in the card heading, next to what the preview shows."""
        page = tk.Frame(parent, bg=C["bg"])
        count = self.layout["columns"]
        # Columns are created before the cards: cards are packed into them with pack(in_=…), and only
        # widgets above their column in the stacking order are visible
        columns = [tk.Frame(page, bg=C["bg"]) for _ in range(count)]
        for i, column in enumerate(columns):
            column.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else CARD // 2, 0 if i == count - 1 else CARD // 2))
            page.columnconfigure(i, weight=1, uniform="settings")

        def settings_card(title, demo=None):
            return card(page, title, (t("preview_try"), demo) if demo else None)

        def sliders(title, keys, demo=None):
            box = settings_card(title, demo)
            for key in keys:
                self.add_slider(box, key)
            return box

        def toggle(box, text, key, **pack):
            Toggle(box, text, self.cfg[key], lambda v: self.set_setting(key, v)).pack(fill="x", **pack)

        breaks = sliders(t("card_breaks"), ("mini_interval_min", "mini_duration_sec", "intensity"),
                         lambda: self.show_demo_break("mini"))
        toggle(breaks, t("group_buttons_toggle"), "group_buttons", pady=(0, ITEM))
        long_box = sliders(t("card_long"), ("long_every", "long_duration_min"), lambda: self.show_demo_break("long"))
        toggle(long_box, t("workout_toggle"), "workout_enabled", pady=(0, ITEM))
        toggle(long_box, t("kind_choice_toggle"), "kind_choice", pady=(0, ITEM))
        postpone = sliders(t("card_postpone"), ("postpone_min", "postpone_limit", "warn_before_sec", "pause_min"))

        sound = settings_card(t("card_sound"))
        toggle(sound, t("sound_toggle"), "sound", pady=(0, ITEM))
        self.add_sound_slider(sound)

        # Workday: days, start, end and the work limit
        day_end = settings_card(t("card_day_end"), lambda: self.show_day_end(demo=True))
        self.build_workdays(day_end)
        self.add_slider(day_end, "workday_start")
        lo, hi, step, fmt = SLIDERS["day_end_at"]
        day_end_slider = Slider(day_end, t("s_day_end_at"), lo, hi, step, self.cfg["day_end_at"], fmt,
                                lambda v: self.set_setting("day_end_at", v))

        def toggle_day_end(value):
            self.set_setting("day_end_enabled", value)
            day_end_slider.set_enabled(value)

        # As in Meals: the reminder toggle sits in the slider row; when off, the slider is dimmed
        day_end_slider.label.configure(fg=C["text"], font=font(11))
        Toggle(day_end_slider.head, None, self.cfg["day_end_enabled"], toggle_day_end).pack(
            side="right", padx=(12, 0), before=day_end_slider.value_label)
        day_end_slider.pack(fill="x", pady=(0, ITEM))
        day_end_slider.set_enabled(self.cfg["day_end_enabled"])
        self.add_slider(day_end, "max_work_hours")

        meals = self.build_meals_card(page)

        water = settings_card(t("card_water"), lambda: self.show_water(demo=True))
        toggle(water, t("water_toggle"), "water_enabled", pady=(0, ITEM))
        self.build_water_profile(water)

        other = settings_card(t("card_other"))
        self.build_language_switch(other).pack(fill="x", pady=(0, ITEM))
        Toggle(other, t("autostart_toggle_mac" if system.IS_MAC else "autostart_toggle"), system.get_autostart(),
               self.set_autostart_setting).pack(fill="x", pady=(0, ITEM))
        toggle(other, t("updates_toggle"), "check_updates", pady=(0, ITEM))

        cards = [breaks, long_box, postpone, sound, day_end, meals, water, other]
        for box in cards:
            # The card padding already closes the card: drop the gap after its last setting
            last = box.pack_slaves()[-1]
            top = last.pack_info()["pady"]
            last.pack_configure(pady=(top[0] if isinstance(top, tuple) else 0, 0))
        orders = [range(8), (0, 1, 2, 4, 5, 6, 3, 7)]  # Sound: after breaks or before Other
        page.update_idletasks()
        for column, group in zip(columns, split_orders([c.winfo_reqheight() for c in cards], orders, count)):
            for j, index in enumerate(group):
                # expand: a shorter column stretches its cards to the height of the tallest
                cards[index].pack(in_=column, fill="both", expand=True, pady=(0 if j == 0 else CARD, 0))
        return page

    def build_meals_card(self, parent):
        """Breakfast, lunch, dinner: each is a time slider with the meal name and its toggle in the top row
        (compact, like a schedule line); the slider is inactive while the meal is off."""
        box = card(parent, t("card_meals"), (t("preview_try"), lambda: self.show_meal("lunch", demo=True)))
        for meal in MEALS:
            lo, hi, step, fmt = SLIDERS[f"{meal}_at"]
            slider = Slider(box, t(f"meal_{meal}"), lo, hi, step, self.cfg[f"{meal}_at"], fmt,
                            lambda v, k=f"{meal}_at": self.set_setting(k, v))
            slider.label.configure(fg=C["text"], font=font(11))

            def toggle(value, meal=meal, slider=slider):
                self.set_setting(f"{meal}_enabled", value)
                slider.set_enabled(value)

            Toggle(slider.head, None, self.cfg[f"{meal}_enabled"], toggle).pack(
                side="right", padx=(12, 0), before=slider.value_label)
            slider.pack(fill="x", pady=(0, ITEM))
            slider.set_enabled(self.cfg[f"{meal}_enabled"])
        self.add_slider(box, "meal_pause_min")
        return box

    def build_workdays(self, parent):
        """Workdays as weekday segments (like the language switch): meals and day end are reminded on these days."""
        bg = parent["bg"]
        tk.Label(parent, text=t("workdays_label"), bg=bg, fg=C["muted"], font=font(10)).pack(anchor="w")
        segments = tk.Frame(parent, bg=C["panel"])
        segments.pack(fill="x", pady=(TIGHT, ITEM))
        chips = {}

        def paint():
            for day, chip in chips.items():
                active = day in self.cfg["workdays"]
                chip.configure(bg=C["accent"] if active else C["panel"], fg=C["on_accent"] if active else C["muted"])

        def flip(day):
            self.set_setting("workdays", sorted(set(self.cfg["workdays"]) ^ {day}))  # a new list, not the same one
            paint()

        for day, name in enumerate(t("weekdays").split()):
            chip = tk.Label(segments, text=name, font=font(10), padx=4, pady=3, cursor=HAND)
            chip.pack(side="left", fill="x", expand=True, padx=2, pady=2)
            chip.bind("<Button-1>", lambda e, d=day: flip(d))
            chips[day] = chip
        paint()

    def build_language_switch(self, parent):
        """The Language row with a segmented switch between languages."""
        row = tk.Frame(parent, bg=parent["bg"])
        tk.Label(row, text=t("language"), bg=parent["bg"], fg=C["text"], font=font(11)).pack(side="left")
        segments = tk.Frame(row, bg=C["panel"])
        segments.pack(side="right")
        for code, name in i18n.LANGUAGES.items():
            active = code == i18n.get_language()
            btn = tk.Label(segments, text=name, font=font(10), padx=12, pady=3, cursor=HAND,
                           bg=C["accent"] if active else C["panel"], fg=C["on_accent"] if active else C["muted"])
            btn.pack(side="left", padx=2, pady=2)
            btn.bind("<Button-1>", lambda e, c=code: self.change_language(c))
        return row

    def build_water_profile(self, parent):
        """Intake switch (female / male / custom), the recommendation hint and the water sliders."""
        # Label above the segments, like every slider: the row never forces the column wider
        tk.Label(parent, text=t("water_profile"), bg=parent["bg"], fg=C["muted"], font=font(10)).pack(anchor="w")
        segments = tk.Frame(parent, bg=C["panel"])
        segments.pack(fill="x", pady=(TIGHT, 2 * UNIT))
        self.w["water_profile"] = {}
        for code in (*WATER_PROFILES, "custom"):
            btn = tk.Label(segments, text=t(f"water_profile_{code}"), font=font(10), padx=4, pady=3, cursor=HAND)
            btn.pack(side="left", fill="x", expand=True, padx=2, pady=2)
            btn.bind("<Button-1>", lambda e, c=code: self.set_water_profile(c))
            self.w["water_profile"][code] = btn
        # Initial wrap is narrower than the column so a long line doesn't widen the window; then it follows the width
        hint = tk.Label(parent, bg=parent["bg"], fg=C["muted"], font=font(9), justify="left", anchor="w",
                        wraplength=240)
        hint.pack(fill="x", pady=(0, ITEM))
        hint.bind("<Configure>", lambda e: hint.configure(wraplength=e.width))
        self.w["water_hint"] = hint
        self.w["water_sliders"] = {}
        for key in ("water_interval_min", "water_goal"):
            lo, hi, step, fmt = SLIDERS[key]

            def change(v, k=key):
                self.set_setting(k, v)
                self.refresh_water_profile()  # the custom-mode hint depends on the goal

            slider = Slider(parent, t(f"s_{key}"), lo, hi, step, self.cfg[key], fmt, change)
            slider.pack(fill="x", pady=(0, ITEM))
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
        start, end = self.workday()
        span = f"{fmt_clock(start)}–{fmt_clock(end)}"
        if profile == "custom":
            text = t("water_hint_custom", female=fmt_volume(WATER_PROFILES["female"]),
                     male=fmt_volume(WATER_PROFILES["male"]), goal=fmt_glasses(goal), span=span,
                     interval=fmt_minutes(water_interval_for(goal, end - start)))
        else:
            text = t("water_hint_auto", volume=fmt_volume(goal), span=span,
                     interval=fmt_minutes(self.cfg["water_interval_min"]))
        self.w["water_hint"].configure(text=text)

    def set_water_profile(self, profile):
        if profile == self.cfg["water_profile"]:
            return
        self.cfg["water_profile"] = profile
        if profile == "custom":
            restore_manual_water(self.cfg)  # the person's own values, not the ones computed by the norm
            self.sched.apply_config()
        save_config(self.cfg)
        self.refresh_water_plan()  # a norm: goal and interval from it and the actual workday
        self.flash_saved()
        self.refresh_water_profile()

    def change_language(self, code):
        if code == i18n.get_language():
            return
        self.cfg["language"] = code
        save_config(self.cfg)
        i18n.set_language(code)
        self.icon.menu = self.build_menu()
        self.icon.update_menu()
        self.tooltip = None
        # Rebuild the window outside the click handler, because the button that called it disappears too
        self.root.after(10, self.reopen_main_on_settings)

    def reopen_main_on_settings(self):
        if self.main_win:
            self.close_main()
        self.open_main()
        self.show_page("settings")
        self.flash_saved()

    def sound_name(self):
        """The chosen notification sound, or the first one available on this computer."""
        names = [name for name, _path in system.available_sounds()]
        return self.cfg["sound_name"] if self.cfg["sound_name"] in names else (names[0] if names else "")

    def add_sound_slider(self, parent):
        """The slider steps through system sounds and plays the chosen one right away, to listen to it."""
        sounds = system.available_sounds()
        if len(sounds) < 2:
            return
        names = [name for name, _path in sounds]

        def choose(index):
            self.set_setting("sound_name", names[index])
            system.play_sound(sounds[index][1])

        def label(index):  # Windows: translated event names; macOS: the sounds' own names (Glass, Ping…)
            key = f"snd_{names[index]}"
            return t(key) if key in i18n.STRINGS[i18n.get_language()] else names[index]

        Slider(parent, t("sound_name_label"), 0, len(names) - 1, 1, names.index(self.sound_name()),
               label, choose).pack(fill="x", pady=(0, ITEM))

    def add_slider(self, parent, key):
        """A settings slider; the leftmost position of some means "auto"/"off" (0 in the settings)."""
        lo, hi, step, fmt = SLIDERS[key]
        Slider(parent, t(f"s_{key}"), lo, hi, step, slider_position(key, self.cfg[key]), fmt,
               lambda v, k=key: self.set_setting(k, setting_value(k, v))).pack(fill="x", pady=(0, ITEM))

    def set_setting(self, key, value):
        if self.cfg.get(key) == value:
            return
        self.cfg[key] = value
        save_config(self.cfg)
        self.sched.apply_config()
        if key in ("day_end_at", "day_end_enabled", "workday_start"):
            self.refresh_water_plan()
        self.flash_saved()

    def set_autostart_setting(self, enabled):
        try:
            system.set_autostart(enabled, __file__)
            self.flash_saved()
        except OSError as e:
            messagebox.showerror(APP_NAME, t("autostart_error", e=e), parent=self.main_win)

    def refresh_main(self):
        """Every second: the header and the current page. Status is the most expensive (ring, day timeline), so
        it is redrawn only while visible: not on other tabs or in a minimized window."""
        if not self.main_win or "ring" not in self.w:
            return
        self.w["update"].configure(text=t("update_banner", version=self.update_info[0]) if self.update_info else "")
        if self.pages.get(self.current_page):
            self.pages[self.current_page].relayout()
        if self.current_page == "status" and self.main_win.state() == "normal":
            self.refresh_status()

    def refresh_status(self):
        s = self.sched
        self.draw_ring()
        self.w["pause_btn"].configure(text=t("resume") if s.paused or s.eating else t("pause_btn", time=fmt_minutes(self.cfg["pause_min"])))
        today = self.stats.day(self.today())
        progress = t("water_today", n=today["water"], goal=self.cfg["water_goal"], volume=fmt_volume(today["water"]))
        hover = self.w.get("glass_hover")
        if hover is not None:  # the cursor is on a glass: what a click will do
            progress += f"  →  {hover}{SEP}{fmt_volume(hover)}"
        if not self.cfg["water_enabled"]:
            self.set_headline("water", "—")
            self.w["water_sub"].configure(text=t("water_off"))
        elif s.water_done:  # goal reached: no reminders until tomorrow
            self.set_headline("water", t("water_goal_reached"))
            self.w["water_sub"].configure(text=progress)
        elif s.water_open:
            self.set_headline("water", t("water_now"))
            self.w["water_sub"].configure(text=progress)
        else:
            self.set_headline("water", fmt_time(s.water_remaining), countdown=True)
            self.w["water_sub"].configure(text=t("water_next", progress=progress))
        self.refresh_day_chips()
        now = dt.datetime.now()
        # The day card: today live, or a past day from the day switch (its longest stretch instead of the
        # current one; days from before the event log have no stretch or absence)
        date = self.today() - dt.timedelta(days=self.day_back)
        rec = self.stats.day(date)
        events = self.stats.events(date)
        if self.day_back:
            work = rec["work_sec"]
            reg = regularity(events)
            stretch = (reg["longest_min"], t("longest_day")) if reg else ("—", "")
            away = (reg["away_min"], t("times_n", n=reg["away"]) if reg["away"] else "") if reg else ("—", "")
        else:
            work = rec["work_sec"] + int(self.work_pending)  # not yet recorded time is shown too, live
            reg = regularity(events, self.minute(now)) or {}
            current = 0 if (s.in_break or s.away or s.paused or s.eating) else current_stretch(events, self.minute(now))
            stretch = (current, t("longest_n", time=fmt_minutes(reg["longest_min"])) if reg.get("longest_min") else "")
            away = (reg.get("away_min", 0), t("times_n", n=reg["away"]) if reg.get("away") else "")
        values = {
            "breaks": (rec["mini_done"] + rec["long_done"],
                       t("breaks_split", mini=rec["mini_done"], long=rec["long_done"])),
            "skipped": (rec["skipped"], t("postponed_n", n=rec["postponed"]) if rec["postponed"] else ""),
            "active": (rec["active_sec"] // 60, ""),
            "work": (fmt_hm(work), self.work_span(rec)),
            "stretch": stretch,
            "away": away,
        }
        for key, (value, sub) in values.items():
            self.w[f"today_{key}"].configure(text=value)
            self.w[f"today_{key}_sub"].configure(text=sub)
        # "Finish the day" under the ring buttons: once the day end from the settings has come and the day goes on
        due = (self.cfg["day_end_enabled"] and s.reminders_today(now) and not s.day_finished(now)
               and now >= s.moment(now, self.cfg["day_end_at"]))
        if due != bool(self.w["finish_btn"].winfo_manager()):
            if due:
                self.w["finish_btn"].pack(fill="x", pady=3, after=self.w["reset_btn"])
            else:
                self.w["finish_btn"].pack_forget()
        self.refresh_schedule()
        self.refresh_meal_card(now)
        self.draw_timeline()
        self.render_glasses(today["water"])

    def render_glasses(self, drunk):
        """The row of glasses in the Water card, redrawn only when something changed."""
        goal = self.cfg["water_goal"]
        if self.w.get("glasses_key") == (drunk, goal):
            return
        self.w["glasses_key"] = (drunk, goal)
        self.w["glass_hover"] = None
        frame = self.w["glasses"]
        for child in frame.winfo_children():
            child.destroy()
        glasses = []

        def preview(count):
            """Hover over a glass not yet drunk: which glasses a click adds; None is the normal look."""
            self.w["glass_hover"] = count
            for i, glass in enumerate(glasses):
                state = "add" if count is not None and drunk <= i < count else i < drunk
                glass.configure(image=glass_image(22, 30, state, C["card"]))
            self.refresh_main()

        # Drunk glasses can't be undone: only the ones not yet drunk are clickable.
        # A narrow window fits fewer per row; rows are then split evenly (8 → 4 + 4), never clipped
        shown = min(max(goal, drunk), MAX_GLASSES_SHOWN)
        fit = GLASSES_PER_ROW if self.layout["columns"] > 2 else 6
        per_row = -(-shown // -(-shown // fit)) if shown else fit
        for i in range(shown):
            done = i < drunk
            glass = tk.Label(frame, image=glass_image(22, 30, done, C["card"]), bg=C["card"],
                             cursor="arrow" if done else HAND)
            glass.grid(row=i // per_row, column=i % per_row, padx=3, pady=2)
            if not done:
                glass.bind("<Button-1>", lambda e, n=i + 1: self.set_water(n))
                glass.bind("<Enter>", lambda e, n=i + 1: preview(n))
                glass.bind("<Leave>", lambda e: preview(None))
            glasses.append(glass)

    def set_water(self, count):
        """Glasses drunk today, only more than before: drunk glasses can't be undone."""
        before = self.stats.day(self.today())["water"]
        count = min(count, MAX_GLASSES)
        if count <= before:
            return
        self.stats.set("water", count)
        self.log_water_times(count - before)
        # Just drank: the next reminder counts down anew; an open reminder is no longer needed
        if self.water_win and not self.water_demo:
            self.water_win.destroy()
            self.water_win = None
        self.sync_day()  # the next glass's pace, counting the ones just drunk
        self.sched.water_answered(True)
        self.refresh_main()
        if self.w.get("chart") and self.w["chart"].winfo_ismapped():
            self.draw_stats()
