"""Puerto Rico: the standard base game for 3, 4 or 5 players.

The game follows the role-selection cycle. Each round the players take turns
choosing an unchosen role; the role's action phase runs immediately, starting
with the player who chose it. Unchosen roles gain a doubloon at round end.
"""

from collections.abc import Iterable
from dataclasses import replace
from functools import partial
from importlib.resources import files
from typing import ClassVar, cast

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
)
from boardgames.core.records import (
    dataclass_from_json,
    tagged_json_object,
    to_json_object,
)
from boardgames.games.puerto_rico.constants import (
    BUILDINGS,
    COLONIST_SUPPLY,
    GOOD_SUPPLY,
    GOODS,
    MAX_CITY_SPACES,
    MAX_ISLAND_SPACES,
    PLANTATION_TILES,
    QUARRY_SUPPLY,
    ROLES_BY_PLAYERS,
    SHIP_CAPACITIES,
    STARTING_DOUBLOONS,
    TRADING_HOUSE_SPACES,
    VICTORY_POINT_SUPPLY,
    Good,
    Role,
)
from boardgames.games.puerto_rico.model import (
    Action,
    Build,
    CargoShip,
    DiscardGoods,
    FinishPlacement,
    Goods,
    LoadShip,
    LoadWharf,
    OwnedBuilding,
    Pass,
    PickUpColonist,
    PlaceColonist,
    Plantation,
    PlayerState,
    ProducePrivilege,
    PuertoRicoConfig,
    PuertoRicoState,
    RoleState,
    SelectRole,
    Sell,
    TakePlantation,
    TakeQuarry,
    UseHacienda,
    available_to_build,
    build_cost,
    can_load_anything,
    can_ship,
    city_spaces_used,
    end_game_bonus,
    factory_bonus,
    goods_add,
    goods_from_list,
    goods_get,
    goods_minus,
    goods_plus,
    goods_remove,
    goods_set,
    goods_total,
    island_spaces_used,
    next_player_in_order,
    next_role_picker,
    next_unacted,
    owns_active,
    production,
    public_points,
    replace_at,
    replace_player,
    replace_role,
    role_chooser,
    role_state,
    sell_price,
    ship_victory_points,
    total_points,
    wharf_goods,
)
from boardgames.games.puerto_rico.notation import format_action, parse_action

ROLE_PHASE: dict[Role, str] = {
    "settler": "settler_action",
    "mayor": "mayor_action",
    "builder": "builder_action",
    "craftsman": "craftsman_action",
    "trader": "trader_action",
    "captain": "captain_action",
    "prospector": "role_selection",
    "prospector_2": "role_selection",
}


