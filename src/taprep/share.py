"""What Share Workout sends (DAI-9): the plain-text summary, and links for
browsers without a share sheet."""

from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo
from pathlib import Path
from urllib.parse import quote

from jinja2 import Environment, FileSystemLoader

from taprep.display import clock, format_set
from taprep.session import Workout

# Its own environment, not the page's: the summary is plain text, so nothing
# is HTML-escaped here. The page escapes it once, where it embeds the text.
_text_templates = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
)
_text_templates.filters["set_text"] = format_set


@dataclass(frozen=True)
class ShareLink:
    label: str
    href: str
    new_tab: bool = False  # a web page; mailto: and sms: open an app instead
    phone_only: bool = False  # hidden where the main pointer is a mouse


@dataclass(frozen=True)
class Share:
    """What Share Workout needs: the summary for the share sheet and Copy, and
    the links for browsers without a share sheet."""

    text: str
    links: list[ShareLink]


def share_for(workout: Workout, tz: tzinfo) -> Share:
    text = summary_text(workout, tz)
    return Share(text, share_links(text, summary_text(workout, tz, bold=False)))


def share_links(text: str, plain_text: str) -> list[ShareLink]:
    """WhatsApp, Email and SMS links that open with the summary filled in.
    Only WhatsApp shows *bold*, so Email and SMS get the plain version."""
    subject = plain_text.splitlines()[0]
    # Email wants CRLF line breaks (RFC 6068); the others take plain newlines
    email_body = plain_text.replace("\n", "\r\n")
    return [
        # Not wa.me: its redirect turns emoji such as 🏋️ into "�"
        ShareLink(
            "WhatsApp",
            f"https://api.whatsapp.com/send?text={_encode(text)}",
            new_tab=True,
        ),
        ShareLink(
            "Email", f"mailto:?subject={_encode(subject)}&body={_encode(email_body)}"
        ),
        # Does nothing on a desktop. Phones normally send SMS through the share
        # sheet, but in-app browsers (Instagram, Facebook) often lack one
        ShareLink("SMS", f"sms:?&body={_encode(plain_text)}", phone_only=True),
    ]


def _encode(value: str) -> str:
    """Percent-encode everything, so &, = and # in a name can't end the value."""
    return quote(value, safe="")


def summary_text(workout: Workout, tz: tzinfo, bold: bool = True) -> str:
    """The whole workout as a message for WhatsApp, SMS, email and the like.
    With bold, exercise names are *marked* the way WhatsApp makes them bold.
    Only a finished workout is shared, so the text never goes out of date."""
    if workout.ended_at is None:
        raise ValueError("only a finished workout can be shared")
    return _text_templates.get_template("summary.txt").render(
        workout=workout, when=when(workout, tz), bold=bold
    )


def when(workout: Workout, tz: tzinfo) -> str:
    """E.g. "Tue 29 Sep, 18:02–19:05 (1 h 3 min)", in the user's time zone.
    A workout that ends on a later day shows that day too:
    "Sun 11 Oct, 18:02 – Mon 12 Oct, 09:15 (15 h 13 min)"."""
    start = workout.started_at.astimezone(tz)
    end = workout.ended_at.astimezone(tz)
    took = _duration(_whole_minutes(end) - _whole_minutes(start))
    if end.date() == start.date():
        return f"{_day(start)}, {clock(start, tz)}–{clock(end, tz)} ({took})"
    return f"{_day(start)}, {clock(start, tz)} – {_day(end)}, {clock(end, tz)} ({took})"


def _day(moment: datetime) -> str:
    """E.g. "Tue 29 Sep"."""
    return f"{moment:%a} {moment.day} {moment:%b}"


def _duration(minutes: int) -> str:
    """45 -> "45 min", 60 -> "1 h", 63 -> "1 h 3 min"."""
    hours, minutes = divmod(minutes, 60)
    if not hours:
        return f"{minutes} min"
    return f"{hours} h {minutes} min" if minutes else f"{hours} h"


def _whole_minutes(moment: datetime) -> int:
    """Minutes since the epoch, dropping seconds, so the duration always matches
    the clock times shown (18:02:50 to 19:05:10 reads as 1 h 3 min, not 1 h 2).
    In UTC, so a clock change mid-workout doesn't add or lose an hour."""
    return int(moment.astimezone(UTC).timestamp()) // 60
