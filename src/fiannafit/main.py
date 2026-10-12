from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from fiannafit import session as workout_session
from fiannafit.display import TZ_COOKIE, clock, format_set, parse_timezone
from fiannafit.forms import (
    FormValues,
    InvalidSet,
    parse_set,
    prefill,
    set_values,
    suggestions,
)
from fiannafit.session import (
    Session,
    SessionFull,
    WorkoutFinished,
    load_session,
    normalise_name,
    save_session,
)
from fiannafit.share import share_for

BASE_DIR = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    workout_session.check_config()
    yield


# No API docs: the routes serve HTML fragments to the page, not a public API
app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
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
    workout = session.workout
    tz = parse_timezone(request.cookies.get(TZ_COOKIE))
    finished = workout is not None and workout.ended_at is not None
    return {
        "workout": workout,
        "tz": tz,
        # In the page before the tap: the share sheet only opens straight after one
        "share": share_for(workout, tz) if finished else None,
        "current_exercise": session.current_exercise(),
        "latest": session.latest(),
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
    swap) if the exercise has no sets yet, so a new name keeps what's there,
    or if the name is blank, e.g. just cleared, which also keeps them."""
    session = load_session(request)
    name = normalise_name(exercise)
    form = prefill(session, name) if name else None
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
            screen_context(request, session) | {"whole_screen": True},
        )
        save_session(request, response, session)
        return response
    except InvalidSet as e:
        error = e
    except WorkoutFinished:
        # Sent from a page that's out of date, such as another tab: bring the
        # whole screen up to date, with the pill saying why nothing was logged
        error = InvalidSet(
            "This workout is finished. Start a new workout to log more sets.", ""
        )
        return templates.TemplateResponse(
            request,
            "_log_response.html",
            screen_context(request, session, error=error) | {"whole_screen": True},
            status_code=422,
        )
    except SessionFull:
        # There's always room left to finish and share (ROOM_TO_FINISH_BYTES)
        error = InvalidSet(
            "This workout is too big to store any more sets. "
            "Finish and share it to keep it.",
            "",
        )
    # Nothing was saved: redraw the form from the stored session, keeping what
    # was typed so it doesn't have to be entered again.
    return templates.TemplateResponse(
        request,
        "_log_response.html",
        screen_context(request, load_session(request), typed, error),
        status_code=422,
    )


def screen_update(
    request: Request,
    session: Session,
    form: FormValues | None = None,
    changed: bool = True,
    just_undone: bool = False,
) -> Response:
    """The log panel, cards and top bar, after Undo, Finish or New Workout.
    Saves the session only if it changed. Each of these also answers a request
    from an out-of-date page (another tab, a repeated tap) by showing how
    things are now, rather than with an error."""
    response = templates.TemplateResponse(
        request,
        "_log_response.html",
        screen_context(request, session, form)
        | {"whole_screen": True, "just_undone": just_undone},
    )
    if changed:
        save_session(request, response, session)
    return response


@app.post("/undo", response_class=HTMLResponse)
def undo(request: Request, logged_at: Annotated[str, Form()] = ""):
    """Remove the set the Undo button showed, if it's still the latest, and
    put it in the form: fix a number and log it again, or just log it again."""
    session = load_session(request)
    latest = session.latest()
    try:
        removed = session.delete_last_set(logged_at=datetime.fromisoformat(logged_at))
    except ValueError, WorkoutFinished:
        removed = None
    if removed is None:
        return screen_update(request, session, changed=False)
    exercise, _ = latest
    return screen_update(
        request, session, set_values(exercise.name, removed), just_undone=True
    )


@app.post("/finish", response_class=HTMLResponse)
def finish(request: Request):
    session = load_session(request)
    if session.workout is None:
        return screen_update(request, session, changed=False)
    session.finish()  # always fits: see ROOM_TO_FINISH_BYTES
    return screen_update(request, session)


@app.post("/shared", response_class=HTMLResponse)
def shared(request: Request):
    """Note that the workout was shared, from the share sheet, Copy or a link in
    the Share dialog (DAI-9), so New Workout stops warning that it hasn't been.
    Returns just the top bar: the Share dialog in the log panel may be open."""
    session = load_session(request)
    changed = True
    try:
        session.mark_shared()  # always fits: see ROOM_TO_FINISH_BYTES
    except ValueError:
        changed = False  # sent from a page that's out of date: no finished workout
    response = templates.TemplateResponse(
        request, "_top_bar.html", screen_context(request, session)
    )
    if changed:
        save_session(request, response, session)
    return response


@app.post("/new-workout", response_class=HTMLResponse)
def new_workout(request: Request):
    """Delete the current workout. Recent exercise names are kept."""
    session = load_session(request)
    session.new_workout()
    return screen_update(request, session)


@app.get("/healthz")
def healthz():
    # Liveness check used by ops/deploy.sh after a restart
    return {"status": "ok"}