@register_game
class PuertoRico(Game[PuertoRicoState, Action, PuertoRicoConfig]):
    """Puerto Rico with all base-game roles, buildings and end-game bonuses."""

    id: ClassVar[str] = "puerto_rico"

    # Config ---------------------------------------------------------------

    def parse_config(self, raw: JsonObject) -> PuertoRicoConfig:
        config = dataclass_from_json(PuertoRicoConfig, raw)
        check_config(config)
        return config

    def config_json(self, config: PuertoRicoConfig) -> dict[str, JsonValue]:
        return to_json_object(config)

    # Setup ----------------------------------------------------------------

    def setup(self, config: PuertoRicoConfig, seed: int) -> Transition[PuertoRicoState]:
        rng = Rng.seeded(seed)
        n = config.num_players
        governor_index, rng = rng.below(n)
        order = tuple(PlayerId((governor_index + i) % n) for i in range(n))
        governor = order[0]
        roles = tuple(RoleState(role) for role in ROLES_BY_PLAYERS[n])
        starting = starting_plantations(n)
        players_list: list[PlayerState | None] = [None] * n
        for order_index, seat in enumerate(order):
            players_list[seat] = PlayerState(
                doubloons=STARTING_DOUBLOONS[n],
                plantations=(Plantation(starting[order_index]),),
            )
        players = tuple(player for player in players_list if player is not None)
        deck_counts = dict(PLANTATION_TILES)
        for good in starting:
            deck_counts[good] -= 1
        deck_list = [good for good, count in deck_counts.items() for _ in range(count)]
        shuffled, rng = rng.shuffled(deck_list)
        face_up_count = n + 1
        face_up = tuple(shuffled[:face_up_count])
        plantation_deck = tuple(shuffled[face_up_count:])
        available = tuple(
            name for name, spec in BUILDINGS.items() for _ in range(spec.copies)
        )
        ships = tuple(CargoShip(capacity) for capacity in SHIP_CAPACITIES[n])
        vp_supply = (
            config.victory_point_supply
            if config.victory_point_supply > 0
            else VICTORY_POINT_SUPPLY[n]
        )
        state = PuertoRicoState(
            config=config,
            rng=rng,
            round=1,
            governor=governor,
            order=order,
            phase="role_selection",
            active_role=None,
            active_player=governor,
            roles=roles,
            players=players,
            colonist_ship=n,
            colonist_supply=COLONIST_SUPPLY[n],
            trading_house=(),
            cargo_ships=ships,
            face_up=face_up,
            plantation_deck=plantation_deck,
            available_buildings=available,
            quarry_supply=QUARRY_SUPPLY,
            goods_supply=GOOD_SUPPLY,
            vp_supply=vp_supply,
            players_acted=frozenset(),
            captain_passes=0,
            end_reason=None,
            winner=None,
        )
        events = (
            Event(
                "game_started",
                f"Puerto Rico: {n} players, {seat_label(governor)} is governor.",
                {"num_players": n, "governor": governor},
            ),
            Event(
                "role_selection",
                f"{seat_label(governor)} chooses the first role.",
                {"player": governor},
            ),
        )
        return Transition(state, events)

    # Decisions ------------------------------------------------------------

    def pending_decisions(self, state: PuertoRicoState) -> tuple[Decision, ...]:
        if state.phase == "game_over":
            return ()
        return (
            Decision(
                state.active_player,
                decision_kind(state.phase),
                decision_prompt(state),
            ),
        )

    def legal_actions(
        self, state: PuertoRicoState, decision: Decision
    ) -> ActionSpace[Action]:
        actions = legal_action_list(state, decision.player)
        default = default_action(state, actions)
        return FlatActionSpace(
            actions,
            format_action,
            explain=partial(explain_illegal, state, decision.player),
            default=default,
        )

    def apply(
        self, state: PuertoRicoState, player: PlayerId, action: Action
    ) -> Transition[PuertoRicoState]:
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

    def apply_legal(
        self, state: PuertoRicoState, player: PlayerId, action: Action
    ) -> Transition[PuertoRicoState]:
        """Apply an action already checked by `legal_actions`."""
        if state.phase == "role_selection":
            if not isinstance(action, SelectRole):
                raise IllegalActionError("choose a role now")
            return self.take_role(state, player, action.role)
        if state.phase == "settler_action":
            return self.apply_settler(state, player, action)
        if state.phase == "mayor_action":
            return self.apply_mayor(state, player, action)
        if state.phase == "builder_action":
            return self.apply_builder(state, player, action)
        if state.phase == "craftsman_action":
            return self.apply_craftsman(state, player, action)
        if state.phase == "trader_action":
            return self.apply_trader(state, player, action)
        if state.phase == "captain_action":
            return self.apply_captain(state, player, action)
        if state.phase == "captain_discard":
            return self.apply_discard(state, player, action)
        raise IllegalActionError(f"no action is legal in phase {state.phase!r}")

    def is_terminal(self, state: PuertoRicoState) -> bool:
        return state.phase == "game_over"

    def scores(self, state: PuertoRicoState) -> Scores:
        points: dict[PlayerId, float] = {}
        breakdown: dict[PlayerId, dict[str, float]] = {}
        for seat in range(state.config.num_players):
            player = state.players[seat]
            player_id = PlayerId(seat)
            base = total_points(player)
            points[player_id] = base
            breakdown[player_id] = {
                "vp_chips": player.vp_chips,
                "buildings": sum(
                    BUILDINGS[building.name].victory_points
                    for building in player.buildings
                ),
                "bonus": end_game_bonus(player),
            }
        return Scores(points, breakdown)

    def public_scores(self, state: PuertoRicoState) -> Scores:
        """VP chips stay hidden until the game ends and reveals them."""
        if self.is_terminal(state):
            return self.scores(state)
        return Scores(
            {
                PlayerId(seat): float(public_points(player))
                for seat, player in enumerate(state.players)
            }
        )

    def observe(self, state: PuertoRicoState, viewer: PlayerId | None) -> Observation:
        from boardgames.games.puerto_rico.view import observe

        return observe(state, viewer)

    def render_text(self, observation: Observation) -> str:
        from boardgames.games.puerto_rico.view import render_text

        return render_text(observation)

    def rules_text(self) -> str:
        rules = files("boardgames.games.puerto_rico") / "rules.md"
        return rules.read_text(encoding="utf-8")

    def format_action(self, action: Action) -> str:
        return format_action(action)

    def parse_action(self, text: str) -> Action:
        return parse_action(text)

    def describe_action(self, observation: Observation, action: Action) -> str:
        from boardgames.games.puerto_rico.view import describe_action

        return describe_action(observation, action)

    def action_json(self, action: Action) -> dict[str, JsonValue]:
        return tagged_json_object(action)

    # Role selection -------------------------------------------------------

    def take_role(
        self, state: PuertoRicoState, player: PlayerId, role: Role
    ) -> Transition[PuertoRicoState]:
        role_entry = role_state(state, role)
        if role_entry.taken_by is not None:
            raise IllegalActionError(f"{role} has already been chosen this round")
        if player != state.active_player:
            raise IllegalActionError(f"it is not {seat_label(player)}'s turn")
        owner = state.players[player]
        owner = replace(owner, doubloons=owner.doubloons + role_entry.doubloons)
        state = replace_player(state, player, owner)
        state = replace_role(
            state, role, replace(role_entry, doubloons=0, taken_by=player)
        )
        events = [
            Event(
                "role_taken",
                f"{seat_label(player)} chose {role} "
                f"(+{role_entry.doubloons} doubloons).",
                {
                    "player": player,
                    "role": role,
                    "doubloons": role_entry.doubloons,
                },
            )
        ]
        if role in ("prospector", "prospector_2"):
            owner = replace(
                state.players[player], doubloons=state.players[player].doubloons + 1
            )
            state = replace_player(state, player, owner)
            events.append(
                Event(
                    "prospector_bonus",
                    f"{seat_label(player)} took a prospector: +1 doubloon.",
                    {"player": player, "doubloons": 1},
                )
            )
            state = self.advance_role_picker(state)
            return Transition(state, tuple(events))
        state, phase_events = self.start_role_phase(state, role, player)
        events.extend(phase_events)
        return Transition(state, tuple(events))

    def start_role_phase(
        self, state: PuertoRicoState, role: Role, player: PlayerId
    ) -> tuple[PuertoRicoState, tuple[Event, ...]]:
        phase = ROLE_PHASE[role]
        state = replace(
            state,
            active_role=role,
            phase=phase,  # type: ignore[arg-type]
            active_player=player,
            players_acted=frozenset(),
            captain_passes=0,
        )
        events: list[Event] = []
        if role == "settler":
            state = replace(
                state,
                players=tuple(
                    replace(item, hacienda_used=False) for item in state.players
                ),
            )
        elif role == "mayor":
            state = distribute_colonists(state, player)
            events.append(
                Event(
                    "colonists_distributed",
                    "Colonists from the ship are distributed; "
                    f"{seat_label(player)} takes the extra colonist.",
                    {"player": player},
                )
            )
        elif role == "craftsman":
            state, produced_events = run_production(state)
            events.extend(produced_events)
        elif role == "captain":
            state = replace(
                state,
                players=tuple(
                    replace(
                        item,
                        captain_first_load_done=False,
                        wharf_used=False,
                    )
                    for item in state.players
                ),
            )
        return state, tuple(events)

    # Settler --------------------------------------------------------------

    def apply_settler(
        self, state: PuertoRicoState, player: PlayerId, action: Action
    ) -> Transition[PuertoRicoState]:
        owner = state.players[player]
        if isinstance(action, UseHacienda):
            good = state.plantation_deck[0]
            state = replace(
                state,
                plantation_deck=state.plantation_deck[1:],
            )
            state = replace_player(
                state,
                player,
                replace(
                    owner,
                    plantations=(*owner.plantations, Plantation(good)),
                    hacienda_used=True,
                ),
            )
            event = Event(
                "hacienda_plantation",
                f"{seat_label(player)} drew a {good} plantation.",
                {"player": player, "good": good},
            )
            return Transition(state, (event,))
        if isinstance(action, TakePlantation):
            face_up = list(state.face_up)
            face_up.remove(action.good)
            colonized = False
            if owns_active(owner, "hospice") and state.colonist_supply > 0:
                colonized = True
                state = replace(state, colonist_supply=state.colonist_supply - 1)
            state = replace_player(
                state,
                player,
                replace(
                    owner,
                    plantations=(
                        *owner.plantations,
                        Plantation(action.good, colonized),
                    ),
                ),
            )
            state = replace(state, face_up=tuple(face_up))
            event = Event(
                "plantation_taken",
                f"{seat_label(player)} took a {action.good} plantation"
                + (" and colonized it with the Hospice." if colonized else "."),
                {
                    "player": player,
                    "good": action.good,
                    "colonized": colonized,
                },
            )
            state = self.mark_acted(state, player)
            return Transition(state, (event,))
        if isinstance(action, TakeQuarry):
            state = replace_player(
                state, player, replace(owner, quarries=owner.quarries + 1)
            )
            state = replace(state, quarry_supply=state.quarry_supply - 1)
            event = Event(
                "quarry_taken",
                f"{seat_label(player)} took a quarry.",
                {"player": player},
            )
            state = self.mark_acted(state, player)
            return Transition(state, (event,))
        if isinstance(action, Pass):
            state = self.mark_acted(state, player)
            event = Event(
                "settler_passed",
                f"{seat_label(player)} took no plantation.",
                {"player": player},
            )
            return Transition(state, (event,))
        raise IllegalActionError("only plantation, quarry or pass actions are legal")

    # Mayor ----------------------------------------------------------------

    def apply_mayor(
        self, state: PuertoRicoState, player: PlayerId, action: Action
    ) -> Transition[PuertoRicoState]:
        owner = state.players[player]
        if isinstance(action, PlaceColonist):
            owner = place_colonist(owner, action)
            state = replace_player(state, player, owner)
            event = Event(
                "colonist_placed",
                f"{seat_label(player)} placed a colonist on {colonist_target(action)}.",
                {"player": player, "target": action.target, "index": action.index},
            )
            return Transition(state, (event,))
        if isinstance(action, PickUpColonist):
            owner = pick_up_colonist(owner, action)
            state = replace_player(state, player, owner)
            event = Event(
                "colonist_picked_up",
                f"{seat_label(player)} picked up a colonist from "
                f"{colonist_target(action)}.",
                {"player": player, "target": action.target, "index": action.index},
            )
            return Transition(state, (event,))
        if isinstance(action, FinishPlacement):
            state = self.mark_acted(state, player)
            event = Event(
                "mayor_finished",
                f"{seat_label(player)} finished placing colonists.",
                {"player": player},
            )
            return Transition(state, (event,))
        raise IllegalActionError(
            "only colonist placements, pickups or finish are legal"
        )

    # Builder --------------------------------------------------------------

    def apply_builder(
        self, state: PuertoRicoState, player: PlayerId, action: Action
    ) -> Transition[PuertoRicoState]:
        if isinstance(action, Build):
            name = action.building
            cost = build_cost(state, player, name)
            owner = state.players[player]
            state = replace_player(
                state,
                player,
                replace(
                    owner,
                    doubloons=owner.doubloons - cost,
                    buildings=(*owner.buildings, OwnedBuilding(name)),
                ),
            )
            available = list(state.available_buildings)
            available.remove(name)
            state = replace(state, available_buildings=tuple(available))
            events = [
                Event(
                    "building_built",
                    f"{seat_label(player)} built {name} for {cost} doubloons.",
                    {"player": player, "building": name, "cost": cost},
                )
            ]
            if (
                owns_active(owner, "university")
                and state.colonist_supply > 0
                and BUILDINGS[name].max_colonists > 0
            ):
                new_buildings = list(state.players[player].buildings)
                index = len(new_buildings) - 1
                new_buildings[index] = replace(new_buildings[index], colonists=1)
                state = replace_player(
                    state,
                    player,
                    replace(state.players[player], buildings=tuple(new_buildings)),
                )
                state = replace(state, colonist_supply=state.colonist_supply - 1)
                events.append(
                    Event(
                        "university_colonist",
                        f"The University placed a colonist on {name}.",
                        {"player": player, "building": name},
                    )
                )
            state = self.mark_acted(state, player)
            return Transition(state, tuple(events))
        if isinstance(action, Pass):
            state = self.mark_acted(state, player)
            event = Event(
                "builder_passed",
                f"{seat_label(player)} built nothing.",
                {"player": player},
            )
            return Transition(state, (event,))
        raise IllegalActionError("only build or pass actions are legal")

    # Craftsman ------------------------------------------------------------

    def apply_craftsman(
        self, state: PuertoRicoState, player: PlayerId, action: Action
    ) -> Transition[PuertoRicoState]:
        events: list[Event] = []
        if isinstance(action, ProducePrivilege):
            good = action.good
            owner = state.players[player]
            state = replace_player(
                state,
                player,
                replace(owner, goods=goods_add(owner.goods, good, 1)),
            )
            state = replace(
                state, goods_supply=goods_remove(state.goods_supply, good, 1)
            )
            events.append(
                Event(
                    "privilege_good",
                    f"{seat_label(player)} took an extra {good}.",
                    {"player": player, "good": good},
                )
            )
        elif isinstance(action, Pass):
            events.append(
                Event(
                    "privilege_declined",
                    f"{seat_label(player)} declined the Craftsman privilege.",
                    {"player": player},
                )
            )
        else:
            raise IllegalActionError("only a privilege good or pass is legal")
        state = self.advance_role_picker(
            replace(
                state,
                active_role=None,
                players_acted=frozenset(),
                captain_passes=0,
            )
        )
        return Transition(state, tuple(events))

    # Trader ---------------------------------------------------------------

    def apply_trader(
        self, state: PuertoRicoState, player: PlayerId, action: Action
    ) -> Transition[PuertoRicoState]:
        owner = state.players[player]
        if isinstance(action, Sell):
            good = action.good
            price = sell_price(state, player, good)
            owner = replace(
                owner,
                doubloons=owner.doubloons + price,
                goods=goods_remove(owner.goods, good, 1),
            )
            state = replace_player(state, player, owner)
            state = replace(state, trading_house=(*state.trading_house, good))
            event = Event(
                "good_sold",
                f"{seat_label(player)} sold a {good} for {price} doubloons.",
                {"player": player, "good": good, "price": price},
            )
            state = self.mark_acted(state, player)
            return Transition(state, (event,))
        if isinstance(action, Pass):
            state = self.mark_acted(state, player)
            event = Event(
                "trader_passed",
                f"{seat_label(player)} sold nothing.",
                {"player": player},
            )
            return Transition(state, (event,))
        raise IllegalActionError("only sell or pass actions are legal")

    # Captain --------------------------------------------------------------

    def apply_captain(
        self, state: PuertoRicoState, player: PlayerId, action: Action
    ) -> Transition[PuertoRicoState]:
        owner = state.players[player]
        if isinstance(action, LoadShip):
            good, ship_index = action.good, action.ship
            ship = state.cargo_ships[ship_index]
            quantity = min(goods_get(owner.goods, good), ship.remaining)
            owner = replace(
                owner,
                goods=goods_remove(owner.goods, good, quantity),
            )
            first_load = False
            if (
                role_chooser(state, "captain") == player
                and not owner.captain_first_load_done
            ):
                first_load = True
                owner = replace(owner, captain_first_load_done=True)
            points = ship_victory_points(state, player, quantity)
            owner = replace(owner, vp_chips=owner.vp_chips + points)
            new_ship = replace(ship, good=good, filled=ship.filled + quantity)
            state = replace_player(state, player, owner)
            state = replace(
                state,
                cargo_ships=replace_at(state.cargo_ships, ship_index, new_ship),
                vp_supply=state.vp_supply - points,
            )
            event = Event(
                "goods_shipped",
                f"{seat_label(player)} shipped {quantity} {good} "
                f"for {points} victory points.",
                {
                    "player": player,
                    "good": good,
                    "quantity": quantity,
                    "ship": ship_index,
                    "points": points,
                    "first_load": first_load,
                },
            )
            state = advance_captain(state, player, loaded=True)
            return Transition(state, (event,))
        if isinstance(action, LoadWharf):
            good = action.good
            quantity = goods_get(owner.goods, good)
            owner = replace(
                owner, goods=goods_set(owner.goods, good, 0), wharf_used=True
            )
            first_load = False
            if (
                role_chooser(state, "captain") == player
                and not owner.captain_first_load_done
            ):
                first_load = True
                owner = replace(owner, captain_first_load_done=True)
            points = ship_victory_points(state, player, quantity)
            owner = replace(owner, vp_chips=owner.vp_chips + points)
            state = replace_player(state, player, owner)
            state = replace(state, vp_supply=state.vp_supply - points)
            event = Event(
                "wharf_shipped",
                f"{seat_label(player)} shipped {quantity} {good} by Wharf "
                f"for {points} victory points.",
                {
                    "player": player,
                    "good": good,
                    "quantity": quantity,
                    "points": points,
                    "first_load": first_load,
                },
            )
            state = advance_captain(state, player, loaded=True)
            return Transition(state, (event,))
        if isinstance(action, Pass):
            state = advance_captain(state, player, loaded=False)
            event = Event(
                "captain_passed",
                f"{seat_label(player)} passed.",
                {"player": player},
            )
            return Transition(state, (event,))
        raise IllegalActionError("only ship, wharf or pass actions are legal")

    # Captain discard ------------------------------------------------------

    def apply_discard(
        self, state: PuertoRicoState, player: PlayerId, action: Action
    ) -> Transition[PuertoRicoState]:
        if not isinstance(action, DiscardGoods):
            raise IllegalActionError("choose goods to keep now")
        owner = state.players[player]
        keep = [0, 0, 0, 0, 0]
        discard = [0, 0, 0, 0, 0]
        for index, good in enumerate(GOODS):
            count = goods_get(owner.goods, good)
            if good in action.protected:
                keep[index] = count
            else:
                keep[index] = min(1, count)
                discard[index] = max(0, count - 1)
        state = replace_player(
            state, player, replace(owner, goods=cast(Goods, tuple(keep)))
        )
        state = replace(
            state,
            goods_supply=goods_plus(state.goods_supply, cast(Goods, tuple(discard))),
        )
        event = Event(
            "goods_discarded",
            f"{seat_label(player)} kept goods after shipping.",
            {
                "player": player,
                "protected": list(action.protected),
                "kept": [count for count in keep],
            },
        )
        state = advance_discard(state, player)
        return Transition(state, (event,))

    # Phase plumbing -------------------------------------------------------

    def mark_acted(self, state: PuertoRicoState, player: PlayerId) -> PuertoRicoState:
        acted = state.players_acted | {player}
        if len(acted) >= len(state.order):
            return finish_standard_phase(replace(state, players_acted=acted))
        next_player = next_unacted(replace(state, players_acted=acted), player)
        return replace(
            state,
            players_acted=acted,
            active_player=(
                next_player if next_player is not None else state.active_player
            ),
        )

    def advance_role_picker(self, state: PuertoRicoState) -> PuertoRicoState:
        next_picker = next_role_picker(state)
        if next_picker is None:
            return end_round(state)
        return replace(
            state,
            phase="role_selection",
            active_role=None,
            active_player=next_picker,
            players_acted=frozenset(),
            captain_passes=0,
        )


