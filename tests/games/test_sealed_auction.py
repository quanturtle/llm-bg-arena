from dataclasses import replace

import pytest

from tabletop_arena.core import (
    ConfigError,
    IllegalActionError,
    NotationError,
    PlayerId,
    create_game,
    seats,
)
from tabletop_arena.games.sealed_auction import (
    Bid,
    Lot,
    SealedAuction,
    SealedAuctionConfig,
    SealedAuctionState,
)

GAME = SealedAuction()
CONFIG = SealedAuctionConfig(num_players=3, lots=3, starting_coins=10)
P1, P2, P3 = seats(3)


def start(seed: int = 1, config: SealedAuctionConfig = CONFIG) -> SealedAuctionState:
    return GAME.setup(config, seed).state


def bid_round(state: SealedAuctionState, bids: list[int]) -> SealedAuctionState:
    for player, coins in enumerate(bids):
        state = GAME.apply(state, PlayerId(player), Bid(coins)).state
    return state


def test_every_player_bids_at_once() -> None:
    decisions = GAME.pending_decisions(start())
    assert [decision.player for decision in decisions] == [P1, P2, P3]
    assert {decision.kind for decision in decisions} == {"bid"}
    return


def test_setup_is_deterministic_per_seed() -> None:
    assert start(seed=5) == start(seed=5)
    assert GAME.setup(CONFIG, 5).events == GAME.setup(CONFIG, 5).events
    return


def test_secret_colors_are_dealt_privately() -> None:
    events = GAME.setup(CONFIG, 1).events
    dealt = [event for event in events if event.kind == "color_dealt"]
    assert [event.audience for event in dealt] == [
        frozenset({P1}),
        frozenset({P2}),
        frozenset({P3}),
    ]
    return


def test_bids_range_from_zero_to_own_coins_with_pass_default() -> None:
    state = replace(start(), coins=(10, 2, 10))
    decision = GAME.pending_decisions(state)[1]
    space = GAME.legal_actions(state, decision)
    assert space.listing(100) == (Bid(0), Bid(1), Bid(2))
    assert space.default == Bid(0)
    assert space.explain(Bid(5)) == "You have 2 coins, so you cannot bid 5."
    return


def test_submitted_bid_stays_hidden_from_others() -> None:
    state = start()
    after = GAME.apply(state, P1, Bid(7)).state
    assert GAME.observe(after, P2).data["your_bid"] is None
    assert GAME.observe(after, P2).data["has_bid"] == [True, False, False]
    assert GAME.observe(after, P1).data["your_bid"] == 7
    assert [d.player for d in GAME.pending_decisions(after)] == [P2, P3]
    return


def test_highest_bid_wins_and_pays() -> None:
    state = start()
    lot = state.current
    after = bid_round(state, [3, 5, 0])
    assert after.coins == (10, 5, 10)
    assert after.won[P2] == (lot,)
    assert after.round == 2
    assert after.bids == (None, None, None)
    return


def test_tie_is_broken_by_die_roll_among_tied_players() -> None:
    state = start()
    events = []
    for player, coins in enumerate([4, 4, 1]):
        transition = GAME.apply(state, PlayerId(player), Bid(coins))
        state, events = transition.state, list(transition.events)
    tie = next(event for event in events if event.kind == "tie_broken")
    assert tie.data["tied"] == [0, 1]
    assert tie.data["winner"] in (0, 1)
    return


def test_second_bid_in_a_round_raises() -> None:
    with pytest.raises(IllegalActionError, match="already bid"):
        GAME.apply(GAME.apply(start(), P1, Bid(1)).state, P1, Bid(2))
    return


def test_overbid_raises() -> None:
    with pytest.raises(IllegalActionError, match="cannot bid 11"):
        GAME.apply(start(), P1, Bid(11))
    return


def test_game_ends_after_last_lot_and_reveals_colors() -> None:
    state = bid_round(bid_round(start(), [1, 0, 0]), [0, 2, 0])
    transition = GAME.apply(GAME.apply(state, P1, Bid(0)).state, P2, Bid(0))
    final = GAME.apply(transition.state, P3, Bid(3))
    assert GAME.is_terminal(final.state)
    assert GAME.pending_decisions(final.state) == ()
    assert final.events[-1].kind == "colors_revealed"
    assert GAME.observe(final.state, P1).data["revealed_colors"] is not None
    with pytest.raises(IllegalActionError, match="game is over"):
        GAME.apply(final.state, P1, Bid(0))
    return


def test_score_doubles_secret_color_and_counts_half_coins() -> None:
    state = replace(
        start(),
        won=((Lot("red", 3), Lot("blue", 2)), (), ()),
        secret_colors=("red", "green", "blue"),
        coins=(5, 10, 0),
    )
    scores = GAME.scores(state)
    assert scores.breakdown[P1] == {"lots": 5, "color bonus": 3, "coins": 2}
    assert scores.points == {P1: 10, P2: 5, P3: 0}
    return


def test_notation_round_trips() -> None:
    for coins in range(12):
        assert GAME.parse_action(GAME.format_action(Bid(coins))) == Bid(coins)
    return


@pytest.mark.parametrize("text", ["bid", "bid -1", "bid 03", "Bid 3", "bid  3"])
def test_parse_rejects_non_canonical_text(text: str) -> None:
    with pytest.raises(NotationError):
        GAME.parse_action(text)
    return


@pytest.mark.parametrize(
    "raw", [{"num_players": 5}, {"lots": 13}, {"starting_coins": -1}]
)
def test_parse_config_rejects_unplayable_values(raw: dict[str, int]) -> None:
    with pytest.raises(ConfigError):
        GAME.parse_config(raw)
    return


def test_render_text_shows_own_color_and_bid_status() -> None:
    state = replace(start(), secret_colors=("red", "green", "blue"))
    state = GAME.apply(state, P2, Bid(1)).state
    text = GAME.render_text(GAME.observe(state, P1))
    assert "You are P1. Your secret color is red" in text
    assert "Bids this round: P1 waiting; P2 submitted; P3 waiting." in text
    return


def test_registered_under_its_id() -> None:
    assert isinstance(create_game("sealed_auction"), SealedAuction)
    return
