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
    # Їжа й кінець дня прив'язані до годинника — у тестах вимкнені, якщо їх не ввімкнути явно
    meals_off = {f"{meal}_enabled": False for meal in core.MEALS}
    # Тестова дата — середа; «лише в робочі дні» перевіряємо окремо
    return core.Scheduler({**core.DEFAULTS, **meals_off, "day_end_enabled": False, **overrides})


def at(hour, minute=0, second=0):
    """Мить тестового дня — середи 14.10.2026: тести не залежать від годинника машини."""
    return dt.datetime(2026, 10, 14, hour, minute, second)


def tick_at(s, start, seconds, **kwargs):
    """Тікає по секунді, рухаючи й годинник."""
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
    assert events == ["water"]          # вода нагадала, хоча перерви на паузі
    assert s.remaining == 60            # відлік до перерви стоїть


def test_pause_until_morning_stops_water_too():
    s = make_scheduler(mini_interval_min=1, water_interval_min=5, warn_before_sec=0)
    s.pause(None, now=at(10))
    # Людина не працює далі (інакше день продовжився б), але й не пішла — лише читає без миші
    assert tick_at(s, at(10), 10 * 60, idle=2 * 60) == []
    assert s.water_remaining == 5 * 60
    s.resume()
    assert tick(s, 60, start=at(10, 10)) == ["break"]     # після «Продовжити» все знову рахується


def test_lunch_reminds_once_at_its_time():
    s = make_scheduler(lunch_enabled=True, lunch_at=13 * 60)
    assert s.tick(1, now=at(12, 59)) == []
    assert s.tick(1, now=at(13, 0)) == ["meal"] and s.meal_open == "lunch"
    s.meal_answered("skip", now=at(13, 1))
    assert s.tick(1, now=at(13, 2)) == []   # сьогодні вже нагадали


def test_meal_is_not_shown_long_after_its_time():
    s = make_scheduler(lunch_enabled=True, lunch_at=13 * 60)
    assert s.tick(1, now=at(14, 5)) == []   # комп'ютер прокинувся через годину з лишком


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


def test_eating_freezes_timers_and_asks_to_continue():
    s = make_scheduler(lunch_enabled=True, lunch_at=13 * 60, meal_pause_min=30, mini_interval_min=20,
                       water_interval_min=60, warn_before_sec=0)
    s.tick(1, now=at(13))
    remaining, water = s.remaining, s.water_remaining
    s.meal_answered("eat", now=at(13))
    assert tick_at(s, at(13), 29 * 60) == []
    assert (s.remaining, s.water_remaining) == (remaining, water)   # перерви й вода заморожені
    assert tick_at(s, at(13, 30), 10 * 60) == ["meal_over"]         # питаємо один раз і чекаємо відповіді
    assert s.eating == "lunch"
    s.extend_meal(now=at(13, 40))
    assert tick_at(s, at(13, 40), 15 * 60 + 1) == ["meal_over"]
    s.finish_meal()
    assert not s.eating and s.remaining == 20 * 60 and s.water_remaining == 60 * 60
    assert s.tick(1, now=at(13, 56)) == []


def test_going_to_eat_cancels_timed_pause():
    s = make_scheduler(lunch_enabled=True, lunch_at=13 * 60)
    s.pause(30, now=at(12, 59))
    assert s.tick(1, now=at(13)) == ["meal"]    # звичайна пауза їжі не заважає
    s.meal_answered("eat", now=at(13))
    assert s.paused_until is None and s.eating == "lunch"


def test_day_end_reminds_and_snoozes():
    s = make_scheduler(day_end_enabled=True, day_end_at=18 * 60)
    assert s.tick(1, now=at(17, 59)) == []
    assert s.tick(1, now=at(18)) == ["day_end"]
    assert s.tick(1, now=at(18, 1)) == []          # поки висить — вдруге не показуємо
    s.day_end_answered("snooze", now=at(18, 1))
    assert s.tick(1, now=at(18, 20)) == []
    assert s.tick(1, now=at(18, 31)) == ["day_end"]
    s.day_end_answered("finish")
    assert s.tick(1, now=at(19)) == []             # сьогодні вже завершено