# Helpers ------------------------------------------------------------------


def check_config(config: PuertoRicoConfig) -> None:
    """Raise ConfigError for an unplayable table or supply."""
    if not 3 <= config.num_players <= 5:
        raise ConfigError(
            f"Puerto Rico needs 3, 4 or 5 players, got {config.num_players}"
        )
    if config.victory_point_supply < 0:
        raise ConfigError(
            "victory_point_supply must be 0 (standard) or positive, got "
            f"{config.victory_point_supply}"
        )
    if config.max_rounds < 0:
        raise ConfigError(f"max_rounds must be 0 or positive, got {config.max_rounds}")
    return


def starting_plantations(num_players: int) -> tuple[Good, ...]:
    """Starting tile per order position: indigo first, then corn."""
    indigo_count = num_players - (1 if num_players == 3 else 2)
    return tuple(
        "indigo" if index < indigo_count else "corn" for index in range(num_players)
    )


def distribute_colonists(state: PuertoRicoState, picker: PlayerId) -> PuertoRicoState:
    """Round-robin the ship's colonists from the picker; the picker gets +1."""
    n = len(state.order)
    start = state.order.index(picker)
    allocations = [0] * n
    remaining = state.colonist_ship
    index = 0
    while remaining > 0:
        seat = state.order[(start + index) % n]
        allocations[seat] += 1
        remaining -= 1
        index += 1
    players = tuple(
        replace(
            player, colonists_unplaced=player.colonists_unplaced + allocations[seat]
        )
        for seat, player in enumerate(state.players)
    )
    supply = state.colonist_supply
    if supply > 0:
        players = replace_at(
            players,
            picker,
            replace(
                players[picker],
                colonists_unplaced=players[picker].colonists_unplaced + 1,
            ),
        )
        supply -= 1
    return replace(state, players=players, colonist_ship=0, colonist_supply=supply)


