"""Unit tests for checking and pre-filling the Log Set form (DAI-11)."""

from datetime import UTC, datetime, timedelta

import pytest

from fiannafit.forms import FormValues, InvalidSet, parse_set, prefill, suggestions
from fiannafit.session import Session

T0 = datetime(2026, 10, 5, 17, 2, tzinfo=UTC)


def test_parse_set_valid():
    entry = parse_set(FormValues("  back   squat ", " 5 ", " 102.5 "))
    assert (entry.exercise, entry.reps, entry.weight_kg) == ("back squat", 5, 102.5)


def test_zero_kg_means_bodyweight():
    assert parse_set(FormValues("Pull-up", "12", "0")).weight_kg is None
    assert parse_set(FormValues("Pull-up", "12", "0.00")).weight_kg is None


def test_comma_is_a_decimal_point():
    assert parse_set(FormValues("Bench", "8", "62,5")).weight_kg == 62.5


@pytest.mark.parametrize(
    "exercise, reps, kg, field, message",
    [
        ("", "5", "100", "exercise", "Enter an exercise name."),
        ("   ", "5", "100", "exercise", "Enter an exercise name."),
        ("x" * 41, "5", "100", "exercise", "40 characters or fewer"),
        ("Squat", "", "100", "reps", "whole number from 1 to 999"),
        ("Squat", "0", "100", "reps", "whole number from 1 to 999"),
        ("Squat", "1000", "100", "reps", "whole number from 1 to 999"),
        ("Squat", "5.5", "100", "reps", "whole number from 1 to 999"),
        ("Squat", "-5", "100", "reps", "whole number from 1 to 999"),
        ("Squat", "five", "100", "reps", "whole number from 1 to 999"),
        ("Squat", "٥", "100", "reps", "whole number from 1 to 999"),  # Arabic 5
        ("Squat", "5", "", "kg", "Enter a weight, or 0 for bodyweight."),
        ("Squat", "5", "-10", "kg", "from 0 to 1000 kg"),
        ("Squat", "5", "1000.5", "kg", "from 0 to 1000 kg"),
        ("Squat", "5", "62.555", "kg", "up to 2 decimals"),
        ("Squat", "5", "62.", "kg", "from 0 to 1000 kg"),
        ("Squat", "5", "1e3", "kg", "from 0 to 1000 kg"),
        ("Squat", "5", "heavy", "kg", "from 0 to 1000 kg"),
    ],
)
def test_parse_set_rejects(exercise, reps, kg, field, message):
    with pytest.raises(InvalidSet) as caught:
        parse_set(FormValues(exercise, reps, kg))
    assert caught.value.field == field
    assert message in caught.value.message


def test_limits_are_inclusive():
    entry = parse_set(FormValues("x" * 40, "999", "1000"))
    assert (entry.reps, entry.weight_kg) == (999, 1000)
    assert parse_set(FormValues("Squat", "1", "0.25")).weight_kg == 0.25


def test_prefill_empty_session_has_nothing_to_repeat():
    assert prefill(Session()) is None


def test_prefill_repeats_the_latest_set():
    session = Session()
    session.log_set("Squat", 5, 100, now=T0)
    session.log_set("Bench", 8, 62.5, now=T0 + timedelta(minutes=5))
    assert prefill(session) == FormValues("Bench", "8", "62.5")


def test_prefill_shows_bodyweight_as_zero():
    session = Session()
    session.log_set("Pull-up", 12, None, now=T0)
    assert prefill(session) == FormValues("Pull-up", "12", "0")


def test_prefill_named_exercise_repeats_its_own_last_set():
    session = Session()
    session.log_set("Squat", 5, 100, now=T0)
    session.log_set("Squat", 3, 110, now=T0 + timedelta(minutes=3))
    session.log_set("Bench", 8, 62.5, now=T0 + timedelta(minutes=5))
    assert prefill(session, "Squat") == FormValues("Squat", "3", "110")


def test_prefill_named_exercise_ignores_case():
    session = Session()
    session.log_set("Back Squat", 5, 100, now=T0)
    assert prefill(session, "back squat") == FormValues("back squat", "5", "100")


def test_prefill_unknown_exercise_has_nothing_to_repeat():
    session = Session()
    session.log_set("Deadlift", 5, 140, now=T0)
    session.new_workout()  # in recent names, but with no sets in this workout
    session.log_set("Squat", 5, 100, now=T0)
    assert prefill(session, "Deadlift") is None


def test_suggestions_workout_first_then_recent_without_repeats():
    session = Session()
    session.log_set("Deadlift", 5, 140, now=T0)
    session.new_workout()  # Deadlift stays in recent names only
    session.log_set("Squat", 5, 100, now=T0)
    session.log_set("Bench", 8, 60, now=T0)
    assert suggestions(session) == ["Squat", "Bench", "Deadlift"]


def test_suggestions_without_any_history():
    assert suggestions(Session()) == []
