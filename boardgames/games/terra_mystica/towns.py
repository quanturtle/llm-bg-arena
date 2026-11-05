"""Terra Mystica towns: founding rewards, town tiles and the Mermaids' river choices."""

from dataclasses import replace

from boardgames.core import (
    Event,
    IllegalActionError,
    PlayerId,
    Transition,
    seat_label,
)
from boardgames.games.terra_mystica.constants import (
    CULT_ORDER,
    SCORING_VALUES,
    TOWN_SUPPLY,
    TOWN_TILES,
    BuildingType,
    FactionProfile,
    FactionType,
    Income,
    Resources,
    ScoringAction,
)
from boardgames.games.terra_mystica.cults import cult_top_occupied
from boardgames.games.terra_mystica.model import (
    Action,
    Board,
    Building,
    Hex,
    TakeTownTile,
    TerraMysticaState,
    add_income,
    advance_cult,
    cap_priests,
    income_with_power,
    replace_player,
    settle_town,
)
from boardgames.games.terra_mystica.rounds import advance_turn, round_scoring
from boardgames.games.terra_mystica.strongholds import stronghold_reward


def town_rewards(
    state: TerraMysticaState,
    player: PlayerId,
    board: Board,
    position: Hex,
    resources: Resources,
    victory_points: int,
    keys: int,
    *,
    river: Hex | None = None,
) -> tuple[Board, Resources, int, int, bool]:
    """Mark a new town and award its points, key and faction bonus."""
    owner = state.players[player]
    board, founded = settle_town(
        board,
        position,
        player,
        river=river if owner.profile.type is FactionType.MERMAIDS else None,
        towns_left=TOWN_SUPPLY - state.towns,
    )
    if not founded:
        return board, resources, victory_points, keys, False
    profile = owner.profile
    victory_points += profile.town_vp_bonus
    keys += 1
    resources = add_income(resources, Income(workers=profile.town_workers_bonus))
    if round_scoring(state) is ScoringAction.TOWN:
        victory_points += SCORING_VALUES[ScoringAction.TOWN]
    return board, resources, victory_points, keys, True


def take_town_tile(
    state: TerraMysticaState, player: PlayerId, index: int
) -> Transition[TerraMysticaState]:
    if index < 0 or index >= len(TOWN_TILES):
        raise IllegalActionError("there is no such town tile")
    if state.town_tiles[index] <= 0:
        raise IllegalActionError("that town tile is already taken")
    tile = TOWN_TILES[index]
    owner = state.players[player]
    owner = replace(owner, victory_points=owner.victory_points + tile.victory_points)
    resources = income_with_power(
        owner.resources,
        Income(
            coins=tile.coins,
            workers=tile.workers,
            priests=tile.priests,
            power=tile.power,
        ),
    )
    owner = replace(owner, resources=cap_priests(state, player, resources))
    gained: list[str] = []
    if tile.cult_steps:
        for cult in CULT_ORDER:
            owner, power = advance_cult(
                owner,
                cult,
                1,
                top_occupied=cult_top_occupied(state, player, cult),
            )
            gained.append(f"{cult.value} +1 ({power} power)")
    state = replace_player(state, player, owner)
    town_tiles = list(state.town_tiles)
    town_tiles[index] -= 1
    state = replace(state, town_tiles=tuple(town_tiles))
    events = [
        Event(
            "town_tile",
            f"{seat_label(player)} took town tile {index} "
            f"({tile.victory_points} points).",
            {
                "player": player,
                "town_tile": index,
                "victory_points": tile.victory_points,
                "cults": gained,
            },
        )
    ]
    if state.pending_stronghold:
        state = replace(state, pending_stronghold=False)
        state, events = stronghold_reward(state, player, events)
        if state.phase in ("cult_spades", "stronghold_convert"):
            return Transition(state, tuple(events))
    state = replace(state, phase="action", active_player=player)
    return advance_turn(state, player, tuple(events))


def _town_outcome(
    board: Board,
    position: Hex,
    player: PlayerId,
    river: Hex | None,
    towns_left: int,
) -> tuple[Board, bool]:
    return settle_town(
        board,
        position,
        player,
        river=river,
        towns_left=towns_left,
    )


def _changing_rivers(
    board: Board,
    position: Hex,
    player: PlayerId,
    towns_left: int,
) -> list[Hex]:
    """River spaces that let this component found a new town."""
    direct = _town_outcome(board, position, player, None, towns_left)[1]
    if direct:
        return []
    rivers = {
        neighbour
        for member in board.connected(position, player)
        for neighbour in member.neighbours()
        if (tile := board.tile(neighbour)) is not None and not tile.is_land
    }
    return [
        river
        for river in sorted(rivers)
        if _town_outcome(board, position, player, river, towns_left)[1]
    ]


def build_river_choices(
    board: Board,
    player: PlayerId,
    profile: FactionProfile,
    position: Hex,
    towns_left: int,
) -> list[Hex]:
    """River skips that would change a Mermaid build's town."""
    if profile.type is not FactionType.MERMAIDS:
        return []
    built = board.place(position, Building(BuildingType.DWELLING, player))
    return _changing_rivers(built, position, player, towns_left)


def upgrade_river_choices(
    board: Board,
    player: PlayerId,
    profile: FactionProfile,
    position: Hex,
    target: BuildingType,
    towns_left: int,
) -> list[Hex]:
    """River skips that would change a Mermaid upgrade's town."""
    if profile.type is not FactionType.MERMAIDS:
        return []
    tile = board.tile(position)
    if tile is None or tile.building is None:
        return []
    upgraded = board.replace_tile(
        position, replace(tile, building=replace(tile.building, type=target))
    )
    return _changing_rivers(upgraded, position, player, towns_left)


def town_tile_actions(state: TerraMysticaState) -> list[Action]:
    return [
        TakeTownTile(index) for index, count in enumerate(state.town_tiles) if count > 0
    ]


def explain_town_choice(state: TerraMysticaState, action: Action) -> str:
    if isinstance(action, TakeTownTile):
        if action.index < 0 or action.index >= len(TOWN_TILES):
            return "There is no such town tile."
        if state.town_tiles[action.index] <= 0:
            return "That town tile is already taken."
    return "Choose an available town tile."