def run_production(
    state: PuertoRicoState,
) -> tuple[PuertoRicoState, tuple[Event, ...]]:
    """Every player produces goods in order, limited by the bank."""
    events: list[Event] = []
    for seat in state.order:
        owner = state.players[seat]
        potential = production(owner)
        produced = [0, 0, 0, 0, 0]
        for index, amount in enumerate(potential):
            actual = min(amount, state.goods_supply[index])
            produced[index] = actual
        if any(produced):
            state = replace_player(
                state,
                seat,
                replace(
                    owner, goods=goods_plus(owner.goods, cast(Goods, tuple(produced)))
                ),
            )
            state = replace(
                state,
                goods_supply=goods_minus(
                    state.goods_supply, cast(Goods, tuple(produced))
                ),
            )
            events.append(
                Event(
                    "goods_produced",
                    f"{seat_label(seat)} produced goods.",
                    {"player": seat, "goods": produced},
                )
            )
        bonus = factory_bonus(owner)
        if bonus:
            state = replace_player(
                state,
                seat,
                replace(
                    state.players[seat],
                    doubloons=state.players[seat].doubloons + bonus,
                ),
            )
            events.append(
                Event(
                    "factory_bonus",
                    f"{seat_label(seat)}'s Factory gave {bonus} doubloons.",
                    {"player": seat, "doubloons": bonus},
                )
            )
    return state, tuple(events)


