from dataclasses import dataclass

import pytest

from tabletop_arena.core import ActionSpace, FlatActionSpace, NotationError, Tokens


@dataclass(frozen=True)
class Mark:
    cell: str


@dataclass(frozen=True)
class Move:
    piece: str
    square: int


@dataclass(frozen=True)
class Pass:
    pass


type Step = Move | Pass

PIECES = ("a", "b")
SQUARES = (1, 2, 3)
BLOCKED = Move("b", 2)


def mark_notation(action: Mark) -> str:
    return action.cell


def step_notation(action: Step) -> str:
    if isinstance(action, Pass):
        return "pass"
    return f"move {action.piece} {action.square}"


class StepSpace(ActionSpace[Step]):
    """Factored space: "move <piece> <square>" except one blocked move, or "pass"."""

    def notation(self, action: Step) -> str:
        return step_notation(action)

    def next_tokens(self, prefix: Tokens) -> tuple[str, ...]:
        if prefix == ():
            return ("move", "pass")
        if prefix == ("move",):
            return PIECES
        if len(prefix) == 2 and prefix[0] == "move":
            return tuple(
                str(square) for square in SQUARES if Move(prefix[1], square) != BLOCKED
            )
        return ()

    def action_at(self, prefix: Tokens) -> Step | None:
        if prefix == ("pass",):
            return Pass()
        if len(prefix) == 3 and prefix[0] == "move":
            move = Move(prefix[1], int(prefix[2]))
            return None if move == BLOCKED else move
        return None


def flat_space() -> FlatActionSpace[Mark]:
    return FlatActionSpace([Mark("a1"), Mark("b2"), Mark("c3")], mark_notation)


def test_flat_space_lists_actions_in_given_order() -> None:
    assert flat_space().listing(10) == (Mark("a1"), Mark("b2"), Mark("c3"))
    return


def test_flat_space_listing_over_limit_is_none() -> None:
    assert flat_space().listing(2) is None
    return


def test_flat_space_legality() -> None:
    space = flat_space()
    assert space.is_legal(Mark("b2"))
    assert not space.is_legal(Mark("b3"))
    return


def test_flat_space_tree() -> None:
    space = flat_space()
    assert space.next_tokens(()) == ("a1", "b2", "c3")
    assert space.action_at(("c3",)) == Mark("c3")
    assert space.action_at(()) is None
    return


def test_flat_space_default_explanation() -> None:
    assert flat_space().explain(Mark("b3")) == "'b3' is not a legal action now."
    return


def test_flat_space_custom_explanation() -> None:
    space = FlatActionSpace(
        [Mark("a1")], mark_notation, explain=lambda action: f"{action.cell} is taken."
    )
    assert space.explain(Mark("b1")) == "b1 is taken."
    return


def test_flat_space_rejects_unlisted_default() -> None:
    with pytest.raises(ValueError, match="not a listed action"):
        FlatActionSpace([Mark("a1")], mark_notation, default=Mark("z9"))
    return


def test_flat_space_rejects_shared_notation() -> None:
    with pytest.raises(NotationError, match="share the notation"):
        FlatActionSpace([Mark("a1"), Mark("a1")], mark_notation)
    return


def test_factored_space_legality_walks_tokens() -> None:
    space = StepSpace()
    assert space.is_legal(Move("a", 2))
    assert space.is_legal(Pass())
    assert not space.is_legal(BLOCKED)
    assert not space.is_legal(Move("c", 1))
    return


def test_factored_space_listing_walks_tree() -> None:
    listing = StepSpace().listing(100)
    assert listing is not None
    assert len(listing) == len(PIECES) * len(SQUARES) - 1 + 1
    assert listing[0] == Move("a", 1)
    assert listing[-1] == Pass()
    return


def test_factored_space_listing_over_limit_is_none() -> None:
    assert StepSpace().listing(3) is None
    return
