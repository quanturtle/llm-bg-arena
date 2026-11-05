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
)
from boardgames.core.records import (
    dataclass_from_json,
    tagged_json_object,
    to_json_object,
)
from boardgames.games.puerto_rico.constants import (
    BUILDINGS,
    GOODS,
    MAX_CITY_SPACES,
    MAX_ISLAND_SPACES,
    TRADING_HOUSE_SPACES,
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
    Phase,
    PickUpColonist,
    PlaceColonist,
    Plantation,
    PlayerState,
    ProducePrivilege,
    PuertoRicoConfig,
    PuertoRicoState,
    SelectRole,
    Sell,
    TakePlantation,
    TakeQuarry,
    UseHacienda,
    available_to_build,
    build_cost,
    building_points,
    can_load_on_ship,
    can_ship,
    city_spaces_used,
    end_game_bonus,
    factory_bonus_for_produced,
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
from boardgames.games.puerto_rico.setup import check_config, start_game
from boardgames.games.puerto_rico.view import (
    describe_action,
    observe,
    render_text,
)

ROLE_PHASE: dict[Role, Phase] = {
    "settler": "settler_action",
    "mayor": "mayor_action",
    "builder": "builder_action",
    "craftsman": "craftsman_action",
    "trader": "trader_action",
    "captain": "captain_action",
}


@register_game
class PuertoRico(Game[PuertoRicoState, Action, PuertoRicoConfig]):
    """Puerto Rico with all base-game roles, buildings and end-game bonuses."""

    id: ClassVar[str] = "puerto_rico"
    rules_version: ClassVar[int] = 3

    # Config ---------------------------------------------------------------

    def parse_config(self, raw: JsonObject) -> PuertoRicoConfig:
        config = dataclass_from_json(PuertoRicoConfig, raw)
        check_config(config)
        return config

    def config_json(self, config: PuertoRicoConfig) -> dict[str, JsonValue]:
        return to_json_object(config)

    # Setup ----------------------------------------------------------------

    def setup(self, config: PuertoRicoConfig, seed: int) -> Transition[PuertoRicoState]:
        return start_game(config, seed)

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
        if isinstance(action, DiscardGoods):
            action = replace(
                action,
                protected=tuple(sorted(action.protected, key=GOODS.index)),
            )
        return checked_apply(
            self,
            state,
            player,
            action,
            no_decision=(
                f"{seat_label(player)} has no open decision in phase {state.phase!r}"
            ),
        )

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
        tiebreakers: dict[PlayerId, tuple[float, ...]] = {}
        for seat in range(state.config.num_players):
            player = state.players[seat]
            player_id = PlayerId(seat)
            base = total_points(player)
            points[player_id] = base
            breakdown[player_id] = {
                "vp_chips": player.vp_chips,
                "buildings": building_points(player),
                "bonus": end_game_bonus(player),
            }
            tiebreakers[player_id] = tuple(
                float(value) for value in tiebreak_key(state, player_id)
            )
        return Scores(points, breakdown, tiebreakers)

    def public_scores(self, state: PuertoRicoState) -> Scores:
        """VP chips stay hidden until the game ends and reveals them."""
        if self.is_terminal(state):
            return self.scores(state)
        return Scores(
            {
                PlayerId(seat): float(public_points(player))
                for seat, player in enumerate(state.players)
            },
            tiebreakers={
                PlayerId(seat): tuple(
                    float(value) for value in tiebreak_key(state, PlayerId(seat))
                )
                for seat in range(state.config.num_players)
            },
        )

    def observe(self, state: PuertoRicoState, viewer: PlayerId | None) -> Observation:
        return observe(state, viewer)

    def render_text(self, observation: Observation) -> str:
        return render_text(observation)

    def rules_text(self) -> str:
        rules = files("boardgames.games.puerto_rico") / "rules.md"
        return rules.read_text(encoding="utf-8")

    def format_action(self, action: Action) -> str:
        return format_action(action)

    def parse_action(self, text: str) -> Action:
        return parse_action(text)

    def describe_action(self, observation: Observation, action: Action) -> str:
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
            state = _advance_role_picker(state)
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
            phase=phase,
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
            has_extra = state.colonist_supply > 0
            state = distribute_colonists(state, player)
            events.append(
                Event(
                    "colonists_distributed",
                    "Colonists from the ship are distributed; "
                    + (
                        f"{seat_label(player)} takes the extra colonist."
                        if has_extra
                        else "the supply is empty, so there is no extra colonist."
                    ),
                    {"player": player},
                )
            )
        elif role == "craftsman":
            state, produced_events = run_production(state, player)
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
        events: list[Event] = []
        if isinstance(action, UseHacienda):
            if not state.plantation_deck:
                deck, rng = state.rng.shuffled(state.plantation_discard)
                state = replace(
                    state,
                    plantation_deck=deck,
                    plantation_discard=(),
                    rng=rng,
                )
                events.append(
                    Event(
                        "plantation_discard_reshuffled",
                        "The plantation discard pile was shuffled into a new deck.",
                        {"cards": len(deck)},
                    )
                )
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
            events.append(
                Event(
                    "hacienda_plantation",
                    f"{seat_label(player)} drew a {good} plantation.",
                    {"player": player, "good": good},
                )
            )
            return Transition(state, tuple(events))
        if isinstance(action, TakePlantation):
            face_up = list(state.face_up)
            face_up.remove(action.good)
            colonized = False
            if owner.active("hospice") and action.use_hospice:
                state, colonized = take_colonist(state)
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
            state, advanced = self.mark_acted(state, player)
            return Transition(state, (event, *advanced))
        if isinstance(action, TakeQuarry):
            colonized = False
            if owner.active("hospice") and action.use_hospice:
                state, colonized = take_colonist(state)
            state = replace_player(
                state,
                player,
                replace(
                    state.players[player],
                    quarries=state.players[player].quarries + 1,
                    occupied_quarries=(
                        state.players[player].occupied_quarries
                        + (1 if colonized else 0)
                    ),
                ),
            )
            state = replace(state, quarry_supply=state.quarry_supply - 1)
            data: dict[str, JsonValue] = {"player": player}
            if colonized:
                data["colonized"] = True
            event = Event(
                "quarry_taken",
                f"{seat_label(player)} took a quarry"
                + (" and colonized it with the Hospice." if colonized else "."),
                data,
            )
            state, advanced = self.mark_acted(state, player)
            return Transition(state, (event, *advanced))
        if isinstance(action, Pass):
            state, advanced = self.mark_acted(state, player)
            event = Event(
                "settler_passed",
                f"{seat_label(player)} took no plantation.",
                {"player": player},
            )
            return Transition(state, (event, *advanced))
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
            state, advanced = self.mark_acted(state, player)
            event = Event(
                "mayor_finished",
                f"{seat_label(player)} finished placing colonists.",
                {"player": player},
            )
            return Transition(state, (event, *advanced))
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
            if owner.active("university") and action.use_university:
                state, colonized = take_colonist(state)
                if colonized:
                    new_buildings = list(state.players[player].buildings)
                    index = len(new_buildings) - 1
                    new_buildings[index] = replace(new_buildings[index], colonists=1)
                    state = replace_player(
                        state,
                        player,
                        replace(state.players[player], buildings=tuple(new_buildings)),
                    )
                    events.append(
                        Event(
                            "university_colonist",
                            f"The University placed a colonist on {name}.",
                            {"player": player, "building": name},
                        )
                    )
            state, advanced = self.mark_acted(state, player)
            return Transition(state, (*events, *advanced))
        if isinstance(action, Pass):
            state, advanced = self.mark_acted(state, player)
            event = Event(
                "builder_passed",
                f"{seat_label(player)} built nothing.",
                {"player": player},
            )
            return Transition(state, (event, *advanced))
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
        state = _advance_role_picker(
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
            state, advanced = self.mark_acted(state, player)
            return Transition(state, (event, *advanced))
        if isinstance(action, Pass):
            state, advanced = self.mark_acted(state, player)
            event = Event(
                "trader_passed",
                f"{seat_label(player)} sold nothing.",
                {"player": player},
            )
            return Transition(state, (event, *advanced))
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
            first_load, owner = captain_first_load(state, player, owner)
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
            first_load, owner = captain_first_load(state, player, owner)
            points = ship_victory_points(state, player, quantity)
            owner = replace(owner, vp_chips=owner.vp_chips + points)
            state = replace_player(state, player, owner)
            state = replace(
                state,
                goods_supply=goods_add(state.goods_supply, good, quantity),
                vp_supply=state.vp_supply - points,
            )
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
        keep, discard = discard_counts(owner, action)
        state = replace_player(
            state, player, replace(owner, goods=cast(Goods, tuple(keep)))
        )
        state = replace(
            state,
            goods_supply=goods_plus(state.goods_supply, cast(Goods, tuple(discard))),
        )
        data: dict[str, JsonValue] = {
            "player": player,
            "protected": list(action.protected),
            "keep": action.keep,
            "kept": [count for count in keep],
        }
        event = Event(
            "goods_discarded",
            f"{seat_label(player)} kept goods after shipping.",
            data,
        )
        state = advance_discard(state, player)
        return Transition(state, (event,))

    # Phase plumbing -------------------------------------------------------

    def mark_acted(
        self, state: PuertoRicoState, player: PlayerId
    ) -> tuple[PuertoRicoState, tuple[Event, ...]]:
        acted = state.players_acted | {player}
        if len(acted) >= len(state.order):
            return finish_standard_phase(replace(state, players_acted=acted))
        next_player = next_unacted(replace(state, players_acted=acted), player)
        assert next_player is not None
        return (
            replace(state, players_acted=acted, active_player=next_player),
            (),
        )


# Helpers ------------------------------------------------------------------


def captain_first_load(
    state: PuertoRicoState, player: PlayerId, owner: PlayerState
) -> tuple[bool, PlayerState]:
    """Mark and report the Captain chooser's first shipment of the phase."""
    if role_chooser(state, "captain") == player and not owner.captain_first_load_done:
        return True, replace(owner, captain_first_load_done=True)
    return False, owner


def can_take_quarry(
    state: PuertoRicoState, player: PlayerId, owner: PlayerState
) -> bool:
    """Whether the Settler privilege or a Construction Hut allows a quarry."""
    return role_chooser(state, "settler") == player or owner.active("construction_hut")


def can_take_colonist(state: PuertoRicoState) -> bool:
    """Whether the supply or the ship can provide a bonus colonist."""
    return state.colonist_supply + state.colonist_ship > 0


def take_colonist(state: PuertoRicoState) -> tuple[PuertoRicoState, bool]:
    """Take one colonist from the supply, or from the ship when it is empty."""
    if state.colonist_supply > 0:
        return replace(state, colonist_supply=state.colonist_supply - 1), True
    if state.colonist_ship > 0:
        return replace(state, colonist_ship=state.colonist_ship - 1), True
    return state, False


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
    state: PuertoRicoState, chooser: PlayerId
) -> tuple[PuertoRicoState, tuple[Event, ...]]:
    """Every player produces goods from the Craftsman chooser, limited by the bank."""
    events: list[Event] = []
    start = state.order.index(chooser)
    for offset in range(len(state.order)):
        seat = state.order[(start + offset) % len(state.order)]
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
        bonus = factory_bonus_for_produced(owner, cast(Goods, tuple(produced)))
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


def finish_standard_phase(
    state: PuertoRicoState,
) -> tuple[PuertoRicoState, tuple[Event, ...]]:
    role = state.active_role
    if role == "settler":
        state, events = _finish_settler(state)
    elif role == "mayor":
        state, events = _finish_mayor(state)
    elif role == "trader":
        state, events = _finish_trader(state)
    else:
        events = ()
    return _advance_role_picker(state), events


def _finish_settler(
    state: PuertoRicoState,
) -> tuple[PuertoRicoState, tuple[Event, ...]]:
    face_up_count = len(state.order) + 1
    discard = (*state.plantation_discard, *state.face_up)
    deck = state.plantation_deck
    rng = state.rng
    drawn = deck[:face_up_count]
    deck = deck[len(drawn) :]
    shuffled: tuple[Good, ...] = ()
    reshuffled = False
    if len(drawn) < face_up_count:
        shuffled, rng = rng.shuffled(discard)
        needed = face_up_count - len(drawn)
        drawn = (*drawn, *shuffled[:needed])
        deck = shuffled[needed:]
        discard = ()
        reshuffled = True
    events = [
        Event(
            "face_up_refilled",
            "The face-up plantations were replenished: " + ", ".join(drawn) + ".",
            {"drawn": list(drawn), "reshuffled": reshuffled},
        )
    ]
    if reshuffled:
        events.append(
            Event(
                "plantation_discard_reshuffled",
                "The plantation discard pile was shuffled into a new deck.",
                {"cards": len(shuffled)},
            )
        )
    state = replace(
        state,
        face_up=drawn,
        plantation_deck=deck,
        plantation_discard=discard,
        rng=rng,
    )
    return state, tuple(events)


def _finish_mayor(
    state: PuertoRicoState,
) -> tuple[PuertoRicoState, tuple[Event, ...]]:
    state = refill_colonist_ship(state)
    if not state.colonist_shortage:
        return state, ()
    return state, (
        Event(
            "colonist_shortage",
            "The colonist supply cannot refill the ship; the game will "
            "end at the end of this round.",
            {"ship": state.colonist_ship},
        ),
    )


def _finish_trader(
    state: PuertoRicoState,
) -> tuple[PuertoRicoState, tuple[Event, ...]]:
    if len(state.trading_house) < TRADING_HOUSE_SPACES:
        return state, ()
    supply = goods_plus(state.goods_supply, goods_from_list(list(state.trading_house)))
    return replace(state, trading_house=(), goods_supply=supply), ()


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
        colonist_shortage=refill < needed,
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
    final_governor = state.governor
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
    return check_end_game(state, final_governor=final_governor)


def check_end_game(
    state: PuertoRicoState, *, final_governor: PlayerId | None = None
) -> PuertoRicoState:
    """Set game over when a supply runs out, a city fills or the round limit hits."""
    reason: str | None = None
    if state.vp_supply <= 0:
        reason = "victory point supply exhausted"
    elif state.colonist_shortage:
        reason = "colonist supply exhausted"
    elif any(city_spaces_used(player) >= MAX_CITY_SPACES for player in state.players):
        reason = "a player's city is full"
    elif state.config.max_rounds > 0 and state.round > state.config.max_rounds:
        reason = "round limit reached"
    if reason is None:
        return state
    state = replace(state, final_governor=final_governor)
    winner = compute_winner(state)
    return replace(
        state,
        phase="game_over",
        active_role=None,
        end_reason=reason,
        winner=winner,
    )


def tiebreak_key(state: PuertoRicoState, seat: PlayerId) -> tuple[int, int]:
    """Tie-break order after points: doubloons plus goods, then the governor."""
    player = state.players[seat]
    wealth = player.doubloons + goods_total(player.goods)
    governor = (
        state.final_governor if state.final_governor is not None else state.governor
    )
    distance = (state.order.index(seat) - state.order.index(governor)) % len(
        state.order
    )
    return wealth, -distance


def compute_winner(state: PuertoRicoState) -> PlayerId:
    """Highest score; ties go to the wealthier player, then to the governor."""
    best: PlayerId | None = None
    best_key: tuple[int, int, int] | None = None
    for seat in state.order:
        player = state.players[seat]
        key = (total_points(player), *tiebreak_key(state, seat))
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
        and owner.active("hacienda")
        and not owner.hacienda_used
        and (state.plantation_deck or state.plantation_discard)
    ):
        actions.append(UseHacienda())
    if space:
        hospice = owner.active("hospice") and can_take_colonist(state)
        seen: set[Good] = set()
        for good in state.face_up:
            if good not in seen:
                seen.add(good)
                actions.append(TakePlantation(good))
                if hospice:
                    actions.append(TakePlantation(good, use_hospice=False))
        if can_take_quarry(state, player, owner) and state.quarry_supply > 0:
            actions.append(TakeQuarry())
            if hospice:
                actions.append(TakeQuarry(use_hospice=False))
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
    owner = state.players[player]
    university = owner.active("university") and can_take_colonist(state)
    actions: list[Action] = []
    for name in available_to_build(state, player):
        actions.append(Build(name))
        if university:
            actions.append(Build(name, use_university=False))
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
            if good in state.trading_house and not owner.active("office"):
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
    if not can_load_on_ship(state, player):
        actions.append(Pass())
    return actions


