"""Share Workout in a real browser (DAI-9): the tap hands the summary to the
share sheet, or, without one, opens our dialog of other ways to send it.
Neither test browser has a real share sheet, so navigator.share is replaced
with one that records what it was given. What the page carries is tested in
tests/test_share_button.py."""

import re

import pytest
from helpers import htmx_done, log_set
from playwright.sync_api import Browser, Page, expect

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
        r"🏋️ TapRep workout, \w{3} \d{1,2} \w{3}, "
        r"\d\d:\d\d–\d\d:\d\d \(\d+ min\)\n"
        r"\n"
        r"\*Bench Press\*\n"
        r"8 × 60 kg · 6 × 62\.5 kg\n"
        r"\n"
        r"\*Pull-up\*\n"
        r"10 reps\n"
        r"\n"
        r"Logged with taprep\.barryodev\.io",
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


def test_with_a_share_sheet_the_dialog_stays_closed(app: Page):
    finished_workout(app)
    share(app)
    shared(app)
    expect(app.locator("#share-options")).not_to_be_visible()


# --- Without a share sheet: the dialog -----------------------------------------

# Most desktop browsers. The clipboard is faked as well: the test browsers'
# real clipboards need permissions WebKit can't be given.
NO_SHARE_SHEET = """
Object.defineProperty(navigator, "share", { configurable: true, value: undefined });
window.copied = [];
Object.defineProperty(navigator, "clipboard", {
  configurable: true,
  value: { writeText: async (text) => { window.copied.push(text); } },
});
"""


@pytest.fixture
def no_sheet(page: Page) -> Page:
    page.add_init_script(NO_SHARE_SHEET)
    page.goto("/")
    finished_workout(page)
    return page


def options(page: Page):
    return page.locator("#share-options")


def test_without_a_share_sheet_share_opens_the_dialog(no_sheet: Page):
    # A phone in an in-app browser (Instagram, Facebook): SMS is offered
    share(no_sheet)
    expect(options(no_sheet)).to_be_visible()
    expect(options(no_sheet).get_by_role("heading")).to_have_text("Share Workout")
    expect(options(no_sheet).locator(".share-options .btn:visible")).to_have_text(
        ["Copy to Clipboard", "WhatsApp", "Email", "SMS"]
    )


@pytest.fixture
def desktop(browser: Browser, browser_context_args) -> Page:
    """A desktop browser: a mouse, not a touch screen, and no share sheet."""
    context = browser.new_context(
        **browser_context_args | {"is_mobile": False, "has_touch": False}
    )
    page = context.new_page()
    page.add_init_script(NO_SHARE_SHEET)
    page.goto("/")
    finished_workout(page)
    yield page
    context.close()


def test_on_a_desktop_the_dialog_leaves_out_sms(desktop: Page):
    # sms: links do nothing there
    share(desktop)
    expect(options(desktop).locator(".share-options .btn:visible")).to_have_text(
        ["Copy to Clipboard", "WhatsApp", "Email"]
    )


def test_copy_puts_the_summary_on_the_clipboard(no_sheet: Page):
    summary = no_sheet.locator("#log-panel").get_attribute("data-summary")
    share(no_sheet)
    copy = options(no_sheet).locator("[data-copy]")  # its name changes
    copy.click()

    expect(copy).to_have_text("Copied")
    assert no_sheet.evaluate("window.copied") == [summary]
    assert "*Bench Press*\n8 × 60 kg · 6 × 62.5 kg" in summary
    expect(options(no_sheet)).to_be_visible()  # stays open
    # Back to its label after a moment, even when tapped twice
    copy.click()
    expect(copy).to_have_text("Copy to Clipboard", timeout=5000)
    assert len(no_sheet.evaluate("window.copied")) == 2


