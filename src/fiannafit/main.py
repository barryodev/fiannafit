from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).parent

app = FastAPI()
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