def max_protected_types(owner: PlayerState) -> int:
    """How many goods types the owner's warehouses may protect."""
    return (1 if owner.active("small_warehouse") else 0) + (
        2 if owner.active("large_warehouse") else 0
    )


def discard_actions(owner: PlayerState) -> list[Action]:
    held = [good for good in GOODS if goods_get(owner.goods, good) > 0]
    actions: list[Action] = []
    for size in range(max_protected_types(owner) + 1):
        for combination in combinations(held, size):
            protected = set(combination)
            keepable: list[Good | None] = [
                None,
                *(good for good in held if good not in protected),
            ]
            for keep in keepable:
                actions.append(DiscardGoods(tuple(combination), keep))
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
        discards = [action for action in actions if isinstance(action, DiscardGoods)]
        return max(
            discards,
            key=lambda action: kept_goods(state.players[state.active_player], action),
        )
    return None


def discard_counts(
    owner: PlayerState, action: DiscardGoods
) -> tuple[list[int], list[int]]:
    """Keep and discard counts per good for one discard choice."""
    keep = [0, 0, 0, 0, 0]
    discard = [0, 0, 0, 0, 0]
    for index, good in enumerate(GOODS):
        count = goods_get(owner.goods, good)
        if good in action.protected:
            keep[index] = count
        elif good == action.keep:
            keep[index] = min(1, count)
        discard[index] = count - keep[index]
    return keep, discard


