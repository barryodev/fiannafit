"""Share Workout's summary and fallback links are in the page (DAI-9), so the
share sheet can open straight from the tap. The text and links themselves are
tested in tests/test_share.py; the taps in tests/browser/test_share_sheet.py."""

import html
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

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
    """The text Share Workout would share, as the browser reads it."""
    match = re.search(r'data-summary="([^"]*)"', page)
    return html.unescape(match.group(1)) if match else None


def hrefs(page: str) -> list[str]:
    """The links in the Share dialog, as the browser reads them."""
    dialog = page.split('id="share-options"', 1)[1].split("</dialog>", 1)[0]
    return [html.unescape(href) for href in re.findall(r'href="([^"]*)"', dialog)]


SUMMARY = (
    "🏋️ Fianna Fit workout, Tue 29 Sep, 18:02–19:05 (1 h 3 min)\n"
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
    # Finished now, so the end time and day are today's
    assert share_text(page).startswith("🏋️ Fianna Fit workout, Tue 29 Sep, 18:02 – ")
    assert "*Squat*\n5 × 100 kg" in share_text(page)


def test_summary_uses_the_browsers_time_zone(client):
    client.cookies.set("tz", "Asia/Tokyo")
    start(client, ("Squat", 5, 100))
    assert share_text(client.get("/").text).startswith(
        "🏋️ Fianna Fit workout, Wed 30 Sep, 02:02–03:05 (1 h 3 min)"
    )


def test_no_share_button_while_the_workout_is_open(client):
    start(client, ("Squat", 5, 100), finished=False)
    page = client.get("/").text
    assert "data-summary" not in page
    assert "share-options" not in page


def test_no_share_button_without_a_workout(client):
    page = client.get("/").text
    assert "data-summary" not in page
    assert "share-options" not in page


def test_exercise_names_are_escaped_once_in_the_page(client):
    start(client, ('Curl & "Press" <b>', 8, 20))
    page = client.get("/").text
    assert "<b>" not in page.split("data-summary=", 1)[1].split(">", 1)[0]
    assert '*Curl & "Press" <b>*' in share_text(page)


def test_share_dialog_links_carry_the_summary(client):
    start(client, ('Curl & "Press" <b>', 8, 20))
    page = client.get("/").text
    whatsapp, email, sms = hrefs(page)
    text = share_text(page)
    assert whatsapp == f"https://api.whatsapp.com/send?text={quote(text, safe='')}"
    assert email.startswith("mailto:?subject=") and "&body=" in email
    # Only WhatsApp shows *bold*; the others get the names without it
    plain = text.replace('*Curl & "Press" <b>*', 'Curl & "Press" <b>')
    assert email.endswith(
        f"&body={quote(plain.replace(chr(10), chr(13) + chr(10)), safe='')}"
    )
    assert sms == f"sms:?&body={quote(plain, safe='')}"


def test_only_the_whatsapp_link_opens_a_new_tab(client):
    start(client, ("Squat", 5, 100))
    dialog = client.get("/").text.split('id="share-options"', 1)[1]
    links = re.findall(r"<a [^>]*>", dialog.split("</dialog>", 1)[0])
    assert ['target="_blank"' in a for a in links] == [True, False, False]
    assert ["phone-only" in a for a in links] == [False, False, True]


def test_finish_swaps_in_the_share_dialog(client):
    start(client, ("Squat", 5, 100), finished=False)
    page = client.post("/finish").text
    assert len(hrefs(page)) == 3
