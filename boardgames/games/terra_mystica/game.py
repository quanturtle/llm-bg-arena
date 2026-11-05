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
from boardgames.games.terra_mystica.constants import (
    CULT_ORDER,
    MAX_BUILDINGS,
    SCORING_VALUES,
    TERRAIN_WHEEL,
    TOWN_SUPPLY,
    TOWN_TILES,
    BuildingType,
    Cost,
    FactionProfile,
    FactionType,
    Income,
    Resources,
    ScoringAction,
    Terrain,
)
from boardgames.games.terra_mystica.cults import (
    advance_cult_with_priest,
    cult_top_occupied,
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
    Board,
    BuildDwelling,
    Building,
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
    add_income,
    advance_cult,
    building_cost,
    can_pay,
    can_place_building,
    cap_priests,
    effective_reach,
    effective_reach_cost,
    income_with_power,
    pay,
    replace_at,
    replace_player,
    settle_town,
    shipping_cost,
    shipping_points,
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
    stronghold_reward,
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
                return self.build_dwelling(
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
            return self.take_town_tile(state, player, action.index)
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
            return self.build_dwelling(state, player, action.position, action.river)
        if isinstance(action, TransformTerrain):
            return self.transform_terrain(state, player, action.position, action.to)
        if isinstance(action, UpgradeBuilding):
            return self.upgrade_building(
                state, player, action.position, action.to, action.river
            )
        if isinstance(action, AdvanceShipping):
            return self.advance_shipping(state, player)
        if isinstance(action, AdvanceDigging):
            return self.advance_digging(state, player)
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

    def build_dwelling(
        self,
        state: TerraMysticaState,
        player: PlayerId,
        position: Hex,
        river: Hex | None = None,
        *,
        reach_paid: bool = False,
    ) -> Transition[TerraMysticaState]:
        owner = state.players[player]
        profile = owner.profile
        tile = state.board.tile(position)
        if tile is None:
            raise IllegalActionError("there is no tile there")
        if not tile.is_land:
            raise IllegalActionError("you cannot build on a river")
        if tile.building is not None:
            raise IllegalActionError("that tile is occupied")
        if (
            state.board.count(player, BuildingType.DWELLING)
            >= MAX_BUILDINGS[BuildingType.DWELLING]
        ):
            raise IllegalActionError("you have no dwellings left")
        reach = effective_reach(state.board, player, profile)
        if position not in state.board.reachable_land(player, owner.shipping, reach):
            raise IllegalActionError(
                "the tile must be directly or indirectly adjacent to one of "
                "your structures"
            )
        tunneling = reach > 0 and not _adjacent_to_own(state.board, player, position)
        spades = spades_for(profile, tile.terrain)
        terrain_cost = spade_cost(profile, owner.digging, spades)
        build_cost = building_cost(
            profile,
            BuildingType.DWELLING,
            bool(state.board.adjacent_opponents(position, player)),
        )
        reach_cost = (
            effective_reach_cost(state.board, player, profile)
            if tunneling and not reach_paid
            else Cost()
        )
        total = add_costs(add_costs(terrain_cost, build_cost), reach_cost)
        if not can_pay(owner.resources, total):
            raise IllegalActionError(
                "you cannot pay for that transform, build and tunnel"
            )
        resources = pay(owner.resources, total)
        board = state.board
        if spades:
            board = board.replace_tile(
                position, replace(tile, terrain=profile.home_terrain)
            )
        board = board.place(position, Building(BuildingType.DWELLING, player))
        victory_points = owner.victory_points
        if spades:
            victory_points += spades * profile.spade_vp_bonus
            if round_scoring(state) is ScoringAction.SPADE:
                victory_points += spades * SCORING_VALUES[ScoringAction.SPADE]
        if tunneling and not reach_paid:
            victory_points += profile.reach_vp
        if round_scoring(state) is ScoringAction.DWELLING:
            victory_points += SCORING_VALUES[ScoringAction.DWELLING]
        board, resources, victory_points, keys, founded = _town_rewards(
            state,
            player,
            board,
            position,
            resources,
            victory_points,
            owner.keys,
            river=river,
        )
        owner = replace(
            owner,
            resources=resources,
            victory_points=victory_points,
            keys=keys,
        )
        state = replace_player(state, player, owner)
        state = replace(state, board=board)
        if founded:
            state = replace(state, towns=state.towns + 1)
        route = ""
        if tunneling:
            route = (
                " by tunneling" if profile.reach_cost.workers else " by carpet flight"
            )
        events = [
            Event(
                "built",
                f"{seat_label(player)} built a dwelling at {position.notation()}"
                + route
                + (f" after using {spades} spade(s)." if spades else "."),
                {
                    "player": player,
                    "position": position.notation(),
                    "building": "dwelling",
                    "spades": spades,
                    "tunnel": tunneling,
                },
            )
        ]
        if founded:
            events.append(
                Event(
                    "town_founded",
                    f"{seat_label(player)} founded a town at {position.notation()}.",
                    {"player": player, "position": position.notation()},
                )
            )
            state = replace(state, phase="town_choice", active_player=player)
            return Transition(state, tuple(events))
        return advance_turn(state, player, tuple(events))

    def transform_terrain(
        self,
        state: TerraMysticaState,
        player: PlayerId,
        position: Hex,
        to: Terrain | None = None,
    ) -> Transition[TerraMysticaState]:
        owner = state.players[player]
        profile = owner.profile
        tile = state.board.tile(position)
        if tile is None:
            raise IllegalActionError("there is no tile there")
        if not tile.is_land:
            raise IllegalActionError("you cannot transform a river")
        if tile.building is not None:
            raise IllegalActionError("that tile is occupied")
        reach = effective_reach(state.board, player, profile)
        if position not in state.board.reachable_land(player, owner.shipping, reach):
            raise IllegalActionError(
                "the tile must be directly or indirectly adjacent to one of "
                "your structures"
            )
        target = to or profile.home_terrain
        if target is tile.terrain:
            raise IllegalActionError("that tile is already that terrain")
        if profile.terraform_spades is not None and target is not profile.home_terrain:
            raise IllegalActionError("the Giants can only transform to home terrain")
        tunneling = reach > 0 and not _adjacent_to_own(state.board, player, position)
        spades = spades_for(profile, tile.terrain)
        if target is not profile.home_terrain:
            spades = terrain_distance(tile.terrain, target)
        cost = spade_cost(profile, owner.digging, spades)
        if tunneling:
            cost = add_costs(cost, effective_reach_cost(state.board, player, profile))
        if not can_pay(owner.resources, cost):
            raise IllegalActionError("you cannot pay for that transformation")
        resources = pay(owner.resources, cost)
        board = state.board.replace_tile(position, replace(tile, terrain=target))
        victory_points = owner.victory_points + spades * profile.spade_vp_bonus
        if tunneling:
            victory_points += profile.reach_vp
        if round_scoring(state) is ScoringAction.SPADE:
            victory_points += spades * SCORING_VALUES[ScoringAction.SPADE]
        owner = replace(owner, resources=resources, victory_points=victory_points)
        state = replace_player(state, player, owner)
        state = replace(state, board=board)
        route = ""
        if tunneling:
            route = (
                " by tunneling" if profile.reach_cost.workers else " by carpet flight"
            )
        event = Event(
            "transformed",
            f"{seat_label(player)} transformed {position.notation()} into "
            f"{target.value} with {spades} spade(s){route}.",
            {
                "player": player,
                "position": position.notation(),
                "terrain": target.value,
                "spades": spades,
                "tunnel": tunneling,
            },
        )
        return advance_turn(state, player, (event,))

    def upgrade_building(
        self,
        state: TerraMysticaState,
        player: PlayerId,
        position: Hex,
        target: BuildingType,
        river: Hex | None = None,
    ) -> Transition[TerraMysticaState]:
        owner = state.players[player]
        profile = owner.profile
        tile = state.board.tile(position)
        if tile is None or tile.building is None:
            raise IllegalActionError("there is no building there")
        if tile.building.owner != player:
            raise IllegalActionError("that building belongs to another player")
        if not _valid_upgrade(tile.building.type, target):
            raise IllegalActionError(
                f"{tile.building.type.value} cannot be upgraded to {target.value}"
            )
        if state.board.count(player, target) >= MAX_BUILDINGS[target]:
            raise IllegalActionError(f"you have no {target.value} left")
        cost = building_cost(
            profile,
            target,
            bool(state.board.adjacent_opponents(position, player)),
        )
        if not can_pay(owner.resources, cost):
            raise IllegalActionError("you cannot afford that upgrade")
        resources = pay(owner.resources, cost)
        building = replace(tile.building, type=target, in_town=tile.building.in_town)
        board = state.board.replace_tile(position, replace(tile, building=building))
        victory_points = owner.victory_points
        scored = _scored_upgrade(round_scoring(state), target)
        if scored is not None:
            victory_points += SCORING_VALUES[scored]
        board, resources, victory_points, keys, founded = _town_rewards(
            state,
            player,
            board,
            position,
            resources,
            victory_points,
            owner.keys,
            river=river,
        )
        owner = replace(
            owner,
            resources=resources,
            victory_points=victory_points,
            keys=keys,
        )
        state = replace_player(state, player, owner)
        state = replace(state, board=board)
        if founded:
            state = replace(state, towns=state.towns + 1)
        events = [
            Event(
                "upgraded",
                f"{seat_label(player)} upgraded {position.notation()} to "
                f"{target.value}.",
                {
                    "player": player,
                    "position": position.notation(),
                    "building": target.value,
                },
            )
        ]
        if founded:
            events.append(
                Event(
                    "town_founded",
                    f"{seat_label(player)} founded a town at {position.notation()}.",
                    {"player": player, "position": position.notation()},
                )
            )
        if target is BuildingType.STRONGHOLD:
            if founded:
                state = replace(
                    state,
                    phase="town_choice",
                    active_player=player,
                    pending_stronghold=True,
                )
                return Transition(state, tuple(events))
            state, events = stronghold_reward(state, player, events)
            if state.phase in ("cult_spades", "stronghold_convert"):
                return Transition(state, tuple(events))
        if founded:
            state = replace(state, phase="town_choice", active_player=player)
            return Transition(state, tuple(events))
        return advance_turn(state, player, tuple(events))

    def advance_shipping(
        self, state: TerraMysticaState, player: PlayerId
    ) -> Transition[TerraMysticaState]:
        owner = state.players[player]
        cost = shipping_cost()
        owner = replace(
            owner,
            resources=pay(owner.resources, cost),
            shipping=owner.shipping + 1,
            victory_points=owner.victory_points
            + shipping_points(owner.shipping + 1, owner.profile.shipping_start),
        )
        state = replace_player(state, player, owner)
        event = Event(
            "shipping_advanced",
            f"{seat_label(player)} advanced to shipping {owner.shipping}.",
            {"player": player, "shipping": owner.shipping},
        )
        return advance_turn(state, player, (event,))

    def advance_digging(
        self, state: TerraMysticaState, player: PlayerId
    ) -> Transition[TerraMysticaState]:
        owner = state.players[player]
        cost = owner.profile.digging_cost
        owner = replace(
            owner,
            resources=pay(owner.resources, cost),
            digging=owner.digging + 1,
            victory_points=owner.victory_points + 6,
        )
        state = replace_player(state, player, owner)
        event = Event(
            "digging_advanced",
            f"{seat_label(player)} advanced to digging {owner.digging}.",
            {"player": player, "digging": owner.digging},
        )
        return advance_turn(state, player, (event,))

    def take_town_tile(
        self, state: TerraMysticaState, player: PlayerId, index: int
    ) -> Transition[TerraMysticaState]:
        if index < 0 or index >= len(TOWN_TILES):
            raise IllegalActionError("there is no such town tile")
        if state.town_tiles[index] <= 0:
            raise IllegalActionError("that town tile is already taken")
        tile = TOWN_TILES[index]
        owner = state.players[player]
        owner = replace(
            owner, victory_points=owner.victory_points + tile.victory_points
        )
        resources = income_with_power(
            owner.resources,
            Income(
                coins=tile.coins,
                workers=tile.workers,
                priests=tile.priests,
                power=tile.power,
            ),
        )
        owner = replace(owner, resources=cap_priests(state, player, resources))
        gained: list[str] = []
        if tile.cult_steps:
            for cult in CULT_ORDER:
                owner, power = advance_cult(
                    owner,
                    cult,
                    1,
                    top_occupied=cult_top_occupied(state, player, cult),
                )
                gained.append(f"{cult.value} +1 ({power} power)")
        state = replace_player(state, player, owner)
        town_tiles = list(state.town_tiles)
        town_tiles[index] -= 1
        state = replace(state, town_tiles=tuple(town_tiles))
        events = [
            Event(
                "town_tile",
                f"{seat_label(player)} took town tile {index} "
                f"({tile.victory_points} points).",
                {
                    "player": player,
                    "town_tile": index,
                    "victory_points": tile.victory_points,
                    "cults": gained,
                },
            )
        ]
        if state.pending_stronghold:
            state = replace(state, pending_stronghold=False)
            state, events = stronghold_reward(state, player, events)
            if state.phase in ("cult_spades", "stronghold_convert"):
                return Transition(state, tuple(events))
        state = replace(state, phase="action", active_player=player)
        return advance_turn(state, player, tuple(events))

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
            tunneling = reach > 0 and not _adjacent_to_own(
                state.board, player, position
            )
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
                    if reach > 0 and not _adjacent_to_own(
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
                for river in _build_river_choices(
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
        return [
            TakeTownTile(index)
            for index, count in enumerate(state.town_tiles)
            if count > 0
        ]
    if state.phase != "action":
        return []
    if player != state.active_player:
        return []
    return action_phase_actions(state, player)


def action_phase_actions(state: TerraMysticaState, player: PlayerId) -> list[Action]:
    owner = state.players[player]
    profile = owner.profile
    resources = owner.resources
    actions: list[Action] = []
    build_reachable = set(
        state.board.reachable_land(
            player, owner.shipping, effective_reach(state.board, player, profile)
        )
    )
    reach_cost = effective_reach_cost(state.board, player, profile)
    can_build_dwelling = can_place_building(state.board, player, BuildingType.DWELLING)

    if can_build_dwelling:
        for tile in state.board.tiles:
            if not tile.is_land or tile.building is not None:
                continue
            if tile.position not in build_reachable:
                continue
            spades = spades_for(profile, tile.terrain)
            terrain_cost = spade_cost(profile, owner.digging, spades)
            build_cost = building_cost(
                profile,
                BuildingType.DWELLING,
                bool(state.board.adjacent_opponents(tile.position, player)),
            )
            tunneling = profile.reach > 0 and not _adjacent_to_own(
                state.board, player, tile.position
            )
            total = add_costs(terrain_cost, build_cost)
            if tunneling:
                total = add_costs(total, reach_cost)
            if can_pay(resources, total):
                actions.append(BuildDwelling(tile.position))
                for river in _build_river_choices(
                    state.board,
                    player,
                    profile,
                    tile.position,
                    TOWN_SUPPLY - state.towns,
                ):
                    actions.append(BuildDwelling(tile.position, river=river))

    for tile in state.board.tiles:
        if not tile.is_land or tile.building is not None:
            continue
        if tile.position not in build_reachable:
            continue
        if profile.terraform_spades is not None:
            if tile.terrain is profile.home_terrain:
                continue
            cost = spade_cost(profile, owner.digging, spades_for(profile, tile.terrain))
            if profile.reach > 0 and not _adjacent_to_own(
                state.board, player, tile.position
            ):
                cost = add_costs(cost, reach_cost)
            if can_pay(resources, cost):
                actions.append(TransformTerrain(tile.position))
            continue
        for target in TERRAIN_WHEEL:
            if target is tile.terrain:
                continue
            cost = spade_cost(
                profile,
                owner.digging,
                terrain_distance(tile.terrain, target),
            )
            if profile.reach > 0 and not _adjacent_to_own(
                state.board, player, tile.position
            ):
                cost = add_costs(cost, reach_cost)
            if not can_pay(resources, cost):
                continue
            if target is profile.home_terrain:
                actions.append(TransformTerrain(tile.position))
            else:
                actions.append(TransformTerrain(tile.position, target))

    for position, building in state.board.buildings(player):
        if building.type is BuildingType.DWELLING and can_place_building(
            state.board, player, BuildingType.TRADING_HOUSE
        ):
            cost = building_cost(
                profile,
                BuildingType.TRADING_HOUSE,
                bool(state.board.adjacent_opponents(position, player)),
            )
            if can_pay(resources, cost):
                _append_upgrade(
                    actions,
                    state.board,
                    player,
                    profile,
                    position,
                    BuildingType.TRADING_HOUSE,
                    TOWN_SUPPLY - state.towns,
                )
        if (
            building.type is BuildingType.TRADING_HOUSE
            and can_place_building(state.board, player, BuildingType.TEMPLE)
            and can_pay(resources, profile.costs.temple)
        ):
            _append_upgrade(
                actions,
                state.board,
                player,
                profile,
                position,
                BuildingType.TEMPLE,
                TOWN_SUPPLY - state.towns,
            )
        if (
            building.type is BuildingType.TRADING_HOUSE
            and can_place_building(state.board, player, BuildingType.STRONGHOLD)
            and can_pay(resources, profile.costs.stronghold)
        ):
            _append_upgrade(
                actions,
                state.board,
                player,
                profile,
                position,
                BuildingType.STRONGHOLD,
                TOWN_SUPPLY - state.towns,
            )
        if (
            building.type is BuildingType.TEMPLE
            and can_place_building(state.board, player, BuildingType.SANCTUARY)
            and can_pay(resources, profile.costs.sanctuary)
        ):
            _append_upgrade(
                actions,
                state.board,
                player,
                profile,
                position,
                BuildingType.SANCTUARY,
                TOWN_SUPPLY - state.towns,
            )

    if _shipping_reason(state, player) is None:
        actions.append(AdvanceShipping())
    if _digging_reason(state, player) is None:
        actions.append(AdvanceDigging())

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
                if reach > 0 and not _adjacent_to_own(
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
            if action.river is not None and action.river not in _build_river_choices(
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
        if isinstance(action, TakeTownTile):
            if action.index < 0 or action.index >= len(TOWN_TILES):
                return "There is no such town tile."
            if state.town_tiles[action.index] <= 0:
                return "That town tile is already taken."
        return "Choose an available town tile."
    if state.phase != "action":
        return "The game is over."
    if player != state.active_player:
        return f"It is {seat_label(state.active_player)}'s turn."
    owner = state.players[player]
    profile = owner.profile
    if isinstance(action, BuildDwelling):
        tile = state.board.tile(action.position)
        if tile is None:
            return "There is no tile there."
        if not tile.is_land:
            return "You cannot build on a river."
        if tile.building is not None:
            return "That tile is occupied."
        if action.river is not None:
            if profile.type is not FactionType.MERMAIDS:
                return "Only the Mermaids may join a town across the river."
            if action.river not in _build_river_choices(
                state.board,
                player,
                profile,
                action.position,
                TOWN_SUPPLY - state.towns,
            ):
                return "That river does not change the town here."
        if (
            state.board.count(player, BuildingType.DWELLING)
            >= MAX_BUILDINGS[BuildingType.DWELLING]
        ):
            return "You have no dwellings left."
        reach = effective_reach(state.board, player, profile)
        if action.position not in state.board.reachable_land(
            player, owner.shipping, reach
        ):
            return (
                "The tile must be directly or indirectly adjacent to one of "
                "your structures."
            )
        spades = spades_for(profile, tile.terrain)
        total = add_costs(
            spade_cost(profile, owner.digging, spades),
            building_cost(
                profile,
                BuildingType.DWELLING,
                bool(state.board.adjacent_opponents(action.position, player)),
            ),
        )
        if reach > 0 and not _adjacent_to_own(state.board, player, action.position):
            total = add_costs(total, effective_reach_cost(state.board, player, profile))
        if not can_pay(owner.resources, total):
            return "You cannot pay for that transform, build and tunnel."
        return "That dwelling cannot be built now."
    if isinstance(action, TransformTerrain):
        tile = state.board.tile(action.position)
        if tile is None:
            return "There is no tile there."
        if not tile.is_land:
            return "You cannot transform a river."
        if tile.building is not None:
            return "That tile is occupied."
        target = action.to or profile.home_terrain
        if target is tile.terrain:
            return "That tile is already that terrain."
        if profile.terraform_spades is not None and target is not profile.home_terrain:
            return "The Giants can only transform to home terrain."
        reach = effective_reach(state.board, player, profile)
        if action.position not in state.board.reachable_land(
            player, owner.shipping, reach
        ):
            return (
                "The tile must be directly or indirectly adjacent to one of "
                "your structures."
            )
        spades = spades_for(profile, tile.terrain)
        if target is not profile.home_terrain:
            spades = terrain_distance(tile.terrain, target)
        transform_cost = spade_cost(profile, owner.digging, spades)
        if reach > 0 and not _adjacent_to_own(state.board, player, action.position):
            transform_cost = add_costs(
                transform_cost,
                effective_reach_cost(state.board, player, profile),
            )
        if not can_pay(owner.resources, transform_cost):
            return "You cannot pay for that transformation."
        return "That transformation is not legal now."
    if isinstance(action, UpgradeBuilding):
        tile = state.board.tile(action.position)
        if tile is None or tile.building is None:
            return "There is no building there."
        if tile.building.owner != player:
            return "That building belongs to another player."
        if not _valid_upgrade(tile.building.type, action.to):
            return (
                f"{tile.building.type.value} cannot be upgraded to {action.to.value}."
            )
        if state.board.count(player, action.to) >= MAX_BUILDINGS[action.to]:
            return f"You have no {action.to.value} left."
        if action.river is not None:
            if profile.type is not FactionType.MERMAIDS:
                return "Only the Mermaids may join a town across the river."
            if action.river not in _upgrade_river_choices(
                state.board,
                player,
                profile,
                action.position,
                action.to,
                TOWN_SUPPLY - state.towns,
            ):
                return "That river does not change the town here."
        upgrade_cost = building_cost(
            profile,
            action.to,
            bool(state.board.adjacent_opponents(action.position, player)),
        )
        if not can_pay(owner.resources, upgrade_cost):
            return "You cannot afford that upgrade."
        return "That upgrade is not legal now."
    if isinstance(action, AdvanceShipping):
        return _shipping_reason(state, player) or "You cannot advance shipping now."
    if isinstance(action, AdvanceDigging):
        return _digging_reason(state, player) or "You cannot advance digging now."
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


def _shipping_reason(state: TerraMysticaState, player: PlayerId) -> str | None:
    owner = state.players[player]
    if not owner.profile.can_ship:
        return "Your faction has no shipping track."
    if owner.shipping >= owner.profile.shipping_max:
        return "Your shipping track is already at its maximum."
    if not can_pay(owner.resources, shipping_cost()):
        return "Shipping costs 1 priest and 4 coins."
    return None


def _digging_reason(state: TerraMysticaState, player: PlayerId) -> str | None:
    owner = state.players[player]
    if not owner.profile.can_dig:
        return "Your faction cannot improve its digging."
    if owner.digging >= owner.profile.digging_max:
        return "Your digging track is already at its maximum."
    if not can_pay(owner.resources, owner.profile.digging_cost):
        return "You cannot pay for a digging step."
    return None


def _town_rewards(
    state: TerraMysticaState,
    player: PlayerId,
    board: Board,
    position: Hex,
    resources: Resources,
    victory_points: int,
    keys: int,
    *,
    river: Hex | None = None,
) -> tuple[Board, Resources, int, int, bool]:
    """Mark a new town and award its points, key and faction bonus."""
    owner = state.players[player]
    board, founded = settle_town(
        board,
        position,
        player,
        river=river if owner.profile.type is FactionType.MERMAIDS else None,
        towns_left=TOWN_SUPPLY - state.towns,
    )
    if not founded:
        return board, resources, victory_points, keys, False
    profile = owner.profile
    victory_points += profile.town_vp_bonus
    keys += 1
    resources = add_income(resources, Income(workers=profile.town_workers_bonus))
    if round_scoring(state) is ScoringAction.TOWN:
        victory_points += SCORING_VALUES[ScoringAction.TOWN]
    return board, resources, victory_points, keys, True


def _scored_upgrade(
    action: ScoringAction, target: BuildingType
) -> ScoringAction | None:
    """The round scoring action an upgrade satisfies, if any."""
    if target is BuildingType.TRADING_HOUSE and action is ScoringAction.TRADING_HOUSE:
        return action
    if target in (BuildingType.STRONGHOLD, BuildingType.SANCTUARY) and (
        action is ScoringAction.STRONGHOLD_OR_SANCTUARY
    ):
        return action
    return None


def _valid_upgrade(source: BuildingType, target: BuildingType) -> bool:
    return (
        (source is BuildingType.DWELLING and target is BuildingType.TRADING_HOUSE)
        or (
            source is BuildingType.TRADING_HOUSE
            and target in (BuildingType.TEMPLE, BuildingType.STRONGHOLD)
        )
        or (source is BuildingType.TEMPLE and target is BuildingType.SANCTUARY)
    )


def _town_outcome(
    board: Board,
    position: Hex,
    player: PlayerId,
    river: Hex | None,
    towns_left: int,
) -> tuple[Board, bool]:
    return settle_town(
        board,
        position,
        player,
        river=river,
        towns_left=towns_left,
    )


def _changing_rivers(
    board: Board,
    position: Hex,
    player: PlayerId,
    towns_left: int,
) -> list[Hex]:
    """River spaces that let this component found a new town."""
    direct = _town_outcome(board, position, player, None, towns_left)[1]
    if direct:
        return []
    rivers = {
        neighbour
        for member in board.connected(position, player)
        for neighbour in member.neighbours()
        if (tile := board.tile(neighbour)) is not None and not tile.is_land
    }
    return [
        river
        for river in sorted(rivers)
        if _town_outcome(board, position, player, river, towns_left)[1]
    ]


def _build_river_choices(
    board: Board,
    player: PlayerId,
    profile: FactionProfile,
    position: Hex,
    towns_left: int,
) -> list[Hex]:
    """River skips that would change a Mermaid build's town."""
    if profile.type is not FactionType.MERMAIDS:
        return []
    built = board.place(position, Building(BuildingType.DWELLING, player))
    return _changing_rivers(built, position, player, towns_left)


def _upgrade_river_choices(
    board: Board,
    player: PlayerId,
    profile: FactionProfile,
    position: Hex,
    target: BuildingType,
    towns_left: int,
) -> list[Hex]:
    """River skips that would change a Mermaid upgrade's town."""
    if profile.type is not FactionType.MERMAIDS:
        return []
    tile = board.tile(position)
    if tile is None or tile.building is None:
        return []
    upgraded = board.replace_tile(
        position, replace(tile, building=replace(tile.building, type=target))
    )
    return _changing_rivers(upgraded, position, player, towns_left)


def _append_upgrade(
    actions: list[Action],
    board: Board,
    player: PlayerId,
    profile: FactionProfile,
    position: Hex,
    target: BuildingType,
    towns_left: int,
) -> None:
    """List an upgrade and each Mermaid river skip that changes its town."""
    actions.append(UpgradeBuilding(position, target))
    for river in _upgrade_river_choices(
        board, player, profile, position, target, towns_left
    ):
        actions.append(UpgradeBuilding(position, target, river=river))


def _adjacent_to_own(board: Board, player: PlayerId, position: Hex) -> bool:
    """Whether one of the player's structures shares an edge with `position`."""
    return any(
        (tile := board.tile(neighbour)) is not None
        and tile.building is not None
        and tile.building.owner == player
        for neighbour in position.neighbours()
    )
