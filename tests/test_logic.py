import datetime as dt
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import exercises  # noqa: E402
import i18n  # noqa: E402
import core  # noqa: E402
import updates  # noqa: E402


@pytest.fixture(autouse=True)
def ukrainian():
    i18n.set_language("uk")
    yield
    i18n.set_language("uk")


def make_scheduler(**overrides):
    # Meals and day end are tied to the clock, so they're off in tests unless enabled explicitly
    meals_off = {f"{meal}_enabled": False for meal in core.MEALS}
    # The test date is a Wednesday; "workdays only" is checked separately
    return core.Scheduler({**core.DEFAULTS, **meals_off, "day_end_enabled": False, **overrides})


def at(hour, minute=0, second=0):
    """A moment of the test day, Wednesday 14.10.2026: tests don't depend on the machine's clock."""
    return dt.datetime(2026, 10, 14, hour, minute, second)


def tick_at(s, start, seconds, **kwargs):
    """Ticks second by second, moving the clock too."""
    events = []
    for i in range(seconds):
        events += s.tick(1, now=start + dt.timedelta(seconds=i), **kwargs)
    return events


def tick(s, seconds, start=at(10)):
    return tick_at(s, start, seconds)


def test_break_fires_after_interval_with_warning():
    s = make_scheduler(mini_interval_min=1, warn_before_sec=10)
    assert tick(s, 60) == ["warn", "break"]
    assert s.in_break and s.next_kind() == "mini"


def test_timer_is_frozen_during_break_and_pause():
    s = make_scheduler(mini_interval_min=1)
    tick(s, 60)
    assert s.tick(100, now=at(10, 1)) == []
    s.finish_break()
    s.pause(30, now=at(10, 1))
    assert s.tick(1000, now=at(10, 2)) == [] and s.remaining == 60


def test_timed_pause_stops_breaks_but_not_water():
    s = make_scheduler(mini_interval_min=1, water_interval_min=5, warn_before_sec=0)
    s.pause(30, now=at(10))
    events = tick(s, 5 * 60)
    assert events == ["water"]          # water reminded even though breaks are paused
    assert s.remaining == 60            # the countdown to the break stands


def test_pause_until_morning_stops_water_too():
    s = make_scheduler(mini_interval_min=1, water_interval_min=5, warn_before_sec=0)
    s.pause(None, now=at(10))
    # The person doesn't keep working (or the day would continue) but hasn't left either: just reading without the mouse
    assert tick_at(s, at(10), 10 * 60, idle=2 * 60) == []
    assert s.water_remaining == 5 * 60
    s.resume()
    assert tick(s, 60, start=at(10, 10)) == ["break"]     # after "Continue" everything counts again


def test_lunch_reminds_once_at_its_time():
    s = make_scheduler(lunch_enabled=True, lunch_at=13 * 60)
    assert s.tick(1, now=at(12, 59)) == []
    assert s.tick(1, now=at(13, 0)) == ["meal"] and s.meal_open == "lunch"
    s.meal_answered("skip", now=at(13, 1))
    assert s.tick(1, now=at(13, 2)) == []   # already reminded today


def test_meal_is_not_shown_long_after_its_time():
    s = make_scheduler(lunch_enabled=True, lunch_at=13 * 60)
    assert s.tick(1, now=at(14, 5)) == []   # the computer woke up more than an hour later


def test_disabled_meal_and_pause_until_morning_stay_silent():
    assert make_scheduler(lunch_enabled=False).tick(1, now=at(13)) == []
    s = make_scheduler(lunch_enabled=True, lunch_at=13 * 60)
    s.pause(None, now=at(12, 59))
    assert s.tick(1, now=at(13)) == []


def test_meal_snooze_reminds_again():
    s = make_scheduler(lunch_enabled=True, lunch_at=13 * 60)
    s.tick(1, now=at(13))
    s.meal_answered("snooze", now=at(13))
    assert s.tick(1, now=at(13, 10)) == []
    assert s.tick(1, now=at(13, 15)) == ["meal"]


def test_snooze_lengths_come_from_the_settings():
    s = make_scheduler(lunch_enabled=True, lunch_at=13 * 60, meal_snooze_min=25, day_end_enabled=True,
                       day_end_at=18 * 60, day_end_snooze_min=60, water_later_min=40)
    s.tick(1, now=at(13))
    s.meal_answered("snooze", now=at(13))
    assert s.tick(1, now=at(13, 15)) == []
    assert s.tick(1, now=at(13, 25)) == ["meal"]
    s.meal_answered("eat", now=at(13, 25))
    s.extend_meal(now=at(14))
    assert s.paused_until is None and s.until == at(14, 25)          # "25 more min" after the meal pause
    s.finish_meal()
    s.water_answered(False, now=at(15))
    assert s.water_remaining == 40 * 60                               # "Later" in the water reminder
    assert s.tick(1, now=at(18)) == ["day_end"]
    s.day_end_answered("snooze", now=at(18))
    assert s.tick(1, now=at(18, 30)) == []
    assert s.tick(1, now=at(19)) == ["day_end"]


def test_eating_freezes_timers_and_asks_to_continue():
    s = make_scheduler(lunch_enabled=True, lunch_at=13 * 60, meal_pause_min=30, mini_interval_min=20,
                       water_interval_min=60, warn_before_sec=0)
    s.tick(1, now=at(13))
    remaining, water = s.remaining, s.water_remaining
    s.meal_answered("eat", now=at(13))
    assert tick_at(s, at(13), 29 * 60) == []
    assert (s.remaining, s.water_remaining) == (remaining, water)   # breaks and water are frozen
    assert tick_at(s, at(13, 30), 10 * 60) == ["meal_over"]         # asked once, then waits for the answer
    assert s.eating == "lunch"
    s.extend_meal(now=at(13, 40))
    assert tick_at(s, at(13, 40), 15 * 60 + 1) == ["meal_over"]
    s.finish_meal()
    assert not s.eating and s.remaining == 20 * 60 and s.water_remaining == 60 * 60
    assert s.tick(1, now=at(13, 56)) == []


def test_pause_button_lasts_until_continue_but_not_into_the_next_day():
    s = make_scheduler(mini_interval_min=20, water_enabled=False)   # a plain pause stops only breaks
    s.pause(0, now=at(10))
    assert s.open_pause and s.paused_until == at(6) + dt.timedelta(days=1)
    remaining = s.remaining
    assert tick_at(s, at(10), 3 * 60 * 60) == [] and s.remaining == remaining   # no breaks for hours
    restored = make_scheduler()
    assert restored.restore(s.snapshot(at(13)), at(13, 1)) and restored.open_pause and restored.paused
    assert s.resume(now=at(13)) is False and not s.paused         # "Continue": a plain pause, the day goes on
    s.pause(0, now=at(23))
    s.tick(1, now=at(6) + dt.timedelta(days=1))
    assert not s.paused                                          # forgotten overnight: over by the morning


