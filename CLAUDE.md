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

Dev/debug flags for `src/rhythmos.py`: `--open`, `--test-break` (trigger a break after 1.5 s), `--test-water`, `--smoke-test <dir>` (walks every window and saves screenshots, then exits with a status code — CI runs this against the built macOS app). Installer-only flags that apply a setting and exit immediately: `--set-autostart=on|off`, `--set-language=uk|en`.

Lint with `python3 -m pyflakes src tests` (CI runs it; it also catches duplicate keys in the `i18n.py` dictionaries, which would silently override a string).

## Architecture

All source is in `src/` as flat modules (no package); tests add `src/` to `sys.path` and import `rhythmos`, `exercises`, `i18n` directly.

- **`rhythmos.py`** — the whole app. Pure logic lives at the top and is what tests cover: `Scheduler` (work-time countdown, warn/break/water events, postpone limit, pause), `build_workout`/`regroup_workout`/`build_break` (assemble break steps that sum to an exact duration), `Stats`, config load/save (`DEFAULTS`, `SLIDERS`). Below that is UI: drawing helpers (supersampled Pillow images for the tray ring and widgets), custom Tk widgets (`Slider`, `Toggle`, `flat_button`), and the `App` class.
- **`system.py`** — every OS-specific concern behind `IS_WINDOWS`/`IS_MAC` branches: data dir, fonts, autostart (Windows Task Scheduler via PowerShell; macOS LaunchAgent plist), single-instance lock (named mutex vs `fcntl`) and "show window" signalling, monitors, sounds, notifications, tray startup, system language. Put new platform-dependent code here, not in `rhythmos.py`.
- **`exercises.py`** — the exercise library. Each entry is `(kind, group, level, (title_uk, text_uk), (title_en, text_en))`; `kind` is `mini`/`active`/`long`/`workout`, `group` is one of `GROUPS`. Pools are filtered by kind/group/level and localized at selection time.
- **`updates.py`** — once-a-day check of the latest GitHub release (`AirFast/Rhythmos`, needs the repo to be public); `App.check_updates` runs it in a thread and posts the result to the queue. Uses `certifi` because frozen macOS builds have no system CA bundle.
- **`i18n.py`** — `STRINGS` (UI) and `CONTENT` (warmup/cooldown, water tips) for `uk` and `en`, plus plural-aware formatters (`fmt_minutes`, `fmt_glasses`, …). Language is module-global state (`set_language`). Tests enforce that both languages have identical keys/shape, every slider has labels in both, and every group has exercises for every break type and level — adding a string, slider, or exercise means updating both languages.

### Runtime model

- Tk runs on the main thread. Tray menu callbacks must not touch Tk directly — they `queue.put()` an action, and `App.process_queue` (polled every 100 ms via `root.after`) dispatches it. On Windows pystray runs its own loop in a daemon thread; on macOS both must live on the main thread, so pystray uses `run_detached` on the shared `NSApplication` that Tk already runs (`system.start_tray`/`make_tray_icon`).
- `App.loop` ticks every second using `time.monotonic()` deltas clamped to 5 s, so sleep time isn't counted as work while lock/idle doesn't reset the timer. `Scheduler.tick(seconds, now=None)` returns event names (`"warn"`, `"break"`, `"water"`, `"meal"`, `"meal_over"`, `"day_end"`) — tests drive it directly with `tick(1)` loops. Meal and end-of-workday reminders use wall-clock time (`now`, injectable in tests) rather than the work-time countdown; while `eating` is set, breaks and water are frozen until `finish_meal()`.
- User data (`config.json`, `stats.json`, `rhythmos.log`) lives in `system.data_dir()` (`%APPDATA%\Rhythmos` / `~/Library/Application Support/Rhythmos`). Frozen builds have no console, so stderr is redirected to `rhythmos.log` very early in `rhythmos.py` (before importing pystray) and uncaught errors are logged rather than raised.

## Release

Version is the single `__version__` in `src/rhythmos.py` (build scripts read it). Pushing a `v*` tag triggers `.github/workflows/release.yml`: tests + Windows installer, tests + macOS dmg + smoke test, then a GitHub Release with both artifacts. The macOS app is ad-hoc signed and made a menu-bar-only app (`LSUIElement`) by `build_mac.sh`; on first frozen launch it enables autostart itself since there's no installer. `assets/` icons are regenerated by `tools/make_icon.py` during builds.
