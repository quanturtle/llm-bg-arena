"""Tests for power gained by opponents when a structure is built next to them."""

from dataclasses import replace

from boardgames.games.terra_mystica import (
    Building,
    ChoosePowerGain,
    TerraMysticaState,
    UpgradeBuilding,
)
from boardgames.games.terra_mystica.building import build_dwelling
from boardgames.games.terra_mystica.constants import BuildingType
from boardgames.games.terra_mystica.model import Hex, replace_player
from tests.games.terra_mystica.support import (
    GAME,
    action_state,
    listing,
    start,
    with_resources,
)


def _neighbours(state: TerraMysticaState, position: Hex) -> list[Hex]:
    return [
        neighbour
        for neighbour in position.neighbours()
        if (tile := state.board.tile(neighbour)) is not None and tile.is_land
    ]


def _build_state() -> tuple[TerraMysticaState, Hex, int, int]:
    """A builder structure next to an empty tile next to an opponent structure."""
    state = start(num_players=2, seed=1)
    builder, opponent = state.order
    for tile in state.board.tiles:
        if not tile.is_land:
            continue
        neighbours = _neighbours(state, tile.position)
        if len(neighbours) < 2:
            continue
        build, support = neighbours[0], neighbours[1]
        state = action_state(state, builder, (support, BuildingType.TRADING_HOUSE))
        state = replace(
            state,
            board=state.board.place(build, Building(BuildingType.DWELLING, opponent)),
        )
        return state, tile.position, builder, opponent
    raise AssertionError("no suitable build position")


def test_building_next_to_an_opponent_offers_power() -> None:
    state, position, builder, opponent = _build_state()
    state = with_resources(
        state, opponent, power1=3, power2=9, power3=0, coins=0, workers=0, priests=0
    )
    state = build_dwelling(state, builder, position).state
    assert state.phase == "power_gain"
    (decision,) = GAME.pending_decisions(state)
    assert decision.player == opponent
    assert ChoosePowerGain(True) in listing(state)
    assert ChoosePowerGain(False) in listing(state)
    before = state.players[opponent]
    state = GAME.apply(state, opponent, ChoosePowerGain(True)).state
    after = state.players[opponent]
    assert after.resources.power1 == before.resources.power1 - 1
    assert after.resources.power2 == before.resources.power2 + 1
    assert after.victory_points == before.victory_points
    assert state.phase == "action"
    assert state.active_player == opponent


def test_declining_power_changes_nothing() -> None:
    state, position, builder, opponent = _build_state()
    state = with_resources(
        state, opponent, power1=3, power2=9, power3=0, coins=0, workers=0, priests=0
    )
    state = build_dwelling(state, builder, position).state
    before = state.players[opponent]
    state = GAME.apply(state, opponent, ChoosePowerGain(False)).state
    after = state.players[opponent]
    assert after.resources == before.resources
    assert after.victory_points == before.victory_points


def test_power_gain_is_capped_by_victory_points() -> None:
    state, position, builder, opponent = _build_state()
    neighbour = next(
        neighbour
        for neighbour in position.neighbours()
        if (tile := state.board.tile(neighbour)) is not None
        and tile.building is not None
        and tile.building.owner == opponent
    )
    tile = state.board.tile(neighbour)
    assert tile is not None
    state = replace(
        state,
        board=state.board.replace_tile(
            neighbour,
            replace(tile, building=Building(BuildingType.STRONGHOLD, opponent)),
        ),
    )
    state = with_resources(state, opponent, power1=5, power2=5, power3=0)
    owner = replace(state.players[opponent], victory_points=1)
    state = replace_player(state, opponent, owner)
    state = build_dwelling(state, builder, position).state
    state = GAME.apply(state, opponent, ChoosePowerGain(True)).state
    after = state.players[opponent]
    assert after.victory_points == 0
    assert after.resources.power1 == 3
    assert after.resources.power2 == 7


def test_upgrading_next_to_an_opponent_offers_power() -> None:
    state = start(num_players=2, seed=1)
    builder, opponent = state.order
    for tile in state.board.tiles:
        if not tile.is_land:
            continue
        neighbours = _neighbours(state, tile.position)
        if not neighbours:
            continue
        state = action_state(state, builder, (tile.position, BuildingType.DWELLING))
        state = replace(
            state,
            board=state.board.place(
                neighbours[0], Building(BuildingType.DWELLING, opponent)
            ),
        )
        state = GAME.apply(
            state, builder, UpgradeBuilding(tile.position, BuildingType.TRADING_HOUSE)
        ).state
        assert state.phase == "power_gain"
        assert state.pending_power[0].player == opponent
        return
    raise AssertionError("no suitable upgrade position")
