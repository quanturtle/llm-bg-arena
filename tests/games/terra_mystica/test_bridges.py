"""Tests for Terra Mystica bridges: pairs, payments, limits and town adjacency."""

from dataclasses import replace

from boardgames.games.terra_mystica import (
    Board,
    Bridge,
    BuildBridge,
    Building,
    Hex,
)
from boardgames.games.terra_mystica.bridges import bridge_actions, bridge_pairs
from boardgames.games.terra_mystica.constants import BuildingType, FactionType
from boardgames.games.terra_mystica.model import (
    found_ready_towns,
    replace_player,
)
from tests.games.terra_mystica.support import (
    GAME,
    P1,
    action_state,
    start,
    with_resources,
)


def test_bridge_pairs_have_a_river_between_them() -> None:
    board = Board.base()
    pairs = bridge_pairs(board)
    assert pairs
    for first, second in pairs:
        assert first.distance(second) == 2
        common = set(first.neighbours()) & set(second.neighbours())
        assert any(
            (tile := board.tile(position)) is not None and not tile.is_land
            for position in common
        )


def test_power_bridge_requires_a_building_and_moves_power_to_bowl_one() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    first, second = bridge_pairs(state.board)[0]
    state = action_state(state, player, (first, BuildingType.DWELLING))
    state = with_resources(state, player, power1=0, power2=0, power3=3)
    action = BuildBridge(first, second, "power")
    assert action in bridge_actions(state, player)
    after = GAME.apply(state, player, action).state
    assert Bridge(player, first, second) in after.bridges
    assert "bridge" in after.used_power_actions
    assert after.players[player].resources.power1 == 3
    assert after.players[player].resources.power3 == 0


def test_engineers_pay_two_workers_for_a_bridge() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    first, second = bridge_pairs(state.board)[0]
    state = action_state(state, player, (first, BuildingType.DWELLING))
    state = replace_player(
        state,
        player,
        replace(state.players[player], faction=FactionType.ENGINEERS),
    )
    state = with_resources(state, player, power1=0, power2=0, power3=0, workers=2)
    action = BuildBridge(first, second, "workers")
    assert action in bridge_actions(state, player)
    after = GAME.apply(state, player, action).state
    assert Bridge(player, first, second) in after.bridges
    assert "bridge" not in after.used_power_actions
    assert after.players[player].resources.workers == 0


def test_three_bridges_are_the_limit() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    state = replace(
        state,
        bridges=tuple(Bridge(player, Hex(q, 0), Hex(q + 2, 0)) for q in range(3)),
    )
    assert bridge_actions(state, player) == []


def test_bridge_joins_two_groups_for_a_town() -> None:
    board = Board.base()
    pair: tuple[Hex, Hex] | None = None
    first_neighbour: Hex | None = None
    second_neighbour: Hex | None = None
    for first, second in bridge_pairs(board):
        for candidate in first.neighbours():
            tile = board.tile(candidate)
            if tile is None or not tile.is_land or candidate.distance(second) <= 1:
                continue
            for other in second.neighbours():
                other_tile = board.tile(other)
                if (
                    other_tile is not None
                    and other_tile.is_land
                    and other.distance(first) > 1
                    and other.distance(candidate) > 1
                ):
                    pair = (first, second)
                    first_neighbour = candidate
                    second_neighbour = other
                    break
            if pair is not None:
                break
        if pair is not None:
            break
    assert pair is not None
    assert first_neighbour is not None
    assert second_neighbour is not None
    first, second = pair
    for position, kind in (
        (first, BuildingType.STRONGHOLD),
        (first_neighbour, BuildingType.DWELLING),
        (second, BuildingType.TRADING_HOUSE),
        (second_neighbour, BuildingType.DWELLING),
    ):
        board = board.place(position, Building(kind, P1))
    assert len(board.connected(first, P1)) == 2
    bridge = Bridge(P1, first, second)
    assert len(board.connected(first, P1, (bridge,))) == 4
    board, founded = found_ready_towns(board, P1, 7, 10, (bridge,))
    assert len(founded) == 1
    for position in (first, first_neighbour, second, second_neighbour):
        tile = board.tile(position)
        assert tile is not None and tile.building is not None
        assert tile.building.in_town


def test_bridge_notation() -> None:
    action = BuildBridge(Hex(0, 0), Hex(2, 0))
    assert GAME.format_action(action) == "bridge 0,0 2,0"
    assert GAME.parse_action("bridge 0,0 2,0") == action
    workers = BuildBridge(Hex(0, 0), Hex(2, 0), "workers")
    assert GAME.format_action(workers) == "bridge 0,0 2,0 workers"
    assert GAME.parse_action("bridge 0,0 2,0 workers") == workers
