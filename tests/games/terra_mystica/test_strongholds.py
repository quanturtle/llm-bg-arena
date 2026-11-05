"""Tests for Terra Mystica stronghold rewards."""

from dataclasses import replace

from boardgames.core import PlayerId
from boardgames.games.terra_mystica import (
    ChooseStrongholdPriests,
    Hex,
    SkipCultSpade,
    TerraMysticaState,
    UpgradeBuilding,
)
from boardgames.games.terra_mystica.constants import (
    BuildingType,
    FactionType,
    Resources,
)
from boardgames.games.terra_mystica.model import replace_player
from tests.games.terra_mystica.support import (
    GAME,
    _neutral_scoring,
    action_state,
    start,
)


def _stronghold_state(
    faction: FactionType,
) -> tuple[TerraMysticaState, PlayerId, Hex]:
    state = start(num_players=2, seed=2)
    player = state.order[0]
    position = next(
        tile.position
        for tile in state.board.tiles
        if tile.is_land and tile.building is None
    )
    state = replace_player(
        state,
        player,
        replace(state.players[player], faction=faction),
    )
    state = action_state(state, player, (position, BuildingType.TRADING_HOUSE))
    state = replace_player(
        state,
        player,
        replace(
            state.players[player],
            resources=Resources(coins=50, workers=50, priests=4, power1=5, power2=7),
        ),
    )
    return _neutral_scoring(state), player, position


def test_stronghold_one_time_rewards() -> None:
    state, player, position = _stronghold_state(FactionType.CULTISTS)
    before = state.players[player].victory_points
    after = GAME.apply(
        state, player, UpgradeBuilding(position, BuildingType.STRONGHOLD)
    ).state
    assert after.players[player].victory_points - before == 7

    state, player, position = _stronghold_state(FactionType.ALCHEMISTS)
    after = GAME.apply(
        state, player, UpgradeBuilding(position, BuildingType.STRONGHOLD)
    ).state
    resources = after.players[player].resources
    assert (resources.power1, resources.power2, resources.power3) == (0, 5, 7)

    state, player, position = _stronghold_state(FactionType.MERMAIDS)
    state = replace_player(state, player, replace(state.players[player], shipping=1))
    before_player = state.players[player]
    after = GAME.apply(
        state, player, UpgradeBuilding(position, BuildingType.STRONGHOLD)
    ).state
    assert after.players[player].shipping == 2
    assert after.players[player].victory_points == before_player.victory_points + 2

    state, player, position = _stronghold_state(FactionType.MERMAIDS)
    state = replace_player(state, player, replace(state.players[player], shipping=5))
    before_player = state.players[player]
    after = GAME.apply(
        state, player, UpgradeBuilding(position, BuildingType.STRONGHOLD)
    ).state
    assert after.players[player].shipping == 5
    assert after.players[player].victory_points == before_player.victory_points


def test_halfling_and_darkling_stronghold_rewards_need_a_choice() -> None:
    state, player, position = _stronghold_state(FactionType.HALFLINGS)
    before = state.players[player].victory_points
    after = GAME.apply(
        state, player, UpgradeBuilding(position, BuildingType.STRONGHOLD)
    ).state
    assert after.phase == "cult_spades"
    assert after.cult_spades[player] == 3
    assert after.players[player].victory_points - before == 3
    after = GAME.apply(after, player, SkipCultSpade()).state
    assert after.phase == "action"

    state, player, position = _stronghold_state(FactionType.DARKLINGS)
    after = GAME.apply(
        state, player, UpgradeBuilding(position, BuildingType.STRONGHOLD)
    ).state
    assert after.phase == "stronghold_convert"
    before_resources = after.players[player].resources
    after = GAME.apply(after, player, ChooseStrongholdPriests(3)).state
    assert after.phase == "action"
    resources = after.players[player].resources
    assert resources.workers == before_resources.workers - 3
    assert resources.priests == before_resources.priests + 3
