from collections import Counter

from boardgames.core import seats
from boardgames.games.catan import PlaceSettlement
from boardgames.games.catan.geometry import HEX_NEIGHBORS, VERTEX_HEXES
from boardgames.games.catan.model import (
    NUMBER_TOKENS,
    RESOURCES,
    TERRAIN_RESOURCE,
    empty_hand,
    hand_total,
    hand_with,
)
from boardgames.games.catan.setup import setup_order
from tests.games.catan.support import CONFIG, GAME, P1, play_setup, start


def test_setup_prepares_a_seeded_board() -> None:
    state = start()
    terrains = Counter(board_hex.terrain for board_hex in state.hexes)
    assert terrains == {
        "forest": 4,
        "pasture": 4,
        "fields": 4,
        "hills": 3,
        "mountains": 3,
        "desert": 1,
    }
    numbers = sorted(
        board_hex.number for board_hex in state.hexes if board_hex.number is not None
    )
    assert tuple(numbers) == tuple(sorted(NUMBER_TOKENS))
    assert state.hexes[state.robber].terrain == "desert"
    assert len(state.ports) == 9
    assert sum(1 for port in state.ports if port.resource is None) == 4
    assert sorted(
        port.resource for port in state.ports if port.resource is not None
    ) == sorted(RESOURCES)
    assert all(building is None for building in state.buildings)
    assert all(owner is None for owner in state.roads)
    assert all(hand_total(hand) == 0 for hand in state.hands)
    assert state.phase == "setup_settlement"
    assert state.turn == 1


def test_six_and_eight_tokens_never_touch() -> None:
    for seed in range(50):
        hexes = start(seed=seed).hexes
        red = [hex_id for hex_id, board in enumerate(hexes) if board.number in (6, 8)]
        assert len(red) == 4
        assert not any(
            other in red for hex_id in red for other in HEX_NEIGHBORS[hex_id]
        )


def test_setup_is_deterministic_per_seed() -> None:
    assert start(seed=9) == start(seed=9)
    assert GAME.setup(CONFIG, 9).events == GAME.setup(CONFIG, 9).events
    assert start(seed=9) != start(seed=10)


def test_setup_turn_order_snakes_back() -> None:
    state = start()
    order = setup_order(CONFIG)
    assert [state.active] == [order[0]]
    state, placements = play_setup()
    players = [player for player, _ in placements]
    expected = [player for player in order for _ in range(2)]
    assert players == expected
    assert state.phase == "roll"
    assert state.active == P1
    assert state.turn == 1
    for player in seats(3):
        settlements = sum(
            1
            for building in state.buildings
            if building is not None
            and building.player == player
            and building.kind == "settlement"
        )
        roads = sum(1 for owner in state.roads if owner == player)
        assert settlements == 2
        assert roads == 2


def test_second_settlement_grants_starting_resources() -> None:
    state, placements = play_setup()
    second: dict[int, int] = {}
    for player, action in placements:
        if isinstance(action, PlaceSettlement):
            if player in second:
                second[player] = action.vertex
            else:
                second[player] = -1
    for player in seats(3):
        expected = empty_hand()
        for hex_id in VERTEX_HEXES[second[player]]:
            board_hex = state.hexes[hex_id]
            resource = TERRAIN_RESOURCE[board_hex.terrain]
            if resource is not None and hex_id != state.robber:
                expected = hand_with(expected, resource, 1)
        assert state.hands[player] == expected


def test_first_settlement_grants_nothing() -> None:
    state = start()
    decision = GAME.pending_decisions(state)[0]
    action = GAME.legal_actions(state, decision).listing(1000)[0]  # type: ignore[index]
    after = GAME.apply(state, decision.player, action).state
    assert hand_total(after.hands[decision.player]) == 0
    assert after.phase == "setup_road"
    assert after.setup_vertex is not None
