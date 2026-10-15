"""Windows over the work: the break warning and screen, water, meals, day end, corner notifications."""

import datetime as dt
import random
import tkinter as tk

import exercises
import system
from core import (DAY_END_SNOOZE_MIN, DEFAULTS, minute_of_day, MEALS, MEAL_SNOOZE_MIN, build_break, fmt_time, regroup_workout,
                  single_break_step)
from graphics import C, GLASSES_PER_ROW, MAX_GLASSES_SHOWN, PLATE_STATES, check_mark, glass_image, plate_image
from i18n import content, fmt_clock, fmt_minutes, fmt_volume, t
from system import font
from widgets import EDGE, TIGHT, UNIT, demo_badge, flat_button


class Popups:
    """Part of App: everything that appears over other windows."""

    # --- warning before a break ---

    def show_break_warning(self):
        """The "Break soon" window with a live countdown. It stays until the break starts;
        "Postpone" moves the break (with the same limit as on the break screen), "OK" only hides the window."""
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
        """Every second: updates the countdown or removes the window if the break started or the app is paused."""
        if self.toast_kind != "warning":
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
        self.stats.log("break", self.minute(), kind=self.sched.next_kind(), result="postponed", sec=0)
        self.sched.postpone()

    # --- break ---

    def trigger_break(self):
        if self.break_state:
            return
        self.sched.start_break()
        self.show_break(self.sched.next_kind())

    def show_demo_break(self, kind):
        """A preview of the break window with the current settings, without touching the timer or statistics."""
        if self.break_state and not self.break_state["demo"]:
            return
        self.show_break(kind, demo=True)

    def show_break(self, kind, demo=False):
        if self.toast_kind == "warning" and not demo:
            self.close_toast()  # the break started: the warning isn't needed anymore
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
            widgets["title"].pack(pady=(2 * UNIT, 6 * UNIT))
            widgets["text"].pack()
            widgets["timer"].pack(pady=(8 * UNIT, UNIT))
            widgets["info"].pack(pady=(0, 5 * UNIT))
            # Choosing a muscle group replaces the current (and following) exercises
            chips = tk.Frame(frame, bg=C["bg"])
            chips.pack(pady=(0, 6 * UNIT if self.cfg["group_buttons"] else 2 * UNIT))
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
                         bg=C["bg"], fg=C["dim"], font=font(11)).pack(pady=(7 * UNIT, 0))
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
        """A muscle group button on the break screen. Pressing it again gives another exercise of the same group."""
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
                state["left"] = new["secs"]  # a new mini exercise gets the full time
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
        # The break ran to the end, but the person was away the whole time: not a "done" break but an absence
        away = result == "done" and system.idle_seconds() >= self.sched.away_after()
        if elapsed and not away:
            self.stats.add("active_sec", elapsed)
        if not away:  # the log records the absence itself when the person comes back ("back")
            results = {"done": "done", "skip": "skipped", "postpone": "postponed"}
            started = dt.datetime.now() - dt.timedelta(seconds=elapsed)
            self.stats.log("break", self.minute(started), kind=kind, result=results[result], sec=elapsed)
        if away:
            self.sched.finish_break()
        elif result == "done":
            self.stats.add(f"{kind}_done")
            self.sched.finish_break()
            self.beep()
        elif result == "skip":
            self.stats.add("skipped")
            self.sched.finish_break(skipped=True)  # a skipped long break comes back as the next break
        elif result == "postpone":
            self.stats.add("postponed")
            self.sched.postpone()

    # --- water ---

    def show_water(self, demo=False):
        """"Time for some water". It waits for an answer and never closes by itself: the person may have gone
        to get water, and a window that vanished would count the glass as missed."""
        if self.water_win:
            if not self.water_demo or demo:
                return
            self.water_win.destroy()  # a real reminder matters more than a demo
            self.water_win = None
        self.water_demo = demo
        keep = self.kept_toast()
        right, bottom = self.corner(self.meal_win, keep)
        width = 420
        win = self.water_win = self.corner_window(C["water"])
        drunk = self.stats.day(self.today())["water"]
        goal = self.cfg["water_goal"]
        done = drunk >= goal
        self.popup_head(win, t("water_title"), C["water"], t("x_of_y", a=drunk if done else drunk + 1, b=goal),
                        demo, lambda: self.end_water(False))
        glasses = tk.Frame(win, bg=C["panel"])
        glasses.pack(anchor="w", padx=EDGE - 2, pady=(2 * UNIT, 3 * UNIT))
        for i in range(min(max(goal, drunk), MAX_GLASSES_SHOWN)):
            tk.Label(glasses, image=glass_image(18, 24, i < drunk, C["panel"]), bg=C["panel"]).grid(
                row=i // GLASSES_PER_ROW, column=i % GLASSES_PER_ROW, padx=2, pady=2)
        if done:
            tip = t("water_goal_done")
        else:
            tip = random.choice(content("water_tips"))
        tk.Label(win, text=tip, bg=C["panel"], fg=C["text"], font=font(11),
                 wraplength=width - 2 * EDGE - 4, justify="left").pack(anchor="w", padx=EDGE)
        drank = t(f"drank_{self.cfg['water_profile']}")  # feminine / masculine / neutral "Done"
        self.popup_buttons(win, ((t("later"), lambda: self.end_water(False), False),
                                 (drank, lambda: self.end_water(True), True)), C["water"], C["on_water"])
        self.place_in_corner(win, width, right, bottom)
        if demo:
            win.after(60_000, lambda: self.end_water(False) if self.water_win is win else None)
            win.focus_force()
        self.beep()

    # --- meals ---

    def show_meal(self, meal, demo=False):
        """"Lunch time": "Going to eat" pauses breaks and water, "In 15 min" reminds again."""
        self.show_meal_window(meal, "remind", demo)

    def show_meal_over(self):
        """The meal pause is over: ask whether to continue. Without an answer breaks stay stopped."""
        self.show_meal_window(self.sched.eating, "over")

    def show_meal_window(self, meal, mode, demo=False):
        """The meal window, modelled on water: the day's plates, text, a tip and buttons.
        mode: "remind" means time to eat, "over" means "Continue?". It doesn't close by itself: the person may be away."""
        if self.meal_win:
            if demo and not self.meal_demo:
                return  # a real reminder matters more than a demo
            self.meal_win.destroy()
            self.meal_win = None
        self.meal_demo = demo
        keep = self.kept_toast()
        right, bottom = self.corner(self.water_win, keep)
        width = 440
        win = self.meal_win = self.corner_window(C["meal"])
        now = dt.datetime.now()
        meals = [m for m in MEALS if self.cfg[f"{m}_enabled"] or m == meal]
        title = t(f"meal_title_{meal}") if mode == "remind" else t("meal_over_title")
        self.popup_head(win, title, C["meal"], t("x_of_y", a=meals.index(meal) + 1, b=len(meals)),
                        demo, self.close_meal_window)
        # The day's plates: eaten / now / still to come / skipped, like glasses for water
        plates = tk.Frame(win, bg=C["panel"])
        plates.pack(anchor="w", padx=EDGE - 2, pady=(2 * UNIT, 3 * UNIT))
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
            tk.Label(cell, text=fmt_clock(self.meal_time(m, self.today())), bg=C["panel"], fg=C["dim"],
                     font=font(8)).pack()
        if mode == "remind":
            text = t("meal_text", time=fmt_minutes(self.cfg["meal_pause_min"]))
        else:
            text = t("meal_over_text")
        tk.Label(win, text=text, bg=C["panel"], fg=C["text"], font=font(11),
                 wraplength=width - 2 * EDGE - 4, justify="left").pack(anchor="w", padx=EDGE)
        if mode == "remind":
            tk.Label(win, text=random.choice(content("meal_tips")), bg=C["panel"], fg=C["muted"], font=font(10),
                     wraplength=width - 2 * EDGE - 4, justify="left").pack(anchor="w", padx=EDGE, pady=(2 * UNIT, 0))
        if mode == "remind":
            answers = ((t("skip"), "skip", False), (t("meal_snooze", min=MEAL_SNOOZE_MIN), "snooze", False),
                       (t("meal_go"), "eat", True))
        else:
            answers = ((t("meal_more", min=MEAL_SNOOZE_MIN), "more", False), (t("resume"), "continue", True))
        self.popup_buttons(win, [(label, lambda a=answer: self.answer_meal(a), primary)
                                 for label, answer, primary in answers], C["meal"], C["on_meal"])
        self.place_in_corner(win, width, right, bottom)
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
        if self.break_state and not self.break_state["demo"]:  # a break started while the reminder was open
            self.close_break_windows()
            self.sched.finish_break()
        meal = self.sched.meal_open
        self.sched.meal_answered("eat")
        if meal:
            self.set_meal_eaten(meal, True)
        self.icon.update_menu()

    def set_meal_eaten(self, meal, eaten):
        """Marks today's meal eaten: from the reminder ("Going to eat") or with the plate on Status."""
        today = self.today()
        now = dt.datetime.now()
        self.stats.set(f"ate_{meal}", int(eaten))
        self.stats.set("meals", sum(self.stats.day(today)[f"ate_{m}"] for m in MEALS))
        # When the meal was actually eaten: the plate on the timeline stands at this moment, not the planned one
        self.stats.set_times(f"ate_{meal}_at", [minute_of_day(now)] if eaten else [])
        if eaten:
            self.stats.log("meal", self.minute(now), replace=("meal",), meal=meal)
        else:
            self.stats.unlog("meal", meal=meal)
        if self.sched.mark_meal(meal, eaten, now) and not self.meal_demo:  # the reminder is no longer needed
            self.close_meal_window()
        self.refresh_main()

    def finish_meal(self):
        self.sched.finish_meal()
        self.icon.update_menu()

    # --- end of the workday ---

    def show_day_end(self, demo=False):
        """"The workday is over" with the day's summary. "Finish the day" pauses until morning."""
        today = self.stats.day(self.today())
        text = t("day_end_text", breaks=today["mini_done"] + today["long_done"], volume=fmt_volume(today["water"]))
        answer = (lambda _answer: None) if demo else self.answer_day_end
        actions = [(t("day_end_snooze", min=DAY_END_SNOOZE_MIN), lambda: answer("snooze"), False),
                   (t("day_end_finish"), lambda: answer("finish"), True)]
        self.show_toast(t("day_end_title"), text, actions, timeout_ms=60_000 if demo else None,
                        kind="day_end", on_dismiss=None if demo else lambda: answer("snooze"), demo=demo)
        self.beep()

    def answer_day_end(self, answer):
        self.sched.day_end_answered(answer)
        if answer == "finish":
            self.handle(("pause", None))  # the "until morning" pause records when the day was finished

    def show_overwork(self, demo=False):
        """Today's time at the computer reached the limit (max_work_hours): "Finish the day" or "Later".
        It stands in the corner like day end (kind="day_end") until answered; finishing the day removes both.
        Pushed out by another notification, it asks again later instead of deciding "Later" for the person."""
        if demo:  # in the demo, the limit itself (or the default 9 h if it's off)
            seconds = (self.cfg["max_work_hours"] or DEFAULTS["max_work_hours"]) * 3600
        else:
            seconds = self.stats.day(self.today())["work_sec"] + self.work_pending
        worked = fmt_minutes(int(seconds) // 60)
        answer = (lambda _answer: None) if demo else self.answer_overwork
        actions = [(t("later"), lambda: answer("later"), False), (t("day_end_finish"), lambda: answer("finish"), True)]
        self.show_toast(t("overwork_title"), t("overwork_text", time=worked), actions,
                        timeout_ms=60_000 if demo else None, kind="day_end",
                        on_dismiss=None if demo else lambda: answer("snooze"), demo=demo)
        self.beep()

    def answer_overwork(self, answer):
        self.sched.overwork_answered(answer)
        if answer == "finish":
            self.handle(("pause", None))

    # --- own notifications ---

    def corner(self, *below):
        """The bottom right corner of the work area (without the taskbar) for a new window;
        if windows from `below` are already there, above them."""
        _left, _top, right, bottom = system.work_area(self.root)
        for win in below:
            if win:
                bottom = min(bottom, win.winfo_rooty())
        return right, bottom

    def kept_toast(self):
        """Windows share one corner: the break warning and day end stay, and a new window
        goes above them; other notifications close. Returns the notification that stayed."""
        if self.toast_kind in ("warning", "day_end"):
            return self.toast_win
        self.close_toast()
        return None

    def corner_window(self, color):
        """A window above everything, without an OS frame, with a coloured border (the same when focused)."""
        win = tk.Toplevel(self.root, bg=C["panel"], highlightthickness=2, highlightbackground=color,
                          highlightcolor=color)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        return win

    def place_in_corner(self, win, width, right, bottom):
        """Size by content (no narrower than width) and a place in the bottom right corner above `bottom`."""
        win.update_idletasks()
        width = max(width, win.winfo_reqwidth())
        height = win.winfo_reqheight()
        win.geometry(f"{width}x{height}+{right - width - 16}+{bottom - height - 16}")

    def popup_head(self, win, title, color, counter, demo, close):
        """The header of the water or meal window: the title, "2 of 3" on the right and, for a demo, the badge and Esc."""
        head = tk.Frame(win, bg=C["panel"])
        head.pack(fill="x", padx=EDGE, pady=(EDGE, 0))
        tk.Label(head, text=title, bg=C["panel"], fg=color, font=font(16, "semibold")).pack(side="left")
        tk.Label(head, text=counter, bg=C["panel"], fg=C["muted"], font=font(11)).pack(side="right")
        if demo:
            demo_badge(head).pack(side="right", padx=8)
            win.bind("<Escape>", lambda e: close())

    def popup_buttons(self, win, actions, color, on_color):
        """Buttons at the bottom right: actions = [(label, action, primary?)]; the primary one is in the window colour with a check mark."""
        row = tk.Frame(win, bg=C["panel"])
        row.pack(anchor="e", padx=EDGE - UNIT, pady=4 * UNIT)
        for label, command, primary in actions:
            flat_button(row, label, command, size=11, bg=color if primary else C["bg"],
                        fg=on_color if primary else C["text"],
                        image=check_mark(16, on_color) if primary else None).pack(side="left", padx=4)

    def show_toast(self, title, text, actions=(), timeout_ms=10_000, kind="info", on_dismiss=None, demo=False):
        """A popup in the screen corner. We don't rely on system notifications:
        the user may have turned them off (on Windows they then silently disappear),
        and on macOS they are unreliable for apps not signed by Apple.
        actions: [(label, function, primary_button?)]; on_dismiss runs if the window closed without a button
        (a timeout, or another notification pushed it out). timeout_ms=None: it stays until answered —
        for anything that asks the person, so nothing is decided for them while they are away."""
        self.close_toast()
        right, bottom = self.corner(self.water_win, self.meal_win)  # don't cover water and meals
        width = 380
        win = self.corner_window(C["accent"])
        head = tk.Frame(win, bg=C["panel"])
        head.pack(fill="x", padx=EDGE, pady=(4 * UNIT, TIGHT))
        tk.Label(head, text=title, bg=C["panel"], fg=C["accent"], font=font(13, "semibold")).pack(side="left")
        if demo:
            demo_badge(head).pack(side="right", padx=(8, 0))
            win.bind("<Escape>", lambda e: self.close_toast())
        self.toast_text = tk.Label(win, text=text, bg=C["panel"], fg=C["text"], font=font(10),
                                   wraplength=width - 40, justify="left")
        self.toast_text.pack(anchor="w", padx=EDGE, pady=(0, 0 if actions else 4 * UNIT))
        if actions:
            row = tk.Frame(win, bg=C["panel"])
            row.pack(anchor="e", padx=EDGE - UNIT, pady=3 * UNIT)
            for label, command, primary in actions:
                btn = flat_button(row, label, lambda c=command: (self.close_toast(dismissed=False), c()), size=10,
                                  bg=C["accent"] if primary else C["bg"], fg=C["on_accent"] if primary else C["text"])
                btn.configure(padx=14)
                btn.pack(side="left", padx=3)
        else:
            for widget in (win, *win.winfo_children()):
                widget.bind("<Button-1>", lambda e: self.close_toast())
        self.place_in_corner(win, width, right, bottom)  # three buttons may be wider than the standard width
        self.toast_win = win
        self.toast_kind = kind
        self.toast_on_dismiss = on_dismiss
        self.toast_after = self.root.after(timeout_ms, self.close_toast) if timeout_ms else None

    def close_toast(self, dismissed=True):
        if self.toast_after:
            self.root.after_cancel(self.toast_after)
            self.toast_after = None
        if self.toast_win:
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
        else:  # "Later": a missed glass on the day timeline
            self.stats.log("water_missed", self.minute())
        self.sync_day()  # the next glass's pace, counting the one just drunk
        self.sched.water_answered(drank)

    def log_water_times(self, delta):
        """Each glass's time, for the day timeline: added glasses are "now", removed ones are the last ones."""
        today = self.today()
        times = self.stats.times(today, "water_at")
        if delta > 0:
            times += [minute_of_day(dt.datetime.now())] * delta
            for _ in range(delta):
                self.stats.log("water", self.minute())
        else:
            times = times[:max(0, len(times) + delta)]
        self.stats.set_times("water_at", times)
