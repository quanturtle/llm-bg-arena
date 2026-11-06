"""Terra Mystica spade phases: cult-bonus spades and spades from actions.

Cult-bonus spades follow a round with a spade cult bonus. Power-action spades
and the Halflings' stronghold spades open the same phase in the action phase.
"""

from dataclasses import replace

from boardgames.core import (
    Event,
    IllegalActionError,
    PlayerId,
    Transition,
    seat_label,
)
from boardgames.games.terra_mystica.building import adjacent_to_own, build_dwelling
from boardgames.games.terra_mystica.constants import (
    SCORING_VALUES,
    TERRAIN_WHEEL,
    TOWN_SUPPLY,
    BuildingType,
    Cost,
    FactionType,
    ScoringAction,
    Terrain,
)
from boardgames.games.terra_mystica.model import (
    Action,
    BuildDwelling,
    Hex,
    SkipCultSpade,
    TerraMysticaState,
    Tile,
    TradeCoinsForVp,
    TradeVpForCoin,
    UseCultSpade,
    add_costs,
    building_cost,
    can_pay,
    can_place_building,
    effective_reach,
    effective_reach_cost,
    pay,
    replace_at,
    replace_player,
    spade_cost,
    spades_for,
    terrain_distance,
)
from boardgames.games.terra_mystica.power import (
    alchemist_trades,
    explain_trade_coins_for_vp,
    explain_trade_vp_for_coin,
    trade_coins_for_vp,
    trade_vp_for_coin,
)
from boardgames.games.terra_mystica.rounds import (
    advance_turn,
    cult_spade_event,
    next_cult_spade_player,
    round_scoring,
    round_tile,
    start_next_round,
)
from boardgames.games.terra_mystica.towns import build_river_choices


def _action_spade_offer(
    state: TerraMysticaState,
    player: PlayerId,
    tile: Tile,
    target: Terrain,
) -> tuple[str | None, int, Cost, bool]:
    """Check one action-phase spade placement.

    Returns rejection (or None), spade cost, payment, and whether it tunnels or flies.
    """
    owner = state.players[player]
    profile = owner.profile
    budget = state.cult_spades[player]
    transformed = state.spade_transformed
    limit = 3 if state.spade_require_all else 2
    if budget <= 0:
        return ("You have no spades left.", 0, Cost(), False)
    if tile.terrain is target:
        return ("That tile is already that terrain.", 0, Cost(), False)
    if len(transformed) >= limit:
        return (
            f"Spades may only be applied to {limit} tiles in one action.",
            0,
            Cost(),
            False,
        )
    if tile.position in transformed:
        return ("That tile is already transformed.", 0, Cost(), False)

    if target is profile.home_terrain:
        cost = spades_for(profile, tile.terrain)
        if cost <= 0:
            return ("That tile is already that terrain.", 0, Cost(), False)
        missing = max(0, cost - budget)
        if missing > 0 and not (state.spade_topup and not transformed):
            return ("You do not have enough spades.", 0, Cost(), False)
    else:
        if profile.terraform_spades is not None:
            return (
                "The Giants can only transform to their home terrain.",
                0,
                Cost(),
                False,
            )
        if state.spade_intermediate:
            return (
                "Spades may only stop at non-home terrain once per action.",
                0,
                Cost(),
                False,
            )
        cost = terrain_distance(tile.terrain, target)
        if not transformed and not state.spade_require_all and cost < budget:
            return (
                "Stopping at non-home terrain must use all your remaining spades.",
                0,
                Cost(),
                False,
            )
        missing = max(0, cost - budget)
        if missing > 0 and not (state.spade_topup and not transformed):
            return ("You do not have enough spades.", 0, Cost(), False)

    tunneling = effective_reach(
        state.board, player, profile
    ) > 0 and not adjacent_to_own(state.board, player, tile.position)
    if tunneling and state.spade_reach_used:
        return ("You can only tunnel or fly once per spade action.", 0, Cost(), False)
    payment = spade_cost(profile, owner.digging, missing)
    if tunneling:
        payment = add_costs(payment, effective_reach_cost(state.board, player, profile))
    if not can_pay(owner.resources, payment):
        return (
            "You cannot pay for the missing spades or the tunnel.",
            0,
            Cost(),
            False,
        )
    return (None, cost, payment, tunneling)


