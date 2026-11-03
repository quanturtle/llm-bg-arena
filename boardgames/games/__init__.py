"""Game implementations. Importing this package registers every game."""

from boardgames.core import registered_game_ids
from boardgames.games import catan, k_in_a_row, sealed_auction

__all__ = ["catan", "game_ids", "k_in_a_row", "sealed_auction"]


def game_ids() -> tuple[str, ...]:
    """Ids of every shipped game, sorted; calling it guarantees they are registered."""
    return registered_game_ids()
