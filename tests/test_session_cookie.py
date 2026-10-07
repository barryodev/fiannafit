"""The session cookie as seen through HTTP (DAI-8), via the logging routes."""

import pytest
from fastapi.testclient import TestClient

from fiannafit.main import app
from fiannafit.session import COOKIE_NAME, decode


@pytest.fixture
def client():
    # https, so the client stores and sends the Secure cookie
    with TestClient(app, base_url="https://testserver") as c:
        yield c


def log(client, exercise="Squat", reps="5", kg="100"):
    return client.post("/sets", data={"exercise": exercise, "reps": reps, "kg": kg})


def test_cookie_attributes(client):
    r = log(client)
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
    log(client)
    log(client)
    workout = decode(client.cookies[COOKIE_NAME]).workout
    assert len(workout.exercises[0].sets) == 2
    assert client.get("/").text.count('<li class="set">5 × 100 kg</li>') == 2


def test_garbage_cookie_gives_empty_session_and_is_cleared(client):
    client.cookies.set(COOKIE_NAME, "garbage")
    r = client.get("/")
    assert r.status_code == 200
    assert "No workout yet. Log your first set to start." in r.text
    assert (
        'session=""' in r.headers["set-cookie"]
        or "max-age=0" in r.headers["set-cookie"].lower()
    )


def test_garbage_cookie_replaced_by_a_write(client):
    client.cookies.set(COOKIE_NAME, "garbage")
    r = log(client)
    assert r.status_code == 200
    assert len(r.headers.get_list("set-cookie")) == 1
    assert decode(r.cookies[COOKIE_NAME]).workout is not None
