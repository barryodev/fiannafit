# Fianna Fit

Low-friction workout logger. FastAPI + Jinja2 + HTMX, managed with [uv](https://docs.astral.sh/uv/).

## Run locally

```sh
uv sync                                          # create .venv and install deps from uv.lock
cp .env.example .env                             # once; then set SESSION_SECRET_KEY in it
uv run --env-file .env uvicorn fiannafit.main:app --reload   # serve on http://127.0.0.1:8000
```

The app refuses to start without `SESSION_SECRET_KEY`, which signs the workout cookie.
Open http://localhost:8000 (localhost, not 127.0.0.1, so the browser keeps the Secure
cookie over http).

## Try it on your phone

```sh
ops/local-phone-test.sh
```

Serves the app over HTTPS on your home network and prints the address to open on the
phone (same Wi-Fi). The workout cookie is Secure, so it needs HTTPS; the script makes a
self-signed certificate on first run, kept in `~/.local/share/fiannafit-dev/`, outside the
repo. The phone warns about it once per address: tap through to continue.

## Test

```sh
uv run playwright install chromium webkit   # once: the browsers for tests/browser
uv run pytest
```

Every run includes the browser tests in `tests/browser/`, in Chromium and WebKit (the
nearest stand-in for iOS Safari). They start the app over HTTPS with a throwaway
certificate, so the Secure session cookie works as in production.

```sh
uv run pytest tests/browser --browser chromium              # one engine only
uv run pytest tests/browser --show                           # watch them run
```

`--show` opens the browser and slows each step down (`--headed --slowmo 300`), in
Chromium only. On a desktop with display scaling (e.g. GNOME's text scaling), a headed
WebKit window zooms the page, so the layout tests that compare widths fail there.
Headless WebKit isn't affected.

## Lint & format

```sh
uv run ruff check        # lint
uv run ruff format       # format
```
