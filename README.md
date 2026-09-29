# Fianna Fit

Low-friction workout logger. FastAPI + Jinja2 + HTMX, managed with [uv](https://docs.astral.sh/uv/).

## Run locally

```sh
uv sync                                          # create .venv and install deps from uv.lock
uv run uvicorn fiannafit.main:app --reload       # serve on http://127.0.0.1:8000
```

## Test

```sh
uv run pytest
```

## Lint & format

```sh
uv run ruff check        # lint
uv run ruff format       # format
```
