import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import exercises  # noqa: E402
import i18n  # noqa: E402
import rhythmos  # noqa: E402
import updates  # noqa: E402


@pytest.fixture(autouse=True)
def ukrainian():
    i18n.set_language("uk")
    yield
    i18n.set_language("uk")


def make_scheduler(**overrides):
    return rhythmos.Scheduler(dict(rhythmos.DEFAULTS, **overrides))


def tick(s, seconds):
    events = []
    for _ in range(seconds):
        events += s.tick(1)
    return events


def test_break_fires_after_interval_with_warning():
    s = make_scheduler(mini_interval_min=1, warn_before_sec=10)
    assert tick(s, 60) == ["warn", "break"]
    assert s.in_break and s.next_kind() == "mini"


def test_timer_is_frozen_during_break_and_pause():
    s = make_scheduler(mini_interval_min=1)
    tick(s, 60)
    assert s.tick(100) == []
    s.finish_break()
    s.pause(30)
    assert s.tick(1000) == [] and s.remaining == 60


def test_timed_pause_stops_breaks_but_not_water():
    s = make_scheduler(mini_interval_min=1, water_interval_min=5, warn_before_sec=0)
    s.pause(30)
    events = tick(s, 5 * 60)
    assert events == ["water"]          # вода нагадала, хоча перерви на паузі
    assert s.remaining == 60            # відлік до перерви стоїть


def test_pause_until_morning_stops_water_too():
    s = make_scheduler(mini_interval_min=1, water_interval_min=5, warn_before_sec=0)
    s.pause(None)
    assert tick(s, 10 * 60) == []
    assert s.water_remaining == 5 * 60
    s.resume()
    assert tick(s, 60) == ["break"]     # після «Продовжити» все знову рахується


def test_every_nth_break_is_long():
    s = make_scheduler(long_every=3)
    kinds = []
    for _ in range(6):
        kinds.append(s.next_kind())
        s.finish_break()
    assert kinds == ["mini", "mini", "long", "mini", "mini", "long"]


def test_postpone_limit():
    s = make_scheduler(postpone_limit=2, postpone_min=5)
    s.postpone()
    s.postpone()
    assert s.remaining == 300 and not s.can_postpone()
    s.finish_break()
    assert s.can_postpone()


@pytest.mark.parametrize("minutes", [2, 3, 5, 7, 10, 15, 30])
@pytest.mark.parametrize("level", [1, 2, 3])
def test_workout_fills_exact_duration(minutes, level):
    steps = rhythmos.build_workout(minutes * 60, level)
    assert sum(step["secs"] for step in steps) == minutes * 60
    assert steps[0]["kind"] == "warmup" and steps[-1]["kind"] == "cooldown"


def test_long_break_without_workout_is_single_step():
    cfg = dict(rhythmos.DEFAULTS, workout_enabled=False)
    assert [s["kind"] for s in rhythmos.build_break("long", cfg)] == ["list"]


@pytest.mark.parametrize("value, text", [(1, "1 раз"), (2, "2 рази"), (5, "5 разів"), (0, "не можна")])
def test_fmt_times(value, text):
    assert rhythmos.fmt_times(value) == text


@pytest.mark.parametrize("value, text", [(1, "1 склянка (≈0,25 л)"), (4, "4 склянки (≈1 л)"), (8, "8 склянок (≈2 л)")])
def test_fmt_glasses(value, text):
    assert rhythmos.fmt_glasses(value) == text


def test_both_languages_have_the_same_strings():
    assert set(i18n.STRINGS["uk"]) == set(i18n.STRINGS["en"])
    assert len(i18n.t("weekdays").split()) == 7
    i18n.set_language("en")
    assert len(i18n.t("weekdays").split()) == 7


def test_both_languages_have_the_same_content_shape():
    uk, en = i18n.CONTENT["uk"], i18n.CONTENT["en"]
    assert set(uk) == set(en)
    assert len(uk["water_tips"]) == len(en["water_tips"])


def test_exercise_entries_are_complete():
    for kind, group, level, uk, en in exercises.EXERCISES:
        assert kind in ("mini", "active", "long", "workout")
        assert group in exercises.GROUPS
        assert (level in (1, 2, 3)) == (kind == "workout")
        for title, body in (uk, en):
            assert title and body
            assert isinstance(body, list) == (kind == "long")


@pytest.mark.parametrize("group", exercises.GROUPS)
@pytest.mark.parametrize("level", [1, 2, 3])
def test_every_group_has_exercises_for_every_break(group, level):
    assert exercises.mini_pool(level, group)
    assert exercises.long_pool(group)
    assert exercises.workout_pool(level, group)


def test_regroup_replaces_only_upcoming_work_steps():
    steps = rhythmos.build_workout(300, 2)
    first_work = next(i for i, s in enumerate(steps) if s["kind"] == "work")
    before = steps[first_work]["title"]
    start = first_work + 1
    rhythmos.regroup_workout(steps, start, 2, "legs")
    legs = {title for title, _, _ in exercises.workout_pool(2, "legs")}
    assert steps[first_work]["title"] == before
    assert all(s["title"] in legs for s in steps[start:] if s["kind"] == "work")
    for i, s in enumerate(steps):
        if s["kind"] == "rest":
            following = next(n for n in steps[i + 1:] if n["kind"] == "work")
            assert following["title"] in s["text"]