def test_going_to_eat_cancels_timed_pause():
    s = make_scheduler(lunch_enabled=True, lunch_at=13 * 60)
    s.pause(30, now=at(12, 59))
    assert s.tick(1, now=at(13)) == ["meal"]    # a plain pause doesn't block the meal
    s.meal_answered("eat", now=at(13))
    assert s.paused_until is None and s.eating == "lunch"


def test_day_end_reminds_and_snoozes():
    s = make_scheduler(day_end_enabled=True, day_end_at=18 * 60)
    assert s.tick(1, now=at(17, 59)) == []
    assert s.tick(1, now=at(18)) == ["day_end"]
    assert s.tick(1, now=at(18, 1)) == []          # not shown twice while open
    s.day_end_answered("snooze", now=at(18, 1))
    assert s.tick(1, now=at(18, 20)) == []
    assert s.tick(1, now=at(18, 31)) == ["day_end"]
    s.day_end_answered("finish")
    assert s.tick(1, now=at(19)) == []             # already finished today


def test_day_end_waits_for_meal_and_skips_after_pause_until_morning():
    s = make_scheduler(day_end_enabled=True, day_end_at=18 * 60, dinner_enabled=True, dinner_at=18 * 60)
    assert s.tick(1, now=at(18)) == ["meal"]
    s.meal_answered("skip", now=at(18))
    assert s.tick(1, now=at(18, 1)) == ["day_end"]
    s = make_scheduler(day_end_enabled=True, day_end_at=18 * 60)
    s.pause(None, now=at(17, 59))                      # a fixed time: independent of the machine's clock
    assert s.tick(1, now=at(18)) == []


def test_each_state_freezes_what_the_table_says():
    s = make_scheduler(mini_interval_min=20, water_interval_min=60, warn_before_sec=0)
    assert s.state == core.WORKING and s.frozen() == frozenset()
    s.pause(30, now=at(10))
    assert s.state == core.PAUSED and s.frozen() == {core.BREAKS}
    s.tick(5 * 60, now=at(10, 1), idle=10 * 60)                 # walked away during the pause
    assert s.state == core.AWAY and s.mode == core.PAUSED       # the pause isn't lost
    assert s.frozen() == {core.BREAKS, core.WATER, core.CLOCK}
    assert s.tick(1, now=at(10, 40), idle=0) == ["back"]       # the pause ended meanwhile
    assert s.state == core.WORKING


def test_timed_pause_ends_by_itself():
    s = make_scheduler()
    s.pause(30, now=at(10))
    assert s.paused and s.paused_until == at(10, 30)
    s.tick(1, now=at(10, 30))
    assert not s.paused and s.mode == core.WORKING


def test_day_is_the_real_calendar_day():
    assert core.workday_date(at(0, 30)) == dt.date(2026, 10, 14)            # the day runs from 00:00 to 24:00
    assert core.work_started(at(3, 30), 0) is None                           # the day doesn't start at night
    assert core.work_started(at(4, 30), 0) == 4 * 60 + 30
    s = make_scheduler()
    s.pause(None, now=at(23))
    assert s.paused_until == at(6) + dt.timedelta(days=1)                   # "until morning" means until 06:00
    s = make_scheduler(lunch_enabled=True, workdays=[4])                     # Friday only
    assert s.reminders_today(dt.datetime(2026, 10, 16, 23, 0))
    assert not s.reminders_today(dt.datetime(2026, 10, 17, 1, 0))           # after midnight it's Saturday

def test_stats_are_written_to_the_calendar_day(monkeypatch, tmp_path):
    monkeypatch.setattr(core, "STATS_PATH", str(tmp_path / "stats.json"))
    stats = core.Stats(today=lambda: core.workday_date(at(0, 30)))
    stats.add("work_sec", 60)
    assert stats.day(dt.date(2026, 10, 14))["work_sec"] == 60 and stats.day(dt.date(2026, 10, 13))["work_sec"] == 0

def test_stats_are_stored_per_month_and_old_file_is_migrated(monkeypatch, tmp_path):
    path = tmp_path / "stats.json"
    monkeypatch.setattr(core, "STATS_PATH", str(path))
    old = {"2026-09-30": {"water": 5}, "2026-10-01": {"water": 7, "events": [{"type": "water", "at": 600}]}}
    path.write_text(json.dumps(old), encoding="utf-8")
    stats = core.Stats(today=lambda: dt.date(2026, 10, 14))
    assert stats.data == old                                                 # nothing lost
    assert sorted(p.name for p in (tmp_path / "stats").iterdir()) == ["2026-09.json", "2026-10.json"]
    assert not path.exists() and (tmp_path / "stats-before-2.16.json").exists()   # the old file is kept aside
    stats.add("water")                                                       # a write touches only its month
    september = (tmp_path / "stats" / "2026-09.json").read_text(encoding="utf-8")
    assert json.loads(september) == {"2026-09-30": {"water": 5}}
    again = core.Stats(today=lambda: dt.date(2026, 10, 14))
    assert again.day(dt.date(2026, 10, 14))["water"] == 1 and again.day(dt.date(2026, 9, 30))["water"] == 5


def test_day_end_is_asked_once_per_calendar_day():
    s = make_scheduler(day_end_enabled=True, day_end_at=18 * 60)
    assert s.tick(1, now=at(18)) == ["day_end"]
    s.day_end_answered("finish", now=at(18, 1))
    assert s.tick(1, now=at(0, 30) + dt.timedelta(days=1)) == []            # a new day, but not 18:00 yet
    assert s.tick(1, now=at(18) + dt.timedelta(days=1)) == ["day_end"]      # the next evening, again

def test_long_absence_counts_as_a_long_break():
    s = make_scheduler(long_every=3, long_duration_min=5, mini_interval_min=20)
    s.finish_break()
    assert s.breaks_until_long() == 2
    tick_at(s, at(10), 20, idle=6 * 60)                       # 6 min is an absence, but not a long break
    s.tick(1, now=at(10, 1), idle=0)
    assert s.breaks_until_long() == 2
    s.tick(1, now=at(11), idle=10 * 60)                      # 10 min = 2 × the long break
    assert s.tick(1, now=at(11, 1), idle=0) == ["back"]
    assert s.breaks_until_long() == 3 and s.next_kind() == "mini"


