"""Tests for Puerto Rico role selection and the Prospector."""

import pytest

from boardgames.core import IllegalActionError
from boardgames.games.puerto_rico import SelectRole
from boardgames.games.puerto_rico.constants import Role
from boardgames.games.puerto_rico.model import role_chooser
from tests.games.puerto_rico.support import GAME, select_role, start


@pytest.mark.parametrize("role", ["prospector", "prospector_2"])
def test_prospector_gives_a_doubloon_and_skips_the_action_phase(
    role: Role,
) -> None:
    state = start(num_players=5, seed=7)
    player = state.active_player
    before = state.players[player].doubloons
    state = select_role(state, role)
    assert state.players[player].doubloons == before + 1
    assert state.phase == "role_selection"
    assert role_chooser(state, role) == player


@pytest.mark.parametrize(
    ("num_players", "role"), [(3, "prospector"), (4, "prospector_2")]
)
def test_a_role_missing_from_the_game_is_an_illegal_action_not_a_crash(
    num_players: int, role: Role
) -> None:
    state = start(num_players=num_players, seed=1)
    (decision,) = GAME.pending_decisions(state)
    space = GAME.legal_actions(state, decision)
    action = SelectRole(role)
    assert not space.is_legal(action)
    assert f"no {role} role" in space.explain(action)
    with pytest.raises(IllegalActionError, match="role in this game"):
        GAME.apply(state, decision.player, action)
