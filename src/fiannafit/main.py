from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Form, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from fiannafit import session as workout_session
from fiannafit.display import TZ_COOKIE, clock, format_set, parse_timezone
from fiannafit.forms import FormValues, InvalidSet, parse_set, prefill, suggestions
from fiannafit.session import (
    Session,
    SessionFull,
    WorkoutFinished,
    load_session,
    normalise_name,
    save_session,
)

BASE_DIR = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    workout_session.check_config()
    yield


app = FastAPI(lifespan=lifespan)
app.middleware("http")(workout_session.clear_invalid_session_cookie)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.filters["set_text"] = format_set
templates.env.filters["clock"] = clock


def screen_context(
    request: Request,
    session: Session,
    form: FormValues | None = None,
    error: InvalidSet | None = None,
) -> dict:
    """What the templates need to draw the screen, or any part of it."""
    return {
        "workout": session.workout,
        "tz": parse_timezone(request.cookies.get(TZ_COOKIE)),
        "current_exercise": session.current_exercise(),
        "suggestions": suggestions(session),
        "form": form or prefill(session) or FormValues(),
        "error": error,
    }


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    session = load_session(request)
    return templates.TemplateResponse(
        request, "index.html", screen_context(request, session)
    )


@app.get("/log-form", response_class=HTMLResponse)
def log_form(request: Request, exercise: str = ""):
    """The log form pre-filled with this exercise's last set. Tapping a card
    swaps in the whole form; typing a name swaps in just reps and kg. 204 (no
    swap) if the exercise has no sets yet, so a new name keeps what's there."""
    session = load_session(request)
    form = prefill(session, normalise_name(exercise))
    if form is None:
        return Response(status_code=204)
    return templates.TemplateResponse(
        request, "_log_form.html", screen_context(request, session, form)
    )


@app.post("/sets", response_class=HTMLResponse)
def log_set(
    request: Request,
    exercise: Annotated[str, Form()] = "",
    reps: Annotated[str, Form()] = "",
    kg: Annotated[str, Form()] = "",
):
    """Log a set from the form. Fields are plain text and checked by parse_set,
    so every problem comes back as the same red pill, not FastAPI's JSON."""
    typed = FormValues(exercise, reps, kg)
    session = load_session(request)
    try:
        entry = parse_set(typed)
        session.log_set(entry.exercise, entry.reps, entry.weight_kg)
        response = templates.TemplateResponse(
            request,
            "_log_response.html",
            screen_context(request, session) | {"logged": True},
        )
        save_session(request, response, session)
        return response
    except InvalidSet as e:
        error = e
    except WorkoutFinished:
        error = InvalidSet(
            "This workout is finished. Start a new workout to log more sets.", ""
        )
    except SessionFull:
        error = InvalidSet(
            "This workout is too big to store any more sets. Share it to keep it.", ""
        )
    # Nothing was saved: redraw the form from the stored session, keeping what
    # was typed so it doesn't have to be entered again.
    return templates.TemplateResponse(
        request,
        "_log_response.html",
        screen_context(request, load_session(request), typed, error),
        status_code=422,
    )


@app.get("/healthz")
def healthz():
    # Liveness check used by ops/deploy.sh after a restart
    return {"status": "ok"}


# --- Temporary debug routes (DAI-8) -----------------------------------------
# A way to exercise the session cookie by hand (e.g. from /docs) until the
# logging UI exists. DAI-11 removes them.


@app.get("/debug/session")
def debug_session(request: Request):
    session = load_session(request)
    body = session.model_dump(mode="json")
    body["cookie_bytes"] = len(request.cookies.get(workout_session.COOKIE_NAME, ""))
    return body


@app.post("/debug/sets")
def debug_log_set(
    request: Request,
    exercise: str = Query(min_length=1),
    reps: int = Query(ge=1),
    weight_kg: float | None = Query(default=None, ge=0),
):
    session = load_session(request)
    session.log_set(exercise, reps, weight_kg)
    response = JSONResponse(session.model_dump(mode="json"))
    try:
        save_session(request, response, session)
    except SessionFull:
        return JSONResponse({"detail": "session full, set not saved"}, status_code=409)
    return response


@app.post("/debug/new-workout")
def debug_new_workout(request: Request):
    session = load_session(request)
    session.new_workout()
    response = JSONResponse(session.model_dump(mode="json"))
    save_session(request, response, session)
    return response
