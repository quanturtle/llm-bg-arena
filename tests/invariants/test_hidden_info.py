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
