from fastapi.testclient import TestClient

from fiannafit.main import app

client = TestClient(app)


def test_index_renders_page_with_htmx():
    response = client.get("/")
    assert response.status_code == 200
    assert 'hx-get="/hello"' in response.text
    assert "/static/htmx-2.0.11.min.js" in response.text


def test_hello_returns_fragment():
    response = client.get("/hello")
    assert response.status_code == 200
    assert "Hello World" in response.text
    assert "<html" not in response.text


def test_htmx_is_served():
    response = client.get("/static/htmx-2.0.11.min.js")
    assert response.status_code == 200


def test_healthz_returns_ok():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
