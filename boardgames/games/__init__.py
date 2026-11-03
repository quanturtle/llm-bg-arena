"""Game implementations. Importing this package registers every game."""

from boardgames.games import catan, k_in_a_row, sealed_auction

__all__ = ["catan", "k_in_a_row", "sealed_auction"]
