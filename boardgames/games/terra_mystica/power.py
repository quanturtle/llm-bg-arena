"""Terra Mystica power actions and the Alchemists' victory point trades."""

from dataclasses import replace
from typing import cast

from boardgames.core import (
    Event,
    IllegalActionError,
    PlayerId,
    Transition,
    seat_label,
)
from boardgames.games.terra_mystica.constants import (
    CONVERSION_KINDS,
    CONVERSION_POWER,
    CONVERSION_TEXT,
    POWER_ACTION_COSTS,
    POWER_ACTION_INCOME,
    POWER_ACTION_KINDS,
    POWER_ACTION_TEXT,
    FactionType,
    PowerActionKind,
)
from boardgames.games.terra_mystica.model import (
    Action,
    ConversionKind,
    Convert,
    PowerAction,
    TerraMysticaState,
    TradeCoinsForVp,
    TradeVpForCoin,
    add_income,
    burn_power,
    can_spend_power,
    cap_priests,
    power_shortfall,
    priest_capacity,
    replace_at,
    replace_player,
    spend_power,
)
from boardgames.games.terra_mystica.rounds import advance_turn


def _token_count(value: int) -> str:
    return f"{value} token" if value == 1 else f"{value} tokens"


def _burn_text(burned: int) -> str:
    if not burned:
        return ""
    return (
        f", burning {2 * burned} Bowl II tokens and permanently losing "
        f"{_token_count(burned)}"
    )


def take_power_action(
    state: TerraMysticaState, player: PlayerId, kind: PowerActionKind
) -> Transition[TerraMysticaState]:
    owner = state.players[player]
    if kind == "bridge":
        raise IllegalActionError("build a bridge with the bridge action")
    cost = POWER_ACTION_COSTS[kind]
    if kind in state.used_power_actions:
        raise IllegalActionError("that power action was already used this round")
    burned = power_shortfall(owner.resources.power3, cost)
    resources = burn_power(owner.resources, cost)
    if resources is None:
        raise IllegalActionError("you do not have enough power to burn")
    spent = spend_power(resources, cost)
    assert spent is not None
    owner = replace(owner, resources=spent)
    if kind in ("spade", "double_spade"):
        amount = 1 if kind == "spade" else 2
        if owner.profile.type is FactionType.HALFLINGS:
            owner = replace(
                owner,
                victory_points=owner.victory_points
                + amount * owner.profile.spade_vp_bonus,
            )
        state = replace_player(state, player, owner)
        state = replace(
            state,
            used_power_actions=state.used_power_actions | {kind},
            phase="cult_spades",
            cult_spades=replace_at(state.cult_spades, player, amount),
            spade_return="action",
            spade_actor=player,
            power_spade_tiles=(),
            spade_second=None,
            spade_transformed=(),
            spade_intermediate=False,
            spade_reach_used=False,
            spade_topup=True,
            spade_require_all=False,
            active_player=player,
        )
        event = Event(
            "power_action",
            f"{seat_label(player)} spent {cost} power for {amount} spade(s)"
            f"{_burn_text(burned)}.",
            {
                "player": player,
                "kind": kind,
                "cost": cost,
                "burned": burned,
                "bowl2_burned": 2 * burned,
                "spades": amount,
            },
        )
        return Transition(state, (event,))
    resources = cap_priests(state, player, add_income(spent, POWER_ACTION_INCOME[kind]))
    owner = replace(owner, resources=resources)
    state = replace_player(state, player, owner)
    state = replace(state, used_power_actions=state.used_power_actions | {kind})
    reward = POWER_ACTION_TEXT[kind]
    event = Event(
        "power_action",
        f"{seat_label(player)} spent {cost} power for {reward}{_burn_text(burned)}.",
        {
            "player": player,
            "kind": kind,
            "cost": cost,
            "burned": burned,
            "bowl2_burned": 2 * burned,
        },
    )
    return advance_turn(state, player, (event,))


def conversion_actions(state: TerraMysticaState, player: PlayerId) -> list[Action]:
    """Every conversion the player can afford; conversions do not spend the turn."""
    owner = state.players[player]
    actions: list[Action] = []
    for kind in CONVERSION_KINDS:
        cost = CONVERSION_POWER[kind]
        if cost and not can_spend_power(owner.resources, cost):
            continue
        if kind == "power_priest" and owner.resources.priests >= priest_capacity(
            state, player
        ):
            continue
        if kind == "priest_worker" and owner.resources.priests < 1:
            continue
        if kind == "worker_coin" and owner.resources.workers < 1:
            continue
        actions.append(Convert(cast(ConversionKind, kind)))
    return actions


