"""Action spaces: the legal actions of one decision, as a list or a token tree.

Every action has a text notation made of space-separated tokens, such as
"build road e12". An action space is a tree over those tokens. Small spaces list
their actions; large ones expand one token at a time, so an agent can choose the
action type first and its parameters after, and `is_legal` checks a proposed
action without enumerating the rest.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence

from boardgames.core.errors import NotationError

type Tokens = tuple[str, ...]


class ActionSpace[A](ABC):
    """Legal actions for one decision. Subclass it for spaces too large to list."""

    @abstractmethod
    def notation(self, action: A) -> str:
        """The action in the game's text notation."""

    @abstractmethod
    def next_tokens(self, prefix: Tokens) -> tuple[str, ...]:
        """Tokens that extend `prefix` toward at least one legal action."""

    @abstractmethod
    def action_at(self, prefix: Tokens) -> A | None:
        """The legal action whose notation is exactly `prefix`, if any."""

    @property
    def default(self) -> A | None:
        """Action an agent may fall back to, such as "pass"; None if there is none."""
        return None

    def is_legal(self, action: A) -> bool:
        """Whether `action` is one of this space's actions."""
        tokens = tuple(self.notation(action).split())
        for depth, token in enumerate(tokens):
            if token not in self.next_tokens(tokens[:depth]):
                return False
        return self.action_at(tokens) == action

    def explain(self, action: A) -> str:
        """Why `action` is illegal, addressed to the player who proposed it."""
        return f"{self.notation(action)!r} is not a legal action now."

    def listing(self, limit: int) -> tuple[A, ...] | None:
        """Every legal action in tree order, or None if there are more than `limit`."""
        found: list[A] = []
        is_complete = collect_actions(self, (), limit, found)
        return tuple(found) if is_complete else None


def collect_actions[A](
    space: ActionSpace[A], prefix: Tokens, limit: int, found: list[A]
) -> bool:
    """Append the actions under `prefix` depth-first; False once `limit` is exceeded."""
    action = space.action_at(prefix)
    if action is not None:
        found.append(action)
        if len(found) > limit:
            return False
    for token in space.next_tokens(prefix):
        if not collect_actions(space, (*prefix, token), limit, found):
            return False
    return True


class FlatActionSpace[A](ActionSpace[A]):
    """A space small enough to hold every legal action in a tuple."""

    def __init__(
        self,
        actions: Sequence[A],
        notation: Callable[[A], str],
        *,
        explain: Callable[[A], str] | None = None,
        default: A | None = None,
    ) -> None:
        self._actions = tuple(actions)
        self._notation = notation
        self._explain = explain
        self._by_tokens = index_by_tokens(self._actions, notation)
        self._children = children_by_prefix(self._by_tokens)
        if default is not None and default not in self._actions:
            raise ValueError(f"default {notation(default)!r} is not a listed action")
        self._default = default
        return

    def notation(self, action: A) -> str:
        return self._notation(action)

    def next_tokens(self, prefix: Tokens) -> tuple[str, ...]:
        return self._children.get(prefix, ())

    def action_at(self, prefix: Tokens) -> A | None:
        return self._by_tokens.get(prefix)

    @property
    def default(self) -> A | None:
        return self._default

    def is_legal(self, action: A) -> bool:
        return self._by_tokens.get(tuple(self._notation(action).split())) == action

    def explain(self, action: A) -> str:
        if self._explain is None:
            return super().explain(action)
        return self._explain(action)

    def listing(self, limit: int) -> tuple[A, ...] | None:
        return self._actions if len(self._actions) <= limit else None


def index_by_tokens[A](
    actions: Sequence[A], notation: Callable[[A], str]
) -> dict[Tokens, A]:
    """Map each action's notation tokens to the action; shared notations raise."""
    index: dict[Tokens, A] = {}
    for action in actions:
        tokens = tuple(notation(action).split())
        if tokens in index:
            raise NotationError(f"two legal actions share the notation {tokens!r}")
        index[tokens] = action
    return index


def children_by_prefix[A](by_tokens: dict[Tokens, A]) -> dict[Tokens, tuple[str, ...]]:
    """For every prefix of every notation, the distinct next tokens in order seen."""
    children: dict[Tokens, dict[str, None]] = {}
    for tokens in by_tokens:
        for depth, token in enumerate(tokens):
            children.setdefault(tokens[:depth], {})[token] = None
    return {prefix: tuple(tokens) for prefix, tokens in children.items()}
