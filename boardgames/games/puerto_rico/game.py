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
    GOODS,
    TRADING_HOUSE_SPACES,
    Good,
    Role,
)
from boardgames.games.puerto_rico.model import (
    Action,
    CargoShip,
    DiscardGoods,
    FinishPlacement,
    Goods,
    LoadShip,
    LoadWharf,
    Pass,
    Phase,
    PlayerState,
    PuertoRicoConfig,
    PuertoRicoState,
    SelectRole,
    Sell,
    building_points,
    can_load_on_ship,
    can_ship,
    end_game_bonus,
    goods_add,
    goods_get,
    goods_plus,
    goods_remove,
    goods_set,
    goods_total,
    next_player_in_order,
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
from boardgames.games.puerto_rico.roles.builder import (
    apply_builder,
    builder_actions,
    explain_builder,
)
from boardgames.games.puerto_rico.roles.craftsman import (
    apply_craftsman,
    craftsman_actions,
    explain_craftsman,
    run_production,
)
from boardgames.games.puerto_rico.roles.mayor import (
    apply_mayor,
    distribute_colonists,
    explain_mayor,
    mayor_actions,
)
from boardgames.games.puerto_rico.roles.settler import (
    apply_settler,
    explain_settler,
    settler_actions,
)
from boardgames.games.puerto_rico.rounds import (
    advance_role_picker,
    mark_acted,
    tiebreak_key,
)
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
            return apply_settler(state, player, action)
        if state.phase == "mayor_action":
            return apply_mayor(state, player, action)
        if state.phase == "builder_action":
            return apply_builder(state, player, action)
        if state.phase == "craftsman_action":
            return apply_craftsman(state, player, action)
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
            state = advance_role_picker(state)
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
            state, advanced = mark_acted(state, player)
            return Transition(state, (event, *advanced))
        if isinstance(action, Pass):
            state, advanced = mark_acted(state, player)
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


# Helpers ------------------------------------------------------------------


def captain_first_load(
    state: PuertoRicoState, player: PlayerId, owner: PlayerState
) -> tuple[bool, PlayerState]:
    """Mark and report the Captain chooser's first shipment of the phase."""
    if role_chooser(state, "captain") == player and not owner.captain_first_load_done:
        return True, replace(owner, captain_first_load_done=True)
    return False, owner


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
    return advance_role_picker(state)


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
        return explain_settler(state, player, action)
    if phase == "mayor_action":
        return explain_mayor(state, player, action)
    if phase == "builder_action":
        return explain_builder(state, player, action)
    if phase == "craftsman_action":
        return explain_craftsman(state, player, action)
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
