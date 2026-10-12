"""The log panel's HTMX wiring, re-fill, time zone and cookie in a real browser.
What the server returns is tested in tests/test_logging.py; these check that
the browser actually swaps it in."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from helpers import htmx_done, log_set
from playwright.sync_api import Page, Route, expect


@pytest.fixture
def app(page: Page) -> Page:
    page.goto("/")
    # Survives only as long as the page does, so it shows nothing reloaded it
    page.evaluate("window.sameDocument = true")
    return page


def chips(page: Page, exercise: str):
    return page.locator(".card", has_text=exercise).locator(".set")


def assert_no_reload(page: Page) -> None:
    assert page.evaluate("window.sameDocument") is True


def test_logging_a_set_swaps_in_the_cards_top_bar_and_form(app: Page):
    log_set(app, "Back Squat", "5", "100")

    expect(chips(app, "Back Squat")).to_have_text(["5 × 100 kg"])
    expect(app.locator(".workout-time")).to_contain_text("started")
    expect(app.get_by_role("button", name="Finish")).to_be_visible()
    expect(app.locator(".last-logged-name")).to_have_text("Back Squat")
    # The form came back pre-filled for the next set
    expect(app.get_by_label("Exercise")).to_have_value("Back Squat")
    expect(app.get_by_label("Reps")).to_have_value("5")
    expect(app.get_by_label("kg")).to_have_value("100")
    assert_no_reload(app)


def test_an_invalid_set_shows_the_pill_and_keeps_what_was_typed(app: Page):
    log_set(app, "Back Squat", "5", "100")

    log_set(app, "Back Squat", "five", "100")

    expect(app.locator("#log-error")).to_contain_text("Reps must be a whole number")
    expect(app.get_by_label("Reps")).to_have_value("five")
    expect(chips(app, "Back Squat")).to_have_count(1)
    assert_no_reload(app)


def test_log_set_is_disabled_while_its_request_is_in_flight(app: Page):
    held: list[Route] = []
    app.route("**/sets", lambda route: held.append(route))  # held until released
    app.get_by_label("Exercise").fill("Back Squat")
    app.get_by_label("Reps").fill("5")
    app.get_by_label("kg").fill("100")
    log_set_button = app.locator("#log-set")

    log_set_button.click()
    expect(log_set_button).to_be_disabled()
    # A second tap. A disabled button ignores it, so nothing is sent.
    app.evaluate("document.getElementById('log-set').click()")
    app.wait_for_timeout(300)
    assert len(held) == 1

    held[0].continue_()
    expect(chips(app, "Back Squat")).to_have_count(1)
    expect(log_set_button).to_be_enabled()


def test_typing_a_logged_name_refills_only_reps_and_kg(app: Page):
    log_set(app, "Squat", "5", "100")
    log_set(app, "Bench Press", "8", "60")
    name = app.get_by_label("Exercise")

    with htmx_done(app, "htmx:afterRequest"):
        name.fill("squat")

    expect(app.get_by_label("Reps")).to_have_value("5")
    expect(app.get_by_label("kg")).to_have_value("100")
    # The name field wasn't swapped: it keeps the user's spelling and focus,
    # so the keyboard stays up
    expect(name).to_have_value("squat")
    expect(name).to_be_focused()


def test_tapping_a_card_fills_the_form_and_clears_the_pill(app: Page):
    log_set(app, "Squat", "5", "100")
    log_set(app, "Bench Press", "8", "60")
    log_set(app, "Bench Press", "", "60")
    expect(app.locator("#log-error")).to_be_visible()

    with htmx_done(app):
        app.locator(".card-pick", has_text="Squat").tap()

    expect(app.locator("#log-error")).to_have_count(0)
    expect(app.get_by_label("Exercise")).to_have_value("Squat")
    expect(app.get_by_label("Reps")).to_have_value("5")
    expect(app.get_by_label("kg")).to_have_value("100")


@pytest.mark.browser_context_args(timezone_id="Asia/Kolkata")
def test_clock_times_use_the_browsers_time_zone(app: Page):
    # UTC+5:30 all year, so it can never be mistaken for the server's UTC
    kolkata = ZoneInfo("Asia/Kolkata")
    before = datetime.now(UTC)

    log_set(app, "Back Squat", "5", "100")

    after = datetime.now(UTC)
    started = app.locator(".workout-time").inner_text()
    local_times = {f"started {t.astimezone(kolkata):%H:%M}" for t in (before, after)}
    assert started in local_times
    assert started != f"started {before:%H:%M}"


def test_the_workout_survives_a_reload(app: Page):
    log_set(app, "Back Squat", "5", "100")
    log_set(app, "Back Squat", "5", "100")

    app.reload()

    expect(chips(app, "Back Squat")).to_have_text(["5 × 100 kg", "5 × 100 kg"])
    expect(app.locator(".workout-time")).to_contain_text("started")
    expect(app.locator(".last-logged-name")).to_have_text("Back Squat")


def test_suggestions_wait_until_typing_pauses(app: Page):
    # The browser's dropdown can't be seen by the tests, but whether the field
    # is linked to it can: unlinked while typing, linked again after a pause
    name = app.get_by_label("Exercise")
    expect(name).to_have_attribute("list", "exercise-suggestions")

    name.press_sequentially("Squ", delay=100)
    expect(name).not_to_have_attribute("list", "exercise-suggestions")
    name.press("Backspace")
    expect(name).not_to_have_attribute("list", "exercise-suggestions")

    expect(name).to_have_attribute("list", "exercise-suggestions", timeout=1000)


# --- Clear Exercise (DAI-29) -------------------------------------------------


def test_clear_exercise_only_shows_while_the_field_has_text(app: Page):
    name = app.get_by_label("Exercise")
    clear = app.get_by_role("button", name="Clear")
    expect(clear).to_be_hidden()

    name.fill("Squat")
    expect(clear).to_be_visible()

    name.fill("")
    expect(clear).to_be_hidden()


def test_clear_exercise_sits_beside_the_field_and_lines_up_with_it(app: Page):
    name = app.get_by_label("Exercise")
    name.fill("Squat")
    field = name.bounding_box()
    circle = app.locator(".clear-field svg").bounding_box()

    assert circle["x"] >= field["x"] + field["width"]  # outside the box
    assert circle["width"] == circle["height"] == 30
    field_middle = field["y"] + field["height"] / 2
    assert abs(circle["y"] + circle["height"] / 2 - field_middle) <= 1


def test_the_field_keeps_its_width_when_clear_exercise_appears(app: Page):
    name = app.get_by_label("Exercise")
    empty_width = name.bounding_box()["width"]

    name.fill("Squat")

    assert name.bounding_box()["width"] == empty_width


def test_clear_exercise_empties_the_form_and_keeps_the_keyboard_up(app: Page):
    log_set(app, "Squat", "5", "100")
    name = app.get_by_label("Exercise")
    name.focus()

    with htmx_done(app, "htmx:afterRequest"):
        app.get_by_role("button", name="Clear").tap()

    expect(name).to_have_value("")
    expect(name).to_be_focused()
    # A new exercise won't have the same reps and kg. A blank name re-fills
    # nothing, so they stay empty
    expect(app.get_by_label("Reps")).to_have_value("")
    expect(app.get_by_label("kg")).to_have_value("")
    expect(app.get_by_role("button", name="Clear")).to_be_hidden()


def test_clear_exercise_focuses_the_field_when_it_was_not_focused(app: Page):
    log_set(app, "Squat", "5", "100")
    name = app.get_by_label("Exercise")
    expect(name).not_to_be_focused()

    app.get_by_role("button", name="Clear").tap()

    expect(name).to_have_value("")
    expect(name).to_be_focused()


def test_typing_the_cleared_name_again_still_refills(app: Page):
    # HTMX only asks when the name has changed since it last asked, so it must
    # see the clear, or retyping the same name would send nothing
    log_set(app, "Squat", "5", "100")
    log_set(app, "Bench Press", "8", "60")
    name = app.get_by_label("Exercise")
    with htmx_done(app, "htmx:afterRequest"):
        name.fill("Squat")
    expect(app.get_by_label("Reps")).to_have_value("5")

    with htmx_done(app, "htmx:afterRequest"):
        app.get_by_role("button", name="Clear").tap()
    with htmx_done(app, "htmx:afterRequest"):
        name.fill("Squat")

    expect(app.get_by_label("Reps")).to_have_value("5")
    expect(app.get_by_label("kg")).to_have_value("100")


def test_clear_exercise_works_after_an_error_swaps_the_form(app: Page):
    log_set(app, "Squat", "", "100")
    expect(app.locator("#log-error")).to_be_visible()

    app.get_by_role("button", name="Clear").tap()

    expect(app.get_by_label("Exercise")).to_have_value("")
    expect(app.get_by_label("kg")).to_have_value("")