def cult_spade_actions(state: TerraMysticaState, player: PlayerId) -> list[Action]:
    owner = state.players[player]
    profile = owner.profile
    budget = state.cult_spades[player]
    action_phase = state.spade_return == "action"
    reach = effective_reach(state.board, player, profile) if action_phase else 0
    reachable = set(state.board.reachable_land(player, owner.shipping, reach))
    actions: list[Action] = []

    transformed = state.spade_transformed
    tile_limit = 3 if state.spade_require_all else 2
    if budget > 0 and len(transformed) < tile_limit:
        for tile in state.board.tiles:
            if not tile.is_land or tile.building is not None:
                continue
            if tile.terrain is profile.home_terrain:
                continue
            if tile.position not in reachable:
                continue
            if tile.position in transformed:
                continue
            if action_phase:
                targets = [profile.home_terrain]
                if profile.terraform_spades is None:
                    targets.extend(
                        target
                        for target in TERRAIN_WHEEL
                        if target is not tile.terrain
                        and target is not profile.home_terrain
                    )
                for target in targets:
                    reason, _, _, _ = _action_spade_offer(state, player, tile, target)
                    if reason is not None:
                        continue
                    actions.append(
                        UseCultSpade(
                            tile.position,
                            None if target is profile.home_terrain else target,
                        )
                    )
                continue
            if profile.terraform_spades is not None:
                if budget >= spades_for(profile, tile.terrain):
                    actions.append(UseCultSpade(tile.position))
                continue
            for target in TERRAIN_WHEEL:
                if target is tile.terrain:
                    continue
                cost = terrain_distance(tile.terrain, target)
                if cost > budget:
                    continue
                if target is profile.home_terrain:
                    actions.append(UseCultSpade(tile.position))
                else:
                    actions.append(UseCultSpade(tile.position, target))

    if (
        action_phase
        and state.power_spade_tiles
        and (
            not state.spade_require_all
            or budget == 0
            or not any(isinstance(action, UseCultSpade) for action in actions)
        )
        and can_place_building(state.board, player, BuildingType.DWELLING)
    ):
        for position in state.power_spade_tiles:
            build_cost = building_cost(
                profile,
                BuildingType.DWELLING,
                bool(state.board.adjacent_opponents(position, player)),
            )
            if can_pay(owner.resources, build_cost):
                actions.append(BuildDwelling(position))
                for river in build_river_choices(
                    state.board,
                    player,
                    profile,
                    position,
                    TOWN_SUPPLY - state.towns,
                ):
                    actions.append(BuildDwelling(position, river=river))

    if action_phase:
        actions.extend(alchemist_trades(state, player))

    actions.append(SkipCultSpade())
    return actions


def _has_cult_spade_choice(state: TerraMysticaState, player: PlayerId) -> bool:
    """Whether the spade phase offers anything beyond skipping."""
    return any(
        not isinstance(action, SkipCultSpade)
        for action in cult_spade_actions(state, player)
    )


def _build_on_spade_tile(
    state: TerraMysticaState, player: PlayerId, action: BuildDwelling
) -> Transition[TerraMysticaState]:
    """End the spade phase and build on a tile its spades transformed."""
    state = replace(
        state,
        phase="action",
        cult_spades=replace_at(state.cult_spades, player, 0),
        spade_return="round",
        spade_actor=None,
        power_spade_tiles=(),
        spade_second=None,
        spade_transformed=(),
        spade_intermediate=False,
        spade_reach_used=False,
        spade_topup=True,
        spade_require_all=False,
    )
    return build_dwelling(state, player, action.position, action.river, reach_paid=True)


def _advance_cult_spades(
    state: TerraMysticaState, events: tuple[Event, ...]
) -> Transition[TerraMysticaState]:
    if state.spade_return == "action":
        actor = state.spade_actor
        assert actor is not None
        if state.cult_spades[actor] > 0:
            return Transition(state, events)
        if state.power_spade_tiles and _has_cult_spade_choice(state, actor):
            return Transition(state, events)
        state = replace(
            state,
            phase="action",
            cult_spades=replace_at(state.cult_spades, actor, 0),
            spade_return="round",
            spade_actor=None,
            power_spade_tiles=(),
            spade_second=None,
            spade_transformed=(),
            spade_intermediate=False,
            spade_reach_used=False,
            spade_topup=True,
            spade_require_all=False,
            active_player=actor,
        )
        return advance_turn(state, actor, events)
    next_player = next_cult_spade_player(state)
    if next_player is None:
        return start_next_round(state, events)
    if next_player == state.active_player:
        return Transition(state, events)
    event = cult_spade_event(state, next_player, round_tile(state).bonus)
    return Transition(replace(state, active_player=next_player), (*events, event))


