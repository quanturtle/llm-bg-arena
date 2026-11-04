"""Immutable model for a Terra Mystica match: board, players, actions and state."""

from dataclasses import dataclass, replace
from typing import Literal, cast

from boardgames.core import PlayerId, Rng
from boardgames.games.terra_mystica.constants import (
    BASE_MAP_ROWS,
    CULT_ORDER,
    CULT_POWER_THRESHOLDS,
    FACTION_BY_TYPE,
    MAX_BUILDINGS,
    POWER_VALUES,
    TERRAIN_WHEEL,
    BuildingType,
    Cost,
    Cult,
    CultPositions,
    FactionProfile,
    FactionType,
    Income,
    Resources,
    ScoringAction,
    Terrain,
)

type Phase = Literal["setup", "action", "game_over"]


@dataclass(frozen=True, order=True)
class Hex:
    """Axial coordinates for the pointy-top hex board."""

    q: int
    r: int

    def neighbours(self) -> tuple["Hex", ...]:
        """The six hexes sharing an edge with this one."""
        return (
            Hex(self.q + 1, self.r),
            Hex(self.q - 1, self.r),
            Hex(self.q, self.r + 1),
            Hex(self.q, self.r - 1),
            Hex(self.q + 1, self.r - 1),
            Hex(self.q - 1, self.r + 1),
        )

    def notation(self) -> str:
        return f"{self.q},{self.r}"


@dataclass(frozen=True)
class Building:
    """A structure on the board."""

    type: BuildingType
    owner: PlayerId
    in_town: bool = False

    @property
    def power_value(self) -> int:
        return POWER_VALUES[self.type]


@dataclass(frozen=True)
class Tile:
    """One map hex."""

    position: Hex
    terrain: Terrain
    building: Building | None = None

    @property
    def is_land(self) -> bool:
        return self.terrain is not Terrain.RIVER


