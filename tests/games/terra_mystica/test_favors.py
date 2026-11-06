"""Tests for the temple favor tiles and their immediate and ongoing effects."""

from dataclasses import replace

from boardgames.core import PlayerId
from boardgames.games.terra_mystica import (
    Board,
    BuildDwelling,
    Building,
    Hex,
    Pass,
    TakeFavorTile,
    TerraMysticaState,
    UpgradeBuilding,
)
from boardgames.games.terra_mystica.constants import (
    BuildingType,
    Cult,
    CultBonus,
    FactionType,
    ScoringAction,
    ScoringTile,
)
from boardgames.games.terra_mystica.model import (
    available_favors,
    replace_player,
    town_power,
    town_ready,
)
from boardgames.games.terra_mystica.rounds import income_for
from tests.games.terra_mystica.support import (
    GAME,
    _neutral_scoring,
    action_state,
    listing,
    start,
)


def _temple_state(
    faction: FactionType = FactionType.WITCHES,
) -> tuple[TerraMysticaState, PlayerId]:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    tile = next(
        tile
        for tile in state.board.tiles
        if tile.is_land and tile.building is None
    )
    state = action_state(state, player, (tile.position, BuildingType.TRADING_HOUSE))
    state = replace_player(
        state,
        player,
        replace(state.players[player], faction=faction),
    )
    state = GAME.apply(
        state, player, UpgradeBuilding(tile.position, BuildingType.TEMPLE)
    ).state
    return state, player


def test_temple_grants_a_favor_tile() -> None:
    state, player = _temple_state()
    assert state.phase == "favor_choice"
    assert state.pending_favors == 1
    assert TakeFavorTile(0) in listing(state)
    before = state.players[player]
    after = GAME.apply(state, player, TakeFavorTile(0)).state
    assert after.phase == "action"
    assert after.pending_favors == 0
    assert 0 in after.players[player].favors
    assert after.players[player].cult(Cult.FIRE) == before.cult(Cult.FIRE) + 3


def test_chaos_magicians_get_two_temple_favors() -> None:
    state, player = _temple_state(FactionType.CHAOS_MAGICIANS)
    assert state.pending_favors == 2
    state = GAME.apply(state, player, TakeFavorTile(0)).state
    assert state.phase == "favor_choice"
    assert state.pending_favors == 1
    state = GAME.apply(state, player, TakeFavorTile(1)).state
    assert state.phase == "action"
    assert state.players[player].favors == frozenset({0, 1})


def test_taken_favor_tiles_are_not_offered_again() -> None:
    state, player = _temple_state(FactionType.CHAOS_MAGICIANS)
    state = GAME.apply(state, player, TakeFavorTile(0)).state
    assert TakeFavorTile(0) not in listing(state)
    assert TakeFavorTile(1) in listing(state)
    assert 0 not in available_favors(state)


def test_sanctuary_grants_a_favor_tile() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    tile = next(
        tile
        for tile in state.board.tiles
        if tile.is_land and tile.building is None
    )
    state = action_state(state, player, (tile.position, BuildingType.TEMPLE))
    state = GAME.apply(
        state, player, UpgradeBuilding(tile.position, BuildingType.SANCTUARY)
    ).state
    assert state.phase == "favor_choice"
    assert state.pending_favors == 1


def test_favor_choice_comes_before_the_town_tile() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    position = next(
        tile.position
        for tile in state.board.tiles
        if tile.is_land
        and tile.building is None
        and len(
            [
                neighbour
                for neighbour in tile.position.neighbours()
                if (other := state.board.tile(neighbour)) is not None
                and other.is_land
            ]
        )
        >= 3
    )
    neighbours = [
        neighbour
        for neighbour in position.neighbours()
        if (tile := state.board.tile(neighbour)) is not None and tile.is_land
    ][:3]
    state = action_state(
        state,
        player,
        (position, BuildingType.TEMPLE),
        (neighbours[0], BuildingType.TEMPLE),
        (neighbours[1], BuildingType.DWELLING),
        (neighbours[2], BuildingType.DWELLING),
    )
    state = GAME.apply(
        state, player, UpgradeBuilding(position, BuildingType.SANCTUARY)
    ).state
    assert state.phase == "favor_choice"
    assert state.pending_favors == 1
    assert state.pending_town
    state = GAME.apply(state, player, TakeFavorTile(0)).state
    assert state.phase == "town_choice"
    assert not state.pending_town


