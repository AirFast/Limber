"""Головне вікно: вкладки «Стан», «Статистика», «Налаштування» й розкладка під екран."""

import datetime as dt
import tkinter as tk
from tkinter import messagebox

from PIL import ImageTk

import i18n
import system
from core import (APP_NAME, at_minute, minute_of_day, CONFIG_PATH, MAX_GLASSES, MEALS, SLIDERS, WATER_PROFILES, Stats,
                  apply_water_profile, completion_rate, fmt_hm, fmt_time, main_layout, save_json,
                  split_balanced, water_interval_for, water_streak)
from graphics import (C, GLASSES_PER_ROW, MAX_GLASSES_SHOWN, PLATE_STATES, check_mark, dot_image,
                      draw_progress_ring, glass_image, make_app_icon, plate_image, rgba, smooth_image)
from i18n import fmt_after_minis, fmt_clock, fmt_days, fmt_glasses, fmt_minutes, fmt_volume, t
from system import font
from widgets import ScrollArea, Slider, Toggle, card, flat_button, wrap_to_width


TIMELINE_HEIGHT = 76      # шкала дня в картці «Сьогодні»
TITLE_BAR = 32            # приблизна висота заголовка вікна ОС — щоб вікно вміщалося в робочу область
STATS_RANGES = (7, 30)    # перемикач періоду на графіку статистики


class MainWindow:
    """Частина App: головне вікно та його сторінки."""

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
        win.title(f"{APP_NAME} {self.version}")
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
        # Смуга прокрутки (6 + 8 px) живе в правому відступі: правий край вмісту — на одній лінії
        # з правим краєм кнопок вкладок (24 px від краю вікна)
        body.pack(fill="both", expand=True, padx=(24, 24 - ScrollArea.BAR - 8), pady=(4, 20))
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
        return system.work_area(self.root)

    def fit_main_window(self, header, work):
        """Вікно під найбільшу сторінку, але не більше за робочу область екрана — тоді сторінки
        прокручуються. Розмір залежить від мови, шрифтів і масштабу екрана, тож не задаємо його числами."""
        win = self.main_win
        win.update_idletasks()  # розміри, що просять сторінки, рахуються й для прихованого вікна
        frames = self.page_frames.values()
        left, top, right, bottom = work
        # Відступи тіла разом зі смугою прокрутки — 24 + 24; заголовка (18 + 10) і тіла (4 + 20)
        width = max(self.layout["width"], *(page.winfo_reqwidth() + 48 for page in frames))
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
        if not self.saved_check:
            self.saved_check = check_mark(14, C["accent"])
        label.configure(text=t("saved"), image=self.saved_check, compound="right")
        if self._saved_after:
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
        minute = minute_of_day(now)
        drinks = self.stats.times(now.date(), "water_at")
        s = self.sched
        next_water = None
        if self.cfg["water_enabled"] and not s.water_open and not (s.paused and s.pause_water):
            next_water = minute + round(s.water_remaining / 60)
        idle = s.paused or bool(s.eating)
        key = (width, minute, tuple(marks), tuple(drinks), next_water, idle)
        if not force and key == self._timeline_key:
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
            at = at_minute(now.date(), cfg["day_end_at"])
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
        info = self.chart_info
        if not info:
            return
        inside = info["top"] - 20 <= event.y <= info["bottom"] + 62
        self.highlight_day(min(len(info["days"]) - 1, max(0, int(event.x // info["slot"]))) if inside else None)

    def highlight_day(self, index):
        """Підсвітка стовпчика, підказка з деталями дня й картки нагорі для цього дня."""
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
        """Щосекунди: шапка й поточна сторінка. «Стан» — найдорожча (кільце, шкала дня), тож
        перемальовуємо його, лише коли його видно: на інших вкладках і в згорнутому вікні — ні."""
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