def use_cult_spade(
    state: TerraMysticaState,
    player: PlayerId,
    position: Hex,
    to: Terrain | None = None,
) -> Transition[TerraMysticaState]:
    owner = state.players[player]
    profile = owner.profile
    tile = state.board.tile(position)
    budget = state.cult_spades[player]
    action_phase = state.spade_return == "action"
    if tile is None or not tile.is_land or tile.building is not None:
        raise IllegalActionError("choose an empty land tile")
    target = to or profile.home_terrain
    if tile.terrain is target:
        raise IllegalActionError("that tile is already that terrain")
    reach = effective_reach(state.board, player, profile) if action_phase else 0
    if position not in state.board.reachable_land(player, owner.shipping, reach):
        raise IllegalActionError("that tile is not reachable")
    if profile.terraform_spades is not None and target is not profile.home_terrain:
        raise IllegalActionError("the Giants can only reach home terrain")
    if budget <= 0:
        raise IllegalActionError("you have no spades left")

    if action_phase:
        reason, cost, payment, tunneling = _action_spade_offer(
            state, player, tile, target
        )
        if reason is not None:
            raise IllegalActionError(reason)
        transformed = state.spade_transformed
        spent = cost
        remaining = max(0, budget - cost)
        topped_up = max(0, cost - budget)
        points = profile.reach_vp if tunneling else 0
        points += topped_up * profile.spade_vp_bonus
        if round_scoring(state) is ScoringAction.SPADE:
            points += spent * SCORING_VALUES[ScoringAction.SPADE]
        buildable = state.power_spade_tiles
        if target is profile.home_terrain:
            if state.spade_require_all:
                buildable = (*buildable, position)
            elif not transformed:
                buildable = (position,)
        second = (
            position
            if not state.spade_require_all and transformed
            else state.spade_second
        )
        resources = pay(owner.resources, payment)
        owner = replace(
            owner,
            resources=resources,
            victory_points=owner.victory_points + points,
        )
        state = replace_player(
            replace(
                state,
                board=state.board.replace_tile(position, replace(tile, terrain=target)),
                cult_spades=replace_at(state.cult_spades, player, remaining),
                power_spade_tiles=buildable,
                spade_second=second,
                spade_transformed=(*transformed, position),
                spade_intermediate=state.spade_intermediate
                or target is not profile.home_terrain,
                spade_reach_used=state.spade_reach_used or tunneling,
            ),
            player,
            owner,
        )
        event = Event(
            "cult_spade_used",
            f"{seat_label(player)} used {spent} spade(s) at "
            f"{position.notation()} and made it {target.value}.",
            {
                "player": player,
                "position": position.notation(),
                "spades": spent,
                "remaining": remaining,
                "terrain": target.value,
                "victory_points": points,
            },
        )
        return _advance_cult_spades(state, (event,))

    cost = spades_for(profile, tile.terrain)
    if target is not profile.home_terrain:
        cost = terrain_distance(tile.terrain, target)
    if profile.terraform_spades is not None and budget < cost:
        raise IllegalActionError("the Giants forfeit a single cult-bonus spade")
    if cost > budget:
        raise IllegalActionError("you do not have enough cult-bonus spades")
    spent = cost
    board = state.board.replace_tile(position, replace(tile, terrain=target))
    state = replace_player(
        replace(
            state,
            board=board,
            cult_spades=replace_at(state.cult_spades, player, budget - spent),
        ),
        player,
        owner,
    )
    event = Event(
        "cult_spade_used",
        f"{seat_label(player)} used {spent} cult-bonus spade(s) at "
        f"{position.notation()} and made it {target.value}.",
        {
            "player": player,
            "position": position.notation(),
            "spades": spent,
            "remaining": budget - spent,
            "terrain": target.value,
            "victory_points": 0,
        },
    )
    return _advance_cult_spades(state, (event,))