def finish_standard_phase(state: PuertoRicoState) -> PuertoRicoState:
    """Clean up after Settler, Mayor, Builder or Trader, then advance."""
    role = state.active_role
    if role == "settler":
        face_up_count = len(state.order) + 1
        face_up = state.plantation_deck[:face_up_count]
        deck = state.plantation_deck[face_up_count:]
        state = replace(state, face_up=face_up, plantation_deck=deck)
    elif role == "mayor":
        state = refill_colonist_ship(state)
    elif role == "trader":
        if len(state.trading_house) >= TRADING_HOUSE_SPACES:
            supply = goods_plus(
                state.goods_supply, goods_from_list(list(state.trading_house))
            )
            state = replace(state, trading_house=(), goods_supply=supply)
    return _advance_role_picker(state)


def _advance_role_picker(state: PuertoRicoState) -> PuertoRicoState:
    next_picker = next_role_picker(state)
    if next_picker is None:
        return end_round(state)
    return replace(
        state,
        phase="role_selection",
        active_role=None,
        active_player=next_picker,
        players_acted=frozenset(),
        captain_passes=0,
    )


def refill_colonist_ship(state: PuertoRicoState) -> PuertoRicoState:
    """Refill from supply: empty building slots, at least one per player."""
    empty_slots = 0
    for player in state.players:
        for building in player.buildings:
            spec = BUILDINGS[building.name]
            empty_slots += spec.max_colonists - building.colonists
    needed = max(empty_slots, len(state.order))
    refill = min(needed, state.colonist_supply)
    return replace(
        state,
        colonist_ship=refill,
        colonist_supply=state.colonist_supply - refill,
    )


