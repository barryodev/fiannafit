"""Unit tests for how sets, weights and times are shown (DAI-11)."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from fiannafit.display import clock, format_set, format_weight, parse_timezone
from fiannafit.session import LoggedSet

T0 = datetime(2026, 10, 5, 17, 2, tzinfo=UTC)


@pytest.mark.parametrize(
    "weight, text",
    [(100.0, "100"), (62.5, "62.5"), (1.25, "1.25"), (0.0, "0"), (102.5, "102.5")],
)
def test_format_weight_drops_needless_decimals(weight, text):
    assert format_weight(weight) == text


@pytest.mark.parametrize(
    "reps, weight, text",
    [
        (5, 100.0, "5 × 100 kg"),
        (8, 62.5, "8 × 62.5 kg"),
        (12, None, "12 reps"),
        (1, None, "1 rep"),
    ],
)
def test_format_set(reps, weight, text):
    assert format_set(LoggedSet(reps=reps, weight_kg=weight, logged_at=T0)) == text


def test_parse_timezone_accepts_real_zones():
    assert parse_timezone("Europe/Dublin") == ZoneInfo("Europe/Dublin")


@pytest.mark.parametrize("name", [None, "", "Not/AZone", "../../etc/passwd"])
def test_parse_timezone_falls_back_to_utc(name):
    assert parse_timezone(name) is UTC


def test_clock_converts_to_local_time():
    assert clock(T0, ZoneInfo("Europe/Dublin")) == "18:02"  # summer time
    assert (
        clock(datetime(2026, 12, 5, 17, 2, tzinfo=UTC), ZoneInfo("Europe/Dublin"))
        == "17:02"
    )
    assert clock(T0, UTC) == "17:02"
