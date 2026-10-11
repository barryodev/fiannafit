"""The plain-text workout summary that Share sends (DAI-9)."""

from datetime import UTC, datetime, tzinfo
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from fiannafit.display import clock, format_set
from fiannafit.session import Workout

# Its own environment, not the page's: the summary is plain text, so nothing
# is HTML-escaped here. The page escapes it once, where it embeds the text.
_text_templates = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
)
_text_templates.filters["set_text"] = format_set


def summary_text(workout: Workout, tz: tzinfo) -> str:
    """The whole workout as a message for WhatsApp, SMS, email and the like.
    Only a finished workout is shared, so the text never goes out of date."""
    if workout.ended_at is None:
        raise ValueError("only a finished workout can be shared")
    return _text_templates.get_template("summary.txt").render(
        workout=workout, when=when(workout, tz)
    )


def when(workout: Workout, tz: tzinfo) -> str:
    """E.g. "Tue 29 Sep, 18:02–19:05 (63 min)". The day is the day it started."""
    start = workout.started_at.astimezone(tz)
    day = f"{start:%a} {start.day} {start:%b}"
    minutes = _whole_minutes(workout.ended_at) - _whole_minutes(workout.started_at)
    return f"{day}, {clock(start, tz)}–{clock(workout.ended_at, tz)} ({minutes} min)"


def _whole_minutes(moment: datetime) -> int:
    """Minutes since the epoch, dropping seconds, so the duration always matches
    the clock times shown (18:02:50 to 19:05:10 reads as 63 min, not 62).
    In UTC, so a clock change mid-workout doesn't add or lose an hour."""
    return int(moment.astimezone(UTC).timestamp()) // 60
