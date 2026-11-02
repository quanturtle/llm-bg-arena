"""Random playthroughs that check invariants at every step, without the runner."""

from collections.abc import Callable
from typing import Any

from tabletop_arena.core import AnyGame, GameConfig, Rng

MAX_STEPS = 1_000


def random_playthrough(
    game: AnyGame,
    config: GameConfig,
    seed: int,
    check_state: Callable[[Any], None],
) -> tuple[Any, int]:
    """Play random legal actions to the end; returns the final state and step count.

    Before each step it checks every legal action applies and round-trips notation.
    """
    state = game.setup(config, seed).state
    rng = Rng.seeded(seed ^ 0x5EED)
    steps = 0
    while not game.is_terminal(state):
        check_state(state)
        decisions = game.pending_decisions(state)
        assert decisions, "a non-terminal state has no open decision"
        players = [decision.player for decision in decisions]
        assert len(players) == len(set(players)), "two decisions for one player"
        for decision in decisions:
            listing = game.legal_actions(state, decision).listing(10_000)
            assert listing, f"no legal action for {decision}"
            check_every_action(game, state, decision.player, listing)
            action, rng = rng.choice(listing)
            state = game.apply(state, decision.player, action).state
            steps += 1
        assert steps <= MAX_STEPS, "game did not terminate"
    check_state(state)
    assert game.pending_decisions(state) == ()
    return state, steps


def check_every_action(
    game: AnyGame, state: Any, player: Any, listing: tuple[Any, ...]
) -> None:
    """Every listed action round-trips through notation and applies without error."""
    for action in listing:
        notation = game.format_action(action)
        assert game.parse_action(notation) == action, notation
        game.apply(state, player, action)
    return
