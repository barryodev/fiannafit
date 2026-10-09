"""Undo, Finish and New Workout: POST /undo, /finish and /new-workout (DAI-11
step 5), as the page's HTMX buttons send them."""

import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from fiannafit import session as session_module
from fiannafit.main import app
from fiannafit.session import COOKIE_NAME, Session, decode, encode

T0 = datetime(2026, 10, 7, 17, 2, tzinfo=UTC)


@pytest.fixture
def client():
    # https, so the client stores and sends the Secure session cookie
    with TestClient(app, base_url="https://testserver") as c:
        yield c


def start(client, *sets, finished=False) -> Session:
    """Store a workout of (exercise, reps, kg) sets, a minute apart."""
    session = Session()
    for i, (exercise, reps, kg) in enumerate(sets):
        session.log_set(exercise, reps, kg, now=T0 + timedelta(minutes=i))
    if finished:
        session.finish(now=T0 + timedelta(minutes=60))
    client.cookies.set(COOKIE_NAME, encode(session))
    return session


def minute(i: int) -> str:
    return (T0 + timedelta(minutes=i)).isoformat()


def saved(response) -> Session:
    """The session a response saved. Read from the response, not the client:
    the test's own cookie and the server's would clash in the client's jar."""
    return decode(response.cookies[COOKIE_NAME])


def input_value(html, name):
    return re.search(rf'name="{name}" value="([^"]*)"', html).group(1)


def top_bar(html):
    return re.search(r"<header .*?</header>", html, re.DOTALL).group(0)


def chips(html):
    return re.findall(r'<li class="set">([^<]*)</li>', html)


# --- Undo ---------------------------------------------------------------------


def test_undo_removes_the_latest_set(client):
    start(client, ("Squat", 5, 100), ("Bench", 8, 60), ("Bench", 8, 65))
    r = client.post("/undo", data={"logged_at": minute(2)})
    assert r.status_code == 200
    squat, bench = saved(r).workout.exercises
    assert [s.weight_kg for s in bench.sets] == [60]
    assert len(squat.sets) == 1


def test_undo_puts_the_removed_set_in_the_form(client):
    # Not the set now last: the removed one, to fix a number or log it again
    start(client, ("Bench", 8, 60), ("Bench", 6, 62.5))
    html = client.post("/undo", data={"logged_at": minute(1)}).text
    assert input_value(html, "exercise") == "Bench"
    assert input_value(html, "reps") == "6"
    assert input_value(html, "kg") == "62.5"


def test_undo_of_a_bodyweight_set_puts_0_kg_in_the_form(client):
    start(client, ("Pull-up", 12, None))
    html = client.post("/undo", data={"logged_at": minute(0)}).text
    assert input_value(html, "kg") == "0"


def test_undo_swaps_in_the_cards_top_bar_and_last_line(client):
    start(client, ("Squat", 5, 100), ("Bench", 8, 60))
    html = client.post("/undo", data={"logged_at": minute(1)}).text
    assert '<div id="workout" class="workout-list" hx-swap-oob="true">' in html
    assert 'id="top-bar" class="top-bar" hx-swap-oob="true"' in html
    assert chips(html) == ["5 × 100 kg"]
    assert '<span class="last-logged-name">Squat</span>' in html


def test_undo_of_the_only_set_goes_back_to_no_workout(client):
    start(client, ("Squat", 5, 100))
    r = client.post("/undo", data={"logged_at": minute(0)})
    html = r.text
    assert saved(r).workout is None
    assert "No workout yet." in html
    assert ">Finish</button>" not in top_bar(html)
    assert input_value(html, "exercise") == "Squat"


@pytest.mark.parametrize("logged_at", [minute(0), "", "yesterday"])
def test_undo_that_doesnt_name_the_latest_set_changes_nothing(client, logged_at):
    # minute(0): a repeated tap, or a page that's out of date
    start(client, ("Squat", 5, 100), ("Squat", 5, 105))
    r = client.post("/undo", data={"logged_at": logged_at})
    assert r.status_code == 200
    assert "set-cookie" not in r.headers
    # The page is brought up to date instead
    assert chips(r.text) == ["5 × 100 kg", "5 × 105 kg"]


def test_undo_after_finish_changes_nothing(client):
    start(client, ("Squat", 5, 100), finished=True)
    r = client.post("/undo", data={"logged_at": minute(0)})
    assert r.status_code == 200
    assert "set-cookie" not in r.headers
    assert ">Share Workout</button>" in r.text


def test_undo_button_names_the_latest_set(client):
    start(client, ("Squat", 5, 100), ("Bench", 8, 60))
    html = client.get("/").text
    button = re.search(r'<button[^>]*hx-post="/undo"[^>]*>', html).group(0)
    assert f'hx-vals=\'{{"logged_at": "{minute(1)}"}}\'' in button
    assert 'hx-sync="#log-panel:drop"' in button
    assert 'hx-disabled-elt="this"' in button


def test_undo_button_arrives_disabled_straight_after_an_undo(client):
    # app.js enables it a moment later, once a double tap would be over
    start(client, ("Squat", 5, 100), ("Squat", 5, 105))
    html = client.post("/undo", data={"logged_at": minute(1)}).text
    button = re.search(r'<button[^>]*hx-post="/undo"[^>]*>', html).group(0)
    assert button.endswith(" disabled data-cooldown>")


