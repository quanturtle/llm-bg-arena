"""Immutable data model for Puerto Rico: goods, buildings, actions and state.

The state is a plain dataclass; every update returns a new instance. Player
seats are numbered from 0 and indexed directly in `players`.
"""

from dataclasses import dataclass, replace
from typing import Literal, cast

from boardgames.core import PlayerId, Rng
from boardgames.games.puerto_rico.constants import (
    BUILDINGS,
    GOOD_INDEX,
    GOOD_PRICE,
    GOODS,
    LARGE_PRODUCTION_NAMES,
    MAX_CITY_SPACES,
    PRODUCTION_NAMES,
    BuildingSpec,
    Good,
    Role,
)

type Goods = tuple[int, int, int, int, int]
type Phase = Literal[
    "role_selection",
    "settler_action",
    "mayor_action",
    "builder_action",
    "craftsman_action",
    "trader_action",
    "captain_action",
    "captain_discard",
    "game_over",
]

type Action = (
    SelectRole
    | TakePlantation
    | TakeQuarry
    | UseHacienda
    | Pass
    | Build
    | ProducePrivilege
    | Sell
    | LoadShip
    | LoadWharf
    | PlaceColonist
    | PickUpColonist
    | FinishPlacement
    | DiscardGoods
)


@dataclass(frozen=True)
class PuertoRicoConfig:
    """Standard Puerto Rico for 3, 4 or 5 players.

    `victory_point_supply` 0 uses the standard supply (75/100/122).
    `max_rounds` 0 means no round limit.
    """

    num_players: int = 4
    victory_point_supply: int = 0
    max_rounds: int = 0


@dataclass(frozen=True)
class Plantation:
    """An island tile: a good-producing plantation, colonized or not."""

    good: Good
    colonized: bool = False


@dataclass(frozen=True)
class OwnedBuilding:
    """A building on a player's city board, with its current colonists."""

    name: str
    colonists: int = 0

    @property
    def active(self) -> bool:
        """A building works while at least one colonist occupies it."""
        return self.colonists > 0

    @property
    def spec(self) -> BuildingSpec:
        return BUILDINGS[self.name]


@dataclass(frozen=True)
class CargoShip:
    """One of the three cargo ships; a ship carries a single good type."""

    capacity: int
    good: Good | None = None
    filled: int = 0

    @property
    def remaining(self) -> int:
        return self.capacity - self.filled

    @property
    def empty(self) -> bool:
        return self.filled == 0

    @property
    def full(self) -> bool:
        return self.filled >= self.capacity


@dataclass(frozen=True)
class RoleState:
    """A role card: doubloons piled on it and the player who took it this round."""

    role: Role
    doubloons: int = 0
    taken_by: PlayerId | None = None


@dataclass(frozen=True)
class PlayerState:
    """Everything one player owns and has placed."""

    doubloons: int = 0
    vp_chips: int = 0
    goods: Goods = (0, 0, 0, 0, 0)
    plantations: tuple[Plantation, ...] = ()
    quarries: int = 0
    occupied_quarries: int = 0
    buildings: tuple[OwnedBuilding, ...] = ()
    colonists_unplaced: int = 0
    captain_first_load_done: bool = False
    wharf_used: bool = False
    hacienda_used: bool = False

    @property
    def active_quarries(self) -> int:
        return self.occupied_quarries

    def owns(self, name: str) -> bool:
        return any(building.name == name for building in self.buildings)

    def active(self, name: str) -> bool:
        return any(
            building.name == name and building.active for building in self.buildings
        )

    def building(self, name: str) -> OwnedBuilding | None:
        return next((b for b in self.buildings if b.name == name), None)


@dataclass(frozen=True)
class PuertoRicoState:
    """The whole game: board, roles, players, supplies and phase pointers."""

    config: PuertoRicoConfig
    rng: Rng
    round: int
    governor: PlayerId
    order: tuple[PlayerId, ...]
    phase: Phase
    active_role: Role | None
    active_player: PlayerId
    roles: tuple[RoleState, ...]
    players: tuple[PlayerState, ...]
    colonist_ship: int
    colonist_supply: int
    trading_house: tuple[Good, ...]
    cargo_ships: tuple[CargoShip, ...]
    face_up: tuple[Good, ...]
    plantation_deck: tuple[Good, ...]
    available_buildings: tuple[str, ...]
    quarry_supply: int
    goods_supply: Goods
    vp_supply: int
    players_acted: frozenset[PlayerId]
    captain_passes: int
    end_reason: str | None
    winner: PlayerId | None


