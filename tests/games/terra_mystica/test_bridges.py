"""Tests for Terra Mystica bridges: pairs, payments, limits and town adjacency."""

from dataclasses import replace

from boardgames.games.terra_mystica import (
    Board,
    Bridge,
    BuildBridge,
    BuildDwelling,
    Building,
    Hex,
    UpgradeBuilding,
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
    listing,
    start,
    with_resources,
)


def test_bridge_pairs_cross_the_edge_between_two_river_spaces() -> None:
    board = Board.base()
    pairs = bridge_pairs(board)
    assert pairs
    for first, second in pairs:
        assert first.distance(second) == 2
        common = set(first.neighbours()) & set(second.neighbours())
        assert len(common) == 2
        assert all(
            (tile := board.tile(position)) is not None and not tile.is_land
            for position in common
        )


def test_bridge_pairs_reject_a_land_side_and_a_straight_crossing() -> None:
    pairs = {frozenset(pair) for pair in bridge_pairs(Board.base())}
    # Only one of the two spaces between 9,2 and 8,4 is river; 9,3 is land.
    assert frozenset((Hex(9, 2), Hex(8, 4))) not in pairs
    # 1,1 is the only river space between 1,0 and 1,2; this is a straight gap.
    assert frozenset((Hex(1, 0), Hex(1, 2))) not in pairs


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
        bridges=tuple(
            Bridge(player, first, second)
            for first, second in bridge_pairs(state.board)[:3]
        ),
    )
    assert bridge_actions(state, player) == []


def test_bridge_makes_the_far_end_reachable_without_shipping() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    first, second = bridge_pairs(state.board)[0]
    state = action_state(state, player, (first, BuildingType.DWELLING))
    state = replace_player(
        state,
        player,
        replace(
            state.players[player],
            faction=FactionType.WITCHES,
            shipping=0,
        ),
    )
    assert BuildDwelling(second) not in listing(state)
    state = replace(state, bridges=(Bridge(player, first, second),))
    assert BuildDwelling(second) in listing(state)
    after = GAME.apply(state, player, BuildDwelling(second)).state
    tile = after.board.tile(second)
    assert tile is not None and tile.building is not None
    assert tile.building.owner == player


def test_bridge_gives_the_trading_house_discount() -> None:
    state = start(num_players=2, seed=1)
    player, opponent = state.order
    first, second = bridge_pairs(state.board)[0]
    state = action_state(state, player, (first, BuildingType.DWELLING))
    state = replace(
        state,
        board=state.board.place(second, Building(BuildingType.DWELLING, opponent)),
        bridges=(Bridge(player, first, second),),
    )
    profile = state.players[player].profile
    before = state.players[player].resources.coins
    action = UpgradeBuilding(first, BuildingType.TRADING_HOUSE)
    assert action in listing(state)
    after = GAME.apply(state, player, action).state
    assert (
        after.players[player].resources.coins
        == before - profile.costs.trading_house.coins // 2
    )


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
