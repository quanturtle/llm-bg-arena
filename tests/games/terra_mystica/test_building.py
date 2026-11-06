"""Tests for Terra Mystica building: dwellings, terraforming, upgrades and shipping."""

from dataclasses import replace

import pytest

from boardgames.core import IllegalActionError, PlayerId, seats
from boardgames.games.terra_mystica import (
    AdvanceShipping,
    BuildDwelling,
    Building,
    Hex,
    TerraMysticaState,
    TransformTerrain,
    UpgradeBuilding,
)
from boardgames.games.terra_mystica.constants import (
    FACTION_BY_TYPE,
    TERRAIN_WHEEL,
    BuildingType,
    Cult,
    CultBonus,
    FactionType,
    Resources,
    ScoringAction,
    ScoringTile,
    Terrain,
)
from boardgames.games.terra_mystica.model import (
    replace_player,
    spade_cost,
    spades_for,
    terrain_distance,
)
from tests.games.terra_mystica.support import (
    GAME,
    _neutral_scoring,
    _same_terrain_pair,
    _terrain_target,
    action_state,
    empty_land_tiles,
    listing,
    play_setup,
    start,
    with_resources,
)


def test_build_dwelling_uses_an_adjacent_home_tile() -> None:
    state = play_setup(start(num_players=2, seed=1))
    player = state.active_player
    before = state.board.count(player, BuildingType.DWELLING)
    action = next(
        action for action in listing(state) if isinstance(action, BuildDwelling)
    )
    state = GAME.apply(state, player, action).state
    assert state.board.count(player, BuildingType.DWELLING) == before + 1
    tile = state.board.tile(action.position)
    assert tile is not None and tile.building is not None
    assert tile.building.owner == player


def test_transform_around_home_terrain_costs_the_long_way() -> None:
    state = play_setup(start(num_players=2, seed=1))
    player = state.order[0]
    mountain = next(
        tile
        for tile in state.board.tiles
        if tile.terrain is Terrain.MOUNTAIN and tile.building is None
    )
    neighbour = next(
        position
        for position in mountain.position.neighbours()
        if (tile := state.board.tile(position)) is not None
        and tile.is_land
        and tile.building is None
    )
    state = action_state(state, player, (neighbour, BuildingType.DWELLING))
    state = replace_player(
        state,
        player,
        replace(
            state.players[player],
            faction=FactionType.CHAOS_MAGICIANS,
            resources=Resources(coins=50, workers=50),
        ),
    )
    action = TransformTerrain(mountain.position, Terrain.DESERT)
    assert action in listing(state)
    before = state.players[player].resources.workers
    after = GAME.apply(state, player, action).state
    assert after.players[player].resources.workers == before - 15
    tile = after.board.tile(mountain.position)
    assert tile is not None and tile.terrain is Terrain.DESERT


def test_build_dwelling_requires_adjacency() -> None:
    state = play_setup(start(num_players=2, seed=2))
    player = state.active_player
    home = state.players[player].home_terrain
    reachable = set(state.board.reachable_land(player, state.players[player].shipping))
    target = next(
        tile.position
        for tile in state.board.tiles
        if tile.is_land
        and tile.terrain is home
        and tile.building is None
        and tile.position not in reachable
    )
    with pytest.raises(IllegalActionError, match="adjacent"):
        GAME.apply(state, player, BuildDwelling(target))


def test_transform_and_build_changes_terrain_and_pays_spades() -> None:
    state = play_setup(start(num_players=3, seed=5))
    player = state.active_player
    action = next(
        (
            action
            for action in listing(state)
            if isinstance(action, BuildDwelling)
            and (tile := state.board.tile(action.position)) is not None
            and tile.terrain is not state.players[player].home_terrain
        ),
        None,
    )
    if action is None:
        pytest.skip("no adjacent non-home tile in this setup")
    tile = state.board.tile(action.position)
    assert tile is not None
    spades = spades_for(state.players[player].profile, tile.terrain)
    assert spades > 0
    before = state.players[player].resources
    state = GAME.apply(state, player, action).state
    new_tile = state.board.tile(action.position)
    assert new_tile is not None
    assert new_tile.terrain is state.players[player].home_terrain
    assert state.players[player].resources.workers <= before.workers