def test_skipped_long_break_comes_back_once():
    s = make_scheduler(long_every=2)
    s.finish_break()
    assert s.next_kind() == "long"
    s.finish_break(skipped=True)
    assert s.next_kind() == "long" and s.breaks_until_long() == 1   # a skipped long break comes once more
    s.finish_break(skipped=True)
    assert s.next_kind() == "mini"                                  # the second time the rhythm goes on
    s.finish_break()
    assert s.next_kind() == "long"
    s.finish_break(skipped=True)
    s.finish_break()                                                # the returned long break is done
    assert s.next_kind() == "mini" and s.breaks_until_long() == 2
    s.finish_break(skipped=True)                                    # a skipped mini break: nothing special
    assert s.next_kind() == "long"


def test_short_break_instead_of_long_keeps_the_long_one_next():
    s = make_scheduler(long_every=3)
    s.breaks_taken = 2
    assert s.next_kind() == "long"
    s.choose_kind("mini")
    assert s.next_kind() == "mini" and s.swapped and s.breaks_until_long() == 2
    s.finish_break()
    assert s.chosen is None and s.next_kind() == "long"            # the long break moved to the next one
    s.choose_kind("mini")
    s.finish_break(skipped=True)                                   # a skipped swap counts as the long one skipped
    assert s.next_kind() == "long" and s.long_skipped
    s.finish_break()
    assert s.next_kind() == "mini" and s.breaks_until_long() == 3


def test_long_break_instead_of_mini_starts_the_count_over():
    s = make_scheduler(long_every=3)
    s.finish_break()
    assert s.breaks_until_long() == 2
    s.choose_kind("long")
    assert s.next_kind() == "long" and s.breaks_until_long() == 1
    s.choose_kind("mini")                                          # changed the mind back: no choice left
    assert s.chosen is None and not s.swapped
    s.choose_kind("long")
    s.postpone()
    assert s.next_kind() == "long"                                 # the choice survives a postponement
    s.finish_break()
    assert s.next_kind() == "mini" and s.breaks_until_long() == 3   # a full cycle until the next long one
    s.choose_kind("long")
    s.finish_break(skipped=True)                                   # skipped: as a skipped mini break
    assert s.breaks_until_long() == 2


def test_break_kind_choice_is_dropped_after_an_absence_and_kept_after_a_restart():
    s = make_scheduler(long_every=3)
    s.choose_kind("long")
    restored = make_scheduler(long_every=3)
    assert restored.restore(s.snapshot(at(10)), at(10, 1)) and restored.next_kind() == "long"
    s.tick(1, now=at(10), idle=10 * 60)
    assert s.tick(1, now=at(10, 1), idle=0) == ["back"]
    assert s.chosen is None


def test_smart_water_pacing_follows_the_rest_of_the_day():
    s = make_scheduler(water_interval_min=60, water_goal=8)
    assert s.water_interval(at(10)) == 60 * 60                      # day end unknown: as in the settings
    s.update_day(drunk=4, workday_end=at(18))
    assert s.water_interval(at(10)) == 2 * 60 * 60                  # ahead: 8 h for 4 glasses
    s.update_day(drunk=4, workday_end=at(14))
    assert s.water_interval(at(10)) == 60 * 60                      # 4 h for 4 glasses
    s.update_day(drunk=1, workday_end=at(13))
    assert s.water_interval(at(10)) == 3 * 3600 // 7                 # behind: more often
    s.update_day(drunk=1, workday_end=at(11))
    assert s.water_interval(at(10)) == 15 * 60                     # behind: more often, but not more often than 15 min
    s.update_day(drunk=7, workday_end=at(18))
    s.water_answered(True, now=at(17))
    assert s.water_remaining == 60 * 60                             # the last glass is an hour before the end
    s.water_answered(False, now=at(17))
    assert s.water_remaining == 15 * 60                             # "Later" as before
    s.update_day(drunk=8, workday_end=at(18))
    assert s.water_done


def test_overwork_warns_once_a_day():
    s = make_scheduler(max_work_hours=9)
    s.update_day(drunk=0, worked=9 * 3600 - 1)
    assert s.tick(1, now=at(18)) == []
    s.update_day(drunk=0, worked=9 * 3600)
    assert s.tick(1, now=at(18, 1)) == ["overwork"]
    assert s.tick(1, now=at(18, 2)) == []                       # not shown twice while open
    s.overwork_answered("later", now=at(18, 2))
    assert s.tick(1, now=at(19)) == []                          # once a day
    assert s.tick(1, now=at(19) + dt.timedelta(days=1)) == ["overwork"]   # the next day (worked comes from App)
    # Pushed out by another notification before an answer: asked again later, not decided as "later"
    pushed = make_scheduler(max_work_hours=9)
    pushed.update_day(drunk=0, worked=9 * 3600)
    assert pushed.tick(1, now=at(18)) == ["overwork"]
    pushed.overwork_answered("snooze", now=at(18, 1))
    assert pushed.tick(1, now=at(18, 30)) == []
    assert pushed.tick(1, now=at(18, 31)) == ["overwork"]
    off = make_scheduler(max_work_hours=0)
    off.update_day(drunk=0, worked=20 * 3600)
    assert off.tick(1, now=at(20)) == []


def test_overwork_waits_for_the_day_end_reminder():
    s = make_scheduler(max_work_hours=9, day_end_enabled=True, day_end_at=18 * 60)
    s.update_day(drunk=0, worked=10 * 3600)
    assert s.tick(1, now=at(18)) == ["day_end"]
    assert s.tick(1, now=at(18, 1)) == []
    s.day_end_answered("snooze", now=at(18, 1))
    assert s.tick(1, now=at(18, 2)) == ["overwork"]


def test_busy_holds_the_break_for_at_most_half_an_hour():
    s = make_scheduler(mini_interval_min=1, warn_before_sec=10)
    assert tick_at(s, at(10), 49) == []
    assert tick_at(s, at(10, 0, 49), 10 * 60, busy=True) == ["break_held"]   # neither a warning nor a break
    assert s.remaining == 0 and not s.in_break
    assert s.tick(1, now=at(10, 11), busy=False) == ["break"]               # the call ended
    s.finish_break()
    events = tick_at(s, at(11), 40 * 60, busy=True)
    assert events == ["break_held", "break"] and s.in_break                  # but no longer than 30 min


def test_busy_does_not_hold_water():
    s = make_scheduler(water_interval_min=15, mini_interval_min=60)
    assert tick_at(s, at(10), 15 * 60, busy=True) == ["water"]