def take_conversion(
    state: TerraMysticaState, player: PlayerId, kind: ConversionKind
) -> Transition[TerraMysticaState]:
    """Apply one free conversion without passing the turn."""
    owner = state.players[player]
    resources = owner.resources
    burned = 0
    cost = CONVERSION_POWER[kind]
    if cost:
        if not can_spend_power(resources, cost):
            raise IllegalActionError("you do not have enough power to burn")
        burned = power_shortfall(resources.power3, cost)
        burned_resources = burn_power(resources, cost)
        assert burned_resources is not None
        spent = spend_power(burned_resources, cost)
        assert spent is not None
        resources = spent
    if kind == "power_priest":
        if resources.priests >= priest_capacity(state, player):
            raise IllegalActionError("you have no priest token left")
        resources = replace(resources, priests=resources.priests + 1)
    elif kind == "power_worker":
        resources = replace(resources, workers=resources.workers + 1)
    elif kind == "power_coin":
        resources = replace(resources, coins=resources.coins + 1)
    elif kind == "priest_worker":
        if resources.priests < 1:
            raise IllegalActionError("you have no priest to convert")
        resources = replace(
            resources, priests=resources.priests - 1, workers=resources.workers + 1
        )
    elif kind == "worker_coin":
        if resources.workers < 1:
            raise IllegalActionError("you have no worker to convert")
        resources = replace(
            resources, workers=resources.workers - 1, coins=resources.coins + 1
        )
    else:
        raise IllegalActionError("unknown conversion")
    owner = replace(owner, resources=cap_priests(state, player, resources))
    state = replace_player(state, player, owner)
    event = Event(
        "conversion",
        f"{seat_label(player)} converted {CONVERSION_TEXT[kind]}{_burn_text(burned)}.",
        {
            "player": player,
            "kind": kind,
            "burned": burned,
            "bowl2_burned": 2 * burned,
        },
    )
    return Transition(state, (event,))


def trade_vp_for_coin(
    state: TerraMysticaState, player: PlayerId
) -> Transition[TerraMysticaState]:
    owner = state.players[player]
    if owner.victory_points <= 0:
        raise IllegalActionError("you have no victory point to trade")
    owner = replace(
        owner,
        victory_points=owner.victory_points - 1,
        resources=replace(owner.resources, coins=owner.resources.coins + 1),
    )
    event = Event(
        "alchemist_trade",
        f"{seat_label(player)} traded 1 victory point for 1 coin.",
        {"player": player, "coins": 1, "victory_points": -1},
    )
    return Transition(replace_player(state, player, owner), (event,))


def trade_coins_for_vp(
    state: TerraMysticaState, player: PlayerId
) -> Transition[TerraMysticaState]:
    owner = state.players[player]
    if owner.resources.coins < 2:
        raise IllegalActionError("you have no two coins to trade")
    owner = replace(
        owner,
        victory_points=owner.victory_points + 1,
        resources=replace(owner.resources, coins=owner.resources.coins - 2),
    )
    event = Event(
        "alchemist_trade",
        f"{seat_label(player)} traded 2 coins for 1 victory point.",
        {"player": player, "coins": -2, "victory_points": 1},
    )
    return Transition(replace_player(state, player, owner), (event,))


def power_actions(state: TerraMysticaState, player: PlayerId) -> list[Action]:
    owner = state.players[player]
    actions: list[Action] = []
    for kind in POWER_ACTION_KINDS:
        if kind in state.used_power_actions:
            continue
        if can_spend_power(owner.resources, POWER_ACTION_COSTS[kind]):
            actions.append(PowerAction(kind))
    return actions


def alchemist_trades(state: TerraMysticaState, player: PlayerId) -> list[Action]:
    owner = state.players[player]
    actions: list[Action] = []
    if owner.profile.type is FactionType.ALCHEMISTS:
        if owner.victory_points > 0:
            actions.append(TradeVpForCoin())
        if owner.resources.coins >= 2:
            actions.append(TradeCoinsForVp())
    return actions


def explain_power_action(
    state: TerraMysticaState, player: PlayerId, action: PowerAction
) -> str:
    owner = state.players[player]
    if action.kind in state.used_power_actions:
        return "That power action was already used this round."
    if not can_spend_power(owner.resources, POWER_ACTION_COSTS[action.kind]):
        return "You do not have enough power to burn."
    return "That power action is not legal now."


def explain_conversion(
    state: TerraMysticaState, player: PlayerId, action: Convert
) -> str:
    owner = state.players[player]
    kind = action.kind
    if kind not in CONVERSION_POWER:
        return "There is no such conversion."
    cost = CONVERSION_POWER[kind]
    if cost and not can_spend_power(owner.resources, cost):
        return "You do not have enough power to burn."
    if kind == "power_priest" and owner.resources.priests >= priest_capacity(
        state, player
    ):
        return "You have no priest token left."
    if kind == "priest_worker" and owner.resources.priests < 1:
        return "You have no priest to convert."
    if kind == "worker_coin" and owner.resources.workers < 1:
        return "You have no worker to convert."
    return "That conversion is not legal now."


def explain_trade_vp_for_coin(state: TerraMysticaState, player: PlayerId) -> str:
    owner = state.players[player]
    if owner.profile.type is not FactionType.ALCHEMISTS:
        return "Only the Alchemists may trade victory points for coins."
    if owner.victory_points <= 0:
        return "You have no victory point to trade."
    return "That trade is not legal now."


def explain_trade_coins_for_vp(state: TerraMysticaState, player: PlayerId) -> str:
    owner = state.players[player]
    if owner.profile.type is not FactionType.ALCHEMISTS:
        return "Only the Alchemists may trade coins for victory points."
    if owner.resources.coins < 2:
        return "You need 2 coins for that trade."
    return "That trade is not legal now."
