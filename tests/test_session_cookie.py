"""The session cookie as seen through HTTP (DAI-8), via the debug routes."""

import pytest
from fastapi.testclient import TestClient

from fiannafit.main import app


@pytest.fixture
def client():
    # https, so the client stores and sends the Secure cookie
    with TestClient(app, base_url="https://testserver") as c:
        yield c


def test_cookie_attributes(client):
    r = client.post("/debug/sets", params={"exercise": "Squat", "reps": 5})
    header = r.headers["set-cookie"].lower()
    for attribute in [
        "httponly",
        "secure",
        "samesite=lax",
        "path=/",
        "max-age=7776000",
    ]:
        assert attribute in header


def test_sets_persist_between_requests(client):
    client.post(
        "/debug/sets", params={"exercise": "Squat", "reps": 5, "weight_kg": 100}
    )
    client.post(
        "/debug/sets", params={"exercise": "Squat", "reps": 5, "weight_kg": 100}
    )
    body = client.get("/debug/session").json()
    assert len(body["workout"]["exercises"][0]["sets"]) == 2


def test_garbage_cookie_gives_empty_session_and_is_cleared(client):
    client.cookies.set("session", "garbage")
    r = client.get("/debug/session")
    assert r.status_code == 200
    assert r.json()["workout"] is None
    assert (
        'session=""' in r.headers["set-cookie"]
        or "max-age=0" in r.headers["set-cookie"].lower()
    )


def test_garbage_cookie_replaced_by_a_write(client):
    client.cookies.set("session", "garbage")
    r = client.post("/debug/sets", params={"exercise": "Squat", "reps": 5})
    assert r.status_code == 200
    assert len(r.headers.get_list("set-cookie")) == 1
    assert client.get("/debug/session").json()["workout"] is not None


def test_new_workout_keeps_recent_exercises(client):
    client.post("/debug/sets", params={"exercise": "Squat", "reps": 5})
    body = client.post("/debug/new-workout").json()
    assert body["workout"] is None
    assert body["recent_exercises"] == ["Squat"]
