# Fianna Fit

Low-friction workout logger. FastAPI + Jinja2 + HTMX, managed with [uv](https://docs.astral.sh/uv/).

## Run locally

```sh
uv sync                                          # create .venv and install deps from uv.lock
cp .env.example .env                             # once; then set SESSION_SECRET_KEY in it
uv run --env-file .env uvicorn fiannafit.main:app --reload   # serve on http://127.0.0.1:8000
```

The app refuses to start without `SESSION_SECRET_KEY`, which signs the workout cookie.
Until the logging UI exists (DAI-11), the temporary `/debug/...` routes can be tried from
http://localhost:8000/docs (localhost, so the browser keeps the Secure cookie over http).

## Test

```sh
uv run pytest
```

## Lint & format

```sh
uv run ruff check        # lint
uv run ruff format       # format
```
