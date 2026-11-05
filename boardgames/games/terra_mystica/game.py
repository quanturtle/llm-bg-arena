"""Terra Mystica: the standard base game for two to five players."""

from dataclasses import replace
from functools import partial
from importlib.resources import files
from typing import ClassVar

from boardgames.core import (
    ActionSpace,
    ConfigError,
    Decision,
    Event,
    FlatActionSpace,
    Game,
    IllegalActionError,
    JsonObject,
    JsonValue,
    Observation,
    PlayerId,
    Rng,
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
    CULT_ORDER_STEPS,
    FACTION_BY_TYPE,
    FACTIONS_BY_TERRAIN,
    MAX_BUILDINGS,
    POWER_ACTION_COSTS,
    POWER_ACTION_INCOME,
    POWER_ACTION_KINDS,
    PRIEST_SUPPLY,
    SCORING_TILES,
    SCORING_VALUES,
    STANDARD_DWELLING_INCOME,
    STANDARD_TEMPLE_INCOME,
    STANDARD_TRADING_HOUSE_INCOME,
    TERRAIN_WHEEL,
    TOWN_SUPPLY,
    TOWN_TILES,
    BuildingType,
    Cost,
    Cult,
    CultBonus,
    FactionProfile,
    FactionType,
    Income,
    PowerActionKind,
    Resources,
    ScoringAction,
    ScoringTile,
    Terrain,
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
    PlayerState,
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
    add_resources,
    advance_cult,
    building_cost,
    building_counts,
    burn_power,
    can_pay,
    can_place_building,
    can_spend_power,
    cult_bonus_json,
    cult_limit,
    effective_reach,
    effective_reach_cost,
    gain_power,
    income_with_power,
    pay,
    replace_at,
    replace_player,
    settle_town,
    shipping_cost,
    shipping_points,
    spade_cost,
    spades_for,
    spend_power,
    terrain_distance,
)
from boardgames.games.terra_mystica.notation import format_action, parse_action
from boardgames.games.terra_mystica.scoring import final_scores
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
        rng = Rng.seeded(seed)
        n = config.num_players
        first_seat, rng = rng.below(n)
        order: tuple[PlayerId, ...] = tuple(
            PlayerId((first_seat + offset) % n) for offset in range(n)
        )
        terrains, rng = rng.shuffled(TERRAIN_WHEEL)
        factions: list[FactionType] = []
        for terrain in terrains[:n]:
            options = FACTIONS_BY_TERRAIN[terrain]
            choice, rng = rng.below(len(options))
            factions.append(options[choice])
        while True:
            scoring_order, rng = rng.shuffled(SCORING_TILES)
            late = scoring_order[4 : config.rounds]
            if not any(tile.action is ScoringAction.SPADE for tile in late):
                break
        scoring = scoring_order[: config.rounds]

        profiles = [FACTION_BY_TYPE[faction] for faction in factions]
        player_states = tuple(
            PlayerState(
                faction=profile.type,
                resources=profile.starting_resources,
                victory_points=20,
                cults=profile.starting_cults,
                shipping=profile.shipping_start,
                digging=profile.digging_start,
            )
            for profile in profiles
        )

        setup_queue = initial_setup_queue(order, player_states)
        state = TerraMysticaState(
            config=config,
            rng=rng,
            board=Board.base(),
            players=player_states,
            order=order,
            active_player=setup_queue[0],
            phase="setup",
            setup_queue=setup_queue,
            passed=frozenset(),
            pass_order=(),
            round=1,
            scoring=scoring,
            cult_spades=(0,) * n,
            used_power_actions=frozenset(),
            used_orders={},
        )
        events = (
            Event(
                "game_started",
                f"Terra Mystica: {n} players, {seat_label(order[0])} starts.",
                {"num_players": n, "starting_player": order[0]},
            ),
            Event(
                "factions",
                "; ".join(
                    f"{seat_label(PlayerId(seat))} plays {player.faction.value}"
                    for seat, player in enumerate(player_states)
                ),
                {
                    "factions": [
                        {"player": seat, "faction": player.faction.value}
                        for seat, player in enumerate(player_states)
                    ]
                },
            ),
            Event(
                "scoring_tiles",
                "Round scoring: "
                + ", ".join(
                    f"{tile.action.value} ({_bonus_text(tile.bonus)})"
                    for tile in scoring
                )
                + ".",
                {
                    "scoring": [tile.action.value for tile in scoring],
                    "bonuses": [cult_bonus_json(tile.bonus) for tile in scoring],
                },
            ),
            Event(
                "setup_dwelling",
                f"{seat_label(setup_queue[0])} places a starting dwelling.",
                {"player": setup_queue[0]},
            ),
        )
        return Transition(state, events)

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
            return (
                Decision(
                    state.active_player,
                    "cult_spade",
                    "Spend a cult-bonus spade on a reachable tile, or skip.",
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
            return self.place_starting_dwelling(state, player, action.position)
        if state.phase == "cult_spades":
            if (
                isinstance(action, BuildDwelling)
                and state.spade_return == "action"
                and action.position in state.power_spade_tiles
            ):
                if state.spade_require_all and state.cult_spades[player] > 0:
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
                return self.build_dwelling(state, player, action.position, action.river)
            if isinstance(action, UseCultSpade):
                return self.use_cult_spade(state, player, action.position, action.to)
            if isinstance(action, SkipCultSpade):
                return self.skip_cult_spade(state, player)
            if (
                state.spade_return == "action"
                and isinstance(action, TradeVpForCoin)
                and state.players[player].profile.type is FactionType.ALCHEMISTS
            ):
                return self.trade_vp_for_coin(state, player)
            if (
                state.spade_return == "action"
                and isinstance(action, TradeCoinsForVp)
                and state.players[player].profile.type is FactionType.ALCHEMISTS
            ):
                return self.trade_coins_for_vp(state, player)
            raise IllegalActionError("spend a spade or skip now")
        if state.phase == "stronghold_convert":
            if not isinstance(action, ChooseStrongholdPriests):
                raise IllegalActionError("choose how many workers to trade")
            return self.choose_stronghold_priests(state, player, action.workers)
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

    # Setup actions --------------------------------------------------------

    def place_starting_dwelling(
        self, state: TerraMysticaState, player: PlayerId, position: Hex
    ) -> Transition[TerraMysticaState]:
        owner = state.players[player]
        tile = state.board.tile(position)
        if tile is None:
            raise IllegalActionError("there is no tile there")
        if not tile.is_land:
            raise IllegalActionError("you cannot build on a river")
        if tile.terrain is not owner.home_terrain:
            raise IllegalActionError("starting dwellings must be on home terrain")
        if tile.building is not None:
            raise IllegalActionError("that tile is occupied")
        board = state.board.place(position, Building(BuildingType.DWELLING, player))
        queue = state.setup_queue[1:]
        events = [
            Event(
                "dwelling_placed",
                f"{seat_label(player)} placed a starting dwelling at "
                f"{position.notation()}.",
                {"player": player, "position": position.notation()},
            )
        ]
        if queue:
            state = replace(
                state,
                board=board,
                setup_queue=queue,
                active_player=queue[0],
            )
            events.append(
                Event(
                    "setup_dwelling",
                    f"{seat_label(queue[0])} places a starting dwelling.",
                    {"player": queue[0]},
                )
            )
            return Transition(state, tuple(events))
        state = replace(state, board=board, setup_queue=())
        state, round_events = start_round(state)
        return Transition(state, (*events, *round_events))

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
            return self.send_priest(state, player, action.cult, action.order)
        if isinstance(action, AdvanceCult):
            return self.advance_cult_with_priest(state, player, action.cult)
        if isinstance(action, PowerAction):
            return self.take_power_action(state, player, action.kind)
        if isinstance(action, TradeVpForCoin):
            return self.trade_vp_for_coin(state, player)
        if isinstance(action, TradeCoinsForVp):
            return self.trade_coins_for_vp(state, player)
        if isinstance(action, Pass):
            return self.pass_turn(state, player)
        raise IllegalActionError("unknown action")

    def build_dwelling(
        self,
        state: TerraMysticaState,
        player: PlayerId,
        position: Hex,
        river: Hex | None = None,
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
            effective_reach_cost(state.board, player, profile) if tunneling else Cost()
        )
        total = _add_costs(_add_costs(terrain_cost, build_cost), reach_cost)
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
            if _round_scoring(state) is ScoringAction.SPADE:
                victory_points += spades * SCORING_VALUES[ScoringAction.SPADE]
        if tunneling:
            victory_points += profile.reach_vp
        if _round_scoring(state) is ScoringAction.DWELLING:
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
        return self.advance_turn(state, player, tuple(events))

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
            cost = _add_costs(cost, effective_reach_cost(state.board, player, profile))
        if not can_pay(owner.resources, cost):
            raise IllegalActionError("you cannot pay for that transformation")
        resources = pay(owner.resources, cost)
        board = state.board.replace_tile(position, replace(tile, terrain=target))
        victory_points = owner.victory_points + spades * profile.spade_vp_bonus
        if tunneling:
            victory_points += profile.reach_vp
        if _round_scoring(state) is ScoringAction.SPADE:
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
        return self.advance_turn(state, player, (event,))

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
        scored = _scored_upgrade(_round_scoring(state), target)
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
            state, events = _stronghold_reward(state, player, events)
            if state.phase in ("cult_spades", "stronghold_convert"):
                return Transition(state, tuple(events))
        if founded:
            state = replace(state, phase="town_choice", active_player=player)
            return Transition(state, tuple(events))
        return self.advance_turn(state, player, tuple(events))

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
        return self.advance_turn(state, player, (event,))

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
        return self.advance_turn(state, player, (event,))

    def send_priest(
        self,
        state: TerraMysticaState,
        player: PlayerId,
        cult: Cult,
        order: int,
    ) -> Transition[TerraMysticaState]:
        owner = state.players[player]
        if owner.resources.priests <= 0:
            raise IllegalActionError("you have no priest to send")
        if (cult, order) in state.used_orders:
            raise IllegalActionError("that order space is already occupied")
        resources = replace(owner.resources, priests=owner.resources.priests - 1)
        owner = replace(owner, resources=resources)
        state = replace(state, used_orders={**state.used_orders, (cult, order): player})
        steps = CULT_ORDER_STEPS[order]
        owner, gained = advance_cult(
            owner,
            cult,
            steps,
            top_occupied=_cult_top_occupied(state, player, cult),
        )
        state = replace_player(state, player, owner)
        event = Event(
            "priest_sent",
            f"{seat_label(player)} sent a priest to {cult.value} order {order} "
            f"and advanced {steps} (gain {gained} power).",
            {
                "player": player,
                "cult": cult.value,
                "order": order,
                "steps": steps,
                "power": gained,
            },
        )
        return self.advance_turn(state, player, (event,))

    def advance_cult_with_priest(
        self, state: TerraMysticaState, player: PlayerId, cult: Cult
    ) -> Transition[TerraMysticaState]:
        owner = state.players[player]
        if owner.resources.priests <= 0:
            raise IllegalActionError("you have no priest to send")
        if owner.cult(cult) >= _cult_limit_for(state, player, cult):
            raise IllegalActionError("that cult track cannot advance further")
        owner = replace(
            owner,
            resources=replace(owner.resources, priests=owner.resources.priests - 1),
        )
        owner, gained = advance_cult(
            owner,
            cult,
            1,
            top_occupied=_cult_top_occupied(state, player, cult),
        )
        state = replace_player(state, player, owner)
        event = Event(
            "cult_advanced",
            f"{seat_label(player)} spent a priest and advanced {cult.value} by 1 "
            f"(gain {gained} power).",
            {"player": player, "cult": cult.value, "steps": 1, "power": gained},
        )
        return self.advance_turn(state, player, (event,))

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
        owner = replace(owner, resources=_cap_priests(state, player, resources))
        gained: list[str] = []
        if tile.cult_steps:
            for cult in CULT_ORDER:
                owner, power = advance_cult(
                    owner,
                    cult,
                    1,
                    top_occupied=_cult_top_occupied(state, player, cult),
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
            state, events = _stronghold_reward(state, player, events)
            if state.phase in ("cult_spades", "stronghold_convert"):
                return Transition(state, tuple(events))
        state = replace(state, phase="action", active_player=player)
        return self.advance_turn(state, player, tuple(events))

    def choose_stronghold_priests(
        self, state: TerraMysticaState, player: PlayerId, workers: int
    ) -> Transition[TerraMysticaState]:
        owner = state.players[player]
        supply = _priest_capacity(state, player) - owner.resources.priests
        maximum = max(0, min(3, owner.resources.workers, supply))
        if workers < 0 or workers > maximum:
            raise IllegalActionError(
                "the Darklings may trade at most three workers this way"
            )
        resources = replace(
            owner.resources,
            workers=owner.resources.workers - workers,
            priests=owner.resources.priests + workers,
        )
        owner = replace(owner, resources=resources)
        state = replace_player(state, player, owner)
        state = replace(state, phase="action", active_player=player)
        event = Event(
            "stronghold_convert",
            f"{seat_label(player)} traded {workers} worker(s) for priests as the "
            "Darklings' stronghold reward.",
            {"player": player, "workers": workers, "priests": workers},
        )
        return self.advance_turn(state, player, (event,))

    def take_power_action(
        self, state: TerraMysticaState, player: PlayerId, kind: PowerActionKind
    ) -> Transition[TerraMysticaState]:
        owner = state.players[player]
        cost = POWER_ACTION_COSTS[kind]
        if kind in state.used_power_actions:
            raise IllegalActionError("that power action was already used this round")
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
                spade_topup=True,
                spade_require_all=False,
                active_player=player,
            )
            event = Event(
                "power_action",
                f"{seat_label(player)} spent {cost} power for {amount} spade(s).",
                {"player": player, "kind": kind, "cost": cost, "spades": amount},
            )
            return Transition(state, (event,))
        resources = _cap_priests(
            state, player, _add_income(spent, POWER_ACTION_INCOME[kind])
        )
        owner = replace(owner, resources=resources)
        state = replace_player(state, player, owner)
        state = replace(state, used_power_actions=state.used_power_actions | {kind})
        event = Event(
            "power_action",
            f"{seat_label(player)} spent {cost} power for {kind}.",
            {"player": player, "kind": kind, "cost": cost},
        )
        return self.advance_turn(state, player, (event,))

    def trade_vp_for_coin(
        self, state: TerraMysticaState, player: PlayerId
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
        self, state: TerraMysticaState, player: PlayerId
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

    def pass_turn(
        self, state: TerraMysticaState, player: PlayerId
    ) -> Transition[TerraMysticaState]:
        passed = state.passed | {player}
        pass_order = (*state.pass_order, player)
        event = Event(
            "passed",
            f"{seat_label(player)} passed.",
            {"player": player},
        )
        if len(passed) >= len(state.players):
            state = replace(state, passed=passed, pass_order=pass_order)
            return end_round(state, (event,))
        next_player = _next_unpassed(
            replace(state, passed=passed, pass_order=pass_order), player
        )
        state = replace(
            state,
            passed=passed,
            pass_order=pass_order,
            active_player=next_player,
        )
        return Transition(state, (event,))

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
                payment = _add_costs(
                    payment, effective_reach_cost(state.board, player, profile)
                )
            if not can_pay(owner.resources, payment):
                raise IllegalActionError(
                    "you cannot pay for the missing spades or the tunnel"
                )
            spent = cost
            remaining = max(0, budget - cost)
            points = profile.reach_vp if tunneling else 0
            if _round_scoring(state) is ScoringAction.SPADE:
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
        state = replace(
            state,
            cult_spades=replace_at(state.cult_spades, player, 0),
            power_spade_tiles=(),
            spade_second=None,
        )
        event = Event(
            "cult_spade_skipped",
            f"{seat_label(player)} skipped {remaining} cult-bonus spade(s).",
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
            return self.advance_turn(state, actor, events)
        next_player = _next_cult_spade_player(state)
        if next_player is None:
            return _start_next_round(state, events)
        if next_player == state.active_player:
            return Transition(state, events)
        event = _cult_spade_event(state, next_player, _round_tile(state).bonus)
        return Transition(replace(state, active_player=next_player), (*events, event))

    def advance_turn(
        self,
        state: TerraMysticaState,
        player: PlayerId,
        events: tuple[Event, ...],
    ) -> Transition[TerraMysticaState]:
        unpassed = [seat for seat in state.order if seat not in state.passed]
        if unpassed == [player]:
            return Transition(state, events)
        next_player = _next_unpassed(state, player)
        return Transition(replace(state, active_player=next_player), events)


def check_config(config: TerraMysticaConfig) -> None:
    if not 2 <= config.num_players <= 5:
        raise ConfigError(
            f"Terra Mystica needs 2 to 5 players, got {config.num_players}"
        )
    if not 1 <= config.rounds <= 6:
        raise ConfigError(f"rounds must be from 1 to 6, got {config.rounds}")
    return


def initial_setup_queue(
    order: tuple[PlayerId, ...], players: tuple[PlayerState, ...]
) -> tuple[PlayerId, ...]:
    """Clockwise first, counterclockwise second, then Nomads and Chaos Magicians."""
    first = tuple(
        seat for seat in order if players[seat].profile.starting_dwellings > 1
    )
    second = tuple(reversed(first))
    extras = tuple(
        seat
        for seat in order
        for _ in range(max(0, players[seat].profile.starting_dwellings - 2))
    )
    chaos = tuple(
        seat for seat in order if players[seat].profile.starting_dwellings == 1
    )
    return (*first, *second, *extras, *chaos)


def start_round(
    state: TerraMysticaState,
) -> tuple[TerraMysticaState, tuple[Event, ...]]:
    """Enter the action phase and run the income phase."""
    round_number = state.round
    tile = _round_tile(state)
    state = replace(
        state,
        phase="action",
        active_player=state.order[0],
        passed=frozenset(),
        pass_order=(),
        used_power_actions=frozenset(),
        cult_spades=(0,) * len(state.players),
        spade_return="round",
        spade_actor=None,
        power_spade_tiles=(),
        spade_second=None,
        spade_topup=True,
        spade_require_all=False,
    )
    events: list[Event] = [
        Event(
            "round_started",
            f"Round {round_number}: {tile.action.value} scores; "
            f"cult bonus {_bonus_text(tile.bonus)}.",
            {
                "round": round_number,
                "scoring": tile.action.value,
                "bonus": cult_bonus_json(tile.bonus),
            },
        )
    ]
    for seat in state.order:
        owner = state.players[seat]
        income = income_for(state.board, seat, owner)
        resources = _cap_priests(
            state, seat, income_with_power(owner.resources, income)
        )
        owner = replace(
            owner,
            resources=resources,
            victory_points=owner.victory_points + income.victory_points,
        )
        state = replace_player(state, seat, owner)
        events.append(
            Event(
                "income",
                f"{seat_label(seat)} collects income.",
                {
                    "player": seat,
                    "coins": income.coins,
                    "workers": income.workers,
                    "priests": income.priests,
                    "power": income.power,
                    "victory_points": income.victory_points,
                },
            )
        )
    return state, tuple(events)


def end_round(
    state: TerraMysticaState, events: tuple[Event, ...]
) -> Transition[TerraMysticaState]:
    if state.round >= state.config.rounds:
        state = replace(state, phase="game_over", end_reason="after the final round")
        final = final_scores(state)
        best = max(points for points, _ in final.values())
        winners = [seat for seat, (points, _) in final.items() if points == best]
        names = ", ".join(seat_label(seat) for seat in winners)
        game_over = Event(
            "game_over",
            f"Game over: {names} with {best} points.",
            {
                "winners": winners,
                "scores": [
                    {
                        "player": seat,
                        "points": final[seat][0],
                        "breakdown": final[seat][1],
                    }
                    for seat in seats(len(state.players))
                ],
            },
        )
        return Transition(state, (*events, game_over))
    first = state.pass_order[0]
    start = state.order.index(first)
    new_order = (*state.order[start:], *state.order[:start])
    state = replace(state, order=new_order)
    bonus = _round_tile(state).bonus
    if bonus.reward == "spades":
        budgets = tuple(
            _cult_bonus_amount(state.players[seat], bonus)
            for seat in range(len(state.players))
        )
        for seat, budget in enumerate(budgets):
            owner = state.players[seat]
            if owner.profile.type is FactionType.HALFLINGS:
                state = replace_player(
                    state,
                    PlayerId(seat),
                    replace(
                        owner,
                        victory_points=owner.victory_points
                        + budget * owner.profile.spade_vp_bonus,
                    ),
                )
        state = replace(
            state,
            phase="cult_spades",
            cult_spades=budgets,
            spade_return="round",
            spade_actor=None,
            power_spade_tiles=(),
            spade_second=None,
            spade_topup=True,
            spade_require_all=False,
        )
        next_player = _next_cult_spade_player(state)
        if next_player is None:
            return _start_next_round(state, events)
        event = _cult_spade_event(state, next_player, bonus)
        return Transition(replace(state, active_player=next_player), (*events, event))
    bonus_events: list[Event] = []
    for seat in new_order:
        state, bonus_event = _apply_cult_bonus(state, seat, bonus)
        if bonus_event is not None:
            bonus_events.append(bonus_event)
    return _start_next_round(state, (*events, *bonus_events))


def _start_next_round(
    state: TerraMysticaState, events: tuple[Event, ...]
) -> Transition[TerraMysticaState]:
    """Finish cleanup and begin the next round."""
    state = replace(
        state,
        round=state.round + 1,
        passed=frozenset(),
        pass_order=(),
        used_power_actions=frozenset(),
        active_player=state.order[0],
        cult_spades=(0,) * len(state.players),
        spade_return="round",
        spade_actor=None,
        power_spade_tiles=(),
        spade_second=None,
        spade_topup=True,
        spade_require_all=False,
    )
    state, round_events = start_round(state)
    return Transition(state, (*events, *round_events))


def _cult_bonus_amount(player: PlayerState, bonus: CultBonus) -> int:
    return (player.cult(bonus.cult) // bonus.per) * bonus.amount


def _apply_cult_bonus(
    state: TerraMysticaState, seat: PlayerId, bonus: CultBonus
) -> tuple[TerraMysticaState, Event | None]:
    """Pay one non-spade end-of-round cult bonus to one player."""
    owner = state.players[seat]
    amount = _cult_bonus_amount(owner, bonus)
    if amount <= 0:
        return state, None
    if bonus.reward == "priests":
        resources = _cap_priests(
            state, seat, _add_income(owner.resources, Income(priests=amount))
        )
        owner = replace(owner, resources=resources)
    elif bonus.reward == "workers":
        resources = _add_income(owner.resources, Income(workers=amount))
        owner = replace(owner, resources=resources)
    elif bonus.reward == "coins":
        resources = _add_income(owner.resources, Income(coins=amount))
        owner = replace(owner, resources=resources)
    elif bonus.reward == "power":
        resources = gain_power(owner.resources, amount)
        owner = replace(owner, resources=resources)
    elif bonus.reward == "spades":
        raise ValueError("spades need a player's choice")
    state = replace_player(state, seat, owner)
    event = Event(
        "cult_bonus",
        f"{seat_label(seat)} gained {amount} {bonus.reward} from the "
        f"{bonus.cult.value} cult bonus.",
        {
            "player": seat,
            "cult": bonus.cult.value,
            "reward": bonus.reward,
            "amount": amount,
        },
    )
    return state, event


def _cult_spade_event(
    state: TerraMysticaState, player: PlayerId, bonus: CultBonus
) -> Event:
    return Event(
        "cult_bonus",
        f"{seat_label(player)} may use {state.cult_spades[player]} "
        "cult-bonus spade(s).",
        {
            "player": player,
            "cult": bonus.cult.value,
            "reward": bonus.reward,
            "amount": state.cult_spades[player],
        },
    )


def _next_cult_spade_player(state: TerraMysticaState) -> PlayerId | None:
    return next((seat for seat in state.order if state.cult_spades[seat] > 0), None)


def _claimed_priests(state: TerraMysticaState, player: PlayerId) -> int:
    return sum(1 for owner in state.used_orders.values() if owner == player)


def _priest_capacity(state: TerraMysticaState, player: PlayerId) -> int:
    return PRIEST_SUPPLY - _claimed_priests(state, player)


def _cap_priests(
    state: TerraMysticaState, player: PlayerId, resources: Resources
) -> Resources:
    return replace(
        resources, priests=min(resources.priests, _priest_capacity(state, player))
    )


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
                        payment = _add_costs(
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
        and (not state.spade_require_all or budget == 0)
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

    if action_phase and profile.type is FactionType.ALCHEMISTS:
        if owner.victory_points > 0:
            actions.append(TradeVpForCoin())
        if owner.resources.coins >= 2:
            actions.append(TradeCoinsForVp())

    actions.append(SkipCultSpade())
    return actions


def _round_tile(state: TerraMysticaState) -> ScoringTile:
    return state.scoring[state.round - 1]


def _bonus_text(bonus: CultBonus) -> str:
    return f"{bonus.amount} {bonus.reward} per {bonus.per} {bonus.cult.value}"


def income_for(board: Board, seat: PlayerId, player: PlayerState) -> Income:
    profile = player.profile
    counts = building_counts(board, seat)
    dwellings = counts[BuildingType.DWELLING]
    trading = counts[BuildingType.TRADING_HOUSE]
    temples = counts[BuildingType.TEMPLE]
    sanctuaries = counts[BuildingType.SANCTUARY]
    strongholds = counts[BuildingType.STRONGHOLD]

    dwelling_income = (
        Income()
        if dwellings == 0
        else (profile.dwelling_income or STANDARD_DWELLING_INCOME)[dwellings - 1]
    )
    trading_income = (
        Income()
        if trading == 0
        else (profile.trading_house_income or STANDARD_TRADING_HOUSE_INCOME)[
            trading - 1
        ]
    )
    temple_income = (
        Income()
        if temples == 0
        else (profile.temple_income or STANDARD_TEMPLE_INCOME)[temples - 1]
    )
    sanctuary_income = profile.sanctuary_income if sanctuaries else Income()
    stronghold_income = profile.stronghold_income if strongholds else Income()
    return Income(
        coins=(
            profile.base_income.coins
            + dwelling_income.coins
            + trading_income.coins
            + temple_income.coins
            + sanctuary_income.coins
            + stronghold_income.coins
        ),
        workers=(
            profile.base_income.workers
            + dwelling_income.workers
            + trading_income.workers
            + temple_income.workers
            + sanctuary_income.workers
            + stronghold_income.workers
        ),
        priests=(
            profile.base_income.priests
            + dwelling_income.priests
            + trading_income.priests
            + temple_income.priests
            + sanctuary_income.priests
            + stronghold_income.priests
        ),
        power=(
            profile.base_income.power
            + dwelling_income.power
            + trading_income.power
            + temple_income.power
            + sanctuary_income.power
            + stronghold_income.power
        ),
        victory_points=profile.base_income.victory_points,
    )


def legal_action_list(state: TerraMysticaState, player: PlayerId) -> list[Action]:
    if state.phase == "setup":
        owner = state.players[player]
        return [
            BuildDwelling(tile.position)
            for tile in state.board.tiles
            if tile.is_land
            and tile.terrain is owner.home_terrain
            and tile.building is None
        ]
    if state.phase == "cult_spades":
        return _cult_spade_actions(state, player)
    if state.phase == "stronghold_convert":
        owner = state.players[player]
        supply = _priest_capacity(state, player) - owner.resources.priests
        maximum = max(0, min(3, owner.resources.workers, supply))
        return [ChooseStrongholdPriests(workers) for workers in range(maximum + 1)]
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
            total = _add_costs(terrain_cost, build_cost)
            if tunneling:
                total = _add_costs(total, reach_cost)
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
                cost = _add_costs(cost, reach_cost)
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
                cost = _add_costs(cost, reach_cost)
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

    if owner.resources.priests > 0:
        for cult in CULT_ORDER:
            for order in range(4):
                if (cult, order) not in state.used_orders:
                    actions.append(SendPriest(cult, order))
            if owner.cult(cult) < _cult_limit_for(state, player, cult):
                actions.append(AdvanceCult(cult))

    for kind in POWER_ACTION_KINDS:
        if kind in state.used_power_actions:
            continue
        if can_spend_power(owner.resources, POWER_ACTION_COSTS[kind]):
            actions.append(PowerAction(kind))

    if profile.type is FactionType.ALCHEMISTS:
        if owner.victory_points > 0:
            actions.append(TradeVpForCoin())
        if owner.resources.coins >= 2:
            actions.append(TradeCoinsForVp())

    actions.append(Pass())
    return actions


def explain_illegal(state: TerraMysticaState, player: PlayerId, action: Action) -> str:
    if state.phase == "setup":
        if isinstance(action, BuildDwelling):
            tile = state.board.tile(action.position)
            if tile is None:
                return "There is no tile there."
            if not tile.is_land:
                return "You cannot build on a river."
            if tile.building is not None:
                return "That tile is occupied."
            if tile.terrain is not state.players[player].home_terrain:
                return "Starting dwellings must be on your home terrain."
        return "Place a starting dwelling on a free home-terrain tile."
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
                    payment = _add_costs(
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
            if state.spade_require_all and budget > 0:
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
            if profile.type is not FactionType.ALCHEMISTS:
                return "Only the Alchemists may trade victory points for coins."
            if owner.victory_points <= 0:
                return "You have no victory point to trade."
            return "That trade is not legal now."
        if isinstance(action, TradeCoinsForVp):
            if profile.type is not FactionType.ALCHEMISTS:
                return "Only the Alchemists may trade coins for victory points."
            if owner.resources.coins < 2:
                return "You need 2 coins for that trade."
            return "That trade is not legal now."
        if isinstance(action, SkipCultSpade):
            return "Skipping is always legal."
        return "Spend a spade or skip."
    if state.phase == "stronghold_convert":
        owner = state.players[player]
        supply = _priest_capacity(state, player) - owner.resources.priests
        maximum = max(0, min(3, owner.resources.workers, supply))
        if isinstance(action, ChooseStrongholdPriests) and (
            action.workers < 0 or action.workers > maximum
        ):
            return "Trade at most three workers for priests."
        return "Choose how many workers to trade."
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
        total = _add_costs(
            spade_cost(profile, owner.digging, spades),
            building_cost(
                profile,
                BuildingType.DWELLING,
                bool(state.board.adjacent_opponents(action.position, player)),
            ),
        )
        if reach > 0 and not _adjacent_to_own(state.board, player, action.position):
            total = _add_costs(
                total, effective_reach_cost(state.board, player, profile)
            )
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
            transform_cost = _add_costs(
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
        if owner.resources.priests <= 0:
            return "You have no priest to send."
        if (action.cult, action.order) in state.used_orders:
            return "That order space is already occupied."
        return "You cannot send a priest there now."
    if isinstance(action, AdvanceCult):
        if owner.resources.priests <= 0:
            return "You have no priest to send."
        if owner.cult(action.cult) >= _cult_limit_for(state, player, action.cult):
            return "That cult track cannot advance further."
        return "You cannot advance that cult now."
    if isinstance(action, PowerAction):
        if action.kind in state.used_power_actions:
            return "That power action was already used this round."
        if not can_spend_power(owner.resources, POWER_ACTION_COSTS[action.kind]):
            return "You do not have enough power to burn."
        return "That power action is not legal now."
    if isinstance(action, TradeVpForCoin):
        if profile.type is not FactionType.ALCHEMISTS:
            return "Only the Alchemists may trade victory points for coins."
        if owner.victory_points <= 0:
            return "You have no victory point to trade."
        return "That trade is not legal now."
    if isinstance(action, TradeCoinsForVp):
        if profile.type is not FactionType.ALCHEMISTS:
            return "Only the Alchemists may trade coins for victory points."
        if owner.resources.coins < 2:
            return "You need 2 coins for that trade."
        return "That trade is not legal now."
    if isinstance(action, Pass):
        return "Passing is always legal."
    return "That action is not legal now."


def _round_scoring(state: TerraMysticaState) -> ScoringAction:
    return _round_tile(state).action


def _cult_top_occupied(state: TerraMysticaState, player: PlayerId, cult: Cult) -> bool:
    return any(
        other != player and state.players[other].cult(cult) >= 10
        for other in seats(len(state.players))
    )


def _cult_limit_for(state: TerraMysticaState, player: PlayerId, cult: Cult) -> int:
    return cult_limit(state.players[player], _cult_top_occupied(state, player, cult))


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


def _stronghold_reward(
    state: TerraMysticaState,
    player: PlayerId,
    events: list[Event],
) -> tuple[TerraMysticaState, list[Event]]:
    """Apply a faction's one-time stronghold reward."""
    owner = state.players[player]
    profile = owner.profile
    if profile.type is FactionType.CULTISTS:
        owner = replace(owner, victory_points=owner.victory_points + 7)
        events.append(
            Event(
                "stronghold_reward",
                f"{seat_label(player)} scored 7 points from the stronghold.",
                {"player": player, "victory_points": 7},
            )
        )
    elif profile.type is FactionType.ALCHEMISTS:
        owner = replace(owner, resources=gain_power(owner.resources, 12))
        events.append(
            Event(
                "stronghold_reward",
                f"{seat_label(player)} gained 12 power from the stronghold.",
                {"player": player, "power": 12},
            )
        )
    elif profile.type is FactionType.MERMAIDS:
        if owner.shipping < profile.shipping_max:
            level = owner.shipping + 1
            owner = replace(
                owner,
                shipping=level,
                victory_points=owner.victory_points
                + shipping_points(level, profile.shipping_start),
            )
            events.append(
                Event(
                    "stronghold_reward",
                    f"{seat_label(player)} advanced to shipping {level} "
                    "and scored its points.",
                    {"player": player, "shipping": level},
                )
            )
        else:
            events.append(
                Event(
                    "stronghold_reward",
                    f"{seat_label(player)} is already at maximum shipping.",
                    {"player": player, "shipping": owner.shipping},
                )
            )
    elif profile.type is FactionType.HALFLINGS:
        owner = replace(
            owner,
            victory_points=owner.victory_points + 3 * profile.spade_vp_bonus,
        )
        state = replace_player(state, player, owner)
        state = replace(
            state,
            phase="cult_spades",
            cult_spades=replace_at(state.cult_spades, player, 3),
            spade_return="action",
            spade_actor=player,
            spade_second=None,
            spade_topup=False,
            spade_require_all=True,
            active_player=player,
        )
        events.append(
            Event(
                "stronghold_reward",
                f"{seat_label(player)} gained 3 spades from the stronghold.",
                {"player": player, "spades": 3},
            )
        )
        return state, events
    elif profile.type is FactionType.DARKLINGS:
        state = replace(state, phase="stronghold_convert", active_player=player)
        events.append(
            Event(
                "stronghold_reward",
                f"{seat_label(player)} may trade up to three workers for priests.",
                {"player": player},
            )
        )
        return state, events
    state = replace_player(state, player, owner)
    return state, events


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
    resources = _add_income(resources, Income(workers=profile.town_workers_bonus))
    if _round_scoring(state) is ScoringAction.TOWN:
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


def _add_costs(first: Cost, second: Cost) -> Cost:
    return Cost(
        coins=first.coins + second.coins,
        workers=first.workers + second.workers,
        priests=first.priests + second.priests,
        power=first.power + second.power,
    )


def _add_income(resources: Resources, income: Income) -> Resources:
    return add_resources(resources, income)


def _next_unpassed(state: TerraMysticaState, player: PlayerId) -> PlayerId:
    index = state.order.index(player)
    for offset in range(1, len(state.order) + 1):
        candidate = state.order[(index + offset) % len(state.order)]
        if candidate not in state.passed:
            return candidate
    return player
