"""Unit tests for the plain-text workout summary and share links (DAI-9)."""

import re
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import pytest

from taprep.session import Session
from taprep.share import share_links, summary_text, when

DUBLIN = ZoneInfo("Europe/Dublin")
T0 = datetime(2026, 9, 29, 17, 2, tzinfo=UTC)  # 18:02 in Dublin (summer time)


def workout(*sets, finished_after=timedelta(minutes=20)):
    """A finished workout from (exercise, reps, kg) tuples, logged a minute apart."""
    session = Session()
    for i, (name, reps, kg) in enumerate(sets):
        session.log_set(name, reps, kg, now=T0 + timedelta(minutes=i))
    session.finish(now=T0 + finished_after)
    return session.workout


def test_typical_workout():
    w = workout(
        ("Barbell Bench Press", 8, 60),
        ("Barbell Bench Press", 8, 60),
        ("Barbell Bench Press", 6, 62.5),
        ("Back Squat", 5, 100),
        ("Back Squat", 5, 100),
        ("Back Squat", 5, 100),
        finished_after=timedelta(minutes=63),
    )
    assert summary_text(w, DUBLIN) == (
        "🏋️ TapRep workout, Tue 29 Sep, 18:02–19:05 (1 h 3 min)\n"
        "\n"
        "*Barbell Bench Press*\n"
        "8 × 60 kg · 8 × 60 kg · 6 × 62.5 kg\n"
        "\n"
        "*Back Squat*\n"
        "5 × 100 kg · 5 × 100 kg · 5 × 100 kg\n"
        "\n"
        "Logged with taprep.barryodev.io"
    )


def test_bodyweight_sets_show_reps_only():
    w = workout(
        ("Pull-up", 10, None),
        ("Pull-up", 1, None),
        ("Dip", 12, None),
        ("Dip", 8, 10),  # weighted dip in the same exercise
    )
    assert summary_text(w, DUBLIN) == (
        "🏋️ TapRep workout, Tue 29 Sep, 18:02–18:22 (20 min)\n"
        "\n"
        "*Pull-up*\n"
        "10 reps · 1 rep\n"
        "\n"
        "*Dip*\n"
        "12 reps · 8 × 10 kg\n"
        "\n"
        "Logged with taprep.barryodev.io"
    )


def test_plain_version_has_no_bold_marks():
    w = workout(("Back Squat", 5, 100), ("Pull-up", 10, None))
    assert summary_text(w, DUBLIN, bold=False) == (
        "🏋️ TapRep workout, Tue 29 Sep, 18:02–18:22 (20 min)\n"
        "\n"
        "Back Squat\n"
        "5 × 100 kg\n"
        "\n"
        "Pull-up\n"
        "10 reps\n"
        "\n"
        "Logged with taprep.barryodev.io"
    )


def test_only_a_finished_workout_is_shared():
    session = Session()
    session.log_set("Back Squat", 5, 100, now=T0)
    with pytest.raises(ValueError):
        summary_text(session.workout, DUBLIN)


def test_exercise_names_are_not_html_escaped():
    # Plain text: the page escapes it once, where it embeds it
    w = workout(('Curl & Press <heavy> "Tom\'s"', 8, 20))
    assert '*Curl & Press <heavy> "Tom\'s"*\n' in summary_text(w, DUBLIN)


def test_times_and_day_are_in_the_users_time_zone():
    # 17:02 UTC on Tue 29 Sep is already Wed 30 Sep in Auckland
    w = workout(("Row", 10, 50))
    assert when(w, UTC) == "Tue 29 Sep, 17:02–17:22 (20 min)"
    assert when(w, DUBLIN) == "Tue 29 Sep, 18:02–18:22 (20 min)"
    assert when(w, ZoneInfo("Pacific/Auckland")) == "Wed 30 Sep, 06:02–06:22 (20 min)"


def test_workout_ending_on_a_later_day_shows_both_days():
    w = workout(("Row", 10, 50), finished_after=timedelta(hours=7, minutes=13))
    assert when(w, DUBLIN) == "Tue 29 Sep, 18:02 – Wed 30 Sep, 01:15 (7 h 13 min)"


def test_a_workout_left_open_for_days():
    # Finish forgotten: the cookie keeps a workout for up to 90 days
    w = workout(("Row", 10, 50), finished_after=timedelta(days=6, minutes=7))
    assert when(w, DUBLIN) == "Tue 29 Sep, 18:02 – Mon 5 Oct, 18:09 (144 h 7 min)"