def test_upgrade_dwelling_to_trading_house() -> None:
    state = play_setup(start(num_players=2, seed=2))
    player = state.active_player
    state = with_resources(state, player, coins=30, workers=10)
    action = next(
        action
        for action in listing(state)
        if isinstance(action, UpgradeBuilding)
        and action.to is BuildingType.TRADING_HOUSE
    )
    state = GAME.apply(state, player, action).state
    tile = state.board.tile(action.position)
    assert tile is not None and tile.building is not None
    assert tile.building.type is BuildingType.TRADING_HOUSE


def with_witches_dwelling(
    state: TerraMysticaState, player: PlayerId
) -> tuple[TerraMysticaState, Hex]:
    start_position, target = next(
        (tile.position, neighbour)
        for tile in state.board.tiles
        if tile.is_land and tile.building is None
        for neighbour in tile.position.neighbours()
        if (other := state.board.tile(neighbour)) is not None
        and other.is_land
        and other.building is None
    )
    state = action_state(state, player, (start_position, BuildingType.DWELLING))
    state = replace_player(
        state, player, replace(state.players[player], faction=FactionType.WITCHES)
    )
    return state, target


def test_shipping_is_not_listed_at_the_maximum() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    owner = replace(
        state.players[player],
        faction=FactionType.WITCHES,
        shipping=FACTION_BY_TYPE[FactionType.WITCHES].shipping_max,
        resources=Resources(coins=20, workers=5, priests=3),
    )
    state = replace_player(
        state,
        player,
        owner,
    )
    state = replace(
        state,
        phase="action",
        setup_queue=(),
        active_player=player,
        passed=frozenset(),
        pass_order=(),
        round=1,
    )
    assert AdvanceShipping() not in listing(state)


def test_mermaids_earn_two_points_on_their_first_shipping_step() -> None:
    state = start(num_players=2, seed=1, rounds=1)
    player = state.order[0]
    state = replace(
        state,
        phase="action",
        setup_queue=(),
        active_player=player,
        passed=frozenset(),
        pass_order=(),
        round=1,
        scoring=(
            ScoringTile(ScoringAction.DWELLING, CultBonus(Cult.WATER, 4, "priests")),
        ),
    )
    owner = replace(
        state.players[player],
        faction=FactionType.MERMAIDS,
        shipping=1,
        resources=Resources(coins=20, workers=5, priests=3),
    )
    state = replace_player(state, player, owner)
    before = state.players[player].victory_points
    after = GAME.apply(state, player, AdvanceShipping()).state
    assert after.players[player].shipping == 2
    assert after.players[player].victory_points == before + 2


@pytest.mark.parametrize(
    ("target", "source"),
    [
        (BuildingType.STRONGHOLD, BuildingType.TRADING_HOUSE),
        (BuildingType.SANCTUARY, BuildingType.TEMPLE),
    ],
)
def test_both_five_vp_tiles_score_strongholds_or_sanctuaries(
    target: BuildingType, source: BuildingType
) -> None:
    state = start(num_players=2, seed=1, rounds=1)
    player = state.order[0]
    position = empty_land_tiles(state)[0]
    state = action_state(state, player, (position, source))
    state = replace(
        state,
        scoring=(
            ScoringTile(
                ScoringAction.STRONGHOLD_OR_SANCTUARY,
                CultBonus(Cult.AIR, 2, "workers"),
            ),
        ),
    )
    before = state.players[player].victory_points
    after = GAME.apply(state, player, UpgradeBuilding(position, target)).state
    assert after.players[player].victory_points == before + 5


def test_ninth_dwelling_is_explained_by_supply() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    positions = empty_land_tiles(state)
    board = state.board
    for position in positions[:8]:
        board = board.place(position, Building(BuildingType.DWELLING, player))
    state = replace(
        state,
        board=board,
        phase="action",
        setup_queue=(),
        active_player=player,
        passed=frozenset(),
    )
    (decision,) = GAME.pending_decisions(state)
    space = GAME.legal_actions(state, decision)
    assert space.explain(BuildDwelling(positions[8])) == "You have no dwellings left."


