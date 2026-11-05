"""Catan trading: bank and harbour trades, and one-for-one offers between players."""

from dataclasses import replace

from boardgames.core import (
    Event,
    IllegalActionError,
    PlayerId,
    Transition,
    seat_label,
    seats,
)
from boardgames.games.catan.model import (
    RESOURCES,
    AcceptOffer,
    Action,
    BankTrade,
    CatanState,
    DeclineOffer,
    Hand,
    Offer,
    OfferTrade,
    Resource,
    empty_hand,
    hand_get,
    hand_minus,
    hand_with,
    replace_at,
)
from boardgames.games.catan.rules import trade_rates


def bank_trade_actions(state: CatanState, player: PlayerId) -> list[Action]:
    """Bank trades at the player's best rate for every resource they can pay."""
    actions: list[Action] = []
    hand = state.hands[player]
    rates = trade_rates(state, player)
    for give in RESOURCES:
        rate = rates[give]
        if hand_get(hand, give) < rate:
            continue
        for take in RESOURCES:
            if take != give:
                actions.append(BankTrade(give, rate, take))
    return actions


def explain_bank_trade(
    state: CatanState,
    player: PlayerId,
    hand: Hand,
    give: Resource,
    count: int,
    take: Resource,
) -> str:
    """Why a bank trade is illegal."""
    if give == take:
        return "A bank trade must exchange two different resources."
    rate = trade_rates(state, player)[give]
    if count != rate:
        return f"Your bank rate for {give} is {rate}:1, not {count}:1."
    if hand_get(hand, give) < rate:
        return f"You need {rate} {give} for that trade."
    return "You cannot make that bank trade now."


def bank_trade(
    state: CatanState, player: PlayerId, action: BankTrade
) -> Transition[CatanState]:
    """Pay the bank its rate in one resource and take one card of another."""
    cost = hand_with(empty_hand(), action.give, action.give_count)
    hand = hand_minus(state.hands[player], cost)
    if hand is None:
        raise IllegalActionError("you do not have the cards for that bank trade")
    hand = hand_with(hand, action.take, 1)
    events = [
        Event(
            "bank_trade",
            f"{seat_label(player)} traded {action.give_count} {action.give} "
            f"for 1 {action.take} with the bank.",
            {
                "player": player,
                "give": action.give,
                "give_count": action.give_count,
                "take": action.take,
            },
        )
    ]
    return Transition(
        replace(state, hands=replace_at(state.hands, player, hand)),
        tuple(events),
    )


def offer_actions(state: CatanState, player: PlayerId) -> list[Action]:
    """One-for-one offers to each opponent, until the turn's offer limit."""
    actions: list[Action] = []
    hand = state.hands[player]
    can_offer = (
        state.config.max_offers_per_turn == 0
        or state.offers_this_turn < state.config.max_offers_per_turn
    )
    if can_offer:
        for target in seats(state.config.num_players):
            if target == player:
                continue
            for give in RESOURCES:
                if hand_get(hand, give) < 1:
                    continue
                for take in RESOURCES:
                    if take == give:
                        continue
                    actions.append(OfferTrade(give, take, target))
    return actions


def explain_offer(
    state: CatanState, player: PlayerId, hand: Hand, give: Resource, target: PlayerId
) -> str:
    """Why a trade offer is illegal."""
    if (
        state.config.max_offers_per_turn
        and state.offers_this_turn >= state.config.max_offers_per_turn
    ):
        limit = state.config.max_offers_per_turn
        noun = "offer" if limit == 1 else "offers"
        return f"You have already made {limit} {noun} this turn."
    if target == player:
        return "You cannot offer a trade to yourself."
    if not 0 <= target < state.config.num_players:
        return f"There is no {seat_label(target)}."
    if hand_get(hand, give) < 1:
        return f"You have no {give} to offer."
    return "You cannot offer that trade now."


def offer_trade(
    state: CatanState, player: PlayerId, action: OfferTrade
) -> Transition[CatanState]:
    """Open an offer; its target answers in the trade_response phase."""
    offer = Offer(player, action.target, action.give, action.take)
    events = [
        Event(
            "offer_made",
            f"{seat_label(player)} offers {seat_label(action.target)} "
            f"1 {action.give} for 1 {action.take}.",
            {
                "from": player,
                "to": action.target,
                "give": action.give,
                "take": action.take,
            },
        )
    ]
    return Transition(
        replace(
            state,
            pending_offer=offer,
            phase="trade_response",
            offers_this_turn=state.offers_this_turn + 1,
        ),
        tuple(events),
    )


def response_actions(state: CatanState, player: PlayerId) -> list[Action]:
    """Accept when the target holds the requested card; decline always."""
    offer = state.pending_offer
    actions: list[Action] = []
    if (
        offer is not None
        and offer.to_player == player
        and hand_get(state.hands[player], offer.take) > 0
    ):
        actions.append(AcceptOffer())
    actions.append(DeclineOffer())
    return actions


def explain_accept(state: CatanState, player: PlayerId, hand: Hand) -> str:
    """Why accepting the offer is illegal."""
    offer = state.pending_offer
    if offer is None:
        return "There is no open offer to accept."
    if offer.to_player != player:
        return "That offer is not yours to accept."
    if hand_get(hand, offer.take) < 1:
        return f"You have no {offer.take} to give for this offer."
    return "You cannot accept that offer now."


def accept_offer(state: CatanState, player: PlayerId) -> Transition[CatanState]:
    """Swap one card each way and return to the action phase."""
    offer = state.pending_offer
    if offer is None or offer.to_player != player:
        raise IllegalActionError("there is no offer for you to accept")
    giver = offer.from_player
    giver_hand = state.hands[giver]
    taker_hand = state.hands[player]
    if hand_get(giver_hand, offer.give) < 1:
        raise IllegalActionError("the offering player no longer has that card")
    if hand_get(taker_hand, offer.take) < 1:
        raise IllegalActionError("you no longer have the requested card")
    giver_hand = hand_with(hand_with(giver_hand, offer.give, -1), offer.take)
    taker_hand = hand_with(hand_with(taker_hand, offer.take, -1), offer.give)
    hands = replace_at(replace_at(state.hands, giver, giver_hand), player, taker_hand)
    events = [
        Event(
            "offer_accepted",
            f"{seat_label(player)} accepted: {seat_label(giver)} gave "
            f"1 {offer.give} for 1 {offer.take}.",
            {
                "from": giver,
                "to": player,
                "give": offer.give,
                "take": offer.take,
            },
        )
    ]
    return Transition(
        replace(state, hands=hands, pending_offer=None, phase="actions"),
        tuple(events),
    )


def explain_decline(state: CatanState) -> str:
    """Why declining the offer is illegal."""
    if state.pending_offer is None:
        return "There is no open offer to decline."
    return "That offer is not yours to decline."


def decline_offer(state: CatanState, player: PlayerId) -> Transition[CatanState]:
    """Close the offer unanswered and return to the action phase."""
    offer = state.pending_offer
    if offer is None or offer.to_player != player:
        raise IllegalActionError("there is no offer for you to decline")
    events = [
        Event(
            "offer_declined",
            f"{seat_label(player)} declined the offer.",
            {"from": offer.from_player, "to": player},
        )
    ]
    return Transition(
        replace(state, pending_offer=None, phase="actions"),
        tuple(events),
    )
