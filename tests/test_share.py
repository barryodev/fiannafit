"""Unit tests for the plain-text workout summary (DAI-9)."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from fiannafit.session import Session
from fiannafit.share import summary_text, when

DUBLIN = ZoneInfo("Europe/Dublin")
T0 = datetime(2026, 9, 29, 17, 2, tzinfo=UTC)  # 18:02 in Dublin (summer time)


def workout(*sets, finished_after=timedelta(minutes=20)):
    """A finished workout from (exercise, reps, kg) tuples, logged a minute apart."""
    session = Session()
    for i, (name, reps, kg) in enumerate(sets):
        session.log_set(name, reps, kg, now=T0 + timedelta(minutes=i))
    session.finish(now=T0 + finished_after)
    return session.workout


def test_typical_workout():
    w = workout(
        ("Barbell Bench Press", 8, 60),
        ("Barbell Bench Press", 8, 60),
        ("Barbell Bench Press", 6, 62.5),
        ("Back Squat", 5, 100),
        ("Back Squat", 5, 100),
        ("Back Squat", 5, 100),
        finished_after=timedelta(minutes=63),
    )
    assert summary_text(w, DUBLIN) == (
        "🏋️ Fianna Fit workout, Tue 29 Sep, 18:02–19:05 (63 min)\n"
        "\n"
        "*Barbell Bench Press*\n"
        "8 × 60 kg · 8 × 60 kg · 6 × 62.5 kg\n"
        "\n"
        "*Back Squat*\n"
        "5 × 100 kg · 5 × 100 kg · 5 × 100 kg\n"
        "\n"
        "Logged with fiannafit.barryodev.io"
    )


def test_bodyweight_sets_show_reps_only():
    w = workout(
        ("Pull-up", 10, None),
        ("Pull-up", 1, None),
        ("Dip", 12, None),
        ("Dip", 8, 10),  # weighted dip in the same exercise
    )
    assert summary_text(w, DUBLIN) == (
        "🏋️ Fianna Fit workout, Tue 29 Sep, 18:02–18:22 (20 min)\n"
        "\n"
        "*Pull-up*\n"
        "10 reps · 1 rep\n"
        "\n"
        "*Dip*\n"
        "12 reps · 8 × 10 kg\n"
        "\n"
        "Logged with fiannafit.barryodev.io"
    )


def test_only_a_finished_workout_is_shared():
    session = Session()
    session.log_set("Back Squat", 5, 100, now=T0)
    with pytest.raises(ValueError):
        summary_text(session.workout, DUBLIN)


def test_exercise_names_are_not_html_escaped():
    # Plain text: the page escapes it once, where it embeds it
    w = workout(('Curl & Press <heavy> "Tom\'s"', 8, 20))
    assert '*Curl & Press <heavy> "Tom\'s"*\n' in summary_text(w, DUBLIN)


def test_times_and_day_are_in_the_users_time_zone():
    # 17:02 UTC on Tue 29 Sep is already Wed 30 Sep in Auckland
    w = workout(("Row", 10, 50))
    assert when(w, UTC) == "Tue 29 Sep, 17:02–17:22 (20 min)"
    assert when(w, DUBLIN) == "Tue 29 Sep, 18:02–18:22 (20 min)"
    assert when(w, ZoneInfo("Pacific/Auckland")) == "Wed 30 Sep, 06:02–06:22 (20 min)"


def test_workout_past_midnight_keeps_its_start_day():
    w = workout(("Row", 10, 50), finished_after=timedelta(hours=7))
    assert when(w, DUBLIN) == "Tue 29 Sep, 18:02–01:02 (420 min)"


def test_duration_matches_the_clock_times_shown():
    session = Session()
    session.log_set("Row", 10, 50, now=datetime(2026, 9, 29, 17, 2, 50, tzinfo=UTC))
    session.finish(now=datetime(2026, 9, 29, 18, 5, 10, tzinfo=UTC))
    # 62 min 20 s, but 18:02–19:05 reads as 63
    assert when(session.workout, DUBLIN) == "Tue 29 Sep, 18:02–19:05 (63 min)"


def test_duration_across_a_clock_change_is_real_time():
    # Irish clocks go back at 02:00 on 25 Oct 2026 (01:00 UTC)
    session = Session()
    session.log_set("Row", 10, 50, now=datetime(2026, 10, 25, 0, 30, tzinfo=UTC))
    session.finish(now=datetime(2026, 10, 25, 1, 30, tzinfo=UTC))
    assert when(session.workout, DUBLIN) == "Sun 25 Oct, 01:30–01:30 (60 min)"