def test_dwarves_and_fakirs_reach_across_two_and_three_spaces() -> None:
    state = play_setup(start(num_players=2, seed=2))
    player = state.active_player
    occupied = state.board.occupied(player)[0]
    two_away = next(
        tile.position
        for tile in state.board.tiles
        if tile.is_land
        and occupied.distance(tile.position) == 2
        and tile.position not in state.board.reachable_from(occupied, 0)
    )
    assert two_away in state.board.reachable_from(occupied, 0, 2)
    three_away = next(
        tile.position
        for tile in state.board.tiles
        if tile.is_land
        and occupied.distance(tile.position) == 3
        and tile.position not in state.board.reachable_from(occupied, 0)
    )
    assert three_away not in state.board.reachable_from(occupied, 0, 2)
    assert three_away in state.board.reachable_from(occupied, 0, 3)


def test_dwarves_tunnel_costs_two_workers_and_scores_four_points() -> None:
    state = start(num_players=2, seed=2)
    player = state.order[0]
    state = replace_player(
        state,
        player,
        replace(state.players[player], faction=FactionType.DWARVES),
    )
    start_position, target = _same_terrain_pair(state, Terrain.MOUNTAIN, 2)
    state = _neutral_scoring(
        action_state(state, player, (start_position, BuildingType.DWELLING))
    )
    before = state.players[player]
    after = GAME.apply(state, player, BuildDwelling(target)).state
    assert after.players[player].victory_points - before.victory_points == 4
    assert before.resources.workers - after.players[player].resources.workers == 3


def test_transform_can_stop_at_another_terrain() -> None:
    state = play_setup(start(num_players=2, seed=2))
    player = state.active_player
    state, target = with_witches_dwelling(state, player)
    tile = state.board.tile(target)
    assert tile is not None
    to = next(
        terrain
        for terrain in TERRAIN_WHEEL
        if terrain is not tile.terrain
        and terrain is not state.players[player].home_terrain
        and terrain_distance(tile.terrain, terrain) == 1
    )
    action = TransformTerrain(target, to)
    assert action in listing(state)
    after = GAME.apply(state, player, action).state
    changed = after.board.tile(target)
    assert changed is not None and changed.terrain is to


def test_dwarves_can_tunnel_to_transform_without_building() -> None:
    state = start(num_players=2, seed=2)
    player = state.order[0]
    state = replace_player(
        state,
        player,
        replace(state.players[player], faction=FactionType.DWARVES),
    )
    start_position, target = _terrain_target(state, Terrain.FOREST, 2)
    state = _neutral_scoring(
        action_state(state, player, (start_position, BuildingType.DWELLING))
    )
    before = state.players[player]
    tile = state.board.tile(target)
    assert tile is not None
    spades = spades_for(before.profile, tile.terrain)
    expected_workers = spade_cost(before.profile, before.digging, spades).workers + 2
    after = GAME.apply(state, player, TransformTerrain(target)).state
    assert after.players[player].victory_points - before.victory_points == 4
    assert (
        before.resources.workers - after.players[player].resources.workers
        == expected_workers
    )


def test_a_dwarves_stronghold_makes_tunneling_cheaper() -> None:
    state = start(num_players=2, seed=2)
    player = state.order[0]
    state = replace_player(
        state,
        player,
        replace(state.players[player], faction=FactionType.DWARVES),
    )
    start_position, target = _same_terrain_pair(state, Terrain.MOUNTAIN, 2)
    state = _neutral_scoring(
        action_state(state, player, (start_position, BuildingType.STRONGHOLD))
    )
    before = state.players[player]
    after = GAME.apply(state, player, BuildDwelling(target)).state
    assert after.players[player].victory_points - before.victory_points == 4
    assert before.resources.workers - after.players[player].resources.workers == 2


def _fakir_state() -> tuple[TerraMysticaState, PlayerId]:
    state = start(num_players=2, seed=2)
    player = state.order[0]
    state = replace_player(
        state,
        player,
        replace(state.players[player], faction=FactionType.FAKIRS),
    )
    return state, player


