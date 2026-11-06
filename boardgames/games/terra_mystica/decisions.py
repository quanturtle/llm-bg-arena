"""Terra Mystica legality: the legal listing and the illegal-action explanations.

Each phase and action family keeps its rules in its own module; this module
picks the one that applies to the current phase and action.
"""

from boardgames.core import PlayerId, seat_label
from boardgames.games.terra_mystica.building import (
    building_actions,
    explain_build,
    explain_digging,
    explain_shipping,
    explain_transform,
    explain_upgrade,
)
from boardgames.games.terra_mystica.cults import (
    explain_advance_cult,
    explain_send_priest,
    priest_actions,
)
from boardgames.games.terra_mystica.favor import (
    explain_favor,
    favor_actions,
)
from boardgames.games.terra_mystica.model import (
    Action,
    AdvanceCult,
    AdvanceDigging,
    AdvanceShipping,
    BuildDwelling,
    Pass,
    PowerAction,
    SendPriest,
    TerraMysticaState,
    TradeCoinsForVp,
    TradeVpForCoin,
    TransformTerrain,
    UpgradeBuilding,
)
from boardgames.games.terra_mystica.power import (
    alchemist_trades,
    explain_power_action,
    explain_trade_coins_for_vp,
    explain_trade_vp_for_coin,
    power_actions,
)
from boardgames.games.terra_mystica.setup import explain_setup, setup_actions
from boardgames.games.terra_mystica.spades import cult_spade_actions, explain_spade
from boardgames.games.terra_mystica.strongholds import (
    convert_actions,
    explain_convert,
)
from boardgames.games.terra_mystica.towns import (
    explain_town_choice,
    town_tile_actions,
)


def action_phase_actions(state: TerraMysticaState, player: PlayerId) -> list[Action]:
    actions = building_actions(state, player)
    actions.extend(priest_actions(state, player))
    actions.extend(power_actions(state, player))
    actions.extend(alchemist_trades(state, player))
    actions.append(Pass())
    return actions


def legal_action_list(state: TerraMysticaState, player: PlayerId) -> list[Action]:
    if state.phase == "setup":
        return setup_actions(state, player)
    if state.phase == "cult_spades":
        return cult_spade_actions(state, player)
    if state.phase == "stronghold_convert":
        return convert_actions(state, player)
    if state.phase == "town_choice":
        return town_tile_actions(state)
    if state.phase == "favor_choice":
        return favor_actions(state)
    if state.phase != "action":
        return []
    if player != state.active_player:
        return []
    return action_phase_actions(state, player)


def _explain_action(state: TerraMysticaState, player: PlayerId, action: Action) -> str:
    if isinstance(action, BuildDwelling):
        return explain_build(state, player, action)
    if isinstance(action, TransformTerrain):
        return explain_transform(state, player, action)
    if isinstance(action, UpgradeBuilding):
        return explain_upgrade(state, player, action)
    if isinstance(action, AdvanceShipping):
        return explain_shipping(state, player)
    if isinstance(action, AdvanceDigging):
        return explain_digging(state, player)
    if isinstance(action, SendPriest):
        return explain_send_priest(state, player, action)
    if isinstance(action, AdvanceCult):
        return explain_advance_cult(state, player, action)
    if isinstance(action, PowerAction):
        return explain_power_action(state, player, action)
    if isinstance(action, TradeVpForCoin):
        return explain_trade_vp_for_coin(state, player)
    if isinstance(action, TradeCoinsForVp):
        return explain_trade_coins_for_vp(state, player)
    if isinstance(action, Pass):
        return "Passing is always legal."
    return "That action is not legal now."


def explain_illegal(state: TerraMysticaState, player: PlayerId, action: Action) -> str:
    if state.phase == "setup":
        return explain_setup(state, player, action)
    if state.phase == "cult_spades":
        return explain_spade(state, player, action)
    if state.phase == "stronghold_convert":
        return explain_convert(state, player, action)
    if state.phase == "town_choice":
        return explain_town_choice(state, action)
    if state.phase == "favor_choice":
        return explain_favor(state, action)
    if state.phase != "action":
        return "The game is over."
    if player != state.active_player:
        return f"It is {seat_label(state.active_player)}'s turn."
    return _explain_action(state, player, action)
