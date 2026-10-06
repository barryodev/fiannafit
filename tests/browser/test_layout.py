"""Layout rules for the log panel that broke during DAI-11 and were only
caught by checking by hand.

Sets are logged through the DOM (log_set_via_dom), not with fill() and click():
those scroll their target into view, which for the sticky panel scrolls the
page and would look like a jump the app didn't make.
"""

import pytest
from helpers import log_set_via_dom
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
