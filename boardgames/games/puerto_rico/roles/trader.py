"""The Puerto Rico Trader: selling one good to the trading house."""

from dataclasses import replace

from boardgames.core import (
    Event,
    IllegalActionError,
    PlayerId,
    Transition,
    seat_label,
)
from boardgames.games.puerto_rico.constants import GOODS, TRADING_HOUSE_SPACES
from boardgames.games.puerto_rico.model import (
    Action,
    Pass,
    PlayerState,
    PuertoRicoState,
    Sell,
    goods_get,
    goods_remove,
    replace_player,
    sell_price,
)
from boardgames.games.puerto_rico.rounds import mark_acted


def apply_trader(
    state: PuertoRicoState, player: PlayerId, action: Action
) -> Transition[PuertoRicoState]:
    owner = state.players[player]
    if isinstance(action, Sell):
        good = action.good
        price = sell_price(state, player, good)
        owner = replace(
            owner,
            doubloons=owner.doubloons + price,
            goods=goods_remove(owner.goods, good, 1),
        )
        state = replace_player(state, player, owner)
        state = replace(state, trading_house=(*state.trading_house, good))
        event = Event(
            "good_sold",
            f"{seat_label(player)} sold a {good} for {price} doubloons.",
            {"player": player, "good": good, "price": price},
        )
        state, advanced = mark_acted(state, player)
        return Transition(state, (event, *advanced))
    if isinstance(action, Pass):
        state, advanced = mark_acted(state, player)
        event = Event(
            "trader_passed",
            f"{seat_label(player)} sold nothing.",
            {"player": player},
        )
        return Transition(state, (event, *advanced))
    raise IllegalActionError("only sell or pass actions are legal")


def trader_actions(state: PuertoRicoState, owner: PlayerState) -> list[Action]:
    actions: list[Action] = []
    if len(state.trading_house) < TRADING_HOUSE_SPACES:
        for good in GOODS:
            if goods_get(owner.goods, good) <= 0:
                continue
            if good in state.trading_house and not owner.active("office"):
                continue
            actions.append(Sell(good))
    actions.append(Pass())
    return actions


def explain_trader(state: PuertoRicoState, player: PlayerId, action: Action) -> str:
    """Why a Trader action is not legal for `player` now."""
    if isinstance(action, Sell):
        owner = state.players[player]
        if goods_get(owner.goods, action.good) <= 0:
            return f"You have no {action.good}."
        if len(state.trading_house) >= TRADING_HOUSE_SPACES:
            return "The trading house is full."
        if action.good in state.trading_house and not owner.active("office"):
            return f"The trading house already holds {action.good}; you need an Office."
    return "Sell a good you hold or pass."
