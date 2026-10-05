"""The current workout, stored in a signed, compressed, HTTP-only cookie (DAI-8).

This is the only persistence in Phase 1: no database, no history.
"""

import logging
import os
from datetime import UTC, datetime
from typing import Literal

from fastapi import Request, Response
from itsdangerous import BadData, URLSafeTimedSerializer
from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)

COOKIE_NAME = "session"
MAX_AGE_SECONDS = 90 * 24 * 60 * 60  # 90 days from the last write
# Browsers drop cookies over ~4096 bytes (name + value + attributes)
MAX_COOKIE_BYTES = 3800
RECENT_EXERCISES_LIMIT = 10


class LoggedSet(BaseModel):
    reps: int
    weight_kg: float | None = None  # None for bodyweight
    logged_at: datetime


class Exercise(BaseModel):
    name: str
    sets: list[LoggedSet] = []


class Workout(BaseModel):
    started_at: datetime
    ended_at: datetime | None = None
    shared_at: datetime | None = None  # set by DAI-9
    exercises: list[Exercise] = []


class Session(BaseModel):
    """Everything the cookie holds. Bump `v` when the format changes."""

    v: Literal[1] = 1
    workout: Workout | None = None
    recent_exercises: list[str] = []  # most recent first

    def log_set(
        self,
        name: str,
        reps: int,
        weight_kg: float | None = None,
        now: datetime | None = None,
    ) -> None:
        """Add a set, starting the workout if there isn't one yet."""
        now = now or datetime.now(UTC)
        name = " ".join(name.split())
        if not name:
            raise ValueError("exercise name is empty")

        if self.workout is None:
            self.workout = Workout(started_at=now)
        exercise = next(
            (e for e in self.workout.exercises if e.name.casefold() == name.casefold()),
            None,
        )
        if exercise is None:
            exercise = Exercise(name=name)
            self.workout.exercises.append(exercise)
        exercise.sets.append(LoggedSet(reps=reps, weight_kg=weight_kg, logged_at=now))
        self._remember_exercise(exercise.name)

    def new_workout(self) -> None:
        """Drop the current workout. Recent exercise names are kept."""
        self.workout = None

    def _remember_exercise(self, name: str) -> None:
        others = [n for n in self.recent_exercises if n.casefold() != name.casefold()]
        self.recent_exercises = [name, *others][:RECENT_EXERCISES_LIMIT]


class SessionFull(Exception):
    """The session no longer fits in a cookie; the write was refused."""


def _serializer() -> URLSafeTimedSerializer:
    key = os.environ.get("SESSION_SECRET_KEY")
    if not key:
        raise RuntimeError(
            "SESSION_SECRET_KEY is not set. Locally, create .env from .env.example "
            "(see README); on the VM it comes from /etc/fiannafit/env."
        )
    return URLSafeTimedSerializer(key, salt="fiannafit.session")


def check_config() -> None:
    """Fail at startup, not on the first request, if the key is missing."""
    _serializer()


def encode(session: Session) -> str:
    token = _serializer().dumps(session.model_dump(mode="json"))
    if len(token) > MAX_COOKIE_BYTES:
        raise SessionFull(f"session is {len(token)} bytes, limit {MAX_COOKIE_BYTES}")
    return token


def decode(token: str) -> Session | None:
    """Return the session, or None if the token is invalid in any way."""
    try:
        data = _serializer().loads(token, max_age=MAX_AGE_SECONDS)
        return Session.model_validate(data)
    except (BadData, ValidationError) as e:
        log.warning("Ignoring invalid session cookie: %s", type(e).__name__)
        return None


def load_session(request: Request) -> Session:
    """The request's session, or an empty one if the cookie is missing or invalid.

    An invalid cookie is cleared on the way out by clear_invalid_session_cookie,
    unless save_session replaces it first.
    """
    token = request.cookies.get(COOKIE_NAME)
    if token is None:
        return Session()
    session = decode(token)
    if session is None:
        request.state.invalid_session_cookie = True
        return Session()
    return session


def save_session(request: Request, response: Response, session: Session) -> None:
    """Write the session cookie. Raises SessionFull, leaving the old cookie as is."""
    response.set_cookie(
        COOKIE_NAME,
        encode(session),
        max_age=MAX_AGE_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
    )
    request.state.invalid_session_cookie = False


async def clear_invalid_session_cookie(request: Request, call_next):
    """HTTP middleware: delete a cookie that load_session found invalid."""
    response = await call_next(request)
    if getattr(request.state, "invalid_session_cookie", False):
        response.delete_cookie(COOKIE_NAME, httponly=True, secure=True, samesite="lax")
    return response