def test_undo_button_is_enabled_otherwise(client):
    start(client, ("Squat", 5, 100), ("Squat", 5, 105))
    for html in (
        client.get("/").text,
        client.post("/sets", data={"exercise": "Squat", "reps": "5", "kg": "110"}).text,
    ):
        button = re.search(r'<button[^>]*hx-post="/undo"[^>]*>', html).group(0)
        assert "data-cooldown" not in button
        assert not button.endswith(" disabled>")


# --- Finish ---------------------------------------------------------------------


def test_finish_sets_the_end_time(client):
    start(client, ("Squat", 5, 100))
    r = client.post("/finish")
    assert r.status_code == 200
    assert saved(r).workout.ended_at is not None


def test_finished_screen(client):
    start(client, ("Squat", 5, 100))
    client.cookies.set("tz", "UTC")
    html = client.post("/finish").text
    bar = top_bar(html)
    assert re.search(r"17:02–\d\d:\d\d", bar)
    assert ">New Workout</button>" in bar
    assert ">Finish</button>" not in bar
    # The panel holds only Share: no fields, no Last line or Undo
    assert ">Share Workout</button>" in html
    assert 'name="exercise"' not in html
    assert "/undo" not in html
    # Cards can't be tapped, as there's no form to fill
    assert "card-pick" not in html
    assert chips(html) == ["5 × 100 kg"]


def test_page_shows_a_finished_workout_as_finished(client):
    start(client, ("Squat", 5, 100), finished=True)
    html = client.get("/").text
    assert ">Share Workout</button>" in html
    assert ">New Workout</button>" in html
    assert 'name="exercise"' not in html


def test_finish_with_no_workout_changes_nothing(client):
    r = client.post("/finish")
    assert r.status_code == 200
    assert "set-cookie" not in r.headers
    assert "No workout yet." in r.text


def test_finishing_twice_keeps_the_first_end_time(client):
    start(client, ("Squat", 5, 100), finished=True)
    r = client.post("/finish")
    assert saved(r).workout.ended_at == T0 + timedelta(minutes=60)


def test_finish_refused_when_session_is_full(client, monkeypatch):
    start(client, ("Squat", 5, 100))
    before = client.cookies[COOKIE_NAME]
    # The end time won't fit under a limit just above the current size
    monkeypatch.setattr(session_module, "MAX_COOKIE_BYTES", len(before) + 5)
    r = client.post("/finish")
    assert r.status_code == 422
    assert "This workout is too big to store, so it can&#39;t be finished." in r.text
    assert "set-cookie" not in r.headers


def test_a_set_sent_to_a_finished_workout_brings_the_page_up_to_date(client):
    # E.g. from another tab that hasn't seen Finish
    start(client, ("Squat", 5, 100), finished=True)
    r = client.post("/sets", data={"exercise": "Squat", "reps": "5", "kg": "100"})
    assert r.status_code == 422
    assert "This workout is finished." in r.text
    assert ">Share Workout</button>" in r.text
    assert ">New Workout</button>" in top_bar(r.text)


def test_finish_asks_first(client):
    start(client, ("Squat", 5, 100))
    button = re.search(r'<button[^>]*hx-post="/finish"[^>]*>', client.get("/").text)
    assert 'hx-confirm="Finish Workout?"' in button.group(0)
    assert 'data-confirm-body="You can\'t add sets after finishing."' in button.group(0)
    assert 'data-confirm-action="Finish"' in button.group(0)


# --- New Workout ------------------------------------------------------------------


def test_new_workout_clears_the_workout_and_keeps_recent_names(client):
    start(client, ("Squat", 5, 100), ("Bench", 8, 60), finished=True)
    r = client.post("/new-workout")
    html = r.text
    session = saved(r)
    assert session.workout is None
    assert session.recent_exercises == ["Bench", "Squat"]
    assert "No workout yet." in html
    assert input_value(html, "exercise") == ""
    assert input_value(html, "reps") == ""
    datalist = re.search(r"<datalist[^>]*>(.*?)</datalist>", html, re.DOTALL)
    assert re.findall(r'value="([^"]*)"', datalist.group(1)) == ["Bench", "Squat"]


def test_new_workout_asks_first_and_warns_it_is_unshared(client):
    start(client, ("Squat", 5, 100), finished=True)
    html = client.get("/").text
    button = re.search(r'<button[^>]*hx-post="/new-workout"[^>]*>', html).group(0)
    assert 'hx-confirm="Start a New Workout?"' in button
    assert "This workout hasn't been shared. Starting a new one deletes it." in button
    assert 'data-confirm-action="Delete and Start New"' in button


def test_new_workout_is_only_offered_once_finished(client):
    start(client, ("Squat", 5, 100))
    assert "/new-workout" not in client.get("/").text


def test_page_has_the_confirm_dialog(client):
    html = client.get("/").text
    assert '<dialog id="confirm"' in html
    assert '<button value="cancel" class="btn btn-text" autofocus>Cancel</button>' in (
        html
    )