def test_day_end_waits_for_meal_and_skips_after_pause_until_morning():
    s = make_scheduler(day_end_enabled=True, day_end_at=18 * 60, dinner_enabled=True, dinner_at=18 * 60)
    assert s.tick(1, now=at(18)) == ["meal"]
    s.meal_answered("skip", now=at(18))
    assert s.tick(1, now=at(18, 1)) == ["day_end"]
    s = make_scheduler(day_end_enabled=True, day_end_at=18 * 60)
    s.pause(None, now=at(17, 59))                      # час фіксований: не залежить від годинника машини
    assert s.tick(1, now=at(18)) == []


def test_each_state_freezes_what_the_table_says():
    s = make_scheduler(mini_interval_min=20, water_interval_min=60, warn_before_sec=0)
    assert s.state == core.WORKING and s.frozen() == frozenset()
    s.pause(30, now=at(10))
    assert s.state == core.PAUSED and s.frozen() == {core.BREAKS}
    s.tick(5 * 60, now=at(10, 1), idle=10 * 60)                 # відійшов під час паузи
    assert s.state == core.AWAY and s.mode == core.PAUSED       # пауза не губиться
    assert s.frozen() == {core.BREAKS, core.WATER, core.CLOCK}
    assert s.tick(1, now=at(10, 40), idle=0) == ["back"]       # пауза тим часом скінчилась
    assert s.state == core.WORKING


def test_timed_pause_ends_by_itself():
    s = make_scheduler()
    s.pause(30, now=at(10))
    assert s.paused and s.paused_until == at(10, 30)
    s.tick(1, now=at(10, 30))
    assert not s.paused and s.mode == core.WORKING


def test_workday_belongs_to_the_previous_date_until_the_boundary():
    assert core.workday_date(at(0, 30)) == dt.date(2026, 10, 13)
    assert core.workday_date(at(4)) == dt.date(2026, 10, 14)
    assert core.workday_date(at(5, 59), boundary_hour=6) == dt.date(2026, 10, 13)
    assert core.work_started(at(4, 30), 0, boundary_hour=5) is None          # ще вчорашня ніч
    assert core.work_started(at(5, 30), 0, boundary_hour=5) == 5 * 60 + 30
    s = make_scheduler(day_boundary_hour=5)
    s.pause(None, now=at(23))
    assert s.paused_until == at(7) + dt.timedelta(days=1)                   # межа доби + 2 год
    # Вечеря після півночі в п'ятницю — ще п'ятниця, а не вихідний
    s = make_scheduler(lunch_enabled=True, workdays=[4])
    assert s.reminders_today(dt.datetime(2026, 10, 17, 1, 0))
    assert not s.reminders_today(dt.datetime(2026, 10, 17, 9, 0))


def test_stats_are_written_to_the_current_workday(monkeypatch, tmp_path):
    monkeypatch.setattr(core, "STATS_PATH", str(tmp_path / "stats.json"))
    stats = core.Stats(today=lambda: core.workday_date(at(0, 30)))
    stats.add("work_sec", 60)
    assert stats.day(dt.date(2026, 10, 13))["work_sec"] == 60 and stats.day(at(0).date())["work_sec"] == 0


def test_day_end_after_midnight_still_belongs_to_the_evening():
    s = make_scheduler(day_end_enabled=True, day_end_at=18 * 60)
    assert s.tick(1, now=at(0, 30) + dt.timedelta(days=1)) == ["day_end"]   # працює далеко за північ
    s.day_end_answered("finish", now=at(0, 31) + dt.timedelta(days=1))
    assert s.tick(1, now=at(18) + dt.timedelta(days=1)) == ["day_end"]      # наступного вечора — знову


def test_long_absence_counts_as_a_long_break():
    s = make_scheduler(long_every=3, long_duration_min=5, mini_interval_min=20)
    s.finish_break()
    assert s.breaks_until_long() == 2
    tick_at(s, at(10), 20, idle=6 * 60)                       # 6 хв — відсутність, але не довга перерва
    s.tick(1, now=at(10, 1), idle=0)
    assert s.breaks_until_long() == 2
    s.tick(1, now=at(11), idle=10 * 60)                      # 10 хв = 2 × довга перерва
    assert s.tick(1, now=at(11, 1), idle=0) == ["back"]
    assert s.breaks_until_long() == 3 and s.next_kind() == "mini"


def test_skipped_long_break_comes_back_once():
    s = make_scheduler(long_every=2)
    s.finish_break()
    assert s.next_kind() == "long"
    s.finish_break(skipped=True)
    assert s.next_kind() == "long" and s.breaks_until_long() == 1   # пропущена довга — ще раз
    s.finish_break(skipped=True)
    assert s.next_kind() == "mini"                                  # удруге ритм іде далі
    s.finish_break()
    assert s.next_kind() == "long"
    s.finish_break(skipped=True)
    s.finish_break()                                                # повернута довга зроблена
    assert s.next_kind() == "mini" and s.breaks_until_long() == 2
    s.finish_break(skipped=True)                                    # пропущена міні — нічого особливого
    assert s.next_kind() == "long"


