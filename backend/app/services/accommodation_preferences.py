"""Structured hotel choices in the existing private preference field."""

import re

PATTERN = re.compile(r"^stay:stars=([345]);lower=([345,]*);notes:([\s\S]*)$")


def parse_stars(value: str) -> tuple[int, ...] | None:
    match = PATTERN.fullmatch(value)
    if not match:
        return None
    preferred = int(match[1])
    lower = {int(s) for s in match[2].split(",") if s}
    return tuple(sorted({preferred} | {s for s in lower if s < preferred}))


def readable(value: str) -> str:
    stars = parse_stars(value)
    if stars is None:
        return value
    match = PATTERN.fullmatch(value)
    assert match
    return f"Hotel class: {', '.join(map(str, stars))} stars only. {match[3]}".strip()


def group_hotel_stars(generation) -> tuple[tuple[int, ...], bool]:
    choices = [parse_stars(m.accommodation.value) for m in generation.members]
    explicit = [set(choice) for choice in choices if choice is not None]
    if not explicit:
        return (3, 4), False
    # A shared hotel must suit everyone who explicitly selected a class.
    common = set.intersection(*explicit)
    return tuple(sorted(common)), True
