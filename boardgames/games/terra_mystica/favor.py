"""Terra Mystica favor tiles: the temple choice and its immediate effects."""

from dataclasses import replace

from boardgames.core import Event, IllegalActionError, PlayerId, Transition, seat_label
from boardgames.games.terra_mystica.constants import FAVOR_TILES
from boardgames.games.terra_mystica.cults import cult_top_occupied
from boardgames.games.terra_mystica.model import (
    Action,
    TakeFavorTile,
    TerraMysticaState,
    advance_cult,
    available_favors,
    replace_player,
)
from boardgames.games.terra_mystica.rounds import advance_turn
from boardgames.games.terra_mystica.towns import town_rewards


def favor_actions(state: TerraMysticaState) -> list[Action]:
    """Every favor tile still available to take."""
    return [TakeFavorTile(index) for index in available_favors(state)]


def take_favor_tile(
    state: TerraMysticaState, player: PlayerId, index: int
) -> Transition[TerraMysticaState]:
    """Take one favor tile, then ask again or resume the turn."""
    if state.phase != "favor_choice":
        raise IllegalActionError("no favor tile is owed now")
    if player != state.active_player:
        raise IllegalActionError(f"it is {seat_label(state.active_player)}'s turn")
    if index < 0 or index >= len(FAVOR_TILES):
        raise IllegalActionError("there is no such favor tile")
    if index not in available_favors(state):
        raise IllegalActionError("that favor tile is already taken")
    tile = FAVOR_TILES[index]
    owner = state.players[player]
    owner = replace(owner, favors=owner.favors | {index})
    power = 0
    if tile.cult is not None and tile.steps:
        owner, power = advance_cult(
            owner,
            tile.cult,
            tile.steps,
            top_occupied=cult_top_occupied(state, player, tile.cult),
        )
    state = replace_player(state, player, owner)
    pending = max(0, state.pending_favors - 1)
    state = replace(state, pending_favors=pending)
    detail = ""
    if tile.cult is not None and tile.steps:
        detail = f" and advanced {tile.cult.value} by {tile.steps}"
        if power:
            detail += f" (gained {power} power)"
    event = Event(
        "favor_taken",
        f"{seat_label(player)} took favor tile {index} ({tile.label}){detail}.",
        {
            "player": player,
            "favor": index,
            "label": tile.label,
            "cult": tile.cult.value if tile.cult is not None else None,
            "steps": tile.steps,
            "power": power,
        },
    )
    if pending > 0:
        return Transition(
            replace(state, phase="favor_choice", active_player=player), (event,)
        )
    town_position = state.pending_town_position
    if state.pending_town and town_position is not None:
        owner = state.players[player]
        board, resources, victory_points, keys, founded = town_rewards(
            state,
            player,
            state.board,
            town_position,
            owner.resources,
            owner.victory_points,
            owner.keys,
            river=state.pending_town_river,
        )
        owner = replace(
            owner,
            resources=resources,
            victory_points=victory_points,
            keys=keys,
        )
        state = replace_player(state, player, owner)
        state = replace(
            state,
            board=board,
            pending_town=False,
            pending_town_position=None,
            pending_town_river=None,
        )
        events = [event]
        if founded:
            state = replace(state, towns=state.towns + 1)
            events.append(
                Event(
                    "town_founded",
                    f"{seat_label(player)} founded a town at "
                    f"{town_position.notation()}.",
                    {"player": player, "position": town_position.notation()},
                )
            )
            state = replace(state, phase="town_choice", active_player=player)
            return Transition(state, tuple(events))
        state = replace(state, phase="action", active_player=player)
        return advance_turn(state, player, tuple(events))
    state = replace(
        state,
        phase="action",
        active_player=player,
        pending_town=False,
        pending_town_position=None,
        pending_town_river=None,
    )
    return advance_turn(state, player, (event,))


def explain_favor(state: TerraMysticaState, action: Action) -> str:
    """Why a favor tile cannot be taken."""
    if not isinstance(action, TakeFavorTile):
        return "Choose a favor tile."
    if action.index < 0 or action.index >= len(FAVOR_TILES):
        return "There is no such favor tile."
    if action.index not in available_favors(state):
        return "That favor tile is already taken."
    return "That favor tile cannot be taken now."
