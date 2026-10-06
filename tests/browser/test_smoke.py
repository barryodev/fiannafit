from playwright.sync_api import Page


def test_page_loads_with_its_static_files(page: Page):
    # The TestClient renders the templates but never fetches /static, so a bad
    # path to the CSS, HTMX, app.js or the font only shows up here.
    problems = []
    page.on("console", lambda m: m.type == "error" and problems.append(m.text))
    page.on("pageerror", lambda e: problems.append(str(e)))
    page.on("requestfailed", lambda r: problems.append(f"failed: {r.url}"))
    page.on(
        "response", lambda r: r.status >= 400 and problems.append(f"{r.status} {r.url}")
    )

    page.goto("/")
    page.wait_for_load_state("networkidle")

    assert page.evaluate("typeof htmx") == "object"
    assert page.evaluate("typeof showCurrentExercise") == "function"  # app.js
    # Carbon Black, from app.css
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == (
        "rgb(33, 29, 26)"
    )
    # Loads the phone's own Roboto if it has one, otherwise the vendored file
    font_status = page.evaluate("""async () => {
        const roboto = [...document.fonts].find((f) => f.family.replaceAll('"', "") === "Roboto");
        try { await roboto.load(); } catch {}
        return roboto.status;
    }""")
    assert font_status == "loaded"
    assert problems == []
