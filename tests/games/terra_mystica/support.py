"""Shared game instance, seats and state builders for the Terra Mystica tests."""

from dataclasses import replace

from boardgames.core import PlayerId, seats
from boardgames.games.terra_mystica import (
    Action,
    Board,
    Building,
    Hex,
    TerraMystica,
    TerraMysticaConfig,
    TerraMysticaState,
)
from boardgames.games.terra_mystica.constants import (
    BuildingType,
    Cult,
    CultBonus,
    FactionType,
    Resources,
    ScoringAction,
    ScoringTile,
    Terrain,
)
from boardgames.games.terra_mystica.model import replace_player

GAME = TerraMystica()
P1, P2, P3 = seats(3)


def start(num_players: int = 2, seed: int = 1, rounds: int = 1) -> TerraMysticaState:
    return GAME.setup(
        TerraMysticaConfig(num_players=num_players, rounds=rounds), seed
    ).state


def listing(state: TerraMysticaState) -> tuple[Action, ...]:
    (decision,) = GAME.pending_decisions(state)
    actions = GAME.legal_actions(state, decision).listing(10_000)
    assert actions is not None
    return actions


def notations(state: TerraMysticaState) -> list[str]:
    return [GAME.format_action(action) for action in listing(state)]


def play(state: TerraMysticaState, notation: str) -> TerraMysticaState:
    (decision,) = GAME.pending_decisions(state)
    action = GAME.parse_action(notation)
    return GAME.apply(state, decision.player, action).state


def play_setup(state: TerraMysticaState) -> TerraMysticaState:
    while state.phase == "setup":
        state = play(state, notations(state)[0])
    return state


def with_resources(
    state: TerraMysticaState, player: PlayerId, **values: int
) -> TerraMysticaState:
    resources = replace(state.players[player].resources, **values)
    return replace_player(
        state, player, replace(state.players[player], resources=resources)
    )


def action_state(
    state: TerraMysticaState, player: PlayerId, *buildings: tuple[Hex, BuildingType]
) -> TerraMysticaState:
    board = state.board
    for position, building_type in buildings:
        board = board.place(position, Building(building_type, player))
    state = replace_player(
        state,
        player,
        replace(state.players[player], resources=Resources(coins=50, workers=50)),
    )
    return replace(
        state,
        board=board,
        phase="action",
        setup_queue=(),
        active_player=player,
        passed=frozenset(),
        pass_order=(),
        round=1,
    )


def empty_land_tiles(state: TerraMysticaState) -> list[Hex]:
    return [
        tile.position
        for tile in state.board.tiles
        if tile.is_land and tile.building is None
    ]


def _neutral_scoring(state: TerraMysticaState) -> TerraMysticaState:
    tile = ScoringTile(ScoringAction.TRADING_HOUSE, CultBonus(Cult.AIR, 4, "priests"))
    return replace(state, scoring=(tile, tile))


def _town_gap_layout(board: Board, *, river_between: bool) -> tuple[Hex, Hex, Hex, Hex]:
    """Two adjacent pairs, two spaces apart, with a land or river gap."""

    def land(position: Hex) -> bool:
        tile = board.tile(position)
        return tile is not None and tile.is_land

    for a in (tile.position for tile in board.tiles if tile.is_land):
        for a2 in (neighbour for neighbour in a.neighbours() if land(neighbour)):
            for b in (tile.position for tile in board.tiles if tile.is_land):
                if a.distance(b) != 2 or b in a2.neighbours() or b == a2:
                    continue
                middle = [
                    neighbour
                    for neighbour in a.neighbours()
                    if neighbour in b.neighbours()
                ]
                is_river = all(
                    not land(neighbour) and board.tile(neighbour) is not None
                    for neighbour in middle
                )
                if is_river is not river_between:
                    continue
                for b2 in (
                    neighbour for neighbour in b.neighbours() if land(neighbour)
                ):
                    if b2 in (a, a2) or b2 in a.neighbours() or b2 in a2.neighbours():
                        continue
                    return a, a2, b, b2
    raise AssertionError("no two-group layout found")


def _mermaid_gap_state(
    *, weak: bool = False
) -> tuple[TerraMysticaState, PlayerId, Hex, Hex]:
    state = start(num_players=2, seed=2)
    player = state.order[0]
    board = Board.base()
    a, a2, b, b2 = _town_gap_layout(board, river_between=True)
    river = next(
        neighbour for neighbour in a.neighbours() if neighbour in b.neighbours()
    )
    buildings = [(a, BuildingType.STRONGHOLD)]
    if not weak:
        buildings.append((a2, BuildingType.TRADING_HOUSE))
    buildings.append((b, BuildingType.TEMPLE))
    for position, kind in buildings:
        board = board.place(position, Building(kind, player))
    state = replace_player(
        state,
        player,
        replace(
            state.players[player],
            faction=FactionType.MERMAIDS,
            resources=Resources(coins=50, workers=50, priests=5, power1=5, power2=7),
            shipping=1,
        ),
    )
    state = _neutral_scoring(
        replace(
            state,
            board=board,
            phase="action",
            active_player=player,
            passed=frozenset(),
            pass_order=(),
            setup_queue=(),
            round=1,
        )
    )
    return state, player, b2, river


def _terrain_target(
    state: TerraMysticaState, terrain: Terrain, distance: int
) -> tuple[Hex, Hex]:
    starts = [tile.position for tile in state.board.tiles if tile.is_land]
    targets = [
        tile.position
        for tile in state.board.tiles
        if tile.is_land and tile.terrain is terrain
    ]
    for start in starts:
        for target in targets:
            if start.distance(target) == distance:
                return start, target
    raise AssertionError(f"no {terrain.value} tile {distance} from a start")


def _same_terrain_pair(
    state: TerraMysticaState, terrain: Terrain, distance: int
) -> tuple[Hex, Hex]:
    positions = [
        tile.position
        for tile in state.board.tiles
        if tile.is_land and tile.terrain is terrain
    ]
    for start in positions:
        for target in positions:
            if start.distance(target) == distance:
                return start, target
    raise AssertionError(f"no {terrain.value} pair {distance} apart")