def test_smart_water_pacing_follows_the_rest_of_the_day():
    s = make_scheduler(water_interval_min=60, water_goal=8)
    assert s.water_interval(at(10)) == 60 * 60                      # кінець дня невідомий — як у налаштуваннях
    s.update_day(drunk=4, workday_end=at(18))
    assert s.water_interval(at(10)) == 2 * 60 * 60                  # випереджаємо: 8 год на 4 склянки
    s.update_day(drunk=4, workday_end=at(14))
    assert s.water_interval(at(10)) == 60 * 60                      # 4 год на 4 склянки
    s.update_day(drunk=1, workday_end=at(13))
    assert s.water_interval(at(10)) == 3 * 3600 // 7                 # відстаємо — частіше
    s.update_day(drunk=1, workday_end=at(11))
    assert s.water_interval(at(10)) == 15 * 60                     # відстаємо — частіше, але не частіше 15 хв
    s.update_day(drunk=7, workday_end=at(18))
    s.water_answered(True, now=at(17))
    assert s.water_remaining == 60 * 60                             # остання склянка — за годину до кінця
    s.water_answered(False, now=at(17))
    assert s.water_remaining == 15 * 60                             # «Пізніше» — як і раніше
    s.update_day(drunk=8, workday_end=at(18))
    assert s.water_done


def test_overwork_warns_once_a_day():
    s = make_scheduler(max_work_hours=9)
    s.update_day(drunk=0, worked=9 * 3600 - 1)
    assert s.tick(1, now=at(18)) == []
    s.update_day(drunk=0, worked=9 * 3600)
    assert s.tick(1, now=at(18, 1)) == ["overwork"]
    assert s.tick(1, now=at(18, 2)) == []                       # поки висить — удруге не показуємо
    s.overwork_answered("later", now=at(18, 2))
    assert s.tick(1, now=at(19)) == []                          # раз на день
    assert s.tick(1, now=at(19) + dt.timedelta(days=1)) == ["overwork"]   # наступного дня (worked від App)
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
    assert tick_at(s, at(10, 0, 49), 10 * 60, busy=True) == ["break_held"]   # ні попередження, ні перерви
    assert s.remaining == 0 and not s.in_break
    assert s.tick(1, now=at(10, 11), busy=False) == ["break"]               # дзвінок скінчився
    s.finish_break()
    events = tick_at(s, at(11), 40 * 60, busy=True)
    assert events == ["break_held", "break"] and s.in_break                  # але не довше 30 хв


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
    snap = json.loads(json.dumps(s.snapshot(at(13, 2))))   # лише JSON-типи
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
    assert not restored.in_break and restored.remaining == core.BREAK_RESUME_SEC   # перерва — за хвилину
    assert restored.tick(1, now=at(13, 1)) == ["meal"]                            # віконця вже немає


def test_old_or_foreign_state_is_not_restored():
    s = make_scheduler()
    s.finish_break()
    snap = s.snapshot(at(10))
    assert not make_scheduler().restore(snap, at(10) + dt.timedelta(days=1))   # інший робочий день
    assert not make_scheduler().restore(snap, at(10) - dt.timedelta(hours=1))   # з майбутнього
    late = core.Scheduler.snapshot(s, at(4, 30))
    assert not make_scheduler().restore(late, at(4, 30) + dt.timedelta(hours=13))   # старіше 12 год
    for broken in ({}, {"version": 1}, dict(snap, mode="dancing"), dict(snap, remaining="x"), None):
        assert not make_scheduler().restore(broken, at(10, 5))


def test_long_gap_since_the_saved_state_is_an_absence():
    s = make_scheduler(long_every=3, long_duration_min=5, mini_interval_min=20)
    s.finish_break()
    tick(s, 15 * 60)
    restored = make_scheduler(long_every=3, long_duration_min=5, mini_interval_min=20)
    assert restored.restore(s.snapshot(at(10, 15)), at(12))       # комп'ютер був вимкнений майже 2 год
    assert restored.remaining == 20 * 60 and restored.breaks_until_long() == 3


