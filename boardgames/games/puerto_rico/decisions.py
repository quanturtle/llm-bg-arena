"""Puerto Rico decisions: kind, prompt, legal listing, fallback and illegal reasons.

The listing and the reasons dispatch on the phase to the module of the role
that owns it.
"""

from boardgames.core import PlayerId
from boardgames.games.puerto_rico.model import (
    Action,
    DiscardGoods,
    FinishPlacement,
    Pass,
    PuertoRicoState,
)
from boardgames.games.puerto_rico.roles.builder import (
    builder_actions,
    explain_builder,
)
from boardgames.games.puerto_rico.roles.captain import (
    captain_actions,
    discard_actions,
    explain_captain,
    explain_discard,
    kept_goods,
)
from boardgames.games.puerto_rico.roles.craftsman import (
    craftsman_actions,
    explain_craftsman,
)
from boardgames.games.puerto_rico.roles.mayor import explain_mayor, mayor_actions
from boardgames.games.puerto_rico.roles.selection import (
    explain_selection,
    selection_actions,
)
from boardgames.games.puerto_rico.roles.settler import (
    explain_settler,
    settler_actions,
)
from boardgames.games.puerto_rico.roles.trader import explain_trader, trader_actions


def decision_kind(phase: str) -> str:
    return {
        "role_selection": "role",
        "settler_action": "settler",
        "mayor_action": "mayor",
        "builder_action": "builder",
        "craftsman_action": "craftsman",
        "trader_action": "trader",
        "captain_action": "captain",
        "captain_discard": "captain_discard",
    }.get(phase, phase)


def decision_prompt(state: PuertoRicoState) -> str:
    if state.phase == "role_selection":
        return "Choose an unchosen role."
    if state.phase == "settler_action":
        return "Take a plantation or quarry, or pass."
    if state.phase == "mayor_action":
        return "Place or move a colonist, or finish placement."
    if state.phase == "builder_action":
        return "Build a building or pass."
    if state.phase == "craftsman_action":
        return "Take the Craftsman privilege or pass."
    if state.phase == "trader_action":
        return "Sell a good or pass."
    if state.phase == "captain_action":
        return "Load goods on a ship or Wharf, or pass if you cannot."
    if state.phase == "captain_discard":
        return "Choose which goods to keep after shipping."
    return "Choose an action."


def legal_action_list(state: PuertoRicoState, player: PlayerId) -> list[Action]:
    """Every action the deciding player may choose right now."""
    if state.phase == "role_selection":
        return selection_actions(state)
    owner = state.players[player]
    if state.phase == "settler_action":
        return settler_actions(state, player, owner)
    if state.phase == "mayor_action":
        return mayor_actions(owner)
    if state.phase == "builder_action":
        return builder_actions(state, player)
    if state.phase == "craftsman_action":
        return craftsman_actions(state, owner)
    if state.phase == "trader_action":
        return trader_actions(state, owner)
    if state.phase == "captain_action":
        return captain_actions(state, player, owner)
    if state.phase == "captain_discard":
        return discard_actions(owner)
    return []


def default_action(state: PuertoRicoState, actions: list[Action]) -> Action | None:
    """A safe fallback for phases where passing is allowed."""
    if state.phase in (
        "settler_action",
        "builder_action",
        "trader_action",
        "craftsman_action",
    ):
        return Pass()
    if state.phase == "mayor_action":
        return FinishPlacement() if FinishPlacement() in actions else None
    if state.phase == "captain_discard":
        discards = [action for action in actions if isinstance(action, DiscardGoods)]
        return max(
            discards,
            key=lambda action: kept_goods(state.players[state.active_player], action),
        )
    return None


def explain_illegal(state: PuertoRicoState, player: PlayerId, action: Action) -> str:
    """Why `action` is not legal for `player` now."""
    phase = state.phase
    if phase == "role_selection":
        return explain_selection(state, action)
    if phase == "settler_action":
        return explain_settler(state, player, action)
    if phase == "mayor_action":
        return explain_mayor(state, player, action)
    if phase == "builder_action":
        return explain_builder(state, player, action)
    if phase == "craftsman_action":
        return explain_craftsman(state, player, action)
    if phase == "trader_action":
        return explain_trader(state, player, action)
    if phase == "captain_action":
        return explain_captain(state, player, action)
    if phase == "captain_discard":
        return explain_discard(state, player, action)
    return "That action is not legal now."