def _base_tiles() -> tuple[tuple[Hex, Terrain], ...]:
    items: list[tuple[Hex, Terrain]] = []
    for r, row in enumerate(BASE_MAP_ROWS):
        start_q = -(r // 2)
        for offset, terrain in enumerate(row):
            items.append((Hex(start_q + offset, r), terrain))
    return tuple(items)


BASE_TILES: tuple[tuple[Hex, Terrain], ...] = _base_tiles()
HEX_INDEX: dict[Hex, int] = {
    position: index for index, (position, _) in enumerate(BASE_TILES)
}


@dataclass(frozen=True)
class Board:
    """The immutable base map and its buildings."""

    tiles: tuple[Tile, ...]

    @classmethod
    def base(cls) -> "Board":
        return cls(tuple(Tile(position, terrain) for position, terrain in BASE_TILES))

    def tile(self, position: Hex) -> Tile | None:
        index = HEX_INDEX.get(position)
        return None if index is None else self.tiles[index]

    def replace_tile(self, position: Hex, tile: Tile) -> "Board":
        index = HEX_INDEX[position]
        return Board((*self.tiles[:index], tile, *self.tiles[index + 1 :]))

    def place(self, position: Hex, building: Building) -> "Board":
        tile = self.tile(position)
        if tile is None:
            raise ValueError(f"no tile at {position}")
        if not tile.is_land:
            raise ValueError("cannot build on a river")
        if tile.building is not None:
            raise ValueError("tile is already occupied")
        return self.replace_tile(position, replace(tile, building=building))

    def occupied(self, player: PlayerId) -> tuple[Hex, ...]:
        return tuple(
            tile.position
            for tile in self.tiles
            if tile.building is not None and tile.building.owner == player
        )

    def buildings(self, player: PlayerId) -> tuple[tuple[Hex, Building], ...]:
        return tuple(
            (tile.position, tile.building)
            for tile in self.tiles
            if tile.building is not None and tile.building.owner == player
        )

    def adjacent_opponents(self, position: Hex, player: PlayerId) -> tuple[Hex, ...]:
        result: list[Hex] = []
        for neighbour in position.neighbours():
            tile = self.tile(neighbour)
            if (
                tile is not None
                and tile.building is not None
                and tile.building.owner != player
            ):
                result.append(neighbour)
        return tuple(result)

    def reachable_from(self, start: Hex, shipping: int) -> set[Hex]:
        """Land hexes reachable from one structure, crossing rivers up to `shipping`."""
        reachable: set[Hex] = set()
        for neighbour in start.neighbours():
            tile = self.tile(neighbour)
            if tile is None:
                continue
            if tile.is_land:
                reachable.add(neighbour)
            elif shipping > 0:
                self._river_targets(neighbour, shipping, reachable)
        return reachable

    def reachable_land(self, player: PlayerId, shipping: int) -> tuple[Hex, ...]:
        """Empty-or-not land hexes reachable from the player's structures."""
        reachable: set[Hex] = set()
        for start in self.occupied(player):
            reachable |= self.reachable_from(start, shipping)
        return tuple(tile.position for tile in self.tiles if tile.position in reachable)

    def connected_area(
        self, start: Hex, player: PlayerId, shipping: int
    ) -> tuple[Hex, ...]:
        """The player's area through `start`, including shipping crossings."""
        found: list[Hex] = []
        queue: list[Hex] = [start]
        seen: set[Hex] = {start}
        while queue:
            position = queue.pop(0)
            found.append(position)
            reachable = self.reachable_from(position, shipping)
            for other in self.occupied(player):
                if other not in seen and other in reachable:
                    seen.add(other)
                    queue.append(other)
        return tuple(found)

    def _river_targets(self, start: Hex, shipping: int, reachable: set[Hex]) -> None:
        queue: list[tuple[Hex, int]] = [(start, 1)]
        seen: set[Hex] = {start}
        while queue:
            river, depth = queue.pop(0)
            for neighbour in river.neighbours():
                tile = self.tile(neighbour)
                if tile is None:
                    continue
                if tile.is_land:
                    reachable.add(neighbour)
                elif depth < shipping and neighbour not in seen:
                    seen.add(neighbour)
                    queue.append((neighbour, depth + 1))

    def connected(self, start: Hex, player: PlayerId) -> tuple[Hex, ...]:
        """The player's connected structures through the start hex."""
        found: list[Hex] = []
        queue: list[Hex] = [start]
        seen: set[Hex] = {start}
        while queue:
            position = queue.pop(0)
            found.append(position)
            for neighbour in position.neighbours():
                tile = self.tile(neighbour)
                if (
                    tile is not None
                    and tile.building is not None
                    and tile.building.owner == player
                    and neighbour not in seen
                ):
                    seen.add(neighbour)
                    queue.append(neighbour)
        return tuple(found)

    def count(self, player: PlayerId, building: BuildingType) -> int:
        return sum(
            1
            for tile in self.tiles
            if tile.building is not None
            and tile.building.owner == player
            and tile.building.type is building
        )


@dataclass(frozen=True)
class PlayerState:
    """Everything one seat owns and has achieved."""

    faction: FactionType
    resources: Resources
    victory_points: int = 20
    cults: CultPositions = (0, 0, 0, 0)
    shipping: int = 0
    digging: int = 0
    keys: int = 0

    @property
    def profile(self) -> FactionProfile:
        return FACTION_BY_TYPE[self.faction]

    @property
    def home_terrain(self) -> Terrain:
        return self.profile.home_terrain

    def cult(self, cult: Cult) -> int:
        return self.cults[CULT_ORDER.index(cult)]

    def with_cult(self, cult: Cult, value: int) -> "PlayerState":
        index = CULT_ORDER.index(cult)
        values = list(self.cults)
        values[index] = value
        return replace(self, cults=cast(CultPositions, tuple(values)))


@dataclass(frozen=True)
class TerraMysticaConfig:
    """Table size and, for short matches, the number of rounds."""

    num_players: int = 2
    rounds: int = 6


@dataclass(frozen=True)
class TerraMysticaState:
    """The whole immutable state of one match."""

    config: TerraMysticaConfig
    rng: Rng
    board: Board
    players: tuple[PlayerState, ...]
    order: tuple[PlayerId, ...]
    active_player: PlayerId
    phase: Phase
    setup_queue: tuple[PlayerId, ...]
    passed: frozenset[PlayerId]
    pass_order: tuple[PlayerId, ...]
    round: int
    scoring: tuple[ScoringAction, ...]
    used_power_actions: frozenset[str]
    used_orders: frozenset[tuple[Cult, int]]
    end_reason: str | None = None


# --- Actions ----------------------------------------------------------------


@dataclass(frozen=True)
class BuildDwelling:
    """Transform a reachable tile if needed, then build a dwelling on it."""

    position: Hex


@dataclass(frozen=True)
class TransformTerrain:
    """Transform one reachable tile into the faction's home terrain."""

    position: Hex


@dataclass(frozen=True)
class UpgradeBuilding:
    """Upgrade one of the player's structures."""

    position: Hex
    to: BuildingType


@dataclass(frozen=True)
class AdvanceShipping:
    """Spend a priest and four coins to move one step on the shipping track."""


@dataclass(frozen=True)
class AdvanceDigging:
    """Spend the faction's digging cost to move one step on the exchange track."""


@dataclass(frozen=True)
class SendPriest:
    """Send a priest to an unused order space of a cult."""

    cult: Cult
    order: int


@dataclass(frozen=True)
class AdvanceCult:
    """Spend a priest to advance one cult space without using an order space."""

    cult: Cult


@dataclass(frozen=True)
class PowerAction:
    """Spend charged power for a resource from the shared power actions."""

    kind: Literal["priest", "workers", "coins"]


@dataclass(frozen=True)
class Pass:
    """Take no more actions this round."""


type Action = (
    BuildDwelling
    | TransformTerrain
    | UpgradeBuilding
    | AdvanceShipping
    | AdvanceDigging
    | SendPriest
    | AdvanceCult
    | PowerAction
    | Pass
)


# --- Helpers ----------------------------------------------------------------


def replace_at[T](items: tuple[T, ...], index: int, value: T) -> tuple[T, ...]:
    return (*items[:index], value, *items[index + 1 :])


def replace_player(
    state: TerraMysticaState, player: PlayerId, new_player: PlayerState
) -> TerraMysticaState:
    return replace(state, players=replace_at(state.players, player, new_player))


def income_with_power(resources: Resources, income: Income) -> Resources:
    """Add coins, workers and priests, and route power through the bowls."""
    updated = Resources(
        coins=resources.coins + income.coins,
        workers=resources.workers + income.workers,
        priests=resources.priests + income.priests,
        power1=resources.power1,
        power2=resources.power2,
        power3=resources.power3,
    )
    return gain_power(updated, income.power)


def gain_power(resources: Resources, amount: int) -> Resources:
    """Move power tokens forward through the bowls."""
    remaining = amount
    bowl1, bowl2, bowl3 = resources.power1, resources.power2, resources.power3
    if remaining > 0 and bowl1 > 0:
        moved = min(remaining, bowl1)
        bowl1 -= moved
        bowl2 += moved
        remaining -= moved
    if remaining > 0 and bowl2 > 0:
        moved = min(remaining, bowl2)
        bowl2 -= moved
        bowl3 += moved
    return replace(resources, power1=bowl1, power2=bowl2, power3=bowl3)


def spend_power(resources: Resources, amount: int) -> Resources | None:
    """Spend charged power, returning it to Bowl I, or None if it is short."""
    if resources.power3 < amount:
        return None
    return replace(
        resources,
        power1=resources.power1 + amount,
        power3=resources.power3 - amount,
    )


def can_pay(resources: Resources, cost: Cost) -> bool:
    return (
        resources.coins >= cost.coins
        and resources.workers >= cost.workers
        and resources.priests >= cost.priests
        and resources.power3 >= cost.power
    )


def pay(resources: Resources, cost: Cost) -> Resources:
    """Subtract a cost that `can_pay` has already accepted."""
    paid = replace(
        resources,
        coins=resources.coins - cost.coins,
        workers=resources.workers - cost.workers,
        priests=resources.priests - cost.priests,
    )
    if cost.power:
        spent = spend_power(paid, cost.power)
        assert spent is not None
        return spent
    return paid


def add_resources(resources: Resources, income: Income) -> Resources:
    return replace(
        resources,
        coins=resources.coins + income.coins,
        workers=resources.workers + income.workers,
        priests=resources.priests + income.priests,
        power1=resources.power1,
        power2=resources.power2,
        power3=resources.power3,
    )


def terrain_distance(source: Terrain, target: Terrain) -> int:
    """Shortest number of steps between two land terrains on the wheel."""
    if source is Terrain.RIVER or target is Terrain.RIVER:
        raise ValueError("rivers are not part of the terrain wheel")
    start = TERRAIN_WHEEL.index(source)
    end = TERRAIN_WHEEL.index(target)
    difference = abs(start - end)
    return min(difference, len(TERRAIN_WHEEL) - difference)


def spades_for(profile: FactionProfile, terrain: Terrain) -> int:
    """Spades needed to turn `terrain` into the faction's home terrain."""
    if terrain is profile.home_terrain:
        return 0
    if profile.terraform_spades is not None:
        return profile.terraform_spades
    return terrain_distance(terrain, profile.home_terrain)


def spade_cost(profile: FactionProfile, digging: int, spades: int) -> Cost:
    """The workers (or priests) needed to buy `spades`."""
    if spades <= 0:
        return Cost()
    if profile.uses_priests_for_spades:
        return Cost(priests=spades)
    workers_per_spade = max(1, 3 - digging)
    return Cost(workers=spades * workers_per_spade)


def building_cost(
    profile: FactionProfile, building: BuildingType, adjacent_opponent: bool
) -> Cost:
    base = {
        BuildingType.DWELLING: profile.costs.dwelling,
        BuildingType.TRADING_HOUSE: profile.costs.trading_house,
        BuildingType.TEMPLE: profile.costs.temple,
        BuildingType.STRONGHOLD: profile.costs.stronghold,
        BuildingType.SANCTUARY: profile.costs.sanctuary,
    }[building]
    if building is BuildingType.TRADING_HOUSE and adjacent_opponent:
        return replace(base, coins=base.coins // 2)
    return base


def shipping_cost() -> Cost:
    return Cost(priests=1, coins=4)


def shipping_points(level: int) -> int:
    """Victory points printed on the shipping space reached (2, 3, 4, ...)."""
    return level + 1


def cult_gain_power(old: int, new: int) -> int:
    return sum(
        amount
        for threshold, amount in CULT_POWER_THRESHOLDS.items()
        if old < threshold <= new
    )


def cult_limit(player: PlayerState, top_occupied: bool = False) -> int:
    """The furthest cult space the player may reach right now."""
    return 10 if player.keys > 0 and not top_occupied else 9


def advance_cult(
    player: PlayerState, cult: Cult, steps: int, top_occupied: bool = False
) -> tuple[PlayerState, int]:
    """Advance a cult, spending a key to enter space 10; return power gained."""
    current = player.cult(cult)
    limit = 10 if player.keys > 0 and not top_occupied else 9
    new = min(current + steps, limit)
    keys = player.keys
    if new == 10 and current < 10:
        keys -= 1
    gained = cult_gain_power(current, new)
    updated = player.with_cult(cult, new)
    updated = replace(
        updated,
        keys=keys,
        resources=gain_power(updated.resources, gained),
    )
    return updated, gained


def component_power(board: Board, positions: tuple[Hex, ...]) -> int:
    total = 0
    for position in positions:
        tile = board.tile(position)
        if tile is not None and tile.building is not None:
            total += tile.building.power_value
    return total


def component_has_sanctuary(board: Board, positions: tuple[Hex, ...]) -> bool:
    for position in positions:
        tile = board.tile(position)
        if (
            tile is not None
            and tile.building is not None
            and tile.building.type is BuildingType.SANCTUARY
        ):
            return True
    return False


def town_ready(board: Board, positions: tuple[Hex, ...]) -> bool:
    minimum = 3 if component_has_sanctuary(board, positions) else 4
    return len(positions) >= minimum and component_power(board, positions) >= 7


def mark_town(board: Board, positions: tuple[Hex, ...]) -> Board:
    for position in positions:
        tile = board.tile(position)
        if tile is None or tile.building is None:
            continue
        board = board.replace_tile(
            position, replace(tile, building=replace(tile.building, in_town=True))
        )
    return board


def settle_town(board: Board, position: Hex, player: PlayerId) -> tuple[Board, bool]:
    """Mark a new or expanded town; True when a new town was founded."""
    component = board.connected(position, player)
    already = any(
        (tile := board.tile(hex_position)) is not None
        and tile.building is not None
        and tile.building.in_town
        for hex_position in component
    )
    if already:
        return mark_town(board, component), False
    if town_ready(board, component):
        return mark_town(board, component), True
    return board, False


def building_counts(board: Board, player: PlayerId) -> dict[BuildingType, int]:
    return {building: board.count(player, building) for building in BuildingType}


def can_place_building(board: Board, player: PlayerId, building: BuildingType) -> bool:
    return board.count(player, building) < MAX_BUILDINGS[building]
