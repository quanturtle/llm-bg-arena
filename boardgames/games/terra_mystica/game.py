"""Terra Mystica: the standard base game for two to five players."""

from dataclasses import replace
from functools import partial
from importlib.resources import files
from typing import ClassVar

from boardgames.core import (
    ActionSpace,
    Decision,
    Event,
    FlatActionSpace,
    Game,
    IllegalActionError,
    JsonObject,
    JsonValue,
    Observation,
    PlayerId,
    Scores,
    Transition,
    checked_apply,
    register_game,
    seat_label,
    seats,
)
from boardgames.core.records import (
    dataclass_from_json,
    tagged_json_object,
    to_json_object,
)
from boardgames.games.terra_mystica.building import (
    adjacent_to_own,
    advance_digging,
    advance_shipping,
    build_dwelling,
    building_actions,
    explain_build,
    explain_digging,
    explain_shipping,
    explain_transform,
    explain_upgrade,
    transform_terrain,
    upgrade_building,
)
from boardgames.games.terra_mystica.constants import (
    SCORING_VALUES,
    TERRAIN_WHEEL,
    TOWN_SUPPLY,
    BuildingType,
    FactionType,
    ScoringAction,
    Terrain,
)
from boardgames.games.terra_mystica.cults import (
    advance_cult_with_priest,
    explain_advance_cult,
    explain_send_priest,
    priest_actions,
    send_priest,
)
from boardgames.games.terra_mystica.model import (
    Action,
    AdvanceCult,
    AdvanceDigging,
    AdvanceShipping,
    BuildDwelling,
    ChooseStrongholdPriests,
    Hex,
    Pass,
    PowerAction,
    SendPriest,
    SkipCultSpade,
    TakeTownTile,
    TerraMysticaConfig,
    TerraMysticaState,
    TradeCoinsForVp,
    TradeVpForCoin,
    TransformTerrain,
    UpgradeBuilding,
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
from boardgames.games.terra_mystica.notation import format_action, parse_action
from boardgames.games.terra_mystica.power import (
    alchemist_trades,
    explain_power_action,
    explain_trade_coins_for_vp,
    explain_trade_vp_for_coin,
    power_actions,
    take_power_action,
    trade_coins_for_vp,
    trade_vp_for_coin,
)
from boardgames.games.terra_mystica.rounds import (
    advance_turn,
    cult_spade_event,
    next_cult_spade_player,
    pass_turn,
    round_scoring,
    round_tile,
    start_next_round,
)
from boardgames.games.terra_mystica.scoring import final_scores
from boardgames.games.terra_mystica.setup import (
    check_config,
    explain_setup,
    place_starting_dwelling,
    setup_actions,
    start_game,
)
from boardgames.games.terra_mystica.strongholds import (
    choose_stronghold_priests,
    convert_actions,
    explain_convert,
)
from boardgames.games.terra_mystica.towns import (
    build_river_choices,
    explain_town_choice,
    take_town_tile,
    town_tile_actions,
)
from boardgames.games.terra_mystica.view import (
    describe_action,
    observe,
    render_text,
)


@register_game
class TerraMystica(Game[TerraMysticaState, Action, TerraMysticaConfig]):
    """The base game: six rounds, fourteen factions and the standard map."""

    id: ClassVar[str] = "terra_mystica"
    rules_version: ClassVar[int] = 7

    # Config ---------------------------------------------------------------

    def parse_config(self, raw: JsonObject) -> TerraMysticaConfig:
        config = dataclass_from_json(TerraMysticaConfig, raw)
        check_config(config)
        return config

    def config_json(self, config: TerraMysticaConfig) -> dict[str, JsonValue]:
        return to_json_object(config)

    # Setup ----------------------------------------------------------------

    def setup(
        self, config: TerraMysticaConfig, seed: int
    ) -> Transition[TerraMysticaState]:
        return start_game(config, seed)

    # Decisions ------------------------------------------------------------

    def pending_decisions(self, state: TerraMysticaState) -> tuple[Decision, ...]:
        if state.phase == "game_over":
            return ()
        if state.phase == "setup":
            return (
                Decision(
                    state.active_player,
                    "setup_dwelling",
                    "Place one of your starting dwellings on a free home-terrain tile.",
                ),
            )
        if state.phase == "cult_spades":
            kind = "spade" if state.spade_return == "action" else "cult-bonus spade"
            return (
                Decision(
                    state.active_player,
                    "cult_spade",
                    f"Spend a {kind} on a reachable tile, or skip.",
                ),
            )
        if state.phase == "stronghold_convert":
            return (
                Decision(
                    state.active_player,
                    "stronghold_convert",
                    "Trade up to three workers for one priest each.",
                ),
            )
        if state.phase == "town_choice":
            return (
                Decision(
                    state.active_player,
                    "town_choice",
                    "Choose one of the remaining town tiles.",
                ),
            )
        return (
            Decision(
                state.active_player,
                "action",
                "Take one action, or pass when you are done.",
            ),
        )

    def legal_actions(
        self, state: TerraMysticaState, decision: Decision
    ) -> ActionSpace[Action]:
        actions = legal_action_list(state, decision.player)
        default = (
            Pass()
            if state.phase == "action"
            else SkipCultSpade()
            if state.phase == "cult_spades"
            else None
        )
        return FlatActionSpace(
            actions,
            format_action,
            explain=partial(explain_illegal, state, decision.player),
            default=default,
        )

    def apply(
        self, state: TerraMysticaState, player: PlayerId, action: Action
    ) -> Transition[TerraMysticaState]:
        return checked_apply(
            self,
            state,
            player,
            action,
            no_decision=(
                f"{seat_label(player)} has no open decision in phase {state.phase!r}"
            ),
        )

    # Rules ----------------------------------------------------------------

    def apply_legal(
        self, state: TerraMysticaState, player: PlayerId, action: Action
    ) -> Transition[TerraMysticaState]:
        if state.phase == "setup":
            if not isinstance(action, BuildDwelling):
                raise IllegalActionError("place a starting dwelling now")
            return place_starting_dwelling(state, player, action.position)
        if state.phase == "cult_spades":
            if (
                isinstance(action, BuildDwelling)
                and state.spade_return == "action"
                and action.position in state.power_spade_tiles
            ):
                if (
                    state.spade_require_all
                    and state.cult_spades[player] > 0
                    and _has_spade_transform(state, player)
                ):
                    raise IllegalActionError(
                        "spend all the stronghold spades before building"
                    )
                state = replace(
                    state,
                    phase="action",
                    cult_spades=replace_at(state.cult_spades, player, 0),
                    spade_return="round",
                    spade_actor=None,
                    power_spade_tiles=(),
                    spade_second=None,
                    spade_topup=True,
                    spade_require_all=False,
                )
                return build_dwelling(
                    state, player, action.position, action.river, reach_paid=True
                )
            if isinstance(action, UseCultSpade):
                return self.use_cult_spade(state, player, action.position, action.to)
            if isinstance(action, SkipCultSpade):
                return self.skip_cult_spade(state, player)
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
        if state.phase == "stronghold_convert":
            if not isinstance(action, ChooseStrongholdPriests):
                raise IllegalActionError("choose how many workers to trade")
            return choose_stronghold_priests(state, player, action.workers)
        if state.phase == "town_choice":
            if not isinstance(action, TakeTownTile):
                raise IllegalActionError("choose a town tile now")
            return take_town_tile(state, player, action.index)
        if state.phase != "action":
            raise IllegalActionError("the game is over")
        if player != state.active_player:
            raise IllegalActionError(f"it is {seat_label(state.active_player)}'s turn")
        return self.apply_action(state, player, action)

    def is_terminal(self, state: TerraMysticaState) -> bool:
        return state.phase == "game_over"

    def scores(self, state: TerraMysticaState) -> Scores:
        if self.is_terminal(state):
            final = final_scores(state)
            return Scores(
                {
                    player: float(final[player][0])
                    for player in seats(len(state.players))
                },
                {player: final[player][1] for player in seats(len(state.players))},
            )
        return Scores(
            {
                player: float(state.players[player].victory_points)
                for player in seats(len(state.players))
            }
        )

    def public_scores(self, state: TerraMysticaState) -> Scores:
        """Terra Mystica has no hidden victory points."""
        return self.scores(state)

    def observe(self, state: TerraMysticaState, viewer: PlayerId | None) -> Observation:
        return observe(state, viewer)

    def render_text(self, observation: Observation) -> str:
        return render_text(observation)

    def rules_text(self) -> str:
        rules = files("boardgames.games.terra_mystica") / "rules.md"
        return rules.read_text(encoding="utf-8")

    def format_action(self, action: Action) -> str:
        return format_action(action)

    def parse_action(self, text: str) -> Action:
        return parse_action(text)

    def describe_action(self, observation: Observation, action: Action) -> str:
        return describe_action(observation, action)

    def action_json(self, action: Action) -> dict[str, JsonValue]:
        return tagged_json_object(action)

    # Round plumbing -------------------------------------------------------

    def apply_action(
        self, state: TerraMysticaState, player: PlayerId, action: Action
    ) -> Transition[TerraMysticaState]:
        if isinstance(action, BuildDwelling):
            return build_dwelling(state, player, action.position, action.river)
        if isinstance(action, TransformTerrain):
            return transform_terrain(state, player, action.position, action.to)
        if isinstance(action, UpgradeBuilding):
            return upgrade_building(
                state, player, action.position, action.to, action.river
            )
        if isinstance(action, AdvanceShipping):
            return advance_shipping(state, player)
        if isinstance(action, AdvanceDigging):
            return advance_digging(state, player)
        if isinstance(action, SendPriest):
            return send_priest(state, player, action.cult, action.order)
        if isinstance(action, AdvanceCult):
            return advance_cult_with_priest(state, player, action.cult)
        if isinstance(action, PowerAction):
            return take_power_action(state, player, action.kind)
        if isinstance(action, TradeVpForCoin):
            return trade_vp_for_coin(state, player)
        if isinstance(action, TradeCoinsForVp):
            return trade_coins_for_vp(state, player)
        if isinstance(action, Pass):
            return pass_turn(state, player)
        raise IllegalActionError("unknown action")

    def use_cult_spade(
        self,
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
            if target is not profile.home_terrain:
                raise IllegalActionError(
                    "spades must transform a tile all the way to home terrain"
                )
            first = state.power_spade_tiles[0] if state.power_spade_tiles else None
            if first is not None:
                if position == first:
                    raise IllegalActionError("that tile is already transformed")
                if state.spade_second is not None:
                    raise IllegalActionError(
                        "spades may only be applied to one more tile"
                    )
            cost = spades_for(profile, tile.terrain)
            missing = max(0, cost - budget)
            if missing > 0 and not state.spade_topup:
                raise IllegalActionError("you do not have enough spades")
            tunneling = reach > 0 and not adjacent_to_own(state.board, player, position)
            payment = spade_cost(profile, owner.digging, missing)
            if tunneling:
                payment = add_costs(
                    payment, effective_reach_cost(state.board, player, profile)
                )
            if not can_pay(owner.resources, payment):
                raise IllegalActionError(
                    "you cannot pay for the missing spades or the tunnel"
                )
            spent = cost
            remaining = max(0, budget - cost)
            points = profile.reach_vp if tunneling else 0
            if round_scoring(state) is ScoringAction.SPADE:
                points += spent * SCORING_VALUES[ScoringAction.SPADE]
            first_tiles = (position,) if first is None else state.power_spade_tiles
            second = None if first is None else position
            resources = pay(owner.resources, payment)
            owner = replace(
                owner,
                resources=resources,
                victory_points=owner.victory_points + points,
            )
            state = replace_player(
                replace(
                    state,
                    board=state.board.replace_tile(
                        position, replace(tile, terrain=target)
                    ),
                    cult_spades=replace_at(state.cult_spades, player, remaining),
                    power_spade_tiles=first_tiles,
                    spade_second=second,
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
            return self._advance_cult_spades(state, (event,))

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
        return self._advance_cult_spades(state, (event,))

    def skip_cult_spade(
        self, state: TerraMysticaState, player: PlayerId
    ) -> Transition[TerraMysticaState]:
        remaining = state.cult_spades[player]
        kind = "spade" if state.spade_return == "action" else "cult-bonus spade"
        state = replace(
            state,
            cult_spades=replace_at(state.cult_spades, player, 0),
            power_spade_tiles=(),
            spade_second=None,
        )
        event = Event(
            "cult_spade_skipped",
            f"{seat_label(player)} skipped {remaining} {kind}(s).",
            {"player": player, "spades": remaining},
        )
        return self._advance_cult_spades(state, (event,))

    def _advance_cult_spades(
        self, state: TerraMysticaState, events: tuple[Event, ...]
    ) -> Transition[TerraMysticaState]:
        if state.spade_return == "action":
            actor = state.spade_actor
            assert actor is not None
            if state.cult_spades[actor] > 0 or state.power_spade_tiles:
                return Transition(state, events)
            state = replace(
                state,
                phase="action",
                cult_spades=replace_at(state.cult_spades, actor, 0),
                spade_return="round",
                spade_actor=None,
                power_spade_tiles=(),
                spade_second=None,
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


def _cult_spade_actions(state: TerraMysticaState, player: PlayerId) -> list[Action]:
    owner = state.players[player]
    profile = owner.profile
    budget = state.cult_spades[player]
    action_phase = state.spade_return == "action"
    reach = effective_reach(state.board, player, profile) if action_phase else 0
    reachable = set(state.board.reachable_land(player, owner.shipping, reach))
    actions: list[Action] = []

    if budget > 0:
        first = state.power_spade_tiles[0] if state.power_spade_tiles else None
        if not (first is not None and state.spade_second is not None):
            for tile in state.board.tiles:
                if not tile.is_land or tile.building is not None:
                    continue
                if tile.terrain is profile.home_terrain:
                    continue
                if tile.position not in reachable:
                    continue
                if first is not None and tile.position == first:
                    continue
                if action_phase:
                    cost = spades_for(profile, tile.terrain)
                    missing = max(0, cost - budget)
                    if missing > 0 and not state.spade_topup:
                        continue
                    payment = spade_cost(profile, owner.digging, missing)
                    if reach > 0 and not adjacent_to_own(
                        state.board, player, tile.position
                    ):
                        payment = add_costs(
                            payment,
                            effective_reach_cost(state.board, player, profile),
                        )
                    if can_pay(owner.resources, payment):
                        actions.append(UseCultSpade(tile.position))
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


def _has_spade_transform(state: TerraMysticaState, player: PlayerId) -> bool:
    return any(
        isinstance(action, UseCultSpade)
        for action in _cult_spade_actions(state, player)
    )


def legal_action_list(state: TerraMysticaState, player: PlayerId) -> list[Action]:
    if state.phase == "setup":
        return setup_actions(state, player)
    if state.phase == "cult_spades":
        return _cult_spade_actions(state, player)
    if state.phase == "stronghold_convert":
        return convert_actions(state, player)
    if state.phase == "town_choice":
        return town_tile_actions(state)
    if state.phase != "action":
        return []
    if player != state.active_player:
        return []
    return action_phase_actions(state, player)


def action_phase_actions(state: TerraMysticaState, player: PlayerId) -> list[Action]:
    actions = building_actions(state, player)
    actions.extend(priest_actions(state, player))
    actions.extend(power_actions(state, player))
    actions.extend(alchemist_trades(state, player))
    actions.append(Pass())
    return actions


def explain_illegal(state: TerraMysticaState, player: PlayerId, action: Action) -> str:
    if state.phase == "setup":
        return explain_setup(state, player, action)
    if state.phase == "cult_spades":
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
                if target is not profile.home_terrain:
                    return "Spades must transform a tile all the way to home terrain."
                first = state.power_spade_tiles[0] if state.power_spade_tiles else None
                if first is not None:
                    if action.position == first:
                        return "That tile is already transformed."
                    if state.spade_second is not None:
                        return "Spades may only be applied to one more tile."
                cost = spades_for(profile, tile.terrain)
                missing = max(0, cost - budget)
                if missing > 0 and not state.spade_topup:
                    return "You do not have enough spades."
                payment = spade_cost(profile, owner.digging, missing)
                if reach > 0 and not adjacent_to_own(
                    state.board, player, action.position
                ):
                    payment = add_costs(
                        payment, effective_reach_cost(state.board, player, profile)
                    )
                if not can_pay(owner.resources, payment):
                    return "You cannot pay for the missing spades or the tunnel."
                return "That spade cannot be used there now."
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
            if (
                state.spade_require_all
                and budget > 0
                and _has_spade_transform(state, player)
            ):
                return "Spend all the stronghold spades before building."
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
    if state.phase == "stronghold_convert":
        return explain_convert(state, player, action)
    if state.phase == "town_choice":
        return explain_town_choice(state, action)
    if state.phase != "action":
        return "The game is over."
    if player != state.active_player:
        return f"It is {seat_label(state.active_player)}'s turn."
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
