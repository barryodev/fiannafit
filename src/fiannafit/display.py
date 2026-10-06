"""How the logging screen shows sets, weights and clock times (DAI-11)."""

from datetime import UTC, datetime, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fiannafit.session import LoggedSet

# Set by a small script in base.html; the server itself runs in UTC.
TZ_COOKIE = "tz"


def parse_timezone(name: str | None) -> tzinfo:
    """The browser's time zone, or UTC if it's missing or not a real zone.

    Chrome still sends some old names (Asia/Calcutta, Europe/Kiev). Ubuntu's
    tzdata dropped them, so the tzdata package is a dependency: ZoneInfo falls
    back to it for names the system doesn't have.
    """
    if name:
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError, ValueError:
            pass
    return UTC


def format_weight(weight_kg: float) -> str:
    """100.0 -> "100", 62.5 -> "62.5"."""
    return f"{weight_kg:g}"


def format_set(logged_set: LoggedSet) -> str:
    """E.g. "5 × 100 kg", or reps only for a bodyweight set: "12 reps"."""
    reps = logged_set.reps
    if logged_set.weight_kg is None:
        return f"{reps} rep" if reps == 1 else f"{reps} reps"
    return f"{reps} × {format_weight(logged_set.weight_kg)} kg"


def clock(moment: datetime, tz: tzinfo) -> str:
    """A stored UTC time as the user's local wall-clock time, e.g. "18:02"."""
    return moment.astimezone(tz).strftime("%H:%M")
