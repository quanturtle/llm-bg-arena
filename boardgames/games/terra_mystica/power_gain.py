"""Power opponents gain when a structure is built or upgraded next to them."""

from dataclasses import replace

from boardgames.core import Event, IllegalActionError, PlayerId, Transition, seat_label
from boardgames.games.terra_mystica.constants import BuildingType
from boardgames.games.terra_mystica.model import (
    Action,
    ChoosePowerGain,
    Hex,
    PowerGain,
    TerraMysticaState,
    gain_power,
    replace_player,
)
from boardgames.games.terra_mystica.rounds import advance_turn


def _opponent_order(state: TerraMysticaState, actor: PlayerId) -> tuple[PlayerId, ...]:
    """The actor's opponents in clockwise play order, starting to their left."""
    index = state.order.index(actor)
    return tuple(
        state.order[(index + offset) % len(state.order)]
        for offset in range(1, len(state.order))
    )


def queue_power_gains(
    state: TerraMysticaState,
    actor: PlayerId,
    position: Hex,
    building: BuildingType,
) -> TerraMysticaState:
    """Queue each opponent's power offer from a new or upgraded structure."""
    amounts: dict[PlayerId, int] = {}
    for neighbour in state.board.adjacent_opponents(position, actor, state.bridges):
        tile = state.board.tile(neighbour)
        if tile is None or tile.building is None:
            continue
        owner = tile.building.owner
        amounts[owner] = amounts.get(owner, 0) + tile.building.power_value
    pending = tuple(
        PowerGain(player, amounts[player], position, building, actor)
        for player in _opponent_order(state, actor)
        if amounts.get(player, 0) > 0
        and min(
            amounts[player],
            state.players[player].resources.power1
            + state.players[player].resources.power2,
        )
        > 0
    )
    if not pending:
        return state
    return replace(state, pending_power=pending, power_actor=actor)


def power_gain_amount(state: TerraMysticaState, gain: PowerGain) -> tuple[int, int]:
    """The power actually gained and the victory points it costs."""
    owner = state.players[gain.player]
    actual = min(gain.amount, owner.resources.power1 + owner.resources.power2)
    if actual - 1 > owner.victory_points:
        actual = owner.victory_points + 1
    return actual, max(0, actual - 1)


def power_gain_actions(state: TerraMysticaState, player: PlayerId) -> list[Action]:
    """Accept or decline the offer that belongs to `player`."""
    if state.phase != "power_gain" or not state.pending_power:
        return []
    if state.pending_power[0].player != player:
        return []
    return [ChoosePowerGain(True), ChoosePowerGain(False)]


def take_power_gain(
    state: TerraMysticaState, player: PlayerId, accept: bool
) -> Transition[TerraMysticaState]:
    """Resolve one opponent's power offer, then move to the next opponent."""
    if state.phase != "power_gain" or not state.pending_power:
        raise IllegalActionError("no power offer is waiting")
    gain = state.pending_power[0]
    if player != gain.player:
        raise IllegalActionError(f"it is {seat_label(gain.player)}'s power choice")
    owner = state.players[player]
    actual, cost = power_gain_amount(state, gain)
    if accept and actual > 0:
        owner = replace(
            owner,
            resources=gain_power(owner.resources, actual),
            victory_points=owner.victory_points - cost,
        )
        text = (
            f"{seat_label(player)} gained {actual} power from "
            f"{seat_label(gain.builder)}'s {gain.building.value} at "
            f"{gain.position.notation()}"
        )
        if cost:
            text += f" and paid {cost} victory point(s)"
        text += "."
    else:
        text = (
            f"{seat_label(player)} declined {gain.amount} power from "
            f"{seat_label(gain.builder)}'s {gain.building.value} at "
            f"{gain.position.notation()}."
        )
    event = Event(
        "power_gain",
        text,
        {
            "player": player,
            "builder": gain.builder,
            "position": gain.position.notation(),
            "building": gain.building.value,
            "offered": gain.amount,
            "gained": actual if accept else 0,
            "victory_points": -cost if accept else 0,
            "accepted": accept,
        },
    )
    state = replace_player(state, player, owner)
    pending = state.pending_power[1:]
    state = replace(state, pending_power=pending)
    if pending:
        return Transition(replace(state, active_player=pending[0].player), (event,))
    actor = state.power_actor
    if actor is None:
        raise IllegalActionError("no player is waiting to resume their turn")
    state = replace(state, phase="action", active_player=actor, power_actor=None)
    return advance_turn(state, actor, (event,))


def explain_power_gain(
    state: TerraMysticaState, player: PlayerId, action: Action
) -> str:
    """Why this power choice cannot be taken."""
    if not isinstance(action, ChoosePowerGain):
        return "Choose whether to gain power."
    if state.phase != "power_gain" or not state.pending_power:
        return "No power offer is waiting."
    if player != state.pending_power[0].player:
        return f"It is {seat_label(state.pending_power[0].player)}'s power choice."
    return "That power choice is not legal now."
