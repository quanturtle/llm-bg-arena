import pytest

from tabletop_arena.core import UnknownGameError, create_game


def test_unknown_game_id_raises() -> None:
    with pytest.raises(UnknownGameError, match="unknown game 'no_such_game'"):
        create_game("no_such_game")
    return