def end_round(state: PuertoRicoState) -> PuertoRicoState:
    """Add a doubloon to unchosen roles, pass the governorship and check the end."""
    roles = tuple(
        replace(
            role,
            doubloons=role.doubloons + (1 if role.taken_by is None else 0),
            taken_by=None,
        )
        for role in state.roles
    )
    governor_index = state.order.index(state.governor)
    new_governor = state.order[(governor_index + 1) % len(state.order)]
    state = replace(
        state,
        roles=roles,
        governor=new_governor,
        round=state.round + 1,
        phase="role_selection",
        active_role=None,
        active_player=new_governor,
        players_acted=frozenset(),
        captain_passes=0,
    )
    return check_end_game(state)


def check_end_game(state: PuertoRicoState) -> PuertoRicoState:
    """Set game over when a supply runs out, a city fills or the round limit hits."""
    reason: str | None = None
    if state.vp_supply <= 0:
        reason = "victory point supply exhausted"
    elif state.colonist_supply == 0:
        reason = "colonist supply exhausted"
    elif any(city_spaces_used(player) >= MAX_CITY_SPACES for player in state.players):
        reason = "a player's city is full"
    elif state.config.max_rounds > 0 and state.round > state.config.max_rounds:
        reason = "round limit reached"
    if reason is None:
        return state
    winner = compute_winner(state)
    return replace(
        state,
        phase="game_over",
        active_role=None,
        end_reason=reason,
        winner=winner,
    )


def compute_winner(state: PuertoRicoState) -> PlayerId:
    """Highest score; ties go to the wealthier player, then to order."""
    best: PlayerId | None = None
    best_key: tuple[int, int] | None = None
    for seat in state.order:
        player = state.players[seat]
        key = (total_points(player), player.doubloons + goods_total(player.goods))
        if best_key is None or key > best_key:
            best = seat
            best_key = key
    assert best is not None
    return best


def advance_captain(
    state: PuertoRicoState, player: PlayerId, *, loaded: bool
) -> PuertoRicoState:
    """Advance the Captain loading phase; all-pass starts the discard phase."""
    passes = 0 if loaded else state.captain_passes + 1
    if passes >= len(state.order):
        return start_captain_discard(replace(state, captain_passes=passes))
    next_player = next_player_in_order(state, player)
    return replace(state, captain_passes=passes, active_player=next_player)


def start_captain_discard(state: PuertoRicoState) -> PuertoRicoState:
    """Find the first player from the Captain who still holds goods."""
    picker = role_chooser(state, "captain")
    if picker is None:
        picker = state.order[0]
    start = state.order.index(picker)
    acted: set[PlayerId] = set()
    for offset in range(len(state.order)):
        candidate = state.order[(start + offset) % len(state.order)]
        if goods_total(state.players[candidate].goods) > 0:
            return replace(
                state,
                phase="captain_discard",
                active_player=candidate,
                players_acted=frozenset(acted),
            )
        acted.add(candidate)
    return finish_captain_phase(state)


def advance_discard(state: PuertoRicoState, player: PlayerId) -> PuertoRicoState:
    """Move to the next player with goods; all done finishes the Captain phase."""
    acted = set(state.players_acted) | {player}
    if len(acted) >= len(state.order):
        return finish_captain_phase(replace(state, players_acted=frozenset(acted)))
    start = state.order.index(player)
    for offset in range(1, len(state.order) + 1):
        candidate = state.order[(start + offset) % len(state.order)]
        if candidate in acted:
            continue
        if goods_total(state.players[candidate].goods) == 0:
            acted.add(candidate)
            continue
        return replace(
            state,
            active_player=candidate,
            players_acted=frozenset(acted),
        )
    return finish_captain_phase(replace(state, players_acted=frozenset(acted)))


def finish_captain_phase(state: PuertoRicoState) -> PuertoRicoState:
    """Unload full ships, keep partial ones, and reset per-phase flags."""
    supply = state.goods_supply
    ships: list[CargoShip] = []
    for ship in state.cargo_ships:
        if ship.full and ship.good is not None:
            supply = goods_add(supply, ship.good, ship.filled)
            ships.append(CargoShip(ship.capacity))
        else:
            ships.append(ship)
    players = tuple(
        replace(player, captain_first_load_done=False, wharf_used=False)
        for player in state.players
    )
    state = replace(
        state,
        cargo_ships=tuple(ships),
        goods_supply=supply,
        players=players,
        captain_passes=0,
        players_acted=frozenset(),
        active_role=None,
        active_player=state.governor,
        phase="role_selection",
    )
    return _advance_role_picker(state)


