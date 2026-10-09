"""Undo, Finish and New Workout in a real browser (DAI-11 step 5): the confirm
dialog's wiring, and the swaps. What the server returns is tested in
tests/test_workout_actions.py."""

import re

import pytest
from helpers import htmx_done, log_set
from playwright.sync_api import Page, Route, expect


@pytest.fixture
def app(page: Page) -> Page:
    page.goto("/")
    # Survives only as long as the page does, so it shows nothing reloaded it
    page.evaluate("window.sameDocument = true")
    return page


@pytest.fixture
def requests_to(page: Page):
    """The paths of requests the page sends, from here on."""
    sent: list[str] = []
    page.on("request", lambda request: sent.append(request.url.split("/", 3)[3]))
    return sent


def chips(page: Page, exercise: str):
    return page.locator(".card", has_text=exercise).locator(".set")


def assert_no_reload(page: Page) -> None:
    assert page.evaluate("window.sameDocument") is True


def dialog(page: Page):
    return page.locator("#confirm")


def finish(page: Page) -> None:
    page.get_by_role("button", name="Finish").click()
    with htmx_done(page):
        dialog(page).get_by_role("button", name="Finish").click()


# --- Undo ---------------------------------------------------------------------


def test_undo_removes_the_set_and_puts_it_in_the_form(app: Page):
    log_set(app, "Bench Press", "8", "60")
    log_set(app, "Bench Press", "6", "62.5")

    with htmx_done(app):
        app.get_by_role("button", name="Undo").click()

    expect(chips(app, "Bench Press")).to_have_text(["8 × 60 kg"])
    expect(app.locator(".last-logged .set")).to_have_text("8 × 60 kg")
    expect(app.get_by_label("Exercise")).to_have_value("Bench Press")
    expect(app.get_by_label("Reps")).to_have_value("6")
    expect(app.get_by_label("kg")).to_have_value("62.5")
    assert_no_reload(app)


def test_logging_after_undo_puts_the_set_back(app: Page):
    log_set(app, "Bench Press", "8", "60")
    with htmx_done(app):
        app.get_by_role("button", name="Undo").click()
    expect(app.locator(".card")).to_have_count(0)

    with htmx_done(app):
        app.locator("#log-set").click()

    expect(chips(app, "Bench Press")).to_have_text(["8 × 60 kg"])


def test_a_double_tap_on_undo_removes_one_set(app: Page, requests_to: list[str]):
    log_set(app, "Squat", "5", "100")
    log_set(app, "Squat", "5", "105")
    held: list[Route] = []
    app.route("**/undo", lambda route: held.append(route))  # held until released
    undo = app.get_by_role("button", name="Undo")

    undo.click()
    expect(undo).to_be_disabled()
    app.evaluate("document.querySelector('.last-logged .btn').click()")
    app.wait_for_timeout(300)
    assert requests_to.count("undo") == 1

    with htmx_done(app):
        held[0].continue_()
    expect(chips(app, "Squat")).to_have_text(["5 × 100 kg"])


def test_a_double_tap_on_undo_after_the_response_removes_one_set(app: Page):
    # The second tap lands on the new Undo button, which offers the set now
    # last. It's disabled for a moment, so that set stays.
    log_set(app, "Squat", "5", "100")
    log_set(app, "Squat", "5", "105")
    log_set(app, "Squat", "5", "110")

    with htmx_done(app):
        app.get_by_role("button", name="Undo").click()
    app.evaluate("document.querySelector('.last-logged .btn').click()")
    app.wait_for_timeout(300)

    expect(chips(app, "Squat")).to_have_text(["5 × 100 kg", "5 × 105 kg"])
    # Once a double tap would be over, Undo works again
    expect(app.get_by_role("button", name="Undo")).to_be_enabled()
    with htmx_done(app):
        app.get_by_role("button", name="Undo").click()
    expect(chips(app, "Squat")).to_have_text(["5 × 100 kg"])


# --- The confirm dialog -----------------------------------------------------------


