"""Tests for Puerto Rico illegal-action reasons and the fallback action."""

from dataclasses import replace

from boardgames.games.puerto_rico import Build, DiscardGoods, TakePlantation
from boardgames.games.puerto_rico.model import goods_total
from tests.games.puerto_rico.support import (
    GAME,
    select_role,
    start,
    with_goods,
    with_role,
)


def test_declining_a_missing_hospice_or_university_is_explained() -> None:
    state = start(seed=3)
    state = select_role(state, "settler")
    (decision,) = GAME.pending_decisions(state)
    space = GAME.legal_actions(state, decision)
    assert (
        space.explain(TakePlantation(state.face_up[0], use_hospice=False))
        == "You have no active Hospice."
    )
    state = start(seed=6)
    state = select_role(state, "builder")
    (decision,) = GAME.pending_decisions(state)
    space = GAME.legal_actions(state, decision)
    assert (
        space.explain(Build("small_indigo_plant", use_university=False))
        == "You have no active University."
    )


def test_captain_discard_fallback_keeps_a_good() -> None:
    state = start(seed=9)
    player = state.order[0]
    state = with_goods(state, player, corn=2, indigo=3)
    state = with_role(state, "captain", player)
    state = replace(
        state,
        phase="captain_discard",
        active_role="captain",
        active_player=player,
        players_acted=frozenset(state.order[1:]),
    )
    (decision,) = GAME.pending_decisions(state)
    space = GAME.legal_actions(state, decision)
    fallback = space.default
    assert isinstance(fallback, DiscardGoods)
    assert fallback.keep is not None
    after = GAME.apply(state, decision.player, fallback).state
    assert goods_total(after.players[player].goods) == 1
