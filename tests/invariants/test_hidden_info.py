"""Hidden-information leak tests: a viewer's observation must not depend on secrets.

Each test changes everything a viewer may not see and checks that the
observation and its rendered text stay identical.
"""

import asyncio
from dataclasses import replace

from hypothesis import given, settings
from hypothesis import strategies as st

from boardgames.arena.runner import play_match
from boardgames.core import PlayerId, Rng, seats
from boardgames.games.catan import Catan, CatanConfig, CatanState
from boardgames.games.sealed_auction import (
    Bid,
    SealedAuction,
    SealedAuctionConfig,
    SealedAuctionState,
)
from boardgames.games.sealed_auction.game import COLORS
from tests.arena.support import FakeClock, MemorySink, RecordingAgent

GAME = SealedAuction()
CONFIG = SealedAuctionConfig(num_players=3, lots=5)
CATAN = Catan()
CATAN_CONFIG = CatanConfig(num_players=3, victory_points=3)


def mid_round_states(seed: int) -> list[SealedAuctionState]:
    """States from a random game, including ones where some bids are in."""
    states = []
    state = GAME.setup(CONFIG, seed).state
    rng = Rng.seeded(seed)
    while not GAME.is_terminal(state):
        states.append(state)
        player = GAME.pending_decisions(state)[0].player
        coins, rng = rng.below(state.coins[player] + 1)
        state = GAME.apply(state, player, Bid(coins)).state
    return states


def without_secrets_of_others(
    state: SealedAuctionState, viewer: PlayerId | None
) -> SealedAuctionState:
    """Same public state, but every secret the viewer may not see is changed."""
    colors = tuple(
        color if player == viewer else COLORS[(COLORS.index(color) + 1) % 3]
        for player, color in enumerate(state.secret_colors)
    )
    bids = tuple(
        bid if player == viewer or bid is None else state.coins[player] - bid
        for player, bid in enumerate(state.bids)
    )
    return replace(
        state,
        secret_colors=colors,
        bids=bids,
        deck=tuple(reversed(state.deck)),
        rng=Rng(state.rng.state + 1),
    )


@settings(max_examples=50, deadline=None)
@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
def test_observation_ignores_other_players_secrets(seed: int) -> None:
    for state in mid_round_states(seed):
        for viewer in (*seats(CONFIG.num_players), None):
            changed = without_secrets_of_others(state, viewer)
            assert changed != state
            original = GAME.observe(state, viewer)
            assert GAME.observe(changed, viewer) == original
            assert GAME.render_text(GAME.observe(changed, viewer)) == (
                GAME.render_text(original)
            )
    return


def catan_states(seed: int) -> list[CatanState]:
    """Every non-terminal state of a random Catan game."""
    states = []
    state = CATAN.setup(CATAN_CONFIG, seed).state
    rng = Rng.seeded(seed)
    while not CATAN.is_terminal(state):
        states.append(state)
        decision = CATAN.pending_decisions(state)[0]
        listing = CATAN.legal_actions(state, decision).listing(10_000)
        assert listing is not None
        action, rng = rng.choice(listing)
        state = CATAN.apply(state, decision.player, action).state
    return states


def without_catan_secrets_of_others(
    state: CatanState, viewer: PlayerId | None
) -> CatanState:
    """Same public state, but other players' cards are rotated between types.

    Hand and card counts stay the same; the deck order and the RNG change.
    """
    hands = tuple(
        hand if player == viewer else (*hand[1:], hand[0])
        for player, hand in enumerate(state.hands)
    )
    dev_hands = tuple(
        hand if player == viewer else (*hand[1:], hand[0])
        for player, hand in enumerate(state.dev_hands)
    )
    return replace(
        state,
        hands=hands,
        dev_hands=dev_hands,
        dev_deck=tuple(reversed(state.dev_deck)),
        rng=Rng(state.rng.state + 1),
    )


def catan_choices(state: CatanState, viewer: PlayerId) -> list[tuple[str, str]]:
    """The viewer's listed actions, each with its notation and explain text."""
    choices = []
    for decision in CATAN.pending_decisions(state):
        if decision.player != viewer:
            continue
        space = CATAN.legal_actions(state, decision)
        listing = space.listing(10_000)
        assert listing is not None
        for action in listing:
            choices.append((CATAN.format_action(action), space.explain(action)))
    return choices


@settings(max_examples=5, deadline=None)
@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
def test_catan_view_and_choices_ignore_other_players_cards(seed: int) -> None:
    for state in catan_states(seed):
        for viewer in (*seats(CATAN_CONFIG.num_players), None):
            changed = without_catan_secrets_of_others(state, viewer)
            original = CATAN.observe(state, viewer)
            assert CATAN.observe(changed, viewer) == original
            assert CATAN.render_text(CATAN.observe(changed, viewer)) == (
                CATAN.render_text(original)
            )
            if viewer is not None:
                assert catan_choices(changed, viewer) == catan_choices(state, viewer)
    return


def test_requests_carry_only_events_the_player_may_see() -> None:
    agents = [RecordingAgent(seed) for seed in range(3)]
    asyncio.run(
        play_match(
            GAME,
            CONFIG,
            9,
            agents,
            match_id="m",
            sink=MemorySink(),
            clock=FakeClock(),
        )
    )
    for player, agent in enumerate(agents):
        for request in agent.requests:
            assert request.observation.viewer == player
            assert all(e.is_visible_to(PlayerId(player)) for e in request.recent_events)
    return