# Actions ------------------------------------------------------------------


@dataclass(frozen=True)
class SelectRole:
    """Choose an unchosen role during the role-selection phase."""

    role: Role


@dataclass(frozen=True)
class TakePlantation:
    """Take one face-up plantation during the Settler action."""

    good: Good


@dataclass(frozen=True)
class TakeQuarry:
    """Take a quarry instead of a plantation (privilege or Construction Hut)."""


@dataclass(frozen=True)
class UseHacienda:
    """Draw an extra plantation from the deck with an active Hacienda."""


@dataclass(frozen=True)
class Pass:
    """Take no action, or decline a privilege."""


@dataclass(frozen=True)
class Build:
    """Build a building during the Builder action."""

    building: str


@dataclass(frozen=True)
class ProducePrivilege:
    """Take the Craftsman privilege: one extra good from the supply."""

    good: Good


@dataclass(frozen=True)
class Sell:
    """Sell one good to the trading house during the Trader action."""

    good: Good


@dataclass(frozen=True)
class LoadShip:
    """Load one good type on a cargo ship during the Captain action."""

    good: Good
    ship: int


@dataclass(frozen=True)
class LoadWharf:
    """Load all goods of one type on the active Wharf during the Captain action."""

    good: Good


@dataclass(frozen=True)
class PlaceColonist:
    """Place one colonist on a plantation, building or quarry during Mayor."""

    target: Literal["plantation", "building", "quarry"]
    index: int = -1


@dataclass(frozen=True)
class PickUpColonist:
    """Pick a colonist back up during Mayor, returning it to the unplaced pool."""

    target: Literal["plantation", "building", "quarry"]
    index: int = -1


@dataclass(frozen=True)
class FinishPlacement:
    """End your Mayor placements once no more colonists fit."""


@dataclass(frozen=True)
class DiscardGoods:
    """Keep goods after the Captain action; unprotected goods are discarded."""

    protected: tuple[Good, ...] = ()


# Goods helpers ------------------------------------------------------------


def empty_goods() -> Goods:
    return (0, 0, 0, 0, 0)


def goods_total(goods: Goods) -> int:
    return sum(goods)


def goods_get(goods: Goods, good: Good) -> int:
    return goods[GOOD_INDEX[good]]


def goods_set(goods: Goods, good: Good, value: int) -> Goods:
    index = GOOD_INDEX[good]
    result = (*goods[:index], value, *goods[index + 1 :])
    return cast(Goods, result)


def goods_add(goods: Goods, good: Good, amount: int) -> Goods:
    return goods_set(goods, good, goods_get(goods, good) + amount)


def goods_remove(goods: Goods, good: Good, amount: int) -> Goods:
    return goods_set(goods, good, goods_get(goods, good) - amount)


def goods_from(**counts: int) -> Goods:
    result = list(empty_goods())
    for good, count in counts.items():
        result[GOOD_INDEX[good]] = count  # type: ignore[index]
    return tuple(result)  # type: ignore[return-value]


def goods_to_list(goods: Goods) -> list[Good]:
    """The goods expanded one per unit, in fixed order."""
    return [
        good for good, count in zip(GOODS, goods, strict=True) for _ in range(count)
    ]


def goods_to_json(goods: Goods) -> list[int]:
    return list(goods)


def goods_from_list(goods: list[Good]) -> Goods:
    result = list(empty_goods())
    for good in goods:
        result[GOOD_INDEX[good]] += 1
    return tuple(result)  # type: ignore[return-value]


def goods_plus(first: Goods, second: Goods) -> Goods:
    return tuple(a + b for a, b in zip(first, second, strict=True))  # type: ignore[return-value]


def goods_minus(first: Goods, second: Goods) -> Goods:
    return tuple(a - b for a, b in zip(first, second, strict=True))  # type: ignore[return-value]


def goods_json_map(goods: Goods) -> dict[str, int]:
    """Only the goods actually held, keyed by name."""
    return {good: count for good, count in zip(GOODS, goods, strict=True) if count}