def test_fakirs_flight_costs_a_priest() -> None:
    state, player = _fakir_state()
    start_position, two_away = _terrain_target(state, Terrain.DESERT, 2)
    state = action_state(state, player, (start_position, BuildingType.DWELLING))
    state = with_resources(state, player, priests=5)
    state = _neutral_scoring(state)
    before = state.players[player]
    after = GAME.apply(state, player, BuildDwelling(two_away)).state
    assert after.players[player].victory_points - before.victory_points == 4
    assert before.resources.priests - after.players[player].resources.priests == 1


def test_a_fakirs_stronghold_extends_flight_range() -> None:
    state, player = _fakir_state()
    start_position, three_away = _terrain_target(state, Terrain.DESERT, 3)
    without_stronghold = action_state(
        state, player, (start_position, BuildingType.DWELLING)
    )
    assert BuildDwelling(three_away) not in listing(without_stronghold)

    with_stronghold = action_state(
        state, player, (start_position, BuildingType.STRONGHOLD)
    )
    with_stronghold = with_resources(with_stronghold, player, priests=5)
    with_stronghold = _neutral_scoring(with_stronghold)
    before = with_stronghold.players[player]
    after = GAME.apply(with_stronghold, player, BuildDwelling(three_away)).state
    assert after.players[player].victory_points - before.victory_points == 4
    assert before.resources.priests - after.players[player].resources.priests == 1


def test_dwelling_round_tile_scores_through_apply() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    state, target = with_witches_dwelling(state, player)
    state = replace(
        state,
        scoring=(
            ScoringTile(ScoringAction.DWELLING, CultBonus(Cult.WATER, 4, "priests")),
        ),
    )
    before = state.players[player].victory_points
    state = GAME.apply(state, player, BuildDwelling(target)).state
    assert state.players[player].victory_points - before == 2
    return


def test_trading_house_round_tile_scores_through_apply() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    state, target = with_witches_dwelling(state, player)
    state = GAME.apply(state, player, BuildDwelling(target)).state
    state = replace(
        state,
        active_player=player,
        scoring=(
            ScoringTile(ScoringAction.TRADING_HOUSE, CultBonus(Cult.AIR, 4, "spades")),
        ),
    )
    before = state.players[player].victory_points
    upgraded = GAME.apply(
        state, player, UpgradeBuilding(target, BuildingType.TRADING_HOUSE)
    ).state.players[player]
    assert upgraded.victory_points - before == 3
    return


def test_spade_round_tile_scores_through_transform() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    home = FACTION_BY_TYPE[FactionType.WITCHES].home_terrain
    start_position, target = next(
        (tile.position, neighbour)
        for tile in state.board.tiles
        if tile.is_land and tile.building is None and tile.terrain is not home
        for neighbour in tile.position.neighbours()
        if (other := state.board.tile(neighbour)) is not None
        and other.is_land
        and other.building is None
        and other.terrain is not home
    )
    state = action_state(state, player, (start_position, BuildingType.DWELLING))
    state = replace_player(
        state, player, replace(state.players[player], faction=FactionType.WITCHES)
    )
    state = replace(
        state,
        scoring=(ScoringTile(ScoringAction.SPADE, CultBonus(Cult.EARTH, 1, "coins")),),
    )
    tile = state.board.tile(target)
    assert tile is not None
    spades = spades_for(state.players[player].profile, tile.terrain)
    before = state.players[player].victory_points
    after = GAME.apply(state, player, TransformTerrain(target)).state
    assert after.players[player].victory_points - before == spades * 2
    return


def test_trading_house_discount_is_applied_by_upgrade() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    other = next(seat for seat in seats(2) if seat != player)
    position = Hex(0, 0)
    neighbour = position.neighbours()[0]
    state = action_state(state, player, (position, BuildingType.DWELLING))
    board = state.board.place(neighbour, Building(BuildingType.DWELLING, other))
    state = replace(state, board=board)
    before = state.players[player].resources.coins
    after = GAME.apply(
        state, player, UpgradeBuilding(position, BuildingType.TRADING_HOUSE)
    ).state.players[player]
    assert before - after.resources.coins == 3
    return
