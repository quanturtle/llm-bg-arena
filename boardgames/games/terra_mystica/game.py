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
    SCORING_TILES,
    SCORING_VALUES,
    STANDARD_DWELLING_INCOME,
    STANDARD_TEMPLE_INCOME,
    STANDARD_TRADING_HOUSE_INCOME,
    TERRAIN_WHEEL,
    BuildingType,
    Cost,
    Cult,
    CultBonus,
    FactionType,
    Income,
    Resources,
    ScoringAction,
    ScoringTile,
)
from boardgames.games.terra_mystica.model import (
    Action,
    AdvanceCult,
    AdvanceDigging,
    AdvanceShipping,
    Board,
    BuildDwelling,
    Building,
    Hex,
    Pass,
    PlayerState,
    PowerAction,
    SendPriest,
    SkipCultSpade,
    TerraMysticaConfig,
    TerraMysticaState,
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
    cult_limit,
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
        scoring_order, rng = rng.shuffled(SCORING_TILES)
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
            used_orders=frozenset(),
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
                    "bonuses": [_bonus_json(tile.bonus) for tile in scoring],
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
        decision = next(
            (item for item in self.pending_decisions(state) if item.player == player),
            None,
        )
        if decision is None:
            raise IllegalActionError(
                f"{seat_label(player)} has no open decision in phase {state.phase!r}"
            )
        space = self.legal_actions(state, decision)
        try:
            is_legal = space.is_legal(action)
        except (TypeError, ValueError, AttributeError) as error:
            raise IllegalActionError(
                f"{seat_label(player)} proposed an unknown action: {error}"
            ) from error
        if not is_legal:
            try:
                reason = space.explain(action)
            except (TypeError, ValueError, IndexError, AttributeError) as error:
                reason = f"that action is not legal now ({error})"
            raise IllegalActionError(reason)
        return self.apply_legal(state, player, action)

    # Rules ----------------------------------------------------------------

    def apply_legal(
        self, state: TerraMysticaState, player: PlayerId, action: Action
    ) -> Transition[TerraMysticaState]:
        if state.phase == "setup":
            if not isinstance(action, BuildDwelling):
                raise IllegalActionError("place a starting dwelling now")
            return self.place_starting_dwelling(state, player, action.position)
        if state.phase == "cult_spades":
            if isinstance(action, UseCultSpade):
                return self.use_cult_spade(state, player, action.position)
            if isinstance(action, SkipCultSpade):
                return self.skip_cult_spade(state, player)
            raise IllegalActionError("spend a cult-bonus spade or skip now")
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
            return self.build_dwelling(state, player, action.position)
        if isinstance(action, TransformTerrain):
            return self.transform_terrain(state, player, action.position)
        if isinstance(action, UpgradeBuilding):
            return self.upgrade_building(state, player, action.position, action.to)
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
        if isinstance(action, Pass):
            return self.pass_turn(state, player)
        raise IllegalActionError("unknown action")

    def build_dwelling(
        self, state: TerraMysticaState, player: PlayerId, position: Hex
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
        if position not in state.board.reachable_land(player, owner.shipping):
            raise IllegalActionError(
                "the tile must be directly or indirectly adjacent to one of "
                "your structures"
            )
        spades = spades_for(profile, tile.terrain)
        terrain_cost = spade_cost(profile, owner.digging, spades)
        build_cost = building_cost(
            profile,
            BuildingType.DWELLING,
            bool(state.board.adjacent_opponents(position, player)),
        )
        total = _add_costs(terrain_cost, build_cost)
        if not can_pay(owner.resources, total):
            raise IllegalActionError("you cannot pay for that transform and build")
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
        if _round_scoring(state) is ScoringAction.DWELLING:
            victory_points += SCORING_VALUES[ScoringAction.DWELLING]
        board, founded = settle_town(board, position, player)
        keys = owner.keys
        if founded:
            victory_points += 5 + profile.town_vp_bonus
            keys += 1
            resources = _add_income(
                resources, Income(workers=profile.town_workers_bonus)
            )
            if _round_scoring(state) is ScoringAction.TOWN:
                victory_points += SCORING_VALUES[ScoringAction.TOWN]
        owner = replace(
            owner,
            resources=resources,
            victory_points=victory_points,
            keys=keys,
        )
        state = replace_player(state, player, owner)
        state = replace(state, board=board)
        events = [
            Event(
                "built",
                f"{seat_label(player)} built a dwelling at {position.notation()}"
                + (f" after using {spades} spade(s)." if spades else "."),
                {
                    "player": player,
                    "position": position.notation(),
                    "building": "dwelling",
                    "spades": spades,
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
        return self.advance_turn(state, player, tuple(events))

    def transform_terrain(
        self, state: TerraMysticaState, player: PlayerId, position: Hex
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
        if position not in state.board.reachable_land(player, owner.shipping):
            raise IllegalActionError(
                "the tile must be directly or indirectly adjacent to one of "
                "your structures"
            )
        if tile.terrain is profile.home_terrain:
            raise IllegalActionError("that tile is already your home terrain")
        spades = spades_for(profile, tile.terrain)
        cost = spade_cost(profile, owner.digging, spades)
        if not can_pay(owner.resources, cost):
            raise IllegalActionError("you cannot pay for that transformation")
        resources = pay(owner.resources, cost)
        board = state.board.replace_tile(
            position, replace(tile, terrain=profile.home_terrain)
        )
        victory_points = owner.victory_points + spades * profile.spade_vp_bonus
        if _round_scoring(state) is ScoringAction.SPADE:
            victory_points += spades * SCORING_VALUES[ScoringAction.SPADE]
        owner = replace(owner, resources=resources, victory_points=victory_points)
        state = replace_player(state, player, owner)
        state = replace(state, board=board)
        event = Event(
            "transformed",
            f"{seat_label(player)} transformed {position.notation()} into "
            f"{profile.home_terrain.value} with {spades} spade(s).",
            {"player": player, "position": position.notation(), "spades": spades},
        )
        return self.advance_turn(state, player, (event,))

    def upgrade_building(
        self,
        state: TerraMysticaState,
        player: PlayerId,
        position: Hex,
        target: BuildingType,
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
        if target is BuildingType.TRADING_HOUSE and (
            _round_scoring(state) is ScoringAction.TRADING_HOUSE
        ):
            victory_points += SCORING_VALUES[ScoringAction.TRADING_HOUSE]
        if target is BuildingType.STRONGHOLD and (
            _round_scoring(state) is ScoringAction.STRONGHOLD
        ):
            victory_points += SCORING_VALUES[ScoringAction.STRONGHOLD]
        if target is BuildingType.SANCTUARY and (
            _round_scoring(state) is ScoringAction.SANCTUARY
        ):
            victory_points += SCORING_VALUES[ScoringAction.SANCTUARY]
        board, founded = settle_town(board, position, player)
        keys = owner.keys
        if founded:
            victory_points += 5 + profile.town_vp_bonus
            keys += 1
            resources = _add_income(
                resources, Income(workers=profile.town_workers_bonus)
            )
            if _round_scoring(state) is ScoringAction.TOWN:
                victory_points += SCORING_VALUES[ScoringAction.TOWN]
        owner = replace(
            owner,
            resources=resources,
            victory_points=victory_points,
            keys=keys,
        )
        state = replace_player(state, player, owner)
        state = replace(state, board=board)
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
        return self.advance_turn(state, player, tuple(events))

    def advance_shipping(
        self, state: TerraMysticaState, player: PlayerId
    ) -> Transition[TerraMysticaState]:
        owner = state.players[player]
        cost = shipping_cost()
        if not can_pay(owner.resources, cost):
            raise IllegalActionError("you cannot pay for a shipping step")
        owner = replace(
            owner,
            resources=pay(owner.resources, cost),
            shipping=owner.shipping + 1,
            victory_points=owner.victory_points + shipping_points(owner.shipping + 1),
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
        if not can_pay(owner.resources, cost):
            raise IllegalActionError("you cannot pay for a digging step")
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
        if owner.cult(cult) >= _cult_limit_for(state, player, cult):
            raise IllegalActionError("that cult track cannot advance further")
        resources = replace(owner.resources, priests=owner.resources.priests - 1)
        owner = replace(owner, resources=resources)
        state = replace(state, used_orders=state.used_orders | {(cult, order)})
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

    def take_power_action(
        self, state: TerraMysticaState, player: PlayerId, kind: str
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
        resources = _add_income(spent, POWER_ACTION_INCOME[kind])
        owner = replace(owner, resources=resources)
        state = replace_player(state, player, owner)
        state = replace(state, used_power_actions=state.used_power_actions | {kind})
        event = Event(
            "power_action",
            f"{seat_label(player)} spent {cost} power for {kind}.",
            {"player": player, "kind": kind, "cost": cost},
        )
        return self.advance_turn(state, player, (event,))

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
        self, state: TerraMysticaState, player: PlayerId, position: Hex
    ) -> Transition[TerraMysticaState]:
        owner = state.players[player]
        tile = state.board.tile(position)
        budget = state.cult_spades[player]
        if tile is None or not tile.is_land or tile.building is not None:
            raise IllegalActionError("choose an empty land tile")
        if tile.terrain is owner.home_terrain:
            raise IllegalActionError("that tile is already your home terrain")
        if position not in state.board.reachable_land(player, owner.shipping):
            raise IllegalActionError("that tile is not reachable")
        cost = spades_for(owner.profile, tile.terrain)
        if cost > budget:
            raise IllegalActionError("you do not have enough cult-bonus spades")
        board = state.board.replace_tile(
            position, replace(tile, terrain=owner.home_terrain)
        )
        state = replace(
            state,
            board=board,
            cult_spades=replace_at(state.cult_spades, player, budget - cost),
        )
        event = Event(
            "cult_spade_used",
            f"{seat_label(player)} used {cost} cult-bonus spade(s) at "
            f"{position.notation()}.",
            {
                "player": player,
                "position": position.notation(),
                "spades": cost,
                "remaining": budget - cost,
            },
        )
        return self._advance_cult_spades(state, (event,))

    def skip_cult_spade(
        self, state: TerraMysticaState, player: PlayerId
    ) -> Transition[TerraMysticaState]:
        remaining = state.cult_spades[player]
        state = replace(state, cult_spades=replace_at(state.cult_spades, player, 0))
        event = Event(
            "cult_spade_skipped",
            f"{seat_label(player)} skipped {remaining} cult-bonus spade(s).",
            {"player": player, "spades": remaining},
        )
        return self._advance_cult_spades(state, (event,))

    def _advance_cult_spades(
        self, state: TerraMysticaState, events: tuple[Event, ...]
    ) -> Transition[TerraMysticaState]:
        next_player = _next_cult_spade_player(state)
        if next_player is None:
            return _start_next_round(state, events)
        return Transition(replace(state, active_player=next_player), events)

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


def initial_setup_queue(
    order: tuple[PlayerId, ...], players: tuple[PlayerState, ...]
) -> tuple[PlayerId, ...]:
    """Clockwise first placements, counterclockwise second, then Nomads and CM."""
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
    )
    events: list[Event] = [
        Event(
            "round_started",
            f"Round {round_number}: {tile.action.value} scores; "
            f"cult bonus {_bonus_text(tile.bonus)}.",
            {
                "round": round_number,
                "scoring": tile.action.value,
                "bonus": _bonus_json(tile.bonus),
            },
        )
    ]
    for seat in state.order:
        owner = state.players[seat]
        income = income_for(state.board, seat, owner)
        resources = income_with_power(owner.resources, income)
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
        state = replace(state, phase="cult_spades", cult_spades=budgets)
        next_player = _next_cult_spade_player(state)
        if next_player is None:
            return _start_next_round(state, events)
        event = Event(
            "cult_bonus",
            f"{seat_label(next_player)} may use {budgets[next_player]} "
            f"cult-bonus spade(s).",
            {
                "player": next_player,
                "cult": bonus.cult.value,
                "reward": bonus.reward,
                "amount": budgets[next_player],
            },
        )
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
        resources = _add_income(owner.resources, Income(priests=amount))
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


def _next_cult_spade_player(state: TerraMysticaState) -> PlayerId | None:
    return next((seat for seat in state.order if state.cult_spades[seat] > 0), None)


def _cult_spade_actions(state: TerraMysticaState, player: PlayerId) -> list[Action]:
    owner = state.players[player]
    budget = state.cult_spades[player]
    reachable = set(state.board.reachable_land(player, owner.shipping))
    actions: list[Action] = []
    for tile in state.board.tiles:
        if not tile.is_land or tile.building is not None:
            continue
        if tile.terrain is owner.home_terrain:
            continue
        if tile.position not in reachable:
            continue
        if spades_for(owner.profile, tile.terrain) <= budget:
            actions.append(UseCultSpade(tile.position))
    actions.append(SkipCultSpade())
    return actions


def _round_tile(state: TerraMysticaState) -> ScoringTile:
    return state.scoring[state.round - 1]


def _bonus_json(bonus: CultBonus) -> dict[str, JsonValue]:
    return {
        "cult": bonus.cult.value,
        "per": bonus.per,
        "reward": bonus.reward,
        "amount": bonus.amount,
    }


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
    reachable = set(state.board.reachable_land(player, owner.shipping))
    can_build_dwelling = can_place_building(state.board, player, BuildingType.DWELLING)

    if can_build_dwelling:
        for tile in state.board.tiles:
            if not tile.is_land or tile.building is not None:
                continue
            if tile.position not in reachable:
                continue
            spades = spades_for(profile, tile.terrain)
            terrain_cost = spade_cost(profile, owner.digging, spades)
            build_cost = building_cost(
                profile,
                BuildingType.DWELLING,
                bool(state.board.adjacent_opponents(tile.position, player)),
            )
            if can_pay(resources, _add_costs(terrain_cost, build_cost)):
                actions.append(BuildDwelling(tile.position))

    for tile in state.board.tiles:
        if not tile.is_land or tile.building is not None:
            continue
        if tile.position not in reachable:
            continue
        if tile.terrain is profile.home_terrain:
            continue
        spades = spades_for(profile, tile.terrain)
        if can_pay(resources, spade_cost(profile, owner.digging, spades)):
            actions.append(TransformTerrain(tile.position))

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
                actions.append(UpgradeBuilding(position, BuildingType.TRADING_HOUSE))
        if (
            building.type is BuildingType.TRADING_HOUSE
            and can_place_building(state.board, player, BuildingType.TEMPLE)
            and can_pay(resources, profile.costs.temple)
        ):
            actions.append(UpgradeBuilding(position, BuildingType.TEMPLE))
        if (
            building.type is BuildingType.TRADING_HOUSE
            and can_place_building(state.board, player, BuildingType.STRONGHOLD)
            and can_pay(resources, profile.costs.stronghold)
        ):
            actions.append(UpgradeBuilding(position, BuildingType.STRONGHOLD))
        if (
            building.type is BuildingType.TEMPLE
            and can_place_building(state.board, player, BuildingType.SANCTUARY)
            and can_pay(resources, profile.costs.sanctuary)
        ):
            actions.append(UpgradeBuilding(position, BuildingType.SANCTUARY))

    if (
        profile.can_ship
        and owner.shipping < profile.shipping_max
        and can_pay(resources, shipping_cost())
    ):
        actions.append(AdvanceShipping())
    if (
        profile.can_dig
        and owner.digging < profile.digging_max
        and can_pay(resources, profile.digging_cost)
    ):
        actions.append(AdvanceDigging())

    if owner.resources.priests > 0:
        for cult in CULT_ORDER:
            if owner.cult(cult) >= _cult_limit_for(state, player, cult):
                continue
            for order in range(4):
                if (cult, order) not in state.used_orders:
                    actions.append(SendPriest(cult, order))
            actions.append(AdvanceCult(cult))

    for kind in ("priest", "workers", "coins"):
        if kind in state.used_power_actions:
            continue
        if can_spend_power(owner.resources, POWER_ACTION_COSTS[kind]):
            actions.append(PowerAction(kind))

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
        if isinstance(action, UseCultSpade):
            tile = state.board.tile(action.position)
            if tile is None or not tile.is_land or tile.building is not None:
                return "There is no empty land tile there."
            if tile.terrain is owner.home_terrain:
                return "That tile is already your home terrain."
            if action.position not in state.board.reachable_land(
                player, owner.shipping
            ):
                return "That tile is not reachable."
            if spades_for(owner.profile, tile.terrain) > state.cult_spades[player]:
                return "You do not have enough cult-bonus spades."
            return "That cult-bonus spade cannot be used there now."
        if isinstance(action, SkipCultSpade):
            return "Skipping is always legal."
        return "Spend a cult-bonus spade or skip."
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
        if action.position not in state.board.reachable_land(player, owner.shipping):
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
        if not can_pay(owner.resources, total):
            return "You cannot pay for that transform and build."
        return "That dwelling cannot be built now."
    if isinstance(action, TransformTerrain):
        tile = state.board.tile(action.position)
        if tile is None:
            return "There is no tile there."
        if not tile.is_land:
            return "You cannot transform a river."
        if tile.building is not None:
            return "That tile is occupied."
        if tile.terrain is profile.home_terrain:
            return "That tile is already your home terrain."
        if action.position not in state.board.reachable_land(player, owner.shipping):
            return (
                "The tile must be directly or indirectly adjacent to one of "
                "your structures."
            )
        spades = spades_for(profile, tile.terrain)
        if not can_pay(owner.resources, spade_cost(profile, owner.digging, spades)):
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
        cost = building_cost(
            profile,
            action.to,
            bool(state.board.adjacent_opponents(action.position, player)),
        )
        if not can_pay(owner.resources, cost):
            return "You cannot afford that upgrade."
        return "That upgrade is not legal now."
    if isinstance(action, AdvanceShipping):
        if not profile.can_ship:
            return "Your faction has no shipping track."
        if owner.shipping >= profile.shipping_max:
            return "Your shipping track is already at its maximum."
        if not can_pay(owner.resources, shipping_cost()):
            return "Shipping costs 1 priest and 4 coins."
        return "You cannot advance shipping now."
    if isinstance(action, AdvanceDigging):
        if not profile.can_dig:
            return "Your faction cannot improve its digging."
        if owner.digging >= profile.digging_max:
            return "Your digging track is already at its maximum."
        if not can_pay(owner.resources, profile.digging_cost):
            return "You cannot pay for a digging step."
        return "You cannot advance digging now."
    if isinstance(action, SendPriest):
        if owner.resources.priests <= 0:
            return "You have no priest to send."
        if (action.cult, action.order) in state.used_orders:
            return "That order space is already occupied."
        if owner.cult(action.cult) >= _cult_limit_for(state, player, action.cult):
            return "That cult track cannot advance further."
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


def _valid_upgrade(source: BuildingType, target: BuildingType) -> bool:
    return (
        (source is BuildingType.DWELLING and target is BuildingType.TRADING_HOUSE)
        or (
            source is BuildingType.TRADING_HOUSE
            and target in (BuildingType.TEMPLE, BuildingType.STRONGHOLD)
        )
        or (source is BuildingType.TEMPLE and target is BuildingType.SANCTUARY)
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