def test_finish_asks_in_the_dialog_with_cancel_focused(app: Page):
    log_set(app, "Squat", "5", "100")

    app.get_by_role("button", name="Finish").click()

    expect(dialog(app)).to_be_visible()
    expect(dialog(app).locator("h2")).to_have_text("Finish Workout?")
    expect(dialog(app).locator("p")).to_have_text("You can't add sets after finishing.")
    expect(dialog(app).get_by_role("button", name="Cancel")).to_be_focused()


@pytest.mark.parametrize("how", ["cancel", "escape", "backdrop"])
def test_backing_out_of_the_dialog_sends_nothing(
    app: Page, requests_to: list[str], how: str
):
    log_set(app, "Squat", "5", "100")
    app.get_by_role("button", name="Finish").click()
    expect(dialog(app)).to_be_visible()

    if how == "cancel":
        dialog(app).get_by_role("button", name="Cancel").click()
    elif how == "escape":
        app.keyboard.press("Escape")
    else:
        app.touchscreen.tap(8, 8)  # the dimmed backdrop, top left

    expect(dialog(app)).to_be_hidden()
    app.wait_for_timeout(300)
    assert "finish" not in requests_to
    expect(app.get_by_role("button", name="Finish")).to_be_visible()
    expect(app.get_by_label("Exercise")).to_be_visible()


def test_a_cancelled_question_is_never_sent_later(app: Page, requests_to: list[str]):
    log_set(app, "Squat", "5", "100")
    app.get_by_role("button", name="Finish").click()
    dialog(app).get_by_role("button", name="Cancel").click()

    finish(app)

    assert requests_to.count("finish") == 1


def test_escape_after_an_earlier_confirm_sends_nothing(
    app: Page, requests_to: list[str]
):
    # The dialog remembers how it was last closed: Finish's confirm mustn't
    # carry over and delete the workout when New Workout is escaped
    log_set(app, "Squat", "5", "100")
    finish(app)

    app.get_by_role("button", name="New Workout").click()
    app.keyboard.press("Escape")

    expect(dialog(app)).to_be_hidden()
    app.wait_for_timeout(300)
    assert "new-workout" not in requests_to
    expect(app.get_by_role("button", name="Share Workout")).to_be_visible()


# --- Finish and New Workout ---------------------------------------------------------


def test_finish_shows_the_finished_screen(app: Page):
    log_set(app, "Squat", "5", "100")

    finish(app)

    expect(app.locator(".workout-time")).to_have_text(
        re.compile(r"^\d\d:\d\d–\d\d:\d\d$")
    )
    expect(app.get_by_role("button", name="New Workout")).to_be_visible()
    expect(app.get_by_role("button", name="Share Workout")).to_be_visible()
    expect(app.get_by_label("Exercise")).to_have_count(0)
    expect(app.locator(".card-pick")).to_have_count(0)
    expect(chips(app, "Squat")).to_have_text(["5 × 100 kg"])
    assert_no_reload(app)


def test_new_workout_warns_then_starts_afresh(app: Page):
    log_set(app, "Squat", "5", "100")
    finish(app)

    app.get_by_role("button", name="New Workout").click()
    expect(dialog(app).locator("h2")).to_have_text("Start a New Workout?")
    expect(dialog(app).locator("p")).to_have_text(
        "This workout hasn't been shared. Starting a new one deletes it."
    )
    with htmx_done(app):
        dialog(app).get_by_role("button", name="Delete and Start New").click()

    expect(app.locator(".empty")).to_have_text(
        "No workout yet. Log your first set to start."
    )
    expect(app.get_by_role("button", name="New Workout")).to_have_count(0)
    expect(app.get_by_label("Exercise")).to_have_value("")
    # Recent names are kept as suggestions
    expect(app.locator("#exercise-suggestions option")).to_have_count(1)
    assert_no_reload(app)


def test_finished_survives_a_reload(app: Page):
    log_set(app, "Squat", "5", "100")
    finish(app)

    app.reload()

    expect(app.get_by_role("button", name="Share Workout")).to_be_visible()
    expect(app.get_by_label("Exercise")).to_have_count(0)