def skip_cult_spade(
    state: TerraMysticaState, player: PlayerId
) -> Transition[TerraMysticaState]:
    remaining = state.cult_spades[player]
    action_phase = state.spade_return == "action"
    kind = "spade" if action_phase else "cult-bonus spade"
    if action_phase and remaining > 0:
        state = replace(
            state,
            cult_spades=replace_at(state.cult_spades, player, 0),
        )
        event = Event(
            "cult_spade_skipped",
            f"{seat_label(player)} skipped {remaining} {kind}(s).",
            {"player": player, "spades": remaining},
        )
        return _advance_cult_spades(state, (event,))
    state = replace(
        state,
        cult_spades=replace_at(state.cult_spades, player, 0),
        power_spade_tiles=(),
        spade_second=None,
        spade_transformed=(),
        spade_intermediate=False,
        spade_reach_used=False,
    )
    text = (
        f"{seat_label(player)} skipped {remaining} {kind}(s)."
        if remaining
        else f"{seat_label(player)} declined to build on the transformed tile."
    )
    event = Event(
        "cult_spade_skipped",
        text,
        {"player": player, "spades": remaining},
    )
    return _advance_cult_spades(state, (event,))


def apply_spade_phase(
    state: TerraMysticaState, player: PlayerId, action: Action
) -> Transition[TerraMysticaState]:
    if (
        isinstance(action, BuildDwelling)
        and state.spade_return == "action"
        and action.position in state.power_spade_tiles
    ):
        return _build_on_spade_tile(state, player, action)
    if isinstance(action, UseCultSpade):
        return use_cult_spade(state, player, action.position, action.to)
    if isinstance(action, SkipCultSpade):
        return skip_cult_spade(state, player)
    if (
        state.spade_return == "action"
        and isinstance(action, TradeVpForCoin)
        and state.players[player].profile.type is FactionType.ALCHEMISTS
    ):
        return trade_vp_for_coin(state, player)
    if (
        state.spade_return == "action"
        and isinstance(action, TradeCoinsForVp)
        and state.players[player].profile.type is FactionType.ALCHEMISTS
    ):
        return trade_coins_for_vp(state, player)
    raise IllegalActionError("spend a spade or skip now")


def explain_spade(state: TerraMysticaState, player: PlayerId, action: Action) -> str:
    owner = state.players[player]
    profile = owner.profile
    budget = state.cult_spades[player]
    action_phase = state.spade_return == "action"
    if isinstance(action, UseCultSpade):
        tile = state.board.tile(action.position)
        if tile is None or not tile.is_land or tile.building is not None:
            return "There is no empty land tile there."
        target = action.to or profile.home_terrain
        if tile.terrain is target:
            return "That tile is already that terrain."
        reach = effective_reach(state.board, player, profile) if action_phase else 0
        if action.position not in state.board.reachable_land(
            player, owner.shipping, reach
        ):
            return "That tile is not reachable."
        if budget <= 0:
            return "You have no spades left."
        if action_phase:
            reason, _, _, _ = _action_spade_offer(state, player, tile, target)
            return reason or "That spade cannot be used there now."
        cost = spades_for(profile, tile.terrain)
        if target is not profile.home_terrain:
            cost = terrain_distance(tile.terrain, target)
        if profile.terraform_spades is not None:
            if target is not profile.home_terrain:
                return "The Giants can only reach home terrain."
            if budget < cost:
                return "The Giants forfeit a single cult-bonus spade."
        if budget < cost:
            return "You do not have enough cult-bonus spades."
        return "That cult-bonus spade cannot be used there now."
    if isinstance(action, BuildDwelling):
        if action.position not in state.power_spade_tiles:
            return "No spade has transformed that tile."
        if action.river is not None and action.river not in build_river_choices(
            state.board,
            player,
            profile,
            action.position,
            TOWN_SUPPLY - state.towns,
        ):
            return "That river does not change the town here."
        return "That dwelling cannot be built there now."
    if isinstance(action, TradeVpForCoin):
        return explain_trade_vp_for_coin(state, player)
    if isinstance(action, TradeCoinsForVp):
        return explain_trade_coins_for_vp(state, player)
    if isinstance(action, SkipCultSpade):
        return "Skipping is always legal."
    return "Spend a spade or skip."
