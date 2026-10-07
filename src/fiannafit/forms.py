"""The Log Set form: checking what was typed, and pre-filling the next set (DAI-11)."""

import re
from dataclasses import dataclass

from fiannafit.display import format_weight
from fiannafit.session import LoggedSet, Session, normalise_name

MAX_NAME_LENGTH = 40
MAX_REPS = 999
MAX_WEIGHT_KG = 1000

_REPS = re.compile(r"[0-9]+")
_WEIGHT = re.compile(r"[0-9]+(\.[0-9]{1,2})?")  # up to 2 decimals, for 1.25 kg plates


@dataclass
class FormValues:
    """The form's fields as text, exactly as shown in the inputs."""

    exercise: str = ""
    reps: str = ""
    kg: str = ""


@dataclass
class SetInput:
    exercise: str
    reps: int
    weight_kg: float | None  # None for bodyweight, which is typed as 0


class InvalidSet(ValueError):
    """What's wrong with the form, worded for the user, and which field it's about."""

    def __init__(self, message: str, field: str):
        super().__init__(message)
        self.message = message
        self.field = field


def parse_set(values: FormValues) -> SetInput:
    """Check the typed values. Raises InvalidSet for the first problem found."""
    name = normalise_name(values.exercise)
    if not name:
        raise InvalidSet("Enter an exercise name.", "exercise")
    if len(name) > MAX_NAME_LENGTH:
        raise InvalidSet(
            f"Keep the exercise name to {MAX_NAME_LENGTH} characters or fewer.",
            "exercise",
        )

    reps = values.reps.strip()
    if not _REPS.fullmatch(reps) or not 1 <= int(reps) <= MAX_REPS:
        raise InvalidSet(f"Reps must be a whole number from 1 to {MAX_REPS}.", "reps")

    # Many EU phone keypads type a comma as the decimal point
    kg = values.kg.strip().replace(",", ".")
    if not kg:
        raise InvalidSet("Enter a weight, or 0 for bodyweight.", "kg")
    if not _WEIGHT.fullmatch(kg) or float(kg) > MAX_WEIGHT_KG:
        raise InvalidSet(
            f"Weight must be a number from 0 to {MAX_WEIGHT_KG} kg, "
            "with up to 2 decimals.",
            "kg",
        )
    weight = float(kg)

    return SetInput(name, int(reps), weight or None)


def prefill(session: Session, name: str | None = None) -> FormValues | None:
    """The next set is most likely a repeat of the latest one, of the given
    exercise or else the one logged to last. None if there's no set to repeat."""
    name = name or session.current_exercise()
    last = session.last_set_of(name) if name else None
    if last is None:
        return None
    return set_values(name, last)


def set_values(name: str, logged_set: LoggedSet) -> FormValues:
    """A logged set as the form shows it, with bodyweight as 0 kg."""
    weight = logged_set.weight_kg
    kg = "0" if weight is None else format_weight(weight)
    return FormValues(name, str(logged_set.reps), kg)


def suggestions(session: Session) -> list[str]:
    """Exercise names to offer: this workout's, then recent ones, no repeats."""
    names = [e.name for e in session.workout.exercises] if session.workout else []
    names += session.recent_exercises
    seen: set[str] = set()
    unique = []
    for name in names:
        if name.casefold() not in seen:
            seen.add(name.casefold())
            unique.append(name)
    return unique