def test_state_survives_a_restart():
    cfg = dict(lunch_enabled=True, lunch_at=13 * 60, long_every=3, mini_interval_min=20, water_interval_min=60)
    s = make_scheduler(**cfg)
    s.finish_break()
    s.postpone()
    tick_at(s, at(12, 59), 2 * 60)
    s.meal_answered("snooze", now=at(13, 1))
    s.update_day(drunk=0)
    snap = json.loads(json.dumps(s.snapshot(at(13, 2))))   # JSON types only
    restored = make_scheduler(**cfg)
    assert restored.restore(snap, at(13, 3))
    assert (restored.breaks_taken, restored.postpones, restored.remaining, restored.water_remaining) == (
        1, 1, s.remaining, s.water_remaining)
    assert restored.meal_state("lunch", at(13, 3)) == ("snoozed", at(13, 16))
    assert restored.tick(1, now=at(13, 16)) == ["meal"]


def test_restored_modes_keep_their_deadlines():
    s = make_scheduler(lunch_enabled=True, lunch_at=13 * 60, meal_pause_min=30)
    s.tick(1, now=at(13))
    s.meal_answered("eat", now=at(13))
    restored = make_scheduler(lunch_enabled=True, lunch_at=13 * 60, meal_pause_min=30)
    assert restored.restore(s.snapshot(at(13, 10)), at(13, 11))
    assert restored.eating == "lunch" and restored.eating_until == at(13, 30)
    assert restored.tick(1, now=at(13, 30)) == ["meal_over"]
    s = make_scheduler(day_end_enabled=True, day_end_at=18 * 60)
    s.pause(None, now=at(18))
    restored = make_scheduler(day_end_enabled=True, day_end_at=18 * 60)
    assert restored.restore(s.snapshot(at(18)), at(18, 1))
    assert restored.pause_water and restored.day_finished(at(19)) and restored.paused_until == s.paused_until


def test_open_reminders_and_breaks_come_back_after_a_restart():
    s = make_scheduler(mini_interval_min=1, warn_before_sec=0, lunch_enabled=True, lunch_at=13 * 60)
    tick_at(s, at(12, 59, 30), 60)
    assert s.in_break and s.meal_open == "lunch"
    restored = make_scheduler(mini_interval_min=1, warn_before_sec=0, lunch_enabled=True, lunch_at=13 * 60)
    assert restored.restore(s.snapshot(at(13)), at(13))
    assert not restored.in_break and restored.remaining == core.BREAK_RESUME_SEC   # the break comes in a minute
    assert restored.tick(1, now=at(13, 1)) == ["meal"]                            # the window is gone


def test_old_or_foreign_state_is_not_restored():
    s = make_scheduler()
    s.finish_break()
    snap = s.snapshot(at(10))
    assert not make_scheduler().restore(snap, at(10) + dt.timedelta(days=1))   # another workday
    assert not make_scheduler().restore(snap, at(10) - dt.timedelta(hours=1))   # from the future
    late = core.Scheduler.snapshot(s, at(4, 30))
    assert not make_scheduler().restore(late, at(4, 30) + dt.timedelta(hours=13))   # older than 12 h
    for broken in ({}, {"version": 1}, dict(snap, mode="dancing"), dict(snap, remaining="x"), None):
        assert not make_scheduler().restore(broken, at(10, 5))


def test_long_gap_since_the_saved_state_is_an_absence():
    s = make_scheduler(long_every=3, long_duration_min=5, mini_interval_min=20)
    s.finish_break()
    tick(s, 15 * 60)
    restored = make_scheduler(long_every=3, long_duration_min=5, mini_interval_min=20)
    assert restored.restore(s.snapshot(at(10, 15)), at(12))       # the computer was off for almost 2 h
    assert restored.remaining == 20 * 60 and restored.breaks_until_long() == 3


def test_restore_day_from_stats():
    s = make_scheduler(lunch_enabled=True, lunch_at=13 * 60, day_end_enabled=True, day_end_at=18 * 60)
    s.restore_day(at(10).date(), eaten=["lunch"], finished_minute=17 * 60 + 30)   # the day was finished at 17:30
    assert s.finished_at == at(17, 30)
    assert s.meal_state("lunch", at(13)) == ("eat", None)
    assert s.tick(1, now=at(13)) == [] and "day_end" not in s.tick(1, now=at(18))   # not asked twice


def test_slider_zero_positions():
    assert core.slider_position("workday_start", 0) == core.SLIDER_ZERO["workday_start"]
    assert core.slider_position("workday_start", 8 * 60) == 8 * 60
    assert core.setting_value("max_work_hours", core.SLIDER_ZERO["max_work_hours"]) == 0
    assert core.setting_value("max_work_hours", 9) == 9
    for key, position in core.SLIDER_ZERO.items():
        assert core.SLIDERS[key][0] == position
    _lo, _hi, _step, fmt = core.SLIDERS["max_work_hours"]
    assert (fmt(5), fmt(9)) == ("вимкнено", "9 год")


def test_split_balanced_keeps_order_and_evens_columns():
    heights = [275, 212, 310, 330, 390, 130, 125, 150, 150]
    for columns in (2, 3, 4):
        groups = core.split_balanced(heights, columns)
        assert len(groups) == columns
        assert [i for g in groups for i in g] == list(range(len(heights)))   # the card order doesn't change
    groups = core.split_balanced(heights, 4)
    tallest = max(sum(heights[i] for i in g) + 14 * (len(g) - 1) for g in groups)
    assert tallest == 310 + 330 + 14                                          # the best possible: "pause + water"
    assert core.split_balanced([100, 100], 3) == [[0], [1]]               # no more columns than cards


def test_split_orders_picks_the_evener_of_the_allowed_orders():
    heights = [277, 213, 313, 151, 317, 313, 330, 162]                      # the real settings cards
    sound_last = (0, 1, 2, 4, 5, 6, 3, 7)
    groups = core.split_orders(heights, [range(8), sound_last], 3)
    assert [i for g in groups for i in g] == list(sound_last)              # Sound isn't left alone in a column
    assert core.split_orders(heights, [range(8)], 4) == core.split_balanced(heights, 4)


def test_main_layout_follows_screen_width():
    assert core.main_layout(2520)["columns"] == 4
    assert core.main_layout(1240)["columns"] == 3
    assert core.main_layout(984) == {"columns": 2, "stat_cards": 3, "width": 900}


def test_completion_rate():
    rec = {"mini_done": 6, "long_done": 2, "skipped": 2}
    assert core.completion_rate(rec) == 80
    assert core.completion_rate({"mini_done": 0, "long_done": 0, "skipped": 0}) is None


def test_water_streak_counts_from_yesterday_until_goal_is_met_today():
    stats = core.Stats.__new__(core.Stats)
    today = dt.date(2026, 10, 14)
    water = {12: 8, 13: 9, 11: 3}   # the goal wasn't met on the 11th: the streak breaks
    stats.data = {dt.date(2026, 10, d).isoformat(): {"water": n} for d, n in water.items()}
    assert core.water_streak(stats, 8, today) == 2          # nothing drunk today yet: count from yesterday
    stats.data[today.isoformat()] = {"water": 8}
    assert core.water_streak(stats, 8, today) == 3


