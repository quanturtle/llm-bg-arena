"""Tests for Terra Mystica towns: founding, town tiles and the Mermaids' river."""

from dataclasses import replace

from boardgames.games.terra_mystica import (
    Board,
    BuildDwelling,
    Building,
    Hex,
    TakeTownTile,
    UpgradeBuilding,
)
from boardgames.games.terra_mystica.constants import (
    FACTION_BY_TYPE,
    TOWN_SUPPLY,
    TOWN_TILES,
    BuildingType,
    Cult,
    CultBonus,
    FactionType,
    ScoringAction,
    ScoringTile,
)
from boardgames.games.terra_mystica.model import replace_player, settle_town, town_ready
from boardgames.games.terra_mystica.towns import build_river_choices
from tests.games.terra_mystica.support import (
    GAME,
    P1,
    _mermaid_gap_state,
    _neutral_scoring,
    _town_gap_layout,
    action_state,
    listing,
    play_setup,
    start,
)


def test_towns_require_power_and_are_marked_once() -> None:
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
                if (other := state.board.tile(neighbour)) is not None and other.is_land
            ]
        )
        >= 3
    )
    types = (
        BuildingType.STRONGHOLD,
        BuildingType.TRADING_HOUSE,
        BuildingType.TEMPLE,
        BuildingType.DWELLING,
    )
    neighbours = [
        neighbour
        for neighbour in position.neighbours()
        if (tile := state.board.tile(neighbour)) is not None and tile.is_land
    ][:3]
    state = action_state(
        state,
        player,
        (position, types[0]),
        *zip(neighbours, types[1:], strict=True),
    )
    component = state.board.connected(position, player)
    assert town_ready(state.board, component)
    board, founded = settle_town(state.board, position, player, towns_left=TOWN_SUPPLY)
    assert founded
    for hex_position in component:
        tile = board.tile(hex_position)
        assert tile is not None and tile.building is not None
        assert tile.building.in_town
    assert not settle_town(board, position, player, towns_left=TOWN_SUPPLY)[1]
    weak = Board.base()
    weak_positions = [Hex(q, 0) for q in range(4)]
    for weak_position, weak_type in zip(
        weak_positions,
        (
            BuildingType.TRADING_HOUSE,
            BuildingType.TRADING_HOUSE,
            BuildingType.DWELLING,
            BuildingType.DWELLING,
        ),
        strict=True,
    ):
        weak = weak.place(weak_position, Building(weak_type, player))
    weak_component = weak.connected(weak_positions[0], player)
    assert not town_ready(weak, weak_component)
    assert not settle_town(weak, weak_positions[0], player, towns_left=TOWN_SUPPLY)[1]


def test_town_supply_stops_after_ten_towns() -> None:
    board = Board.base()
    player = P1
    position = next(tile.position for tile in board.tiles if tile.is_land)
    assert not settle_town(board, position, player, towns_left=0)[1]


def _town_gap_board(river_between: bool) -> tuple[Board, Hex, Hex | None]:
    board = Board.base()
    a, a2, b, b2 = _town_gap_layout(board, river_between=river_between)
    for position, kind in (
        (a, BuildingType.STRONGHOLD),
        (a2, BuildingType.TRADING_HOUSE),
        (b, BuildingType.TEMPLE),
        (b2, BuildingType.DWELLING),
    ):
        board = board.place(position, Building(kind, P1))
    river = next(
        neighbour for neighbour in a.neighbours() if neighbour in b.neighbours()
    )
    return board, b2, river


def test_towns_ignore_indirect_adjacency() -> None:
    board, position, _river = _town_gap_board(river_between=False)
    assert not settle_town(board, position, P1, towns_left=TOWN_SUPPLY)[1]


def test_mermaids_may_join_one_river_space_for_a_town() -> None:
    board, position, river = _town_gap_board(river_between=True)
    assert settle_town(board, position, P1, towns_left=TOWN_SUPPLY, river=river)[1]


def test_mermaids_may_join_the_river_town() -> None:
    state, player, target, river = _mermaid_gap_state()
    assert BuildDwelling(target) in listing(state)
    assert BuildDwelling(target, river=river) in listing(state)

    separate = GAME.apply(state, player, BuildDwelling(target)).state
    joined = GAME.apply(state, player, BuildDwelling(target, river=river)).state
    assert joined.towns == 1
    assert joined.players[player].keys == 1
    assert separate.towns == 0
    assert separate.players[player].keys == 0
    tile = separate.board.tile(target)
    assert tile is not None and tile.building is not None
    assert not tile.building.in_town