def place_colonist(owner: PlayerState, action: PlaceColonist) -> PlayerState:
    """Apply one colonist placement during Mayor."""
    if owner.colonists_unplaced <= 0:
        raise IllegalActionError("no colonists left to place")
    if action.target == "plantation":
        plantation = owner.plantations[action.index]
        if plantation.colonized:
            raise IllegalActionError("that plantation is already colonized")
        return replace(
            owner,
            plantations=replace_at(
                owner.plantations, action.index, replace(plantation, colonized=True)
            ),
            colonists_unplaced=owner.colonists_unplaced - 1,
        )
    if action.target == "building":
        building = owner.buildings[action.index]
        spec = BUILDINGS[building.name]
        if building.colonists >= spec.max_colonists:
            raise IllegalActionError("that building has no empty colonist space")
        return replace(
            owner,
            buildings=replace_at(
                owner.buildings,
                action.index,
                replace(building, colonists=building.colonists + 1),
            ),
            colonists_unplaced=owner.colonists_unplaced - 1,
        )
    if action.target == "quarry":
        if owner.occupied_quarries >= owner.quarries:
            raise IllegalActionError("every quarry already has a colonist")
        return replace(
            owner,
            occupied_quarries=owner.occupied_quarries + 1,
            colonists_unplaced=owner.colonists_unplaced - 1,
        )
    raise IllegalActionError("unknown colonist target")


def pick_up_colonist(owner: PlayerState, action: PickUpColonist) -> PlayerState:
    """Return one colonist to the unplaced pool during Mayor."""
    if action.target == "plantation":
        plantation = owner.plantations[action.index]
        if not plantation.colonized:
            raise IllegalActionError("that plantation has no colonist")
        return replace(
            owner,
            plantations=replace_at(
                owner.plantations, action.index, replace(plantation, colonized=False)
            ),
            colonists_unplaced=owner.colonists_unplaced + 1,
        )
    if action.target == "building":
        building = owner.buildings[action.index]
        if building.colonists <= 0:
            raise IllegalActionError("that building has no colonist")
        return replace(
            owner,
            buildings=replace_at(
                owner.buildings,
                action.index,
                replace(building, colonists=building.colonists - 1),
            ),
            colonists_unplaced=owner.colonists_unplaced + 1,
        )
    if action.target == "quarry":
        if owner.occupied_quarries <= 0:
            raise IllegalActionError("no quarry has a colonist")
        return replace(
            owner,
            occupied_quarries=owner.occupied_quarries - 1,
            colonists_unplaced=owner.colonists_unplaced + 1,
        )
    raise IllegalActionError("unknown colonist target")


def colonist_target(action: PlaceColonist | PickUpColonist) -> str:
    if action.target == "quarry":
        return "a quarry"
    return f"{action.target} {action.index}"


def has_placement_targets(owner: PlayerState) -> bool:
    if owner.colonists_unplaced <= 0:
        return False
    if any(not plantation.colonized for plantation in owner.plantations):
        return True
    if owner.occupied_quarries < owner.quarries:
        return True
    return any(
        building.colonists < BUILDINGS[building.name].max_colonists
        for building in owner.buildings
    )


def legal_action_list(state: PuertoRicoState, player: PlayerId) -> list[Action]:
    """Every action the deciding player may choose right now."""
    if state.phase == "role_selection":
        return [SelectRole(role.role) for role in state.roles if role.taken_by is None]
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


def settler_actions(
    state: PuertoRicoState, player: PlayerId, owner: PlayerState
) -> list[Action]:
    actions: list[Action] = []
    space = island_spaces_used(owner) < MAX_ISLAND_SPACES
    if (
        space
        and owns_active(owner, "hacienda")
        and not owner.hacienda_used
        and state.plantation_deck
    ):
        actions.append(UseHacienda())
    if space:
        seen: set[Good] = set()
        for good in state.face_up:
            if good not in seen:
                seen.add(good)
                actions.append(TakePlantation(good))
        can_quarry = role_chooser(state, "settler") == player or owns_active(
            owner, "construction_hut"
        )
        if can_quarry and state.quarry_supply > 0:
            actions.append(TakeQuarry())
    actions.append(Pass())
    return actions


def mayor_actions(owner: PlayerState) -> list[Action]:
    actions: list[Action] = []
    if owner.colonists_unplaced > 0:
        for index, plantation in enumerate(owner.plantations):
            if not plantation.colonized:
                actions.append(PlaceColonist("plantation", index))
        for index, building in enumerate(owner.buildings):
            spec = BUILDINGS[building.name]
            if building.colonists < spec.max_colonists:
                actions.append(PlaceColonist("building", index))
        if owner.occupied_quarries < owner.quarries:
            actions.append(PlaceColonist("quarry"))
    else:
        # Colonists may be rearranged only after every new colonist is placed;
        # this also keeps a random player from moving the same colonist forever.
        for index, plantation in enumerate(owner.plantations):
            if plantation.colonized:
                actions.append(PickUpColonist("plantation", index))
        for index, building in enumerate(owner.buildings):
            if building.colonists > 0:
                actions.append(PickUpColonist("building", index))
        if owner.occupied_quarries > 0:
            actions.append(PickUpColonist("quarry"))
    if not has_placement_targets(owner):
        actions.append(FinishPlacement())
    return actions


