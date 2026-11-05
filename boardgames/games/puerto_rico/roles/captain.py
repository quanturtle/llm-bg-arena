"""The Puerto Rico Captain: shipping goods, the Wharf and the discard step."""

from collections.abc import Iterable
from dataclasses import replace
from typing import cast

from boardgames.core import (
    Event,
    IllegalActionError,
    JsonValue,
    PlayerId,
    Transition,
    seat_label,
)
from boardgames.games.puerto_rico.constants import GOODS, Good
from boardgames.games.puerto_rico.model import (
    Action,
    CargoShip,
    DiscardGoods,
    Goods,
    LoadShip,
    LoadWharf,
    Pass,
    PlayerState,
    PuertoRicoState,
    can_load_on_ship,
    can_ship,
    goods_add,
    goods_get,
    goods_plus,
    goods_remove,
    goods_set,
    goods_total,
    next_player_in_order,
    replace_at,
    replace_player,
    role_chooser,
    ship_victory_points,
    wharf_goods,
)
from boardgames.games.puerto_rico.rounds import advance_role_picker


def captain_first_load(
    state: PuertoRicoState, player: PlayerId, owner: PlayerState
) -> tuple[bool, PlayerState]:
    """Mark and report the Captain chooser's first shipment of the phase."""
    if role_chooser(state, "captain") == player and not owner.captain_first_load_done:
        return True, replace(owner, captain_first_load_done=True)
    return False, owner


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


def advance_captain(
    state: PuertoRicoState, player: PlayerId, *, loaded: bool
) -> PuertoRicoState:
    """Advance the Captain loading phase; all-pass starts the discard phase."""
    passes = 0 if loaded else state.captain_passes + 1
    if passes >= len(state.order):
        return start_captain_discard(replace(state, captain_passes=passes))
    next_player = next_player_in_order(state, player)
    return replace(state, captain_passes=passes, active_player=next_player)


def apply_captain(
    state: PuertoRicoState, player: PlayerId, action: Action
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
        owner = replace(owner, goods=goods_set(owner.goods, good, 0), wharf_used=True)
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


def apply_discard(
    state: PuertoRicoState, player: PlayerId, action: Action
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


def kept_goods(owner: PlayerState, action: DiscardGoods) -> int:
    """How many cards a discard choice keeps, for the fallback choice."""
    keep, _ = discard_counts(owner, action)
    return sum(keep)


def explain_captain(state: PuertoRicoState, player: PlayerId, action: Action) -> str:
    """Why a Captain action is not legal for `player` now."""
    if isinstance(action, LoadShip):
        owner = state.players[player]
        if goods_get(owner.goods, action.good) <= 0:
            return f"You have no {action.good}."
        if action.ship not in can_ship(state, player, action.good):
            return "That ship cannot take that good now."
    if isinstance(action, LoadWharf) and action.good not in wharf_goods(state, player):
        return "Your Wharf cannot take that good now."
    if isinstance(action, Pass) and can_load_on_ship(state, player):
        return "You must load goods if a ship can take them."
    return "Load goods on a ship or Wharf, or pass if you cannot."


def explain_discard(state: PuertoRicoState, player: PlayerId, action: Action) -> str:
    """Why a discard choice after shipping is not legal for `player` now."""
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
