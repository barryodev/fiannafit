import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from fiannafit.main import app
from fiannafit.session import COOKIE_NAME, Session, encode

T0 = datetime(2026, 10, 5, 17, 2, tzinfo=UTC)  # 18:02 in Dublin (IST)


@pytest.fixture
def client():
    # https, so the client sends the Secure session cookie
    with TestClient(app, base_url="https://testserver") as c:
        yield c


def with_workout(client, *sets):
    session = Session()
    for i, (name, reps, weight) in enumerate(sets):
        session.log_set(name, reps, weight, now=T0 + timedelta(minutes=3 * i))
    client.cookies.set(COOKIE_NAME, encode(session))
    return session


def test_index_without_workout_shows_empty_state(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "No workout yet. Log your first set to start." in response.text
    assert "Share your workout to keep it" not in response.text
    assert "started" not in response.text
    assert "Finish" not in response.text
    # The Undo line is there but empty, keeping the panel's height
    assert re.search(r'<div class="last-logged">\s*</div>', response.text)


def test_index_shows_exercises_in_first_logged_order(client):
    with_workout(
        client,
        ("Back Squat", 5, 100),
        ("Bench Press", 8, 62.5),
        ("Back Squat", 5, 105),
        ("Pull-up", 12, None),
    )
    text = client.get("/").text
    assert text.index("Back Squat") < text.index("Bench Press") < text.index("Pull-up")
    assert re.search(
        r'<li class="set">5 × 100 kg</li>\s*<li class="set">5 × 105 kg</li>', text
    )
    assert "8 × 62.5 kg" in text
    assert "12 reps" in text
    assert "Only saved on this device. Share your workout to keep it." in text
    assert ">Finish</button>" in text
    assert '<span class="last-logged-name">Pull-up</span>' in text


def test_index_shows_start_time_in_browser_time_zone(client):
    with_workout(client, ("Squat", 5, 100))
    client.cookies.set("tz", "Europe/Dublin")
    assert "started 18:02" in client.get("/").text


def test_index_falls_back_to_utc_for_unknown_time_zone(client):
    with_workout(client, ("Squat", 5, 100))
    client.cookies.set("tz", "Not/AZone")
    assert "started 17:02" in client.get("/").text


def test_index_shows_time_range_for_finished_workout(client):
    session = Session()
    session.log_set("Squat", 5, 100, now=T0)
    session.finish(now=T0 + timedelta(minutes=63))
    client.cookies.set(COOKIE_NAME, encode(session))
    client.cookies.set("tz", "Europe/Dublin")
    assert "18:02–19:05" in client.get("/").text


def test_page_sets_time_zone_cookie_and_loads_assets(client):
    text = client.get("/").text
    assert 'document.cookie = "tz="' in text
    assert "/static/css/app.css" in text
    assert "/static/htmx-2.0.11.min.js" in text


@pytest.mark.parametrize(
    "path",
    [
        "/static/htmx-2.0.11.min.js",
        "/static/css/app.css",
        "/static/fonts/roboto-latin-wght.woff2",
    ],
)
def test_static_assets_are_served(client, path):
    assert client.get(path).status_code == 200


def test_hello_world_is_gone(client):
    assert client.get("/hello").status_code == 404


def test_healthz_returns_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
