"""Terra Mystica cult tracks: sending priests and the limits on the top space."""

from dataclasses import replace

from boardgames.core import (
    Event,
    IllegalActionError,
    PlayerId,
    Transition,
    seat_label,
    seats,
)
from boardgames.games.terra_mystica.constants import CULT_ORDER, CULT_ORDER_STEPS, Cult
from boardgames.games.terra_mystica.model import (
    Action,
    AdvanceCult,
    SendPriest,
    TerraMysticaState,
    advance_cult,
    cult_limit,
    replace_player,
)
from boardgames.games.terra_mystica.rounds import advance_turn


def cult_top_occupied(state: TerraMysticaState, player: PlayerId, cult: Cult) -> bool:
    return any(
        other != player and state.players[other].cult(cult) >= 10
        for other in seats(len(state.players))
    )


def _cult_limit_for(state: TerraMysticaState, player: PlayerId, cult: Cult) -> int:
    return cult_limit(state.players[player], cult_top_occupied(state, player, cult))


def send_priest(
    state: TerraMysticaState,
    player: PlayerId,
    cult: Cult,
    order: int,
) -> Transition[TerraMysticaState]:
    owner = state.players[player]
    if owner.resources.priests <= 0:
        raise IllegalActionError("you have no priest to send")
    if (cult, order) in state.used_orders:
        raise IllegalActionError("that order space is already occupied")
    resources = replace(owner.resources, priests=owner.resources.priests - 1)
    owner = replace(owner, resources=resources)
    state = replace(state, used_orders={**state.used_orders, (cult, order): player})
    steps = CULT_ORDER_STEPS[order]
    owner, gained = advance_cult(
        owner,
        cult,
        steps,
        top_occupied=cult_top_occupied(state, player, cult),
    )
    state = replace_player(state, player, owner)
    event = Event(
        "priest_sent",
        f"{seat_label(player)} sent a priest to {cult.value} order {order} "
        f"and advanced {steps} (gain {gained} power).",
        {
            "player": player,
            "cult": cult.value,
            "order": order,
            "steps": steps,
            "power": gained,
        },
    )
    return advance_turn(state, player, (event,))


def advance_cult_with_priest(
    state: TerraMysticaState, player: PlayerId, cult: Cult
) -> Transition[TerraMysticaState]:
    owner = state.players[player]
    if owner.resources.priests <= 0:
        raise IllegalActionError("you have no priest to send")
    if owner.cult(cult) >= _cult_limit_for(state, player, cult):
        raise IllegalActionError("that cult track cannot advance further")
    owner = replace(
        owner,
        resources=replace(owner.resources, priests=owner.resources.priests - 1),
    )
    owner, gained = advance_cult(
        owner,
        cult,
        1,
        top_occupied=cult_top_occupied(state, player, cult),
    )
    state = replace_player(state, player, owner)
    event = Event(
        "cult_advanced",
        f"{seat_label(player)} spent a priest and advanced {cult.value} by 1 "
        f"(gain {gained} power).",
        {"player": player, "cult": cult.value, "steps": 1, "power": gained},
    )
    return advance_turn(state, player, (event,))


def priest_actions(state: TerraMysticaState, player: PlayerId) -> list[Action]:
    owner = state.players[player]
    actions: list[Action] = []
    if owner.resources.priests > 0:
        for cult in CULT_ORDER:
            for order in range(4):
                if (cult, order) not in state.used_orders:
                    actions.append(SendPriest(cult, order))
            if owner.cult(cult) < _cult_limit_for(state, player, cult):
                actions.append(AdvanceCult(cult))
    return actions


def explain_send_priest(
    state: TerraMysticaState, player: PlayerId, action: SendPriest
) -> str:
    owner = state.players[player]
    if owner.resources.priests <= 0:
        return "You have no priest to send."
    if (action.cult, action.order) in state.used_orders:
        return "That order space is already occupied."
    return "You cannot send a priest there now."


def explain_advance_cult(
    state: TerraMysticaState, player: PlayerId, action: AdvanceCult
) -> str:
    owner = state.players[player]
    if owner.resources.priests <= 0:
        return "You have no priest to send."
    if owner.cult(action.cult) >= _cult_limit_for(state, player, action.cult):
        return "That cult track cannot advance further."
    return "You cannot advance that cult now."
