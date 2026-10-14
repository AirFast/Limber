"""Rhythmos — нагадування про перерви з вправами, водою, їжею та статистикою (Windows, macOS).

Точка входу й сам застосунок: трей, щосекундний цикл, черга дій, оновлення, smoke-тест.
Логіка — у core.py, малювання — у graphics.py, віджети — у widgets.py,
вікна поверх роботи — у popups.py, головне вікно — у main_window.py."""
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

if sys.stderr is None:  # збірка без консолі: помилки імпорту інакше зникли б безслідно
    os.makedirs(system.data_dir(), exist_ok=True)
    sys.stderr = sys.stdout = open(os.path.join(system.data_dir(), "rhythmos.log"), "a", encoding="utf-8", buffering=1)

import pystray  # noqa: E402 — після перенаправлення stderr, щоб помилки імпорту потрапили в журнал

import i18n  # noqa: E402
import updates  # noqa: E402
from core import (APP_NAME, CONFIG_PATH, DATA_DIR, LOG_PATH, MEALS, Scheduler, Stats, fmt_time,  # noqa: E402
                  load_config, load_json, minute_of_day, save_json, set_language_setting, work_started)
from graphics import ensure_icon_file, make_icon  # noqa: E402
from i18n import t  # noqa: E402
from main_window import MainWindow  # noqa: E402
from popups import Popups  # noqa: E402

__version__ = "2.9.0"

UPDATE_CHECK_DELAY_MS = 30_000
UPDATE_CHECK_INTERVAL_MS = 60 * 60 * 1000   # щогодини: раз на добу нова версія могла чекати до завтра
UPDATE_RECHECK_ON_OPEN_SEC = 10 * 60        # відкриття головного вікна теж перевіряє, але не частіше


class App(Popups, MainWindow):
    def __init__(self):
        self.version = __version__
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
        self.updating = False  # завантажується й встановлюється оновлення
        self.day_start_noted = None  # дата, для якої початок робочого дня вже записано
        # Сповіщення в куті (popups.show_toast): одне за раз
        self.toast_win = self.toast_text = self.toast_kind = self.toast_after = self.toast_on_dismiss = None
        # Головне вікно (main_window): сторінки, кеші перемальовування, позначка «Збережено»
        self.pages, self.page_frames, self.tab_buttons = {}, {}, {}
        self.current_page = None
        self.chart_info = None
        self._timeline_key = self._ring_key = None
        self.saved_check = self._saved_after = None

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
        if self.cfg["check_updates"] and not self.updating:
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
            print(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} встановлюю оновлення з {value}", file=sys.stderr)
            if self.toast_text:
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
            if action[1] is None:  # «до ранку» — те саме, що «Завершити день»
                self.finish_day()
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


    def finish_day(self):
        """День завершено (кнопкою у віконці кінця дня чи паузою «до ранку»): час — у статистику,
        віконця, що чекали на відповідь, — геть."""
        if not self.stats.day(dt.date.today())["day_end"]:
            self.stats.set("day_end", minute_of_day(dt.datetime.now()))
        if self.toast_kind == "day_end":
            self.close_toast(dismissed=False)
        if not self.meal_demo:
            self.close_meal_window()

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
        self.note_day_start()
        s = self.sched
        if not (s.in_break or s.eating or s.paused):
            self.work_pending += delta
            if self.work_pending >= 60:
                self.flush_work_time()
        self.update_break_warning()
        self.update_tray()
        self.refresh_main()
        self.root.after(1000, self.loop)

    def note_day_start(self):
        """Перша дія з мишею чи клавіатурою сьогодні — початок робочого дня (раз на день)."""
        today = dt.date.today()
        if self.day_start_noted == today:
            return
        if self.stats.day(today)["day_start"]:
            self.day_start_noted = today
            return
        minute = work_started(dt.datetime.now(), system.idle_seconds())
        if minute is not None:
            self.stats.set("day_start", minute)
            self.day_start_noted = today

    def flush_work_time(self):
        seconds = int(self.work_pending)
        if seconds:
            self.stats.add("work_sec", seconds)
            self.work_pending -= seconds

    def beep(self):
        if self.cfg["sound"]:
            system.beep("info", self.sound_name())

def current_version():
    """Версія для порівняння з релізами. RHYTHMOS_VERSION_OVERRIDE — лише для перевірки
    самооновлення в CI: зібрана програма «вдає» стару версію й оновлюється до останнього релізу."""
    return os.environ.get("RHYTHMOS_VERSION_OVERRIDE") or __version__


def quartz_available():
    """Для smoke-тесту: чи є в збірці Quartz (без нього на macOS не видно бездіяльності)."""
    if not system.IS_MAC:
        return "n/a"
    try:
        importlib.import_module("Quartz")
        return "yes"
    except ImportError:
        return "MISSING"


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
        # Бездіяльність (для початку робочого дня): на macOS — через Quartz, який має потрапити в збірку
        (lambda: note(f"idle {system.idle_seconds():.1f} s, day start {app.stats.day(dt.date.today())['day_start']}, "
                      f"quartz {quartz_available()}"), None),
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
