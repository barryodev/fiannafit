from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from fiannafit import session as workout_session
from fiannafit.session import SessionFull, load_session, save_session

BASE_DIR = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    workout_session.check_config()
    yield


app = FastAPI(lifespan=lifespan)
app.middleware("http")(workout_session.clear_invalid_session_cookie)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/hello", response_class=HTMLResponse)
def hello(request: Request):
    # HTML fragment that HTMX swaps into the page
    return templates.TemplateResponse(
        request, "_hello.html", {"now": datetime.now(UTC).strftime("%H:%M:%S")}
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