def test_day_minute_runs_past_midnight_and_clock_wraps():
    day = dt.date(2026, 10, 14)
    assert core.day_minute(day, at(13, 45)) == 13 * 60 + 45
    assert core.day_minute(day, at(0, 30) + dt.timedelta(days=1)) == 24 * 60 + 30   # still the same workday
    assert i18n.fmt_clock(24 * 60 + 30) == "00:30"


def make_stats(monkeypatch, tmp_path, day=dt.date(2026, 10, 14)):
    monkeypatch.setattr(core, "STATS_PATH", str(tmp_path / "stats.json"))
    return core.Stats(today=lambda: day)


def test_event_log_appends_replaces_closes_and_removes(monkeypatch, tmp_path):
    stats = make_stats(monkeypatch, tmp_path)
    day = dt.date(2026, 10, 14)
    stats.log("day_start", 8 * 60 + 40, replace=())
    stats.log("water", 9 * 60)
    stats.log("water", 9 * 60)                                   # two glasses, two events
    stats.log("meal", 13 * 60, replace=("meal",), meal="lunch")
    stats.log("meal", 13 * 60 + 10, replace=("meal",), meal="lunch")   # the same lunch: replaced
    stats.log("day_end", 18 * 60, replace=())
    stats.log("day_end", 18 * 60 + 20, replace=())               # keeps working: the day end moves
    pause = stats.log("pause", 15 * 60, to=None, kind="timed")
    assert stats.open_spans([day]) == [(day, pause, {"type": "pause", "at": 15 * 60, "to": None, "kind": "timed"})]
    stats.close(day, pause, 15 * 60 + 30)
    stats.close(day, pause, 16 * 60)                             # a closed span isn't rewritten
    stats.unlog("meal", meal="lunch")
    events = core.Stats(today=lambda: day).events(day)           # everything is written to disk
    assert [e["type"] for e in events] == ["day_start", "water", "water", "day_end", "pause"]
    assert events[3]["at"] == 18 * 60 + 20 and events[4]["to"] == 15 * 60 + 30
    assert stats.open_spans([day]) == [] and stats.dates() == [day]
    assert stats.day(day)["water"] == 0                          # the log doesn't touch counters


def test_open_spans_last_until_now_or_the_last_event():
    events = [{"type": "day_start", "at": 540}, {"type": "pause", "at": 600, "to": None, "kind": "timed"},
              {"type": "water", "at": 700}]
    assert core.event_spans(events, now=650)[0][1:3] == (600, 650)
    assert core.event_spans(events)[0][1:3] == (600, 700)        # a past day: until the last event
    assert core.day_bounds(events, now=800) == (540, 800)


def test_regularity_from_the_event_log():
    events = [
        {"type": "day_start", "at": 9 * 60},
        {"type": "break", "at": 9 * 60 + 20, "kind": "mini", "result": "done", "sec": 30},
        {"type": "break", "at": 9 * 60 + 40, "kind": "mini", "result": "postponed", "sec": 0},
        {"type": "break", "at": 9 * 60 + 45, "kind": "long", "result": "done", "sec": 300},  # after postponing
        {"type": "break", "at": 10 * 60 + 10, "kind": "mini", "result": "skipped", "sec": 5},
        {"type": "away", "at": 11 * 60, "to": 11 * 60 + 30},
        {"type": "held", "at": 12 * 60, "to": 12 * 60 + 10, "reason": "camera"},
        {"type": "pause", "at": 13 * 60, "to": 13 * 60 + 40, "kind": "eating", "meal": "lunch"},
        {"type": "day_end", "at": 17 * 60},
    ]
    reg = core.regularity(events)
    assert (reg["on_time"], reg["late"], reg["skipped"], reg["postponed"]) == (1, 1, 1, 1)
    assert (reg["away"], reg["away_min"], reg["held"]) == (1, 30, 1)
    assert reg["longest_min"] == 17 * 60 - (13 * 60 + 40)       # after lunch until the day end without a break
    assert core.regularity([]) is None


def test_longest_work_stretch():
    assert core.longest_work_stretch((540, 600), []) == 60
    assert core.longest_work_stretch((540, 720), [(560, 570), (600, 700)]) == 30
    assert core.longest_work_stretch(None, []) == 0


def test_absence_is_logged_only_after_the_day_started():
    day = dt.date(2026, 10, 14)
    assert core.absence_span(day, at(10, 40), 35 * 60, day_start=9 * 60) == (10 * 60 + 5, 10 * 60 + 40)
    assert core.absence_span(day, at(9, 10), 3 * 3600, day_start=9 * 60) == (9 * 60, 9 * 60 + 10)  # from the day start
    assert core.absence_span(day, at(9, 10), 3 * 3600, day_start=0) is None    # still morning: not an absence


def test_scheduler_remembers_how_long_the_absence_was():
    s = make_scheduler(long_duration_min=5)
    s.tick(1, now=at(11), idle=10 * 60)
    assert s.tick(1, now=at(11, 1), idle=0) == ["back"]
    assert s.last_away == 10 * 60


