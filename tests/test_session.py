"""Unit tests for the session model and cookie encoding (DAI-8)."""

import random
from datetime import UTC, datetime, timedelta

import pytest
from itsdangerous import URLSafeTimedSerializer

from fiannafit.session import (
    MAX_COOKIE_BYTES,
    Session,
    SessionFull,
    WorkoutFinished,
    decode,
    encode,
)

T0 = datetime(2026, 10, 5, 18, 0, tzinfo=UTC)


def big_workout(exercises=12, sets=5) -> Session:
    session = Session()
    for e in range(exercises):
        for s in range(sets):
            session.log_set(
                f"Exercise number {e}",
                8,
                60 + 2.5 * s,
                now=T0 + timedelta(minutes=e * 5 + s),
            )
    return session


def test_round_trip():
    session = Session()
    session.log_set("Back Squat", 5, 100, now=T0)
    session.log_set("Pull-up", 10, None, now=T0 + timedelta(minutes=3))
    assert decode(encode(session)) == session


def test_first_set_starts_workout():
    session = Session()
    session.log_set("Back Squat", 5, 100, now=T0)
    assert session.workout.started_at == T0
    assert session.workout.exercises[0].sets[0].weight_kg == 100


def test_sets_join_existing_exercise_ignoring_case_and_spacing():
    session = Session()
    session.log_set("Bench Press", 8, 60, now=T0)
    session.log_set("  bench   press ", 8, 60, now=T0)
    [exercise] = session.workout.exercises
    assert exercise.name == "Bench Press"
    assert len(exercise.sets) == 2


def test_empty_exercise_name_rejected():
    with pytest.raises(ValueError):
        Session().log_set("   ", 5)


def test_tampered_signature_is_invalid():
    token = encode(big_workout(1, 1))
    # Change the signature's first character. Not the last: in base64 its low
    # bits are padding, so some swaps decode to the same, still valid, bytes.
    i = token.rindex(".") + 1
    tampered = token[:i] + ("A" if token[i] != "A" else "B") + token[i + 1 :]
    assert decode(tampered) is None


def test_garbage_is_invalid():
    assert decode("not-a-cookie") is None


def test_wrong_key_is_invalid():
    other = URLSafeTimedSerializer("some-other-key", salt="fiannafit.session")
    assert decode(other.dumps(Session().model_dump(mode="json"))) is None


def test_unknown_version_is_invalid():
    token = encode(Session())
    data = decode(token).model_dump(mode="json") | {"v": 2}
    serializer = URLSafeTimedSerializer("test-only-key", salt="fiannafit.session")
    assert decode(serializer.dumps(data)) is None


def test_big_workout_is_well_under_the_size_guard():
    assert len(encode(big_workout(12, 5))) < MAX_COOKIE_BYTES / 2


def test_size_guard_refuses_oversized_session():
    session = Session()
    # Random names barely compress, so this passes the limit quickly
    rng = random.Random(0)
    for _ in range(200):
        session.log_set(f"{rng.getrandbits(128):x}", 5, now=T0)
    with pytest.raises(SessionFull):
        encode(session)


def test_recent_exercises_most_recent_first_without_duplicates():
    session = Session()
    for name in ["Squat", "Bench", "squat", "Row"]:
        session.log_set(name, 5, now=T0)
    assert session.recent_exercises == ["Row", "Squat", "Bench"]


def test_recent_exercises_limited_to_ten():
    session = Session()
    for i in range(15):
        session.log_set(f"Exercise {i}", 5, now=T0)
    assert session.recent_exercises == [f"Exercise {i}" for i in range(14, 4, -1)]


def test_new_workout_keeps_recent_exercises():
    session = Session()
    session.log_set("Squat", 5, now=T0)
    session.new_workout()
    assert session.workout is None
    assert session.recent_exercises == ["Squat"]


def test_delete_last_set_removes_the_latest_across_exercises():
    session = Session()
    session.log_set("Squat", 5, 100, now=T0)
    session.log_set("Bench", 8, 60, now=T0 + timedelta(minutes=5))
    session.log_set("Squat", 5, 105, now=T0 + timedelta(minutes=10))
    session.log_set("Bench", 8, 62.5, now=T0 + timedelta(minutes=15))

    assert session.delete_last_set().weight_kg == 62.5
    assert session.delete_last_set().weight_kg == 105
    squat, bench = session.workout.exercises
    assert [s.weight_kg for s in squat.sets] == [100]
    assert [s.weight_kg for s in bench.sets] == [60]


def test_delete_last_set_removes_an_emptied_exercise():
    session = Session()
    session.log_set("Squat", 5, 100, now=T0)
    session.log_set("Bench", 8, 60, now=T0 + timedelta(minutes=5))
    session.delete_last_set()
    assert [e.name for e in session.workout.exercises] == ["Squat"]


def test_deleting_the_only_set_unstarts_the_workout():
    session = Session()
    session.log_set("Squat", 5, 100, now=T0)
    session.delete_last_set()
    assert session.workout is None
    assert session.recent_exercises == ["Squat"]


def test_delete_last_set_with_no_workout_does_nothing():
    session = Session()
    assert session.delete_last_set() is None
    assert session.workout is None


def test_finish_sets_end_time_once():
    session = Session()
    session.log_set("Squat", 5, 100, now=T0)
    session.finish(now=T0 + timedelta(minutes=60))
    session.finish(now=T0 + timedelta(minutes=90))  # a double tap
    assert session.workout.ended_at == T0 + timedelta(minutes=60)


def test_finish_without_a_workout_is_rejected():
    with pytest.raises(ValueError):
        Session().finish()


def test_finished_workout_is_read_only():
    session = Session()
    session.log_set("Squat", 5, 100, now=T0)
    session.finish(now=T0 + timedelta(minutes=60))
    with pytest.raises(WorkoutFinished):
        session.log_set("Squat", 5, 100)
    with pytest.raises(WorkoutFinished):
        session.delete_last_set()
    assert len(session.workout.exercises[0].sets) == 1


def test_new_workout_after_finish_can_log_again():
    session = Session()
    session.log_set("Squat", 5, 100, now=T0)
    session.finish(now=T0 + timedelta(minutes=60))
    session.new_workout()
    session.log_set("Squat", 5, 100, now=T0 + timedelta(days=2))
    assert session.workout.started_at == T0 + timedelta(days=2)


def test_last_set_of_ignores_case_and_spacing():
    session = Session()
    session.log_set("Bench Press", 8, 60, now=T0)
    session.log_set("Bench Press", 6, 62.5, now=T0 + timedelta(minutes=3))
    last = session.last_set_of("  bench  PRESS ")
    assert (last.reps, last.weight_kg) == (6, 62.5)


def test_last_set_of_unknown_exercise_is_none():
    session = Session()
    assert session.last_set_of("Squat") is None  # no workout yet
    session.log_set("Bench", 8, 60, now=T0)
    assert session.last_set_of("Squat") is None


def test_current_exercise_follows_the_latest_set():
    session = Session()
    assert session.current_exercise() is None
    session.log_set("Squat", 5, 100, now=T0)
    session.log_set("Bench", 8, 60, now=T0 + timedelta(minutes=5))
    session.log_set("squat", 5, 100, now=T0 + timedelta(minutes=10))
    assert session.current_exercise() == "Squat"
    session.delete_last_set()
    assert session.current_exercise() == "Bench"