def test_restore_day_from_stats():
    s = make_scheduler(lunch_enabled=True, lunch_at=13 * 60, day_end_enabled=True, day_end_at=18 * 60)
    s.restore_day(at(10).date(), eaten=["lunch"], finished_minute=30)    # день завершили о 00:30
    assert s.finished_at == at(0, 30) + dt.timedelta(days=1)
    assert s.meal_state("lunch", at(13)) == ("eat", None)
    assert s.tick(1, now=at(13)) == [] and s.tick(1, now=at(18)) == []


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
        assert [i for g in groups for i in g] == list(range(len(heights)))   # порядок карток не змінюється
    groups = core.split_balanced(heights, 4)
    tallest = max(sum(heights[i] for i in g) + 14 * (len(g) - 1) for g in groups)
    assert tallest == 310 + 330 + 14                                          # найкраще можливе: «пауза + вода»
    assert core.split_balanced([100, 100], 3) == [[0], [1]]               # колонок не більше, ніж карток


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
    water = {12: 8, 13: 9, 11: 3}   # 11-го норму не виконано — серія переривається
    stats.data = {dt.date(2026, 10, d).isoformat(): {"water": n} for d, n in water.items()}
    assert core.water_streak(stats, 8, today) == 2          # сьогодні ще не випито — рахуємо від учора
    stats.data[today.isoformat()] = {"water": 8}
    assert core.water_streak(stats, 8, today) == 3


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
    s.meal_answered("eat", now=at(13, 15))
    assert s.meal_state("lunch", at(13, 20)) == ("eating", at(13, 45))
    s.finish_meal()
    assert s.meal_state("lunch", at(14)) == ("eat", None)
    assert make_scheduler(lunch_at=13 * 60).meal_state("lunch", at(15)) == ("missed", at(13))


def test_next_meal_and_marking_a_meal_eaten_in_advance():
    s = make_scheduler(breakfast_enabled=True, breakfast_at=8 * 60, lunch_enabled=True, lunch_at=13 * 60)
    assert s.next_meal(at(7)) == ("breakfast", at(8))
    assert s.next_meal(at(8, 10)) == ("breakfast", None)       # час снідати вже зараз
    s.mark_meal("breakfast", True, now=at(8, 5))              # тарілку позначили на «Стані»
    assert s.tick(1, now=at(8, 10)) == []                      # без нагадування
    assert s.next_meal(at(8, 10)) == ("lunch", at(13))
    assert s.next_meal(at(15)) is None                         # обід минув — на сьогодні все


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
    assert s.paused_until == at(6)                       # о 06:00 цього ж дня, а не завтра
    s.pause(None, now=at(19))
    assert s.paused_until == at(6) + dt.timedelta(days=1)


def test_snoozes_do_not_carry_over_to_the_next_day():
    s = make_scheduler(day_end_enabled=True, day_end_at=18 * 60, lunch_enabled=True, lunch_at=13 * 60)
    late = at(23, 50)
    assert s.tick(1, now=late) == ["day_end"]
    s.day_end_answered("snooze", now=late)              # нагадати о 00:20 — уже наступна доба
    after_midnight = late + dt.timedelta(minutes=30)
    assert s.tick(1, now=after_midnight) == ["day_end"]  # досі працює — нагадуємо, хоч уже нова доба
    s.day_end_answered("snooze", now=after_midnight)
    # Комп'ютер заснув і прокинувся вранці — вчорашнє «Ще 30 хв» уже ні до чого
    assert s.tick(1, now=at(9) + dt.timedelta(days=1)) == []
    assert s.tick(1, now=at(18) + dt.timedelta(days=1)) == ["day_end"]   # а своє нагадування є
    s.tick(1, now=at(13))
    s.meal_answered("snooze", now=at(13))
    assert s.tick(1, now=at(13, 20) + dt.timedelta(days=1)) == ["meal"]   # лише своє, о 13:00+ наступного дня
    assert s.meal_snoozed == {}


def test_pause_until_morning_cancels_pending_reminders():
    s = make_scheduler(day_end_enabled=True, day_end_at=18 * 60, lunch_enabled=True, lunch_at=13 * 60)
    s.tick(1, now=at(13))
    s.meal_answered("snooze", now=at(13))
    s.pause(None, now=at(13, 5))
    assert s.meal_snoozed == {} and not s.day_end_open
    s.resume()
    assert s.tick(1, now=at(18)) == []                  # день уже завершено — без «робочий день скінчився»


