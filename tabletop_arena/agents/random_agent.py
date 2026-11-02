"""RandomAgent: uniform over legal actions, the floor every other agent must beat."""

from tabletop_arena.agents.base import (
    AgentChoice,
    Chosen,
    DecisionRequest,
    DecisionTrace,
)
from tabletop_arena.core import ActionSpace, JsonValue, Rng, Tokens

LISTING_LIMIT = 100_000


class RandomAgent:
    """Uniform over listed actions; for spaces too large to list, uniform per token."""

    def __init__(self, seed: int, name: str = "random") -> None:
        self._rng = Rng.seeded(seed)
        self._seed = seed
        self._name = name
        return

    @property
    def name(self) -> str:
        return self._name

    def settings(self) -> dict[str, JsonValue]:
        return {"kind": "random", "seed": self._seed}

    async def decide[A](self, request: DecisionRequest[A]) -> AgentChoice[A]:
        listing = request.actions.listing(LISTING_LIMIT)
        if listing is None:
            action, self._rng = walk_tokens(request.actions, self._rng)
        else:
            action, self._rng = self._rng.choice(listing)
        return Chosen(action, DecisionTrace())


def walk_tokens[A](space: ActionSpace[A], rng: Rng) -> tuple[A, Rng]:
    """Pick one token at a time, treating "stop here" as one more option."""
    prefix: Tokens = ()
    while True:
        tokens = space.next_tokens(prefix)
        stop = space.action_at(prefix)
        options = len(tokens) + (0 if stop is None else 1)
        if options == 0:
            raise ValueError(f"action space has a dead end at {prefix!r}")
        index, rng = rng.below(options)
        if index == len(tokens) and stop is not None:
            return stop, rng
        prefix = (*prefix, tokens[index])