def test_links_carry_the_summary(no_sheet: Page):
    summary = no_sheet.locator("#log-panel").get_attribute("data-summary")
    share(no_sheet)
    whatsapp = options(no_sheet).get_by_role("link", name="WhatsApp")
    expect(whatsapp).to_have_attribute(
        "href", re.compile(r"^https://api\.whatsapp\.com/send\?text=")
    )
    # Decoded by the browser itself, as the app it opens would
    sent = whatsapp.evaluate("a => new URL(a.href).searchParams.get('text')")
    assert sent == summary


def test_close_closes_the_dialog(no_sheet: Page):
    share(no_sheet)
    options(no_sheet).get_by_role("button", name="Close").click()
    expect(options(no_sheet)).not_to_be_visible()


def test_tapping_the_backdrop_closes_the_dialog(no_sheet: Page):
    share(no_sheet)
    expect(options(no_sheet)).to_be_visible()
    no_sheet.mouse.click(5, 5)  # outside the dialog, on the dimmed backdrop
    expect(options(no_sheet)).not_to_be_visible()


def test_tapping_inside_the_dialog_keeps_it_open(no_sheet: Page):
    share(no_sheet)
    options(no_sheet).get_by_role("heading").click()
    expect(options(no_sheet)).to_be_visible()


# --- Once shared, New Workout stops warning ----------------------------------------


def new_workout(page: Page):
    return page.get_by_role("button", name="New Workout")


def expect_unshared(page: Page) -> None:
    expect(new_workout(page)).to_have_attribute(
        "data-confirm-action", "Delete and Start New"
    )


def expect_shared(page: Page) -> None:
    expect(new_workout(page)).to_have_attribute("data-confirm-action", "Start New")


def test_after_sharing_new_workout_asks_without_the_warning(app: Page):
    finished_workout(app)
    expect_unshared(app)
    with app.expect_response("**/shared"):
        share(app)

    new_workout(app).click()
    confirm = app.locator("#confirm")
    expect(confirm.locator("p")).to_have_text(
        "You've shared this workout. Starting a new one clears it from here."
    )
    with htmx_done(app):
        confirm.get_by_role("button", name="Start New").click()
    expect(app.locator(".empty")).to_have_text(
        "No workout yet. Log your first set to start."
    )


def test_shared_is_remembered_after_reopening_the_app(app: Page):
    finished_workout(app)
    with app.expect_response("**/shared"):
        share(app)
    app.reload()
    expect_shared(app)


def test_closing_the_share_sheet_keeps_the_warning(app: Page):
    finished_workout(app)
    app.evaluate("window.shareFails = 'AbortError'")
    sent: list[str] = []
    app.on("request", lambda request: sent.append(request.url))
    share(app)
    shared(app)
    app.wait_for_timeout(300)  # time for a request that shouldn't be sent
    assert not [url for url in sent if url.endswith("/shared")]
    expect_unshared(app)


def test_if_the_share_isnt_noted_the_warning_stays(app: Page, page_errors):
    # E.g. no signal in the gym: the share sheet works, the request doesn't
    finished_workout(app)
    app.route("**/shared", lambda route: route.abort())
    with app.expect_event("requestfailed"):
        share(app)
    app.wait_for_timeout(200)
    expect_unshared(app)
    assert page_errors == []


def test_copy_counts_as_shared(no_sheet: Page):
    share(no_sheet)
    with no_sheet.expect_response("**/shared"):
        options(no_sheet).locator("[data-copy]").click()
    expect_shared(no_sheet)
    expect(options(no_sheet)).to_be_visible()  # the top bar changed, not the panel


@pytest.mark.parametrize("label", ["WhatsApp", "Email", "SMS"])
def test_tapping_a_link_counts_as_shared(no_sheet: Page, label: str):
    # Stay on the page: the test can't follow it to WhatsApp or a mail app
    no_sheet.evaluate(
        "window.addEventListener('click', (event) => event.preventDefault())"
    )
    share(no_sheet)
    with no_sheet.expect_response("**/shared"):
        options(no_sheet).get_by_role("link", name=label).click()
    expect_shared(no_sheet)