# Tuple helpers ------------------------------------------------------------


def replace_at[T](items: tuple[T, ...], index: int, value: T) -> tuple[T, ...]:
    return (*items[:index], value, *items[index + 1 :])


def replace_player(
    state: PuertoRicoState, player: PlayerId, new_player: PlayerState
) -> PuertoRicoState:
    return replace(state, players=replace_at(state.players, player, new_player))


def role_state(state: PuertoRicoState, role: Role) -> RoleState:
    return next(item for item in state.roles if item.role == role)


def replace_role(
    state: PuertoRicoState, role: Role, new_role: RoleState
) -> PuertoRicoState:
    return replace(
        state,
        roles=tuple(new_role if item.role == role else item for item in state.roles),
    )


def role_chooser(state: PuertoRicoState, role: Role) -> PlayerId | None:
    return role_state(state, role).taken_by


def active_buildings(player: PlayerState) -> tuple[OwnedBuilding, ...]:
    return tuple(building for building in player.buildings if building.active)


def owns_active(player: PlayerState, name: str) -> bool:
    return player.active(name)


def city_spaces_used(player: PlayerState) -> int:
    """City board spaces filled; large violet buildings take two."""
    return sum(
        2 if BUILDINGS[building.name].victory_points == 4 else 1
        for building in player.buildings
    )


def island_spaces_used(player: PlayerState) -> int:
    return len(player.plantations) + player.quarries


def occupied_island_spaces(player: PlayerState) -> int:
    colonized = sum(1 for plantation in player.plantations if plantation.colonized)
    return colonized + player.occupied_quarries


def production(player: PlayerState) -> Goods:
    """Goods this player's island would produce if the Craftsman is chosen.

    Each active production building needs matching occupied plantations. Corn
    needs no building: every occupied corn plantation produces one corn.
    """
    counts = [0, 0, 0, 0, 0]
    available: dict[Good, int] = {good: 0 for good in GOODS}
    for plantation in player.plantations:
        if plantation.colonized:
            available[plantation.good] += 1
    for good in GOODS:
        if good == "corn":
            counts[GOOD_INDEX[good]] = available[good]
            available[good] = 0
    for building in player.buildings:
        spec = BUILDINGS[building.name]
        if spec.production is None or building.colonists <= 0:
            continue
        good = spec.production
        amount = min(building.colonists, available[good])
        counts[GOOD_INDEX[good]] += amount
        available[good] -= amount
    return tuple(counts)  # type: ignore[return-value]


def factory_bonus(player: PlayerState) -> int:
    """Doubloons from the Factory when two or more goods types are produced."""
    if not owns_active(player, "factory"):
        return 0
    types = sum(1 for count in production(player) if count > 0)
    return {0: 0, 1: 0, 2: 1, 3: 2, 4: 3, 5: 5}[types]


def end_game_bonus(player: PlayerState) -> int:
    """Victory points from violet buildings owned and active, end-game only."""
    bonus = 0
    for building in player.buildings:
        if not building.active:
            continue
        if building.name == "guild_hall":
            bonus += sum(
                2 if other.name in LARGE_PRODUCTION_NAMES else 1
                for other in player.buildings
                if other.name in PRODUCTION_NAMES
            )
        elif building.name == "residence":
            occupied = occupied_island_spaces(player)
            bonus += 4 + max(0, occupied - 9)
        elif building.name == "fortress":
            colonists = (
                sum(1 for plantation in player.plantations if plantation.colonized)
                + player.occupied_quarries
                + sum(other.colonists for other in player.buildings)
                + player.colonists_unplaced
            )
            bonus += colonists // 3
        elif building.name == "customs_house":
            bonus += player.vp_chips // 4
        elif building.name == "city_hall":
            bonus += sum(
                1 for other in player.buildings if other.name not in PRODUCTION_NAMES
            )
    return bonus


def building_points(player: PlayerState) -> int:
    """Base victory points printed on every owned building."""
    return sum(BUILDINGS[building.name].victory_points for building in player.buildings)


def total_points(player: PlayerState) -> int:
    """Final score once the game ends: chips, buildings and end-game bonuses."""
    return player.vp_chips + building_points(player) + end_game_bonus(player)


