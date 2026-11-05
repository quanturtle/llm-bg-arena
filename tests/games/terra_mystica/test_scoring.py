"""Tests for Terra Mystica final scoring: areas, majorities and leftover resources."""

from dataclasses import replace

from boardgames.core import seats
from boardgames.games.terra_mystica import Board, Building
from boardgames.games.terra_mystica.constants import (
    BuildingType,
    FactionType,
    Resources,
)
from boardgames.games.terra_mystica.model import replace_player
from boardgames.games.terra_mystica.scoring import (
    final_scores,
    largest_area,
    split_rank_points,
)
from tests.games.terra_mystica.support import (
    GAME,
    P1,
    P2,
    P3,
    play,
    play_setup,
    start,
    with_resources,
)


def test_final_scores_are_computed_from_board_and_resources() -> None:
    state = play_setup(start(num_players=2, seed=1, rounds=1))
    while not GAME.is_terminal(state):
        state = play(state, "pass")
    final = final_scores(state)
    for seat in seats(2):
        points, breakdown = final[seat]
        assert points == sum(breakdown.values())


def test_leftover_bowl_three_power_scores_as_coins() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    state = with_resources(
        state,
        player,
        coins=0,
        workers=0,
        priests=0,
        power1=0,
        power2=0,
        power3=9,
    )
    assert final_scores(state)[player][1]["resources"] == 3


def test_final_scores_burn_bowl_two_power() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    state = replace_player(
        state,
        player,
        replace(
            state.players[player],
            faction=FactionType.WITCHES,
            resources=Resources(power1=0, power2=6, power3=0),
        ),
    )
    assert final_scores(state)[player][1]["resources"] == 1
    state = with_resources(
        state, player, coins=0, workers=0, priests=0, power1=0, power2=5, power3=0
    )
    assert final_scores(state)[player][1]["resources"] == 0


def test_dwarves_area_scoring_connects_through_their_reach() -> None:
    board = Board.base()
    player = P1
    positions = [tile.position for tile in board.tiles if tile.is_land]
    start = positions[0]
    other = next(position for position in positions if start.distance(position) == 2)
    board = board.place(start, Building(BuildingType.DWELLING, player))
    board = board.place(other, Building(BuildingType.DWELLING, player))
    assert largest_area(board, player, shipping=0, reach=0) == 1
    assert largest_area(board, player, shipping=0, reach=2) == 2


def test_final_majorities_split_ties_and_convert_resources() -> None:
    awards = split_rank_points([(P1, 5), (P2, 5), (P3, 3)], (8, 4, 2))
    assert awards == {P1: 6, P2: 6, P3: 2}
    state = start(num_players=2, seed=1, rounds=1)
    owner = replace(
        state.players[P1],
        faction=FactionType.ALCHEMISTS,
        resources=Resources(coins=5),
        victory_points=0,
        cults=(0, 0, 0, 0),
    )
    state = replace_player(state, P1, owner)
    points, breakdown = final_scores(state)[P1]
    assert breakdown["resources"] == 2
    assert points == sum(breakdown.values())
