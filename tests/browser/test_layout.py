"""Layout rules for the log panel that broke during DAI-11 and were only
caught by checking by hand.

Sets are logged through the DOM (log_set_via_dom), not with fill() and click():
those scroll their target into view, which for the sticky panel scrolls the
page and would look like a jump the app didn't make.
"""

import pytest
from helpers import htmx_done, log_set_via_dom
from playwright.sync_api import Page, expect

LONGEST_NAME = "Single-Arm Dumbbell Romanian Deadlift XL"  # the 40 character limit


def box(page: Page, selector: str) -> dict:
    return page.locator(selector).bounding_box()


@pytest.mark.parametrize("width", [412, 360])
def test_the_log_panel_never_changes_height_or_moves_the_page(page: Page, width: int):
    page.set_viewport_size({"width": width, "height": 915})
    page.goto("/")
    empty_height = box(page, "#log-panel")["height"]

    log_set_via_dom(page, LONGEST_NAME, "5", "62.5")
    with_set_height = box(page, "#log-panel")["height"]
    scroll_before_error = page.evaluate("window.scrollY")

    # The longest error message, which wraps onto two lines
    log_set_via_dom(page, LONGEST_NAME, "5", "heavy")
    expect(page.locator("#log-error")).to_contain_text("Weight must be a number")

    assert with_set_height == empty_height
    assert box(page, "#log-panel")["height"] == empty_height
    assert page.evaluate("window.scrollY") == scroll_before_error


@pytest.mark.parametrize("width", [412, 360])
def test_the_error_pill_floats_20px_above_the_panel(page: Page, width: int):
    page.set_viewport_size({"width": width, "height": 915})
    page.goto("/")

    log_set_via_dom(page, "Back Squat", "", "100")

    pill, panel = box(page, "#log-error"), box(page, "#log-panel")
    assert panel["y"] - (pill["y"] + pill["height"]) == pytest.approx(20, abs=0.5)


@pytest.mark.parametrize("width", [412, 360])
def test_a_long_name_never_pushes_anything_off_screen(page: Page, width: int):
    page.set_viewport_size({"width": width, "height": 915})
    page.goto("/")

    log_set_via_dom(page, LONGEST_NAME, "5", "62.5")

    page_width = page.evaluate("document.documentElement.clientWidth")
    assert page.evaluate("document.documentElement.scrollWidth") == page_width
    undo = box(page, ".last-logged .btn")
    assert undo["x"] + undo["width"] <= page_width
    # Only the name is shortened, never the set Undo would remove
    last_set = page.locator(".last-logged .set")
    expect(last_set).to_have_text("5 × 62.5 kg")
    assert last_set.evaluate("el => el.scrollWidth <= el.clientWidth")


@pytest.mark.parametrize("width", [412, 360])
def test_undo_never_changes_the_panel_height_or_moves_the_page(page: Page, width: int):
    page.set_viewport_size({"width": width, "height": 915})
    page.goto("/")
    empty_height = box(page, "#log-panel")["height"]
    log_set_via_dom(page, "Back Squat", "5", "100")
    log_set_via_dom(page, LONGEST_NAME, "5", "62.5")
    scroll_before = page.evaluate("window.scrollY")

    with htmx_done(page):
        page.evaluate("document.querySelector('.last-logged .btn').click()")
    expect(page.locator(".last-logged-name")).to_have_text("Back Squat")
    assert box(page, "#log-panel")["height"] == empty_height
    # Undoing the only set leaves the Last line empty, still the same height.
    # Undo is briefly disabled after an Undo (against double taps), so wait.
    page.wait_for_selector(".last-logged .btn:enabled")
    with htmx_done(page):
        page.evaluate("document.querySelector('.last-logged .btn').click()")
    expect(page.locator(".last-logged-name")).to_have_count(0)

    assert box(page, "#log-panel")["height"] == empty_height
    assert page.evaluate("window.scrollY") == scroll_before


@pytest.mark.parametrize("width", [412, 360])
def test_the_dialogs_buttons_fit_inside_it(page: Page, width: int):
    page.set_viewport_size({"width": width, "height": 915})
    page.goto("/")
    log_set_via_dom(page, "Back Squat", "5", "100")
    page.get_by_role("button", name="Finish").click()
    with htmx_done(page):
        page.locator("#confirm-action").click()

    # The longest confirm label
    page.get_by_role("button", name="New Workout").click()

    dialog = box(page, "#confirm")
    for button in ("#confirm .btn-text", "#confirm-action"):
        b = box(page, button)
        assert b["x"] >= dialog["x"]
        assert b["x"] + b["width"] <= dialog["x"] + dialog["width"]
    # Its label stays on one line, even if it has to stack under Cancel. The
    # button's height can't show this: it stays 48px with two lines in it.
    label_lines = """el => {
        const range = document.createRange();
        range.selectNodeContents(el);
        return new Set([...range.getClientRects()].map(r => r.top)).size;
    }"""
    assert page.locator("#confirm-action").evaluate(label_lines) == 1