def kept_goods(owner: PlayerState, action: DiscardGoods) -> int:
    """How many cards a discard choice keeps, for the fallback choice."""
    keep, _ = discard_counts(owner, action)
    return sum(keep)


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
            entry = next(
                (item for item in state.roles if item.role == action.role), None
            )
            if entry is None:
                return f"There is no {action.role} role in this game."
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
            if not action.use_hospice:
                if not owner.active("hospice"):
                    return "You have no active Hospice."
                if not can_take_colonist(state):
                    return "There is no colonist available to place."
        if isinstance(action, TakeQuarry):
            if island_spaces_used(owner) >= MAX_ISLAND_SPACES:
                return "Your island is full."
            if state.quarry_supply <= 0:
                return "No quarries remain."
            if not can_take_quarry(state, player, owner):
                return (
                    "You may take a quarry only with the Settler privilege "
                    "or a Construction Hut."
                )
            if not action.use_hospice:
                if not owner.active("hospice"):
                    return "You have no active Hospice."
                if not can_take_colonist(state):
                    return "There is no colonist available to place."
        if isinstance(action, UseHacienda):
            if not owner.active("hacienda"):
                return "You have no active Hacienda."
            if owner.hacienda_used:
                return "Your Hacienda was already used this Settler phase."
            if not state.plantation_deck and not state.plantation_discard:
                return "No plantation remains in the deck or discard pile."
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
        owner = state.players[player]
        if isinstance(action, Build) and action.building not in available_to_build(
            state, player
        ):
            return "You cannot afford that building or have no room."
        if isinstance(action, Build) and not action.use_university:
            if not owner.active("university"):
                return "You have no active University."
            if not can_take_colonist(state):
                return "There is no colonist available to place."
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
            if action.good in state.trading_house and not owner.active("office"):
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
        if isinstance(action, Pass) and can_load_on_ship(state, player):
            return "You must load goods if a ship can take them."
        return "Load goods on a ship or Wharf, or pass if you cannot."
    if phase == "captain_discard":
        if isinstance(action, DiscardGoods):
            owner = state.players[player]
            if action.keep is not None and goods_get(owner.goods, action.keep) <= 0:
                return f"You have no {action.keep}."
            for good in action.protected:
                if goods_get(owner.goods, good) <= 0:
                    return f"You have no {good}."
            if action.keep is not None and action.keep in action.protected:
                return "That good is already protected by a warehouse."
            if len(action.protected) > max_protected_types(owner):
                return "Your warehouses cannot protect that many types."
            return "Choose one good to keep plus the types your warehouses protect."
        return "Choose goods to keep after shipping."
    return "That action is not legal now."
