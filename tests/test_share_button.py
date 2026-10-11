"""The Share Workout button carries the summary in the page (DAI-9), so the
share sheet can open straight from the tap. The text itself is tested in
tests/test_share.py; the tap in tests/browser/test_share_sheet.py."""

import html
import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from fiannafit.main import app
from fiannafit.session import COOKIE_NAME, Session, encode

T0 = datetime(2026, 9, 29, 17, 2, tzinfo=UTC)  # 18:02 in Dublin


@pytest.fixture
def client():
    # https, so the client stores and sends the Secure session cookie
    with TestClient(app, base_url="https://testserver") as c:
        c.cookies.set("tz", "Europe/Dublin")
        yield c


def start(client, *sets, finished=True) -> None:
    """Store a workout of (exercise, reps, kg) sets, a minute apart."""
    session = Session()
    for i, (exercise, reps, kg) in enumerate(sets):
        session.log_set(exercise, reps, kg, now=T0 + timedelta(minutes=i))
    if finished:
        session.finish(now=T0 + timedelta(minutes=63))
    client.cookies.set(COOKIE_NAME, encode(session))


def share_text(page: str) -> str | None:
    """The text the Share button would share, as the browser reads it."""
    match = re.search(r'data-share-text="([^"]*)"', page)
    return html.unescape(match.group(1)) if match else None


SUMMARY = (
    "🏋️ Fianna Fit workout, Tue 29 Sep, 18:02–19:05 (63 min)\n"
    "\n"
    "*Squat*\n"
    "5 × 100 kg\n"
    "\n"
    "Logged with fiannafit.barryodev.io"
)


def test_finished_page_carries_the_summary(client):
    start(client, ("Squat", 5, 100))
    assert share_text(client.get("/").text) == SUMMARY


def test_finish_swaps_in_the_summary(client):
    start(client, ("Squat", 5, 100), finished=False)
    page = client.post("/finish").text
    assert share_text(page).startswith("🏋️ Fianna Fit workout, Tue 29 Sep, 18:02–")
    assert "*Squat*\n5 × 100 kg" in share_text(page)


def test_summary_uses_the_browsers_time_zone(client):
    client.cookies.set("tz", "Asia/Tokyo")
    start(client, ("Squat", 5, 100))
    assert share_text(client.get("/").text).startswith(
        "🏋️ Fianna Fit workout, Wed 30 Sep, 02:02–03:05 (63 min)"
    )


def test_no_share_button_while_the_workout_is_open(client):
    start(client, ("Squat", 5, 100), finished=False)
    assert "data-share-text" not in client.get("/").text


def test_no_share_button_without_a_workout(client):
    assert "data-share-text" not in client.get("/").text


def test_exercise_names_are_escaped_once_in_the_page(client):
    start(client, ('Curl & "Press" <b>', 8, 20))
    page = client.get("/").text
    assert "<b>" not in page.split("data-share-text=", 1)[1].split(">", 1)[0]
    assert '*Curl & "Press" <b>*' in share_text(page)