def test_mermaids_do_not_list_a_river_that_would_cancel_a_new_town() -> None:
    board = Board.base()
    a, a2, b, b2 = _town_gap_layout(board, river_between=True)
    river = next(
        neighbour for neighbour in a.neighbours() if neighbour in b.neighbours()
    )

    used = {a, a2, b, b2, river}

    def extras(positions: tuple[Hex, ...], avoid: set[Hex]) -> list[Hex]:
        found: list[Hex] = []
        for position in positions:
            for neighbour in position.neighbours():
                tile = board.tile(neighbour)
                if (
                    tile is not None
                    and tile.is_land
                    and tile.building is None
                    and neighbour not in used
                    and neighbour not in found
                    and not (set(neighbour.neighbours()) & avoid)
                ):
                    found.append(neighbour)
        return found

    a_extra = extras((a, a2), {b, b2})[:2]
    used |= set(a_extra)
    b_extra = extras((b, b2), {a, a2})[:2]
    assert len(a_extra) == 2
    assert len(b_extra) == 2
    for position, kind, in_town in (
        (a, BuildingType.STRONGHOLD, True),
        (a2, BuildingType.TRADING_HOUSE, True),
        (a_extra[0], BuildingType.DWELLING, True),
        (a_extra[1], BuildingType.DWELLING, True),
        (b, BuildingType.STRONGHOLD, False),
        (b_extra[0], BuildingType.TRADING_HOUSE, False),
        (b_extra[1], BuildingType.DWELLING, False),
    ):
        board = board.place(position, Building(kind, P1, in_town=in_town))
    assert (
        build_river_choices(
            board,
            P1,
            FACTION_BY_TYPE[FactionType.MERMAIDS],
            b2,
            TOWN_SUPPLY,
        )
        == []
    )


def test_mermaids_only_list_join_when_it_changes_the_town() -> None:
    state, _player, target, river = _mermaid_gap_state(weak=True)
    assert BuildDwelling(target) in listing(state)
    assert BuildDwelling(target, river=river) not in listing(state)


def test_only_mermaids_may_join_the_river_town() -> None:
    state = play_setup(start(num_players=2, seed=2))
    player = state.active_player
    target = next(
        tile.position
        for tile in state.board.tiles
        if tile.is_land and tile.building is None
    )
    river = next(tile.position for tile in state.board.tiles if not tile.is_land)
    (decision,) = GAME.pending_decisions(state)
    space = GAME.legal_actions(state, decision)
    assert "Only the Mermaids" in space.explain(BuildDwelling(target, river=river))

    with_building = action_state(state, player, (target, BuildingType.DWELLING))
    (decision,) = GAME.pending_decisions(with_building)
    space = GAME.legal_actions(with_building, decision)
    assert "Only the Mermaids" in space.explain(
        UpgradeBuilding(target, BuildingType.TRADING_HOUSE, river=river)
    )


def test_town_upgrade_awards_points_key_and_round_tile_vp() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    positions = [Hex(q, 0) for q in range(4)]
    state = action_state(
        state,
        player,
        *zip(
            positions,
            (
                BuildingType.TRADING_HOUSE,
                BuildingType.TRADING_HOUSE,
                BuildingType.DWELLING,
                BuildingType.DWELLING,
            ),
            strict=True,
        ),
    )
    state = replace_player(
        state, player, replace(state.players[player], faction=FactionType.WITCHES)
    )
    state = replace(
        state,
        scoring=(ScoringTile(ScoringAction.TOWN, CultBonus(Cult.EARTH, 4, "spades")),),
    )
    before = state.players[player].victory_points
    state = GAME.apply(
        state, player, UpgradeBuilding(positions[3], BuildingType.TRADING_HOUSE)
    ).state
    assert state.phase == "town_choice"
    state = GAME.apply(state, player, TakeTownTile(0)).state
    after = state.players[player]
    assert after.victory_points - before == 15
    assert after.keys == 1
    return


def test_town_tile_choice_awards_its_reward() -> None:
    state = start(num_players=2, seed=1)
    player = state.order[0]
    positions = [Hex(q, 0) for q in range(4)]
    state = _neutral_scoring(state)
    state = action_state(
        state,
        player,
        *zip(
            positions,
            (
                BuildingType.TRADING_HOUSE,
                BuildingType.TRADING_HOUSE,
                BuildingType.DWELLING,
                BuildingType.DWELLING,
            ),
            strict=True,
        ),
    )
    state = GAME.apply(
        state, player, UpgradeBuilding(positions[3], BuildingType.TRADING_HOUSE)
    ).state
    assert state.phase == "town_choice"
    assert {
        action for action in listing(state) if isinstance(action, TakeTownTile)
    } == {TakeTownTile(index) for index in range(len(TOWN_TILES))}
    before = state.players[player]
    state = GAME.apply(state, player, TakeTownTile(2)).state
    after = state.players[player]
    assert state.town_tiles[2] == 1
    assert after.victory_points - before.victory_points == TOWN_TILES[2].victory_points
    assert after.resources.priests == before.resources.priests + 1
