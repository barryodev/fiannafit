"""Share Workout in a real browser (DAI-9): the tap hands the summary to the
share sheet. Neither test browser has a real share sheet, so navigator.share
is replaced with one that records what it was given. What the page carries
is tested in tests/test_share_button.py."""

import re

import pytest
from helpers import htmx_done, log_set
from playwright.sync_api import Page

# Stands in for the share sheet. window.shareFails makes it fail the way a
# real one does, e.g. "AbortError" when the user closes it.
FAKE_SHARE = """
window.shared = [];
Object.defineProperty(navigator, "share", {
  configurable: true,
  value: (data) => {
    // A real share sheet refuses to open unless a tap has just happened
    window.shared.push({ text: data.text, tapped: navigator.userActivation.isActive });
    return window.shareFails
      ? Promise.reject(new DOMException(`Share failed: ${window.shareFails}`, window.shareFails))
      : Promise.resolve();
  },
});
"""


@pytest.fixture
def app(page: Page) -> Page:
    page.add_init_script(FAKE_SHARE)
    page.goto("/")
    return page


@pytest.fixture
def page_errors(page: Page) -> list[str]:
    """Uncaught errors in the page, including rejected promises nobody handled."""
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    return errors


def finished_workout(page: Page) -> None:
    log_set(page, "Bench Press", "8", "60")
    log_set(page, "Bench Press", "6", "62.5")
    log_set(page, "Pull-up", "10", "0")
    page.get_by_role("button", name="Finish").click()
    with htmx_done(page):
        page.locator("#confirm").get_by_role("button", name="Finish").click()


def share(page: Page) -> None:
    page.get_by_role("button", name="Share Workout").click()


def shared(page: Page) -> list[dict]:
    """What the share sheet was given, once it's been opened."""
    page.wait_for_function("() => window.shared.length > 0", timeout=5000)
    return page.evaluate("window.shared")


def test_share_hands_the_summary_to_the_share_sheet(app: Page):
    finished_workout(app)
    share(app)

    [sent] = shared(app)
    assert re.fullmatch(
        r"🏋️ Fianna Fit workout, \w{3} \d{1,2} \w{3}, "
        r"\d\d:\d\d–\d\d:\d\d \(\d+ min\)\n"
        r"\n"
        r"\*Bench Press\*\n"
        r"8 × 60 kg · 6 × 62\.5 kg\n"
        r"\n"
        r"\*Pull-up\*\n"
        r"10 reps\n"
        r"\n"
        r"Logged with fiannafit\.barryodev\.io",
        sent["text"],
    ), sent["text"]


def test_share_is_called_straight_from_the_tap(app: Page):
    finished_workout(app)
    share(app)
    assert shared(app)[0]["tapped"] is True


def test_share_works_after_reopening_the_app(app: Page):
    finished_workout(app)
    app.reload()
    share(app)
    assert "*Bench Press*\n8 × 60 kg · 6 × 62.5 kg" in shared(app)[0]["text"]


def test_closing_the_share_sheet_is_not_an_error(app: Page, page_errors):
    finished_workout(app)
    app.evaluate("window.shareFails = 'AbortError'")
    share(app)
    assert len(shared(app)) == 1
    app.wait_for_timeout(200)  # time for an unhandled rejection to surface
    assert page_errors == []


def test_other_share_failures_are_not_hidden(app: Page):
    # Proves the test above would catch an error, as well as not hiding real ones
    finished_workout(app)
    app.evaluate("window.shareFails = 'NotAllowedError'")
    with app.expect_event("pageerror") as error:
        share(app)
    assert "Share failed: NotAllowedError" in str(error.value)
