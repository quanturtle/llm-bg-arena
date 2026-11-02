"""Game registry: game classes decorated with `@register_game`, looked up by id."""

from typing import Any

from tabletop_arena.core.errors import DuplicateGameError, UnknownGameError
from tabletop_arena.core.game import Game

type AnyGame = Game[Any, Any, Any]

_GAME_CLASSES: dict[str, type[AnyGame]] = {}


def register_game[G: AnyGame](cls: type[G]) -> type[G]:
    """Class decorator that makes a game available to `create_game` under `cls.id`."""
    if cls.id in _GAME_CLASSES:
        raise DuplicateGameError(f"game id {cls.id!r} is already registered")
    _GAME_CLASSES[cls.id] = cls
    return cls


def create_game(game_id: str) -> AnyGame:
    """A new instance of the game registered under `game_id`."""
    if game_id not in _GAME_CLASSES:
        known = ", ".join(registered_game_ids()) or "none"
        raise UnknownGameError(f"unknown game {game_id!r}; registered: {known}")
    return _GAME_CLASSES[game_id]()


def registered_game_ids() -> tuple[str, ...]:
    """Ids of all registered games, sorted."""
    return tuple(sorted(_GAME_CLASSES))
