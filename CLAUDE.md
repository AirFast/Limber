# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Rhythmos is a break-reminder tray/menu-bar app for Windows and macOS (Apple Silicon), written in Python 3.12 with Tkinter for windows and `pystray` + Pillow for the tray icon. Code comments, docstrings, README and build-script messages are in **Ukrainian** — keep new comments in Ukrainian to match. Commits follow Conventional Commits (`feat(macos): …`, `fix: …`, `chore: release x.y.z`).

## Commands

```bash
python3 -m pip install -r requirements.txt -r requirements-build.txt
python3 src/rhythmos.py --open          # run from source, opening the main window
python3 -m pytest -q                  # all tests
python3 -m pytest -q tests/test_logic.py::test_postpone_limit   # single test
./build_mac.sh [version]              # dist/Rhythmos.app + dist/Rhythmos-<ver>-macos-<arch>.dmg
.\build.ps1 [-Version x.y.z]          # Windows: PyInstaller exe + Inno Setup installer
```

Dev/debug flags for `src/rhythmos.py`: `--open`, `--test-break` (trigger a break after 1.5 s), `--test-water`, `--smoke-test <dir>` (walks every window, saves screenshots plus `info.txt` with window/page sizes, then exits with a status code — CI runs it against the built app on both Windows and macOS and uploads `windows-smoke` / `macos-smoke`; look at those screenshots before tagging a release, macOS has broken layouts that Windows did not show). Installer-only flags that apply a setting and exit immediately: `--set-autostart=on|off`, `--set-language=uk|en`.

Lint with `python3 -m pyflakes src tests` (CI runs it; it also catches duplicate keys in the `i18n.py` dictionaries, which would silently override a string).

## Architecture

All source is in `src/` as flat modules (no package); tests add `src/` to `sys.path` and import `core`, `exercises`, `i18n` directly. Dependencies go one way: `core` ← `graphics` ← `widgets` ← `popups` / `main_window` ← `rhythmos`.

- **`core.py`** — all logic without Tk, and what tests cover: config (`DEFAULTS`, `SLIDERS`, water profiles), `Scheduler` (work-time countdown; warn/break/water events; meals and end of day on wall-clock time; postpone limit, pause, eating), `build_workout`/`regroup_workout`/`build_break` (break steps that sum to an exact duration), `Stats` (per-day counters plus time lists such as `water_at`), and layout maths (`split_balanced`, `main_layout`).
- **`graphics.py`** — the palette `C` and everything drawn with Pillow: tray ring, app icon, glasses, plates, dots, check mark. Tk does not anti-alias, so shapes are drawn supersampled (`smooth_image`) and cached as `PhotoImage`s.
- **`widgets.py`** — custom Tk widgets (`flat_button`, `card`, `Slider`, `Toggle`, `ScrollArea`, `demo_badge`). Built from `Label`/`Canvas` because `tk.Button` on macOS ignores colours.
- **`popups.py`** — `Popups` mixin of `App`: break warning and break screens, water/meal/day-end windows and toasts stacked in the screen corner (`corner_window`, `place_in_corner`, `popup_head`, `popup_buttons`).
- **`main_window.py`** — `MainWindow` mixin of `App`: the main window sized to the screen's work area (`main_layout`; pages in `ScrollArea`s scroll when they don't fit) with the Status, Statistics and Settings pages. `refresh_main` runs every second but redraws the Status page only while it is visible.
- **`rhythmos.py`** — entry point and `App(Popups, MainWindow)`: tray, the per-second loop, action queue, update checks, `--smoke-test`. `__version__` lives here.
- **`system.py`** — every OS-specific concern behind `IS_WINDOWS`/`IS_MAC` branches: data dir, fonts, autostart (Windows Task Scheduler via PowerShell; macOS LaunchAgent plist), single-instance lock (named mutex vs `fcntl`) and "show window" signalling, monitors, sounds, notifications, tray startup, system language. Put new platform-dependent code here, not in the UI modules.
- **`exercises.py`** — the exercise library. Each entry is `(kind, group, level, (title_uk, text_uk), (title_en, text_en))`; `kind` is `mini`/`active`/`long`/`workout`, `group` is one of `GROUPS`. Pools are filtered by kind/group/level and localized at selection time.
- **`updates.py`** — hourly (and on opening the main window) check of the latest GitHub release (`AirFast/Rhythmos`, needs the repo to be public); `App.check_updates` runs it in a thread and posts the result to the queue. Uses `certifi` because frozen macOS builds have no system CA bundle.
- **`i18n.py`** — `STRINGS` (UI) and `CONTENT` (warmup/cooldown, water and meal tips) for `uk` and `en`, plus plural-aware formatters (`fmt_minutes`, `fmt_glasses`, …). Language is module-global state (`set_language`). Tests enforce that both languages have identical keys/shape, every slider has labels in both, and every group has exercises for every break type and level — adding a string, slider, or exercise means updating both languages.

### Runtime model

- Tk runs on the main thread. Tray menu callbacks must not touch Tk directly — they `queue.put()` an action, and `App.process_queue` (polled every 100 ms via `root.after`) dispatches it. On Windows pystray runs its own loop in a daemon thread; on macOS both must live on the main thread, so pystray uses `run_detached` on the shared `NSApplication` that Tk already runs (`system.start_tray`/`make_tray_icon`).
- `App.loop` ticks every second using `time.monotonic()` deltas clamped to 5 s, so sleep time isn't counted as work while lock/idle doesn't reset the timer. `Scheduler.tick(seconds, now=None)` returns event names (`"warn"`, `"break"`, `"water"`, `"meal"`, `"meal_over"`, `"day_end"`) — tests drive it directly with `tick(1)` loops. Meal and end-of-workday reminders use wall-clock time (`now`, injectable in tests) rather than the work-time countdown; while `eating` is set, breaks and water are frozen until `finish_meal()`.
- User data (`config.json`, `stats.json`, `rhythmos.log`) lives in `system.data_dir()` (`%APPDATA%\Rhythmos` / `~/Library/Application Support/Rhythmos`). Frozen builds have no console, so stderr is redirected to `rhythmos.log` very early in `rhythmos.py` (before importing pystray) and uncaught errors are logged rather than raised.

## Release

Version is the single `__version__` in `src/rhythmos.py` (build scripts read it). Every push to `main` runs `.github/workflows/release.yml` (lint, tests, Windows installer + smoke test, macOS dmg + smoke test + self-update test); pushing a `v*` tag additionally publishes a GitHub Release with both installers (plus a `LimberSetup-*.exe` copy so pre-rename Limber builds can still auto-update). The macOS app is ad-hoc signed and made a menu-bar-only app (`LSUIElement`) by `build_mac.sh`; on first frozen launch it enables autostart itself since there's no installer. `assets/` icons are regenerated by `tools/make_icon.py` during builds.
