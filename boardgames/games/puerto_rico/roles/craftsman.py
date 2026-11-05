"""The Puerto Rico Craftsman: production for everyone and the chooser's privilege."""

from dataclasses import replace
from typing import cast

from boardgames.core import (
    Event,
    IllegalActionError,
    PlayerId,
    Transition,
    seat_label,
)
from boardgames.games.puerto_rico.constants import GOODS
from boardgames.games.puerto_rico.model import (
    Action,
    Goods,
    Pass,
    PlayerState,
    ProducePrivilege,
    PuertoRicoState,
    factory_bonus_for_produced,
    goods_add,
    goods_minus,
    goods_plus,
    goods_remove,
    production,
    replace_player,
)
from boardgames.games.puerto_rico.rounds import advance_role_picker


def run_production(
    state: PuertoRicoState, chooser: PlayerId
) -> tuple[PuertoRicoState, tuple[Event, ...]]:
    """Every player produces goods from the Craftsman chooser, limited by the bank."""
    events: list[Event] = []
    start = state.order.index(chooser)
    for offset in range(len(state.order)):
        seat = state.order[(start + offset) % len(state.order)]
        owner = state.players[seat]
        potential = production(owner)
        produced = [0, 0, 0, 0, 0]
        for index, amount in enumerate(potential):
            actual = min(amount, state.goods_supply[index])
            produced[index] = actual
        if any(produced):
            state = replace_player(
                state,
                seat,
                replace(
                    owner, goods=goods_plus(owner.goods, cast(Goods, tuple(produced)))
                ),
            )
            state = replace(
                state,
                goods_supply=goods_minus(
                    state.goods_supply, cast(Goods, tuple(produced))
                ),
            )
            events.append(
                Event(
                    "goods_produced",
                    f"{seat_label(seat)} produced goods.",
                    {"player": seat, "goods": produced},
                )
            )
        bonus = factory_bonus_for_produced(owner, cast(Goods, tuple(produced)))
        if bonus:
            state = replace_player(
                state,
                seat,
                replace(
                    state.players[seat],
                    doubloons=state.players[seat].doubloons + bonus,
                ),
            )
            events.append(
                Event(
                    "factory_bonus",
                    f"{seat_label(seat)}'s Factory gave {bonus} doubloons.",
                    {"player": seat, "doubloons": bonus},
                )
            )
    return state, tuple(events)


def apply_craftsman(
    state: PuertoRicoState, player: PlayerId, action: Action
) -> Transition[PuertoRicoState]:
    events: list[Event] = []
    if isinstance(action, ProducePrivilege):
        good = action.good
        owner = state.players[player]
        state = replace_player(
            state,
            player,
            replace(owner, goods=goods_add(owner.goods, good, 1)),
        )
        state = replace(state, goods_supply=goods_remove(state.goods_supply, good, 1))
        events.append(
            Event(
                "privilege_good",
                f"{seat_label(player)} took an extra {good}.",
                {"player": player, "good": good},
            )
        )
    elif isinstance(action, Pass):
        events.append(
            Event(
                "privilege_declined",
                f"{seat_label(player)} declined the Craftsman privilege.",
                {"player": player},
            )
        )
    else:
        raise IllegalActionError("only a privilege good or pass is legal")
    state = advance_role_picker(
        replace(
            state,
            active_role=None,
            players_acted=frozenset(),
            captain_passes=0,
        )
    )
    return Transition(state, tuple(events))


def craftsman_actions(state: PuertoRicoState, owner: PlayerState) -> list[Action]:
    actions: list[Action] = []
    potential = production(owner)
    for index, good in enumerate(GOODS):
        if potential[index] > 0 and state.goods_supply[index] > 0:
            actions.append(ProducePrivilege(good))
    actions.append(Pass())
    return actions


def explain_craftsman(state: PuertoRicoState, player: PlayerId, action: Action) -> str:
    """Why a Craftsman action is not legal for `player` now."""
    if isinstance(action, ProducePrivilege):
        potential = production(state.players[player])
        index = GOODS.index(action.good)
        if potential[index] <= 0 or state.goods_supply[index] <= 0:
            return f"You cannot produce an extra {action.good}."
    return "Take a producible good or pass."
