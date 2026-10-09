from contextlib import contextmanager

from playwright.sync_api import Page


@contextmanager
def htmx_done(page: Page, event: str = "htmx:afterSettle"):
    """Wait for HTMX to finish what the block starts.

    htmx:afterSettle: the response is swapped in and HTMX has wired up the new
    content. Until then a swapped-in form isn't HTMX's yet, and a tap would
    submit it as a plain page load. A response that swaps nothing (204) never
    settles; wait for htmx:afterRequest instead.
    """
    page.evaluate(
        """event => {
            window.htmxDone = false;
            document.addEventListener(event, () => (window.htmxDone = true), { once: true });
        }""",
        event,
    )
    yield
    # Not an awaited promise: wait_for_function times out if HTMX never gets there
    page.wait_for_function("() => window.htmxDone", timeout=5000)


def log_set(page: Page, exercise: str, reps: str, kg: str) -> None:
    """Log a set the way a user would: type, then tap Log Set."""
    name = page.get_by_label("Exercise")
    # A changed name re-fills reps and kg after a pause; let that land first.
    # The same name sends nothing, so there's nothing to wait for.
    if name.input_value() != exercise:
        with htmx_done(page, "htmx:afterRequest"):
            name.fill(exercise)
    page.get_by_label("Reps").fill(reps)
    page.get_by_label("kg").fill(kg)
    with htmx_done(page):
        page.locator("#log-set").click()


def log_set_via_dom(page: Page, exercise: str, reps: str, kg: str) -> None:
    """Log a set without Playwright's fill() and click(), which scroll their
    target into view and so would move the page. For layout and scroll tests.

    Setting a value from JS fires no input event, so there's no re-fill.
    """
    with htmx_done(page):
        page.evaluate(
            """([exercise, reps, kg]) => {
                const form = document.getElementById("log-panel");
                form.elements.exercise.value = exercise;
                form.elements.reps.value = reps;
                form.elements.kg.value = kg;
                document.getElementById("log-set").click();
            }""",
            [exercise, reps, kg],
        )