def public_points(player: PlayerState) -> int:
    """Points others can see: buildings and bonuses, without hidden VP chips.

    The Customs House bonus counts chips, so it stays hidden as well."""
    customs = player.vp_chips // 4 if player.active("customs_house") else 0
    return building_points(player) + end_game_bonus(player) - customs


def sell_price(state: PuertoRicoState, player: PlayerId, good: Good) -> int:
    """Doubloons the trading house pays for one good."""
    owner = state.players[player]
    price = GOOD_PRICE[good]
    if owner.active("small_market"):
        price += 1
    if owner.active("large_market"):
        price += 2
    if role_chooser(state, "trader") == player:
        price += 1
    return price


def ship_victory_points(state: PuertoRicoState, player: PlayerId, quantity: int) -> int:
    """Victory point chips for loading `quantity` goods during the Captain action."""
    points = quantity
    owner = state.players[player]
    if role_chooser(state, "captain") == player and not owner.captain_first_load_done:
        points += 1
    if owner.active("harbor"):
        points += 1
    return points


def can_ship(state: PuertoRicoState, player: PlayerId, good: Good) -> tuple[int, ...]:
    """Indices of ships that may take `good` from this player."""
    owner = state.players[player]
    if goods_get(owner.goods, good) <= 0:
        return ()
    assigned = next(
        (index for index, ship in enumerate(state.cargo_ships) if ship.good == good),
        None,
    )
    if assigned is not None:
        ship = state.cargo_ships[assigned]
        return (assigned,) if not ship.full else ()
    return tuple(index for index, ship in enumerate(state.cargo_ships) if ship.empty)


def can_load_anything(state: PuertoRicoState, player: PlayerId) -> bool:
    """Whether the player has any legal Captain load, including a Wharf."""
    owner = state.players[player]
    if (
        owns_active(owner, "wharf")
        and not owner.wharf_used
        and goods_total(owner.goods)
    ):
        return True
    return any(
        goods_get(owner.goods, good) > 0 and can_ship(state, player, good)
        for good in GOODS
    )


def wharf_goods(state: PuertoRicoState, player: PlayerId) -> tuple[Good, ...]:
    """Good types a player may load on their active, unused Wharf."""
    owner = state.players[player]
    if not owns_active(owner, "wharf") or owner.wharf_used:
        return ()
    return tuple(good for good in GOODS if goods_get(owner.goods, good) > 0)


def build_cost(state: PuertoRicoState, player: PlayerId, name: str) -> int:
    """Effective cost after active quarries and the Builder privilege."""
    spec = BUILDINGS[name]
    owner = state.players[player]
    discount = min(owner.active_quarries, spec.victory_points)
    if role_chooser(state, "builder") == player:
        discount += 1
    return max(0, spec.cost - discount)


def available_to_build(state: PuertoRicoState, player: PlayerId) -> tuple[str, ...]:
    """Buildings the player can afford and has city space for, one per type."""
    owner = state.players[player]
    free_city = MAX_CITY_SPACES - city_spaces_used(owner)
    choices: list[str] = []
    seen: set[str] = set()
    for name in state.available_buildings:
        if name in seen or owner.owns(name):
            continue
        seen.add(name)
        spec = BUILDINGS[name]
        if free_city < (2 if spec.victory_points == 4 else 1):
            continue
        if owner.doubloons < build_cost(state, player, name):
            continue
        choices.append(name)
    return tuple(choices)


def next_unacted(state: PuertoRicoState, after: PlayerId) -> PlayerId | None:
    """Next seat in player order after `after` that has not acted this phase."""
    order = state.order
    start = order.index(after)
    for offset in range(1, len(order) + 1):
        candidate = order[(start + offset) % len(order)]
        if candidate not in state.players_acted:
            return candidate
    return None


def next_role_picker(state: PuertoRicoState) -> PlayerId | None:
    """Next seat in governor order that has not taken a role this round."""
    taken = {role.taken_by for role in state.roles if role.taken_by is not None}
    start = state.order.index(state.governor)
    for offset in range(len(state.order)):
        candidate = state.order[(start + offset) % len(state.order)]
        if candidate not in taken:
            return candidate
    return None


def next_player_in_order(state: PuertoRicoState, after: PlayerId) -> PlayerId:
    """Seat after `after` in the fixed player order, wrapping around."""
    index = state.order.index(after)
    return state.order[(index + 1) % len(state.order)]