def test_export_csv_writes_days_and_events(monkeypatch, tmp_path):
    import csv
    stats = make_stats(monkeypatch, tmp_path)
    stats.add("mini_done")
    stats.set("day_start", 9 * 60)
    stats.log("break", 9 * 60 + 20, kind="mini", result="done", sec=30)
    stats.log("away", 10 * 60, to=10 * 60 + 15)
    stats.data["2026-10-13"] = {"water": 5}                      # an old day without a log
    days, events = core.export_csv(stats, str(tmp_path / "out.csv"))
    assert events.endswith("out-events.csv")
    with open(days, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert [r["date"] for r in rows] == ["2026-10-13", "2026-10-14"]
    assert rows[0]["water"] == "5" and rows[0]["away_count"] == ""
    assert rows[1]["mini_done"] == "1" and rows[1]["day_start"] == "09:00" and rows[1]["away_min"] == "15"
    with open(events, encoding="utf-8-sig", newline="") as f:
        logged = list(csv.DictReader(f))
    assert [(r["time"], r["type"], r["until"]) for r in logged] == [("09:20", "break", ""), ("10:00", "away", "10:15")]


def test_fmt_hm_and_days():
    assert core.fmt_hm(6 * 3600 + 5 * 60 + 59) == "6:05"
    assert [i18n.fmt_days(n) for n in (1, 3, 5, 21)] == ["1 день", "3 дні", "5 днів", "21 день"]


def test_meal_state_follows_the_day():
    s = make_scheduler(lunch_enabled=True, lunch_at=13 * 60, meal_pause_min=30)
    assert s.meal_state("lunch", at(12)) == ("upcoming", at(13))
    s.tick(1, now=at(13))
    assert s.meal_state("lunch", at(13)) == ("open", None)
    s.meal_answered("snooze", now=at(13))
    assert s.meal_state("lunch", at(13, 5)) == ("snoozed", at(13, 15))
    s.tick(1, now=at(13, 15))
    assert s.meal_state("lunch", at(13, 15)) == ("open", at(13, 15))      # snoozed: it stays at the new time
    s.meal_answered("eat", now=at(13, 15))
    assert s.meal_state("lunch", at(13, 20)) == ("eating", at(13, 45))
    s.finish_meal()
    assert s.meal_state("lunch", at(14)) == ("eat", None)
    assert make_scheduler(lunch_at=13 * 60).meal_state("lunch", at(15)) == ("missed", at(13))


def test_next_meal_and_marking_a_meal_eaten_in_advance():
    s = make_scheduler(breakfast_enabled=True, breakfast_at=8 * 60, lunch_enabled=True, lunch_at=13 * 60)
    assert s.next_meal(at(7)) == ("breakfast", at(8))
    assert s.next_meal(at(8, 10)) == ("breakfast", None)       # breakfast time is now
    s.mark_meal("breakfast", True, now=at(8, 5))              # the plate was marked on Status
    assert s.tick(1, now=at(8, 10)) == []                      # no reminder
    assert s.next_meal(at(8, 10)) == ("lunch", at(13))
    assert s.next_meal(at(15)) is None                         # lunch is over: done for today


def test_breaks_until_long():
    s = make_scheduler(long_every=3)
    assert s.breaks_until_long() == 3
    s.breaks_taken = 2
    assert s.breaks_until_long() == 1 and s.next_kind() == "long"


def test_fmt_after_minis():
    assert [i18n.fmt_after_minis(n) for n in (1, 2, 5, 11, 21)] == [
        "після 1 міні-перерви", "після 2 міні-перерв", "після 5 міні-перерв",
        "після 11 міні-перерв", "після 21 міні-перерви"]


def test_pause_until_morning_after_midnight_ends_the_same_morning():
    s = make_scheduler()
    s.pause(None, now=at(0, 30))
    assert s.paused_until == at(6)                       # at 06:00 the same day, not tomorrow
    s.pause(None, now=at(19))
    assert s.paused_until == at(6) + dt.timedelta(days=1)


def test_snoozes_do_not_carry_over_to_the_next_day():
    s = make_scheduler(day_end_enabled=True, day_end_at=18 * 60, lunch_enabled=True, lunch_at=13 * 60)
    late = at(23, 50)
    assert s.tick(1, now=late) == ["day_end"]
    s.day_end_answered("snooze", now=late)              # remind at 00:20, already the next day
    after_midnight = late + dt.timedelta(minutes=30)
    assert s.tick(1, now=after_midnight) == ["day_end"]  # still working: remind, even though it's a new day
    s.day_end_answered("snooze", now=after_midnight)
    # The computer slept and woke up in the morning: yesterday's "30 more min" is pointless
    assert s.tick(1, now=at(9) + dt.timedelta(days=1)) == []
    assert s.tick(1, now=at(18) + dt.timedelta(days=1)) == ["day_end"]   # but its own reminder comes
    s.tick(1, now=at(13))
    s.meal_answered("snooze", now=at(13))
    assert s.tick(1, now=at(13, 20) + dt.timedelta(days=1)) == ["meal"]   # only its own, at 13:00+ the next day
    assert s.meal_snoozed == {}


def test_pause_until_morning_cancels_pending_reminders():
    s = make_scheduler(day_end_enabled=True, day_end_at=18 * 60, lunch_enabled=True, lunch_at=13 * 60)
    s.tick(1, now=at(13))
    s.meal_answered("snooze", now=at(13))
    s.pause(None, now=at(13, 5))
    assert s.meal_snoozed == {} and not s.day_end_open
    s.resume(now=at(13, 6))                              # "Continue": the day goes on
    assert s.tick(1, now=at(13, 20)) == []              # the snoozed lunch doesn't come back
    assert s.tick(1, now=at(18)) == ["day_end"]         # and at its time the person decides about the day


def test_work_started_needs_recent_input_and_morning():
    assert core.work_started(at(8, 42, 30), 20) == 8 * 60 + 42          # the last input was at 8:42
    assert core.work_started(at(8, 42), 5 * 60) is None                  # the person has been away for 5 min
    assert core.work_started(at(3, 30), 0) is None                       # still night
    assert core.work_started(at(4, 0, 30), 45) is None                   # the input was before 4:00


def test_average_minute_skips_days_without_data():
    assert core.average_minute([8 * 60, 0, 9 * 60]) == 8 * 60 + 30
    assert core.average_minute([0, 0]) is None


def test_being_away_is_a_natural_break():
    s = make_scheduler(mini_interval_min=20, long_duration_min=5, water_interval_min=60, warn_before_sec=0)
    tick_at(s, at(10), 15 * 60)                              # 15 min of work
    remaining, water = s.remaining, s.water_remaining
    events = []
    for i in range(30 * 60):                                 # half an hour without mouse and keyboard
        events += s.tick(1, now=at(10, 15) + dt.timedelta(seconds=i), idle=5 * 60 + i)
    assert events == [] and s.away
    assert (s.remaining, s.water_remaining) == (remaining, water)   # the timers stood
    assert s.tick(1, now=at(10, 46), idle=0) == ["back"]
    assert s.remaining == 20 * 60 - 1                        # back: 20 min to the break again
    assert not s.away


def test_short_idle_is_not_away():
    s = make_scheduler(mini_interval_min=20, long_duration_min=5)
    s.tick(60, now=at(10), idle=4 * 60)                      # reading without the mouse for 4 min is still work
    assert not s.away and s.remaining == 19 * 60


def test_no_water_reminders_after_the_goal_is_reached():
    s = make_scheduler(water_interval_min=15, mini_interval_min=60, warn_before_sec=0)
    s.water_done = True
    assert tick_at(s, at(10), 20 * 60) == []
    assert s.water_remaining == 15 * 60


def test_workdays_only_silences_meals_and_day_end_at_the_weekend():
    saturday = dt.datetime(2026, 10, 17, 13, 0)
    s = make_scheduler(lunch_enabled=True, lunch_at=13 * 60, day_end_enabled=True, day_end_at=18 * 60,
                       workdays=[0, 1, 2, 3, 4])
    assert s.tick(1, now=saturday) == [] and s.next_meal(saturday) is None
    assert s.tick(1, now=saturday.replace(hour=18)) == []
    s = make_scheduler(lunch_enabled=True, lunch_at=13 * 60, workdays=list(range(7)))
    assert s.tick(1, now=saturday) == ["meal"]
    s = make_scheduler(lunch_enabled=True, lunch_at=13 * 60, workdays=[5, 6])   # works on weekends only
    assert s.tick(1, now=at(13)) == [] and s.tick(1, now=saturday) == ["meal"]


def test_old_workdays_only_setting_migrates_to_a_list_of_days():
    assert core.migrate_config({"workdays_only": False})["workdays"] == list(range(7))
    assert "workdays" not in core.migrate_config({"workdays_only": True})    # weekdays are the default anyway
    assert core.migrate_config({"workdays_only": False, "workdays": [2, 0, 0]})["workdays"] == [0, 2]
    assert core.migrate_config({"workdays": "пн"})["workdays"] == core.DEFAULTS["workdays"]


def test_finished_day_never_goes_on_by_itself_but_asks_once():
    s = make_scheduler(day_end_enabled=True, day_end_at=18 * 60)
    assert s.tick(1, now=at(18)) == ["day_end"]
    s.day_end_answered("finish", now=at(18, 1))
    s.pause(None, now=at(18, 1))
    assert s.paused_until is not None and s.day_finished(at(18, 2))
    assert s.tick(1, now=at(18, 2), idle=0) == []            # just pressed: not "keeps working" yet
    assert s.tick(1, now=at(18, 4), idle=0) == []            # 2 min at the computer is not enough
    assert s.tick(1, now=at(18, 5), idle=0) == ["ask_continue"]
    assert s.day_finished(at(18, 5)) and s.paused_until is not None   # only asked: the day is still finished
    assert tick_at(s, at(18, 5), 60 * 60) == []               # the window waits; not asked twice
    assert s.continue_answered("continue", now=at(19, 10)) is True
    assert not s.day_finished(at(19, 10)) and s.paused_until is None
    assert s.tick(1, now=at(19, 11), idle=0) == []           # day end isn't asked anymore


def test_no_to_still_working_keeps_the_day_finished_until_morning():
    s = make_scheduler()
    s.pause(None, now=at(18))
    s.tick(1, now=at(20), idle=0)
    assert s.tick(1, now=at(20, 3), idle=0) == ["ask_continue"]
    assert s.continue_answered("no", now=at(20, 4)) is False
    assert tick_at(s, at(20, 4), 2 * 60 * 60) == [] and s.day_finished(at(22, 5))   # a whole evening, no more asking
    restored = make_scheduler()
    assert restored.restore(s.snapshot(at(22, 5)), at(22, 6)) and restored.continue_asked == "no"
    s.resume(now=at(22, 10))
    s.pause(None, now=at(22, 20))                              # finished again: may ask again
    s.tick(1, now=at(22, 21), idle=0)
    assert s.tick(1, now=at(22, 24), idle=0) == ["ask_continue"]


def test_still_working_pushed_out_asks_again_later():
    s = make_scheduler()
    s.pause(None, now=at(18))
    s.tick(1, now=at(20), idle=0)
    assert s.tick(1, now=at(20, 3), idle=0) == ["ask_continue"]
    s.continue_answered("snooze", now=at(20, 4))
    s.tick(1, now=at(20, 4), idle=0)
    assert s.tick(1, now=at(20, 7), idle=0) == ["ask_continue"]


def test_continue_after_finishing_the_day_continues_it_right_away():
    s = make_scheduler(day_end_enabled=True, day_end_at=18 * 60)
    s.pause(None, now=at(17))                                 # "Finish the day" from the tray
    assert s.day_finished(at(17, 1))
    assert s.resume(now=at(17, 1)) is True                    # "Continue" under the timer
    assert not s.day_finished(at(17, 1)) and s.paused_until is None
    assert "ask_continue" not in s.tick(1, now=at(17, 5), idle=0)    # nothing left to ask the person
    assert s.resume(now=at(17, 6)) is False                   # not paused: nothing to continue
    s.pause(30, now=at(17, 10))
    assert s.resume(now=at(17, 11)) is False and not s.day_finished(at(17, 11))  # a timed pause keeps the day
    assert s.tick(1, now=at(18), idle=0) == ["day_end"]       # finished early, continued: asked at its time


def test_continue_after_the_day_end_time_does_not_ask_again_at_once():
    s = make_scheduler(day_end_enabled=True, day_end_at=18 * 60)
    s.pause(None, now=at(18, 30))
    assert s.resume(now=at(18, 40)) is True and not s.day_finished(at(18, 40))
    assert s.tick(1, now=at(18, 41), idle=0) == []            # the person just said "continue"


def test_a_quick_look_after_finishing_does_not_ask():
    s = make_scheduler()
    s.pause(None, now=at(18))
    s.tick(1, now=at(20), idle=0)                             # glanced at mail
    s.tick(1, now=at(20, 1), idle=0)
    assert s.tick(1, now=at(20, 2), idle=5 * 60) == []        # and left
    assert "ask_continue" not in s.tick(1, now=at(21), idle=0) and s.day_finished(at(21))
    assert s.tick(1, now=at(21, 3), idle=0) == ["ask_continue"]   # and now uses the computer for a while


def test_restored_finished_day_stays_finished_and_asks():
    s = make_scheduler()
    s.restore_day(at(10).date(), finished_minute=18 * 60, now=at(20))   # after a restart: "finished at 18:00"
    assert s.day_finished(at(20)) and s.mode == core.FINISHED and s.paused_until == at(6) + dt.timedelta(days=1)
    s.tick(1, now=at(20), idle=0)
    assert s.tick(1, now=at(20, 3), idle=0) == ["ask_continue"] and s.day_finished(at(20, 3))


def test_day_start_is_the_earliest_known_activity():
    stats = core.Stats.__new__(core.Stats)
    stats.data = {"2026-10-14": {"day_start": 18 * 60 + 42, "water_at": [16 * 60 + 15, 18 * 60],
                                 "ate_dinner_at": [17 * 60], "events": [{"type": "break", "at": 3 * 60}]}}
    assert stats.day(dt.date(2026, 10, 14))["day_start"] == 16 * 60 + 15   # 03:00 is night, not counted


def test_water_interval_follows_the_actual_workday():
    assert core.workday_span(8 * 60 + 30, 18 * 60) == (8 * 60 + 30, 18 * 60)
    assert core.workday_span(9 * 60, None) == (9 * 60, 17 * 60)            # day end off: 8 h
    assert core.workday_span(9 * 60, 10 * 60) == (9 * 60, 13 * 60)         # no shorter than 4 h
    assert core.water_interval_for(8, 9 * 60 + 30) == 70                   # 9.5 h for 8 glasses
    cfg = dict(core.DEFAULTS, water_profile="male")
    core.apply_water_profile(cfg, workday=10 * 60)
    assert (cfg["water_goal"], cfg["water_interval_min"]) == (8, 75)


def test_current_stretch_counts_from_the_last_rest():
    events = [{"type": "day_start", "at": 8 * 60},
              {"type": "break", "at": 10 * 60, "kind": "mini", "result": "done", "sec": 30},
              {"type": "away", "at": 11 * 60, "to": 11 * 60 + 20},
              {"type": "break", "at": 12 * 60, "kind": "mini", "result": "skipped"}]
    assert core.current_stretch(events, 9 * 60) == 60                    # since the day start
    assert core.current_stretch(events, 10 * 60 + 30) == 29             # since the end of the break (10:01)
    assert core.current_stretch(events, 12 * 60 + 30) == 70             # a skipped break isn't rest
    assert core.current_stretch([], 9 * 60) == 0


def test_settings_file_keeps_the_persons_own_water_values(monkeypatch, tmp_path):
    """The Male norm computes the goal and interval, but the settings file keeps the person's own values."""
    path = tmp_path / "config.json"
    monkeypatch.setattr(core, "CONFIG_PATH", str(path))
    cfg = dict(core.DEFAULTS, water_profile="custom", water_goal=12, water_interval_min=40)
    core.save_config(cfg)
    cfg["water_profile"] = "male"
    core.apply_water_profile(cfg, workday=10 * 60)
    assert (cfg["water_goal"], cfg["water_interval_min"]) == (8, 75)         # at runtime, from the norm
    core.save_config(cfg)
    saved = core.load_json(str(path), {})
    assert (saved["water_goal"], saved["water_interval_min"]) == (12, 40)    # the file keeps the own values
    cfg["water_profile"] = "custom"
    core.restore_manual_water(cfg)
    assert (cfg["water_goal"], cfg["water_interval_min"]) == (12, 40)        # Custom brings them back


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
    steps = core.build_workout(minutes * 60, level)
    assert sum(step["secs"] for step in steps) == minutes * 60
    assert steps[0]["kind"] == "warmup" and steps[-1]["kind"] == "cooldown"


def test_long_break_without_workout_is_single_step():
    cfg = dict(core.DEFAULTS, workout_enabled=False)
    assert [s["kind"] for s in core.build_break("long", cfg)] == ["list"]


@pytest.mark.parametrize("value, text", [(1, "1 раз"), (2, "2 рази"), (5, "5 разів"), (0, "жодного")])
def test_fmt_times(value, text):
    assert core.fmt_times(value) == text


@pytest.mark.parametrize("value, text", [(1, "1 склянка (≈0,25 л)"), (4, "4 склянки (≈1 л)"), (8, "8 склянок (≈2 л)")])
def test_fmt_glasses(value, text):
    assert core.fmt_glasses(value) == text


def test_both_languages_have_the_same_strings():
    assert set(i18n.STRINGS["uk"]) == set(i18n.STRINGS["en"])
    assert len(i18n.t("weekdays").split()) == 7
    i18n.set_language("en")
    assert len(i18n.t("weekdays").split()) == 7


def test_separators_are_consistent():
    """One separator in every line: "  •  " (two spaces on each side); the old "·" is gone."""
    import re
    for lang in i18n.LANGUAGES:
        for key, text in i18n.STRINGS[lang].items():
            assert "·" not in text, (lang, key)
            assert not re.search(r"(?<!  )•|•(?!  )", text), (lang, key, text)


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
    steps = core.build_workout(300, 2)
    first_work = next(i for i, s in enumerate(steps) if s["kind"] == "work")
    before = steps[first_work]["title"]
    start = first_work + 1
    core.regroup_workout(steps, start, 2, "legs")
    legs = {title for title, _, _ in exercises.workout_pool(2, "legs")}
    assert steps[first_work]["title"] == before
    assert all(s["title"] in legs for s in steps[start:] if s["kind"] == "work")
    for i, s in enumerate(steps):
        if s["kind"] == "rest":
            following = next(n for n in steps[i + 1:] if n["kind"] == "work")
            assert following["title"] in s["text"]


def test_single_step_for_group_avoids_current_exercise():
    cfg = dict(core.DEFAULTS)
    current = core.single_break_step("mini", cfg, "eyes")["title"]
    for _ in range(20):
        assert core.single_break_step("mini", cfg, "eyes", avoid=current)["title"] != current


@pytest.mark.parametrize("profile, goal, interval", [("female", 7, 65), ("male", 8, 60)])
def test_water_profile_sets_goal_and_reachable_interval(profile, goal, interval):
    cfg = dict(core.DEFAULTS, water_profile=profile, water_goal=12, water_interval_min=180)
    core.apply_water_profile(cfg)
    assert (cfg["water_goal"], cfg["water_interval_min"]) == (goal, interval)
    assert goal * interval <= core.WORKDAY_MIN  # the goal fits into the workday


def test_custom_or_unknown_water_profile_keeps_manual_values():
    for profile in ("custom", "child"):
        cfg = dict(core.DEFAULTS, water_profile=profile, water_goal=12, water_interval_min=180)
        core.apply_water_profile(cfg)
        assert (cfg["water_profile"], cfg["water_goal"], cfg["water_interval_min"]) == ("custom", 12, 180)


def test_water_interval_stays_within_slider_range():
    lo, hi, _step, _fmt = core.SLIDERS["water_interval_min"]
    for goal in range(1, 40):
        assert lo <= core.water_interval_for(goal) <= hi


def test_every_slider_has_a_label_in_both_languages():
    for lang in i18n.LANGUAGES:
        i18n.set_language(lang)
        for key in core.SLIDERS:
            assert i18n.t(f"s_{key}")


@pytest.mark.parametrize("fmt, value, text", [
    (core.fmt_times, 1, "1 time"), (core.fmt_times, 3, "3 times"), (core.fmt_times, 0, "none"),
    (core.fmt_glasses, 1, "1 glass (≈0.25 L)"), (core.fmt_glasses, 8, "8 glasses (≈2 L)"),
    (core.fmt_minutes, 90, "1 h 30 min"), (core.fmt_seconds, 75, "1 min 15 s"), (core.fmt_warn, 0, "off"),
])
def test_english_formatting(fmt, value, text):
    i18n.set_language("en")
    assert fmt(value) == text


def test_workout_is_built_in_the_current_language():
    i18n.set_language("en")
    steps = core.build_workout(300, 2)
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


def test_unknown_language_falls_back_to_english():
    i18n.set_language("de")
    assert i18n.get_language() == "en"
