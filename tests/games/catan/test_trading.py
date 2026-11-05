from dataclasses import replace

import pytest

from boardgames.core import IllegalActionError
from boardgames.games.catan import (
    AcceptOffer,
    BankTrade,
    CatanConfig,
    DeclineOffer,
    OfferTrade,
)
from boardgames.games.catan.model import RESOURCES, empty_hand, hand_from
from tests.games.catan.support import (
    GAME,
    P1,
    P2,
    P3,
    action_state,
    listing,
    notation,
    play_setup,
    set_hand,
)


def test_bank_trade_uses_four_to_one_without_a_port() -> None:
    state, _ = play_setup()
    no_ports = replace(state, ports=(), phase="actions", dice=(1, 2))
    funded = set_hand(no_ports, P1, hand_from(wood=4))
    trade = BankTrade("wood", 4, "ore")
    assert GAME.format_action(trade) in notation(funded)
    after = GAME.apply(funded, P1, trade).state
    assert after.hands[P1] == hand_from(ore=1)
    with pytest.raises(IllegalActionError):
        GAME.apply(funded, P1, BankTrade("wood", 3, "ore"))


def test_player_offer_accept_transfers_one_card_each_way() -> None:
    state, _ = play_setup()
    hands = (
        hand_from(wood=1),
        hand_from(ore=1),
        empty_hand(),
    )
    offered = action_state(replace(state, hands=hands))
    offer = OfferTrade("wood", "ore", P2)
    assert offer in listing(offered)
    pending = GAME.apply(offered, P1, offer).state
    assert pending.phase == "trade_response"
    assert pending.pending_offer is not None
    assert [decision.player for decision in GAME.pending_decisions(pending)] == [P2]
    accepted = GAME.apply(pending, P2, AcceptOffer()).state
    assert accepted.phase == "actions"
    assert accepted.hands[P1] == hand_from(ore=1)
    assert accepted.hands[P2] == hand_from(wood=1)
    assert accepted.pending_offer is None


def test_offers_ignore_the_target_hand_and_accept_needs_the_card() -> None:
    state, _ = play_setup()
    offered = action_state(
        replace(state, hands=(hand_from(wood=1), empty_hand(), hand_from(ore=1)))
    )
    assert [a for a in listing(offered) if isinstance(a, OfferTrade)] == [
        OfferTrade("wood", take, target)
        for target in (P2, P3)
        for take in RESOURCES
        if take != "wood"
    ]
    to_p2 = GAME.apply(offered, P1, OfferTrade("wood", "ore", P2)).state
    assert notation(to_p2) == ["decline"]
    with pytest.raises(IllegalActionError, match="You have no ore to give"):
        GAME.apply(to_p2, P2, AcceptOffer())
    to_p3 = GAME.apply(offered, P1, OfferTrade("wood", "ore", P3)).state
    assert notation(to_p3) == ["accept", "decline"]


def test_declining_an_offer_returns_to_the_action_phase() -> None:
    state, _ = play_setup()
    offered = action_state(
        replace(state, hands=(hand_from(wood=1), hand_from(ore=1), empty_hand()))
    )
    offer = next(
        action for action in listing(offered) if isinstance(action, OfferTrade)
    )
    pending = GAME.apply(offered, P1, offer).state
    declined = GAME.apply(pending, P2, DeclineOffer()).state
    assert declined.phase == "actions"
    assert declined.pending_offer is None
    assert declined.hands == pending.hands


def test_offer_limit_ends_trade_talk_for_the_turn() -> None:
    config = CatanConfig(num_players=3, victory_points=5, max_offers_per_turn=1)
    state, _ = play_setup(config)
    offered = action_state(
        replace(
            state,
            hands=(
                hand_from(wood=2),
                hand_from(ore=2),
                hand_from(sheep=1),
            ),
        )
    )
    offer = next(
        action for action in listing(offered) if isinstance(action, OfferTrade)
    )
    pending = GAME.apply(offered, P1, offer).state
    declined = GAME.apply(pending, P2, DeclineOffer()).state
    assert declined.offers_this_turn == 1
    assert not any(isinstance(action, OfferTrade) for action in listing(declined))
    with pytest.raises(IllegalActionError, match="already made 1 offer"):
        GAME.apply(declined, P1, offer)