def test_day_change_is_judged_in_the_users_time_zone():
    # 22:30–00:30 UTC is one day in Dublin (23:30–01:30 crosses midnight there
    # too), but in New York it's 18:30–20:30, all on the same day
    session = Session()
    session.log_set("Row", 10, 50, now=datetime(2026, 9, 29, 22, 30, tzinfo=UTC))
    session.finish(now=datetime(2026, 9, 30, 0, 30, tzinfo=UTC))
    assert (
        when(session.workout, ZoneInfo("America/New_York"))
        == "Tue 29 Sep, 18:30–20:30 (2 h)"
    )
    assert when(session.workout, DUBLIN) == (
        "Tue 29 Sep, 23:30 – Wed 30 Sep, 01:30 (2 h)"
    )


@pytest.mark.parametrize(
    "minutes, shown",
    [
        (0, "0 min"),
        (1, "1 min"),
        (59, "59 min"),
        (60, "1 h"),
        (61, "1 h 1 min"),
        (63, "1 h 3 min"),
        (120, "2 h"),
        (179, "2 h 59 min"),
    ],
)
def test_duration_in_hours_from_an_hour(minutes, shown):
    w = workout(("Row", 10, 50), finished_after=timedelta(minutes=minutes))
    assert when(w, UTC).endswith(f"({shown})")


def test_duration_matches_the_clock_times_shown():
    session = Session()
    session.log_set("Row", 10, 50, now=datetime(2026, 9, 29, 17, 2, 50, tzinfo=UTC))
    session.finish(now=datetime(2026, 9, 29, 18, 5, 10, tzinfo=UTC))
    # 62 min 20 s, but 18:02–19:05 reads as 63
    assert when(session.workout, DUBLIN) == "Tue 29 Sep, 18:02–19:05 (1 h 3 min)"


def test_duration_across_a_clock_change_is_real_time():
    # Irish clocks go back at 02:00 on 25 Oct 2026 (01:00 UTC)
    session = Session()
    session.log_set("Row", 10, 50, now=datetime(2026, 10, 25, 0, 30, tzinfo=UTC))
    session.finish(now=datetime(2026, 10, 25, 1, 30, tzinfo=UTC))
    assert when(session.workout, DUBLIN) == "Sun 25 Oct, 01:30–01:30 (1 h)"


# --- Links for browsers without a share sheet ---------------------------------

TEXT = (
    "🏋️ TapRep workout, Tue 29 Sep, 18:02–19:05 (1 h 3 min)\n"
    "\n"
    "*Curl & Press #2 = 100%?*\n"
    "8 × 20 kg · 12 reps\n"
    "\n"
    "Logged with taprep.barryodev.io"
)
PLAIN_TEXT = TEXT.replace("*", "")


def link(label: str):
    [found] = [li for li in share_links(TEXT, PLAIN_TEXT) if li.label == label]
    return found


def params(href: str) -> dict[str, str]:
    """The link's query, decoded the way the app it opens will decode it."""
    query = parse_qs(urlsplit(href).query, keep_blank_values=True)
    return {key: value for key, [value] in query.items()}


def test_links_are_whatsapp_email_and_sms():
    labels = [li.label for li in share_links(TEXT, PLAIN_TEXT)]
    assert labels == ["WhatsApp", "Email", "SMS"]


def test_whatsapp_link_carries_the_text_with_bold_names():
    whatsapp = link("WhatsApp")
    assert whatsapp.href.startswith("https://api.whatsapp.com/send?text=")
    assert params(whatsapp.href) == {"text": TEXT}
    assert whatsapp.new_tab


def test_email_link_has_a_subject_and_plain_text_with_crlf_line_breaks():
    email = link("Email")
    assert email.href.startswith("mailto:?subject=")
    assert params(email.href) == {
        "subject": "🏋️ TapRep workout, Tue 29 Sep, 18:02–19:05 (1 h 3 min)",
        "body": PLAIN_TEXT.replace("\n", "\r\n"),
    }
    assert not email.new_tab


def test_sms_link_carries_the_plain_text():
    sms = link("SMS")
    assert sms.href.startswith("sms:?&body=")
    assert params(sms.href)["body"] == PLAIN_TEXT
    assert not sms.new_tab


def test_only_sms_is_for_phones_only():
    assert [li.phone_only for li in share_links(TEXT, PLAIN_TEXT)] == [
        False,
        False,
        True,
    ]


@pytest.mark.parametrize("label", ["WhatsApp", "Email", "SMS"])
def test_link_values_are_fully_percent_encoded(label):
    # A raw &, =, #, space or newline from the text would cut the link short
    # or add parameters of its own
    query = urlsplit(link(label).href).query
    for part in filter(None, query.split("&")):
        _, value = part.split("=", 1)
        assert re.fullmatch(r"[A-Za-z0-9._~%-]+", value), part