def test_single_step_for_group_avoids_current_exercise():
    cfg = dict(rhythmos.DEFAULTS)
    current = rhythmos.single_break_step("mini", cfg, "eyes")["title"]
    for _ in range(20):
        assert rhythmos.single_break_step("mini", cfg, "eyes", avoid=current)["title"] != current


def test_every_slider_has_a_label_in_both_languages():
    for lang in i18n.LANGUAGES:
        i18n.set_language(lang)
        for key in rhythmos.SLIDERS:
            assert i18n.t(f"s_{key}")


@pytest.mark.parametrize("fmt, value, text", [
    (rhythmos.fmt_times, 1, "1 time"), (rhythmos.fmt_times, 3, "3 times"), (rhythmos.fmt_times, 0, "not allowed"),
    (rhythmos.fmt_glasses, 1, "1 glass (≈0.25 L)"), (rhythmos.fmt_glasses, 8, "8 glasses (≈2 L)"),
    (rhythmos.fmt_minutes, 90, "1 h 30 min"), (rhythmos.fmt_seconds, 75, "1 min 15 s"), (rhythmos.fmt_warn, 0, "off"),
])
def test_english_formatting(fmt, value, text):
    i18n.set_language("en")
    assert fmt(value) == text


def test_workout_is_built_in_the_current_language():
    i18n.set_language("en")
    steps = rhythmos.build_workout(300, 2)
    assert steps[0]["phase"] == "WARM-UP" and steps[-1]["phase"] == "COOL-DOWN"
    english_titles = {en[0] for kind, _g, level, _uk, en in exercises.EXERCISES if kind == "workout" and level in (1, 2)}
    assert all(s["title"] in english_titles for s in steps if s["kind"] == "work")


@pytest.mark.parametrize("candidate, current, newer", [
    ("v1.4.0", "1.3.0", True), ("1.10.0", "1.9.9", True), ("v1.3.0", "1.3.0", False),
    ("1.2.9", "1.3.0", False), ("v2", "1.9.9", True), ("1.3.1", "1.3", True),
])
def test_version_comparison(candidate, current, newer):
    assert updates.is_newer(candidate, current) is newer


def test_pick_asset_matches_this_platform(monkeypatch):
    assets = [{"name": "Rhythmos-2.0.0-macos-arm64.dmg"}, {"name": "RhythmosSetup-2.0.0.exe"}]
    monkeypatch.setattr(updates.sys, "platform", "win32")
    assert updates.pick_asset(assets)["name"] == "RhythmosSetup-2.0.0.exe"
    monkeypatch.setattr(updates.sys, "platform", "darwin")
    monkeypatch.setattr(updates.platform, "machine", lambda: "arm64")
    assert updates.pick_asset(assets)["name"] == "Rhythmos-2.0.0-macos-arm64.dmg"
    monkeypatch.setattr(updates.platform, "machine", lambda: "x86_64")
    assert updates.pick_asset(assets) is None


def test_download_checks_size_and_checksum(tmp_path):
    import hashlib
    source = tmp_path / "RhythmosSetup-9.9.9.exe"
    source.write_bytes(b"x" * 300_000)
    good = hashlib.sha256(source.read_bytes()).hexdigest()
    asset = {"name": source.name, "url": source.as_uri(), "size": 300_000, "sha256": good}
    seen = []
    path = updates.download(asset, progress=seen.append)
    assert open(path, "rb").read() == source.read_bytes() and seen
    with pytest.raises(OSError):
        updates.download(dict(asset, sha256="0" * 64))
    with pytest.raises(OSError):
        updates.download(dict(asset, size=1))


def test_windows_sound_ids_have_labels_in_both_languages():
    import system
    ids = {sound_id for sound_id, _ in system._WINDOWS_EVENTS + system._WINDOWS_FALLBACK + system._WINDOWS_EXTRA}
    for lang in i18n.LANGUAGES:
        for sound_id in ids:
            assert f"snd_{sound_id}" in i18n.STRINGS[lang], (lang, sound_id)


@pytest.mark.parametrize("lang, glasses, text", [
    ("uk", 0, "≈0 л"), ("uk", 5, "≈1,25 л"), ("uk", 8, "≈2 л"), ("en", 5, "≈1.25 L"), ("en", 42, "≈10.5 L"),
])
def test_fmt_volume(lang, glasses, text):
    i18n.set_language(lang)
    assert i18n.fmt_volume(glasses) == text


def test_migration_from_limber_moves_data_even_if_new_folder_exists(tmp_path, monkeypatch):
    import system
    old, new = tmp_path / "Limber", tmp_path / "Rhythmos"
    old.mkdir()
    new.mkdir()
    (old / "config.json").write_text('{"language": "en"}')
    (old / "stats.json").write_text("{}")
    (new / "rhythmos.log").write_text("log")        # журнал уже відкрито на старті — нова папка існує
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "nothing"))
    # Старе завдання автозапуску «Limber» нібито існує
    monkeypatch.setattr(system.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 0})())
    autostart = system.migrate_old_data(str(new))
    assert (new / "config.json").read_text() == '{"language": "en"}'
    assert (new / "stats.json").exists() and not old.exists()
    if system.IS_WINDOWS:
        assert autostart is True


def test_unknown_language_falls_back_to_english():
    i18n.set_language("de")
    assert i18n.get_language() == "en"