def test_favor_five_can_complete_the_current_town() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    position = next(
        tile.position
        for tile in state.board.tiles
        if tile.is_land
        and tile.building is None
        and len(
            [
                neighbour
                for neighbour in tile.position.neighbours()
                if (other := state.board.tile(neighbour)) is not None
                and other.is_land
            ]
        )
        >= 3
    )
    neighbours = [
        neighbour
        for neighbour in position.neighbours()
        if (tile := state.board.tile(neighbour)) is not None and tile.is_land
    ][:3]
    state = action_state(
        state,
        player,
        (position, BuildingType.TEMPLE),
        (neighbours[0], BuildingType.DWELLING),
        (neighbours[1], BuildingType.DWELLING),
        (neighbours[2], BuildingType.DWELLING),
    )
    state = GAME.apply(
        state, player, UpgradeBuilding(position, BuildingType.SANCTUARY)
    ).state
    assert state.phase == "favor_choice"
    state = GAME.apply(state, player, TakeFavorTile(4)).state
    assert state.phase == "town_choice"


def test_favor_tiles_add_income() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    favored = replace_player(
        state,
        player,
        replace(state.players[player], favors=frozenset({6, 7, 8})),
    )
    plain = replace_player(
        state,
        player,
        replace(state.players[player], favors=frozenset()),
    )
    income = income_for(favored.board, player, favored.players[player])
    base = income_for(plain.board, player, plain.players[player])
    assert income.coins == base.coins + 3
    assert income.workers == base.workers + 1
    assert income.power == base.power + 5


def test_favor_tiles_pay_vp_for_buildings() -> None:
    state = _neutral_scoring(start(num_players=2, seed=1))
    player = state.order[0]
    state = replace_player(
        state,
        player,
        replace(state.players[player], favors=frozenset({10})),
    )
    start_position = next(
        tile.position
        for tile in state.board.tiles
        if tile.is_land and tile.building is None
    )
    state = action_state(state, player, (start_position, BuildingType.DWELLING))
    action = next(
        action for action in listing(state) if isinstance(action, BuildDwelling)
    )
    before = state.players[player].victory_points
    after = GAME.apply(state, player, action).state
    assert after.players[player].victory_points == before + 2

    state = start(num_players=2, seed=1)
    player = state.order[0]
    tile = next(
        tile
        for tile in state.board.tiles
        if tile.is_land and tile.building is None
    )
    state = action_state(state, player, (tile.position, BuildingType.DWELLING))
    state = replace_player(
        state,
        player,
        replace(state.players[player], favors=frozenset({9})),
    )
    state = replace(
        state,
        scoring=(
            ScoringTile(ScoringAction.DWELLING, CultBonus(Cult.WATER, 4, "priests")),
            ScoringTile(ScoringAction.DWELLING, CultBonus(Cult.WATER, 4, "priests")),
        ),
    )
    upgrade = UpgradeBuilding(tile.position, BuildingType.TRADING_HOUSE)
    assert upgrade in listing(state)
    before = state.players[player].victory_points
    after = GAME.apply(state, player, upgrade).state
    assert after.players[player].victory_points == before + 3


def test_favor_tile_pays_pass_vp() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    positions = [
        tile.position
        for tile in state.board.tiles
        if tile.is_land and tile.building is None
    ][:2]
    state = action_state(
        state,
        player,
        (positions[0], BuildingType.TRADING_HOUSE),
        (positions[1], BuildingType.TRADING_HOUSE),
    )
    state = replace_player(
        state,
        player,
        replace(state.players[player], favors=frozenset({11})),
    )
    before = state.players[player].victory_points
    after = GAME.apply(state, player, Pass()).state
    assert after.players[player].victory_points == before + 3


def test_favor_tile_lowers_the_town_power_needed() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    state = replace_player(
        state,
        player,
        replace(state.players[player], favors=frozenset({4})),
    )
    assert town_power(state.players[player]) == 6
    board = Board.base()
    positions = [Hex(q, 0) for q in range(4)]
    for position, kind in zip(
        positions,
        (
            BuildingType.TRADING_HOUSE,
            BuildingType.TRADING_HOUSE,
            BuildingType.DWELLING,
            BuildingType.DWELLING,
        ),
        strict=True,
    ):
        board = board.place(position, Building(kind, player))
    component = board.connected(positions[0], player)
    assert not town_ready(board, component)
    assert town_ready(board, component, power=town_power(state.players[player]))


def test_favor_notation() -> None:
    assert GAME.format_action(TakeFavorTile(5)) == "favor 5"
    assert GAME.parse_action("favor 5") == TakeFavorTile(5)


def test_observation_and_text_show_favors() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    state = replace_player(
        state,
        player,
        replace(state.players[player], favors=frozenset({0, 6})),
    )
    observation = GAME.observe(state, None)
    data = observation.data
    players = data["players"]
    assert isinstance(players, list)
    entry = players[int(player)]
    assert isinstance(entry, dict)
    assert entry["favors"] == [
        {"index": 0, "label": "3 Fire cult steps"},
        {
            "index": 6,
            "label": "2 Earth cult steps; 1 worker and 1 power each round",
        },
    ]
    text = GAME.render_text(observation)
    assert "favors [0 3 Fire cult steps, 6 2 Earth cult steps" in text
