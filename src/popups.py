"""Вікна поверх роботи: попередження й екран перерви, вода, їжа, кінець дня, сповіщення в куті."""

import datetime as dt
import random
import tkinter as tk

import exercises
import system
from core import (DAY_END_SNOOZE_MIN, minute_of_day, MEALS, MEAL_SNOOZE_MIN, build_break, fmt_time, regroup_workout,
                  single_break_step)
from graphics import C, GLASSES_PER_ROW, MAX_GLASSES_SHOWN, PLATE_STATES, check_mark, glass_image, plate_image
from i18n import content, fmt_clock, fmt_minutes, fmt_volume, t
from system import font
from widgets import demo_badge, flat_button


class Popups:
    """Частина App: усе, що з'являється поверх інших вікон."""

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
        if self.toast_kind == "warning" and not demo:
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
        keep = self.kept_toast()
        right, bottom = self.corner(self.meal_win, keep)
        width = 420
        win = self.water_win = self.corner_window(C["water"])
        drunk = self.stats.day(dt.date.today())["water"]
        goal = self.cfg["water_goal"]
        done = drunk >= goal
        self.popup_head(win, t("water_title"), C["water"], t("x_of_y", a=drunk if done else drunk + 1, b=goal),
                        demo, lambda: self.end_water(False))
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
        drank = t(f"drank_{self.cfg['water_profile']}")  # «Випила» / «Випив» / нейтральне «Готово»
        self.popup_buttons(win, ((t("later"), lambda: self.end_water(False), False),
                                 (drank, lambda: self.end_water(True), True)), C["water"], C["on_water"])
        self.place_in_corner(win, width, right, bottom)
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
        keep = self.kept_toast()
        right, bottom = self.corner(self.water_win, keep)
        width = 440
        win = self.meal_win = self.corner_window(C["meal"])
        now = dt.datetime.now()
        meals = [m for m in MEALS if self.cfg[f"{m}_enabled"] or m == meal]
        title = t(f"meal_title_{meal}") if mode == "remind" else t("meal_over_title")
        self.popup_head(win, title, C["meal"], t("x_of_y", a=meals.index(meal) + 1, b=len(meals)),
                        demo, self.close_meal_window)
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
        self.stats.set_times(f"ate_{meal}_at", [minute_of_day(now)] if eaten else [])
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
            self.stats.set("day_end", minute_of_day(dt.datetime.now()))
            self.handle(("pause", None))

    # --- власні сповіщення ---

    def corner(self, *below):
        """Правий нижній кут робочої області (без панелі завдань) для нового віконця;
        якщо там уже стоять віконця з `below` — над ними."""
        _left, _top, right, bottom = system.work_area(self.root)
        for win in below:
            if win:
                bottom = min(bottom, win.winfo_rooty())
        return right, bottom

    def kept_toast(self):
        """Віконця живуть у тому самому куті: попередження про перерву й кінець дня лишаються, а нове
        віконце стає над ними; решта сповіщень закривається. Повертає сповіщення, що лишилось."""
        if self.toast_kind in ("warning", "day_end"):
            return self.toast_win
        self.close_toast()
        return None

    def corner_window(self, color):
        """Віконце поверх усього, без рамки ОС, з кольоровою рамкою (однаковою й у фокусі)."""
        win = tk.Toplevel(self.root, bg=C["panel"], highlightthickness=2, highlightbackground=color,
                          highlightcolor=color)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        return win

    def place_in_corner(self, win, width, right, bottom):
        """Розмір за вмістом (не вужче за width) і місце в правому нижньому куті над `bottom`."""
        win.update_idletasks()
        width = max(width, win.winfo_reqwidth())
        height = win.winfo_reqheight()
        win.geometry(f"{width}x{height}+{right - width - 16}+{bottom - height - 16}")

    def popup_head(self, win, title, color, counter, demo, close):
        """Шапка віконця води чи їжі: заголовок, «2 з 3» праворуч і, для демо, позначка й Esc."""
        head = tk.Frame(win, bg=C["panel"])
        head.pack(fill="x", padx=20, pady=(16, 0))
        tk.Label(head, text=title, bg=C["panel"], fg=color, font=font(16, "semibold")).pack(side="left")
        tk.Label(head, text=counter, bg=C["panel"], fg=C["muted"], font=font(11)).pack(side="right")
        if demo:
            demo_badge(head).pack(side="right", padx=8)
            win.bind("<Escape>", lambda e: close())

    def popup_buttons(self, win, actions, color, on_color):
        """Кнопки внизу праворуч: actions — [(напис, дія, головна?)]; головна — у кольорі віконця з галочкою."""
        row = tk.Frame(win, bg=C["panel"])
        row.pack(anchor="e", padx=16, pady=14)
        for label, command, primary in actions:
            flat_button(row, label, command, size=11, bg=color if primary else C["bg"],
                        fg=on_color if primary else C["text"],
                        image=check_mark(16, on_color) if primary else None).pack(side="left", padx=4)

    def show_toast(self, title, text, actions=(), timeout_ms=10_000, kind="info", on_dismiss=None, demo=False):
        """Спливаюче віконце в куті екрана. Не покладаємося на системні сповіщення:
        користувач міг їх вимкнути (на Windows вони тоді просто мовчки зникають),
        а на macOS вони ненадійні для програм без підпису Apple.
        actions: [(напис, функція, головна_кнопка?)]; on_dismiss — якщо віконце зникло без натискання кнопки
        (тайм-аут або його витіснило інше сповіщення)."""
        self.close_toast()
        right, bottom = self.corner(self.water_win, self.meal_win)  # не перекриваємо воду й їжу
        width = 380
        win = self.corner_window(C["accent"])
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
        self.place_in_corner(win, width, right, bottom)  # три кнопки можуть бути ширшими за стандартну ширину
        self.toast_win = win
        self.toast_kind = kind
        self.toast_on_dismiss = on_dismiss
        self.toast_after = self.root.after(timeout_ms, self.close_toast)

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
        self.sched.water_answered(drank)

    def log_water_times(self, delta):
        """Час кожної склянки — для шкали дня: додані склянки — «зараз», зняті — останні з кінця."""
        today = dt.date.today()
        times = self.stats.times(today, "water_at")
        if delta > 0:
            times += [minute_of_day(dt.datetime.now())] * delta
        else:
            times = times[:max(0, len(times) + delta)]
        self.stats.set_times("water_at", times)