def test_work_started_needs_recent_input_and_morning():
    assert core.work_started(at(8, 42, 30), 20) == 8 * 60 + 42          # остання дія — 8:42
    assert core.work_started(at(8, 42), 5 * 60) is None                  # людини немає вже 5 хв
    assert core.work_started(at(3, 30), 0) is None                       # ще ніч
    assert core.work_started(at(4, 0, 30), 45) is None                   # дія була до 4:00


def test_average_minute_skips_days_without_data():
    assert core.average_minute([8 * 60, 0, 9 * 60]) == 8 * 60 + 30
    assert core.average_minute([0, 0]) is None


def test_being_away_is_a_natural_break():
    s = make_scheduler(mini_interval_min=20, long_duration_min=5, water_interval_min=60, warn_before_sec=0)
    tick_at(s, at(10), 15 * 60)                              # 15 хв роботи
    remaining, water = s.remaining, s.water_remaining
    events = []
    for i in range(30 * 60):                                 # пів години без миші й клавіатури
        events += s.tick(1, now=at(10, 15) + dt.timedelta(seconds=i), idle=5 * 60 + i)
    assert events == [] and s.away
    assert (s.remaining, s.water_remaining) == (remaining, water)   # таймери стояли
    assert s.tick(1, now=at(10, 46), idle=0) == ["back"]
    assert s.remaining == 20 * 60 - 1                        # повернувся — до перерви знову 20 хв
    assert not s.away


def test_short_idle_is_not_away():
    s = make_scheduler(mini_interval_min=20, long_duration_min=5)
    s.tick(60, now=at(10), idle=4 * 60)                      # читає без миші 4 хв — це ще робота
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
    s = make_scheduler(lunch_enabled=True, lunch_at=13 * 60, workdays=[5, 6])   # працює лише у вихідні
    assert s.tick(1, now=at(13)) == [] and s.tick(1, now=saturday) == ["meal"]


def test_old_workdays_only_setting_migrates_to_a_list_of_days():
    assert core.migrate_config({"workdays_only": False})["workdays"] == list(range(7))
    assert "workdays" not in core.migrate_config({"workdays_only": True})    # будні — і так за замовчуванням
    assert core.migrate_config({"workdays_only": False, "workdays": [2, 0, 0]})["workdays"] == [0, 2]
    assert core.migrate_config({"workdays": "пн"})["workdays"] == core.DEFAULTS["workdays"]


def test_finished_day_is_not_asked_again_and_continues_if_still_working():
    s = make_scheduler(day_end_enabled=True, day_end_at=18 * 60)
    assert s.tick(1, now=at(18)) == ["day_end"]
    s.day_end_answered("finish", now=at(18, 1))
    s.pause(None, now=at(18, 1))
    assert s.paused_until is not None and s.day_finished(at(18, 2))
    assert s.tick(1, now=at(18, 2), idle=0) == []            # щойно натиснув — ще не «працює далі»
    assert s.tick(1, now=at(18, 5), idle=0) == ["day_continued"]
    assert s.paused_until is None                            # таймери знову йдуть
    assert s.tick(1, now=at(19), idle=0) == []               # і про кінець дня вже не питаємо
    assert not s.day_finished(at(9) + dt.timedelta(days=1))  # нова доба — новий день


def test_water_interval_follows_the_actual_workday():
    assert core.workday_span(8 * 60 + 30, 18 * 60) == (8 * 60 + 30, 18 * 60)
    assert core.workday_span(9 * 60, None) == (9 * 60, 17 * 60)            # кінець дня вимкнено — 8 год
    assert core.workday_span(9 * 60, 10 * 60) == (9 * 60, 13 * 60)         # не коротше 4 год
    assert core.water_interval_for(8, 9 * 60 + 30) == 70                   # 9,5 год на 8 склянок
    cfg = dict(core.DEFAULTS, water_profile="male")
    core.apply_water_profile(cfg, workday=10 * 60)
    assert (cfg["water_goal"], cfg["water_interval_min"]) == (8, 75)


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


@pytest.mark.parametrize("value, text", [(1, "1 раз"), (2, "2 рази"), (5, "5 разів"), (0, "не можна")])
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
    """Один роздільник у всіх рядках: «  •  » (дві пропуски з кожного боку), старої «·» немає."""
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
    assert goal * interval <= core.WORKDAY_MIN  # мету встигаємо за робочий день


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
    (core.fmt_times, 1, "1 time"), (core.fmt_times, 3, "3 times"), (core.fmt_times, 0, "not allowed"),
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
