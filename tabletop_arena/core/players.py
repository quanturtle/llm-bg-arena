"""Player identities: seats numbered from 0 in table order."""

from typing import NewType

PlayerId = NewType("PlayerId", int)


def seats(count: int) -> tuple[PlayerId, ...]:
    """All seats at a table of `count` players."""
    return tuple(PlayerId(index) for index in range(count))


def seat_label(player: PlayerId) -> str:
    """Label numbered from 1, so seat 0 is "P1"."""
    return f"P{player + 1}"
