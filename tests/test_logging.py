"""Logging a set through POST /sets, as the page's HTMX form does (DAI-11)."""

import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from fiannafit import session as session_module
from fiannafit.main import app
from fiannafit.session import COOKIE_NAME, Session, decode, encode

T0 = datetime(2026, 10, 5, 17, 2, tzinfo=UTC)


@pytest.fixture
def client():
    # https, so the client stores and sends the Secure session cookie
    with TestClient(app, base_url="https://testserver") as c:
        yield c


def log(client, exercise, reps, kg):
    return client.post("/sets", data={"exercise": exercise, "reps": reps, "kg": kg})


def stored(client) -> Session:
    return decode(client.cookies[COOKIE_NAME])


def input_value(html, name):
    return re.search(rf'name="{name}" value="([^"]*)"', html).group(1)


def test_first_set_starts_the_workout_and_is_stored(client):
    r = log(client, "Back Squat", "5", "100")
    assert r.status_code == 200
    workout = stored(client).workout
    assert workout.started_at is not None
    [exercise] = workout.exercises
    assert (exercise.name, exercise.sets[0].reps) == ("Back Squat", 5)
    assert exercise.sets[0].weight_kg == 100


def test_response_swaps_in_cards_and_start_time(client):
    client.cookies.set("tz", "Europe/Dublin")
    html = log(client, "Back Squat", "5", "100").text
    assert '<div id="workout" class="workout-list" hx-swap-oob="true">' in html
    assert '<span id="workout-time" class="workout-time" hx-swap-oob="true">' in html
    assert "started " in html
    assert "5 × 100 kg" in html


def test_response_form_is_prefilled_for_a_repeat_set(client):
    html = log(client, "Back Squat", "5", "102.5").text
    assert input_value(html, "exercise") == "Back Squat"
    assert input_value(html, "reps") == "5"
    assert input_value(html, "kg") == "102.5"


def test_repeat_sets_join_the_same_exercise(client):
    log(client, "Bench Press", "8", "60")
    log(client, "  bench   press ", "8", "60")
    [exercise] = stored(client).workout.exercises
    assert exercise.name == "Bench Press"
    assert len(exercise.sets) == 2


def test_bodyweight_set_is_zero_kg(client):
    html = log(client, "Pull-up", "12", "0").text
    assert stored(client).workout.exercises[0].sets[0].weight_kg is None
    assert "12 reps" in html
    assert input_value(html, "kg") == "0"


def test_comma_decimal_weight(client):
    log(client, "Bench Press", "8", "62,5")
    assert stored(client).workout.exercises[0].sets[0].weight_kg == 62.5


def test_latest_exercise_card_is_marked_for_scrolling(client):
    log(client, "Squat", "5", "100")
    html = log(client, "Bench", "8", "60").text
    assert re.search(r'<section class="card" id="current-exercise">\s*<h2>Bench', html)


@pytest.mark.parametrize(
    "exercise, reps, kg, field, message",
    [
        ("", "5", "100", "exercise", "Enter an exercise name."),
        ("Squat", "0", "100", "reps", "Reps must be a whole number from 1 to 999."),
        ("Squat", "5", "", "kg", "Enter a weight, or 0 for bodyweight."),
    ],
)
def test_invalid_set_shows_error_and_keeps_typed_values(
    client, exercise, reps, kg, field, message
):
    r = log(client, exercise, reps, kg)
    assert r.status_code == 422
    assert "set-cookie" not in r.headers
    assert 'class="error-pill" role="alert"' in r.text
    assert message in r.text
    assert re.search(
        rf'class="field[^"]* invalid">\s*<span>[^<]*</span>\s*<input[^>]*name="{field}"',
        r.text,
    )
    assert input_value(r.text, "exercise") == exercise
    assert input_value(r.text, "reps") == reps
    assert input_value(r.text, "kg") == kg
    assert "hx-swap-oob" not in r.text  # only the form changes


def test_invalid_set_leaves_existing_workout_alone(client):
    log(client, "Squat", "5", "100")
    before = client.cookies[COOKIE_NAME]
    log(client, "Squat", "five", "100")
    assert client.cookies[COOKIE_NAME] == before


def test_set_refused_when_session_is_full(client, monkeypatch):
    log(client, "Squat", "5", "100")
    before = client.cookies[COOKIE_NAME]
    # One more set won't fit under a limit just above the current size
    monkeypatch.setattr(session_module, "MAX_COOKIE_BYTES", len(before) + 5)
    r = log(client, "Squat", "5", "100")
    assert r.status_code == 422
    assert (
        "This workout is too big to store any more sets. Share it to keep it." in r.text
    )
    assert "set-cookie" not in r.headers
    assert client.cookies[COOKIE_NAME] == before
    assert input_value(r.text, "exercise") == "Squat"


def test_set_refused_when_workout_is_finished(client):
    session = Session()
    session.log_set("Squat", 5, 100, now=T0)
    session.finish(now=T0 + timedelta(minutes=60))
    client.cookies.set(COOKIE_NAME, encode(session))
    r = log(client, "Squat", "5", "100")
    assert r.status_code == 422
    assert "This workout is finished." in r.text
    assert len(stored(client).workout.exercises[0].sets) == 1


def test_exercise_names_are_escaped(client):
    html = log(client, "<b>Squat</b>", "5", "100").text
    assert "<b>Squat</b>" not in html
    assert "&lt;b&gt;Squat&lt;/b&gt;" in html


def test_page_is_prefilled_from_the_cookie(client):
    log(client, "Deadlift", "5", "140")
    html = client.get("/").text
    assert input_value(html, "exercise") == "Deadlift"
    assert input_value(html, "reps") == "5"
    assert input_value(html, "kg") == "140"


def test_page_suggests_workout_and_recent_exercises(client):
    log(client, "Deadlift", "5", "140")
    client.post("/debug/new-workout")
    log(client, "Squat", "5", "100")
    html = client.get("/").text
    datalist = re.search(
        r'<datalist id="exercise-suggestions">(.*?)</datalist>', html, re.DOTALL
    )
    assert re.findall(r'value="([^"]*)"', datalist.group(1)) == ["Squat", "Deadlift"]


def test_form_guards_against_double_taps(client):
    html = client.get("/").text
    assert 'hx-sync="this:drop"' in html
    assert 'hx-disabled-elt="#log-set"' in html


def test_page_swaps_in_validation_errors(client):
    html = client.get("/").text
    assert '{"code": "422", "swap": true}' in html