def builder_actions(state: PuertoRicoState, player: PlayerId) -> list[Action]:
    actions: list[Action] = [Build(name) for name in available_to_build(state, player)]
    actions.append(Pass())
    return actions


def craftsman_actions(state: PuertoRicoState, owner: PlayerState) -> list[Action]:
    actions: list[Action] = []
    potential = production(owner)
    for index, good in enumerate(GOODS):
        if potential[index] > 0 and state.goods_supply[index] > 0:
            actions.append(ProducePrivilege(good))
    actions.append(Pass())
    return actions


def trader_actions(state: PuertoRicoState, owner: PlayerState) -> list[Action]:
    actions: list[Action] = []
    if len(state.trading_house) < TRADING_HOUSE_SPACES:
        for good in GOODS:
            if goods_get(owner.goods, good) <= 0:
                continue
            if good in state.trading_house and not owns_active(owner, "office"):
                continue
            actions.append(Sell(good))
    actions.append(Pass())
    return actions


def captain_actions(
    state: PuertoRicoState, player: PlayerId, owner: PlayerState
) -> list[Action]:
    actions: list[Action] = []
    for good in GOODS:
        if goods_get(owner.goods, good) <= 0:
            continue
        for ship in can_ship(state, player, good):
            actions.append(LoadShip(good, ship))
    for good in wharf_goods(state, player):
        actions.append(LoadWharf(good))
    if not can_load_anything(state, player):
        actions.append(Pass())
    return actions


def discard_actions(owner: PlayerState) -> list[Action]:
    held = [good for good in GOODS if goods_get(owner.goods, good) > 0]
    max_protected = 0
    if owns_active(owner, "small_warehouse"):
        max_protected += 1
    if owns_active(owner, "large_warehouse"):
        max_protected += 2
    actions: list[Action] = []
    for size in range(max_protected + 1):
        for combination in combinations(held, size):
            actions.append(DiscardGoods(tuple(combination)))
    return actions


def combinations(items: list[Good], size: int) -> Iterable[tuple[Good, ...]]:
    """All size-length combinations of `items`, in their original order."""
    if size == 0:
        yield ()
        return
    if size > len(items):
        return
    for index in range(len(items) - size + 1):
        head = items[index]
        for rest in combinations(items[index + 1 :], size - 1):
            yield (head, *rest)


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
        return DiscardGoods() if DiscardGoods() in actions else None
    return None


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


def explain_illegal(state: PuertoRicoState, player: PlayerId, action: Action) -> str:
    """Why `action` is not legal for `player` now."""
    phase = state.phase
    if phase == "role_selection":
        if isinstance(action, SelectRole):
            entry = role_state(state, action.role)
            if entry.taken_by is not None:
                return f"{action.role} was already chosen this round."
        return "Choose a role that nobody has taken this round."
    if phase == "settler_action":
        owner = state.players[player]
        if isinstance(action, TakePlantation):
            if action.good not in state.face_up:
                return f"No {action.good} plantation is face up."
            if island_spaces_used(owner) >= MAX_ISLAND_SPACES:
                return "Your island is full."
        if isinstance(action, TakeQuarry):
            if state.quarry_supply <= 0:
                return "No quarries remain."
            return (
                "You may take a quarry only with the Settler privilege "
                "or a Construction Hut."
            )
        if isinstance(action, UseHacienda):
            if not owns_active(owner, "hacienda"):
                return "You have no active Hacienda."
            if owner.hacienda_used:
                return "Your Hacienda was already used this Settler phase."
            if not state.plantation_deck:
                return "The plantation deck is empty."
        return "Take a face-up plantation, a quarry if allowed, or pass."
    if phase == "mayor_action":
        if isinstance(action, FinishPlacement) and has_placement_targets(
            state.players[player]
        ):
            return "You still have colonists to place."
        if isinstance(action, PlaceColonist | PickUpColonist):
            return "That colonist placement is not available now."
        return "Place or move a colonist, or finish."
    if phase == "builder_action":
        if isinstance(action, Build) and action.building not in available_to_build(
            state, player
        ):
            return "You cannot afford that building or have no room."
        return "Build an available building or pass."
    if phase == "craftsman_action":
        if isinstance(action, ProducePrivilege):
            potential = production(state.players[player])
            index = GOODS.index(action.good)
            if potential[index] <= 0 or state.goods_supply[index] <= 0:
                return f"You cannot produce an extra {action.good}."
        return "Take a producible good or pass."
    if phase == "trader_action":
        if isinstance(action, Sell):
            owner = state.players[player]
            if goods_get(owner.goods, action.good) <= 0:
                return f"You have no {action.good}."
            if len(state.trading_house) >= TRADING_HOUSE_SPACES:
                return "The trading house is full."
            if action.good in state.trading_house and not owns_active(owner, "office"):
                return (
                    f"The trading house already holds {action.good}; "
                    "you need an Office."
                )
        return "Sell a good you hold or pass."
    if phase == "captain_action":
        if isinstance(action, LoadShip):
            owner = state.players[player]
            if goods_get(owner.goods, action.good) <= 0:
                return f"You have no {action.good}."
            if action.ship not in can_ship(state, player, action.good):
                return "That ship cannot take that good now."
        if isinstance(action, LoadWharf) and action.good not in wharf_goods(
            state, player
        ):
            return "Your Wharf cannot take that good now."
        if isinstance(action, Pass) and can_load_anything(state, player):
            return "You must load goods if you can."
        return "Load goods on a ship or Wharf, or pass if you cannot."
    if phase == "captain_discard":
        return "Choose the goods your warehouses protect."
    return "That action is not legal now."
