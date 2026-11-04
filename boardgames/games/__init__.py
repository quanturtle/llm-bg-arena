"""Game implementations. Importing this package registers every game."""

from boardgames.core import registered_game_ids
from boardgames.games import catan, puerto_rico, terra_mystica, tic_tac_toe

__all__ = ["catan", "game_ids", "puerto_rico", "terra_mystica", "tic_tac_toe"]


def game_ids() -> tuple[str, ...]:
    """Ids of every shipped game, sorted; calling it guarantees they are registered."""
    return registered_game_ids()
