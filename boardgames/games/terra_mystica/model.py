"""Immutable model for a Terra Mystica match: board, players, actions and state."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Literal, cast

from boardgames.core import JsonValue, PlayerId, Rng
from boardgames.games.terra_mystica.constants import (
    BASE_MAP_ROWS,
    CULT_ORDER,
    CULT_POWER_THRESHOLDS,
    FACTION_BY_TYPE,
    FAVOR_TILES,
    MAX_BUILDINGS,
    POWER_VALUES,
    PRIEST_SUPPLY,
    TERRAIN_WHEEL,
    BuildingType,
    Cost,
    Cult,
    CultBonus,
    CultPositions,
    FactionProfile,
    FactionType,
    FavorTile,
    Income,
    PowerActionKind,
    Resources,
    ScoringTile,
    Terrain,
)

type Phase = Literal[
    "setup",
    "action",
    "cult_spades",
    "stronghold_convert",
    "town_choice",
    "favor_choice",
    "game_over",
]


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

    def distance(self, other: "Hex") -> int:
        """Hex distance, counting each edge as one step."""
        dq = self.q - other.q
        dr = self.r - other.r
        return (abs(dq) + abs(dr) + abs(dq + dr)) // 2


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

    def reachable_from(self, start: Hex, shipping: int, reach: int = 0) -> set[Hex]:
        """Land hexes reachable from one structure, crossing rivers up to `shipping`.

        `reach` is a faction's tunneling or carpet range in steps; it ignores rivers.
        """
        reachable: set[Hex] = set()
        for neighbour in start.neighbours():
            tile = self.tile(neighbour)
            if tile is None:
                continue
            if tile.is_land:
                reachable.add(neighbour)
            elif shipping > 0:
                self._river_targets(neighbour, shipping, reachable)
        if reach > 0:
            reachable.update(
                tile.position
                for tile in self.tiles
                if tile.is_land and start.distance(tile.position) <= reach
            )
        return reachable

    def reachable_land(
        self, player: PlayerId, shipping: int, reach: int = 0
    ) -> tuple[Hex, ...]:
        """Empty-or-not land hexes reachable from the player's structures."""
        reachable: set[Hex] = set()
        for start in self.occupied(player):
            reachable |= self.reachable_from(start, shipping, reach)
        return tuple(tile.position for tile in self.tiles if tile.position in reachable)

    def connected_area(
        self, start: Hex, player: PlayerId, shipping: int, reach: int = 0
    ) -> tuple[Hex, ...]:
        """The player's area through `start`, including shipping and faction reach."""
        found: list[Hex] = []
        queue: list[Hex] = [start]
        seen: set[Hex] = {start}
        while queue:
            position = queue.pop(0)
            found.append(position)
            reachable = self.reachable_from(position, shipping, reach)
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
    favors: frozenset[int] = frozenset()

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
    scoring: tuple[ScoringTile, ...]
    cult_spades: tuple[int, ...]
    used_power_actions: frozenset[PowerActionKind]
    used_orders: Mapping[tuple[Cult, int], PlayerId]
    towns: int = 0
    town_tiles: tuple[int, ...] = (2, 2, 2, 2, 2)
    pending_stronghold: bool = False
    pending_favors: int = 0
    pending_town: bool = False
    pending_town_position: Hex | None = None
    pending_town_river: Hex | None = None
    spade_return: Literal["round", "action"] = "round"
    spade_actor: PlayerId | None = None
    power_spade_tiles: tuple[Hex, ...] = ()
    spade_second: Hex | None = None
    spade_transformed: tuple[Hex, ...] = ()
    spade_intermediate: bool = False
    spade_reach_used: bool = False
    spade_topup: bool = True
    spade_require_all: bool = False
    end_reason: str | None = None


# --- Actions ----------------------------------------------------------------


@dataclass(frozen=True)
class BuildDwelling:
    """Transform a reachable tile if needed, then build a dwelling on it.

    Mermaids may set `river` to the one river space they ignore for a town.
    """

    position: Hex
    river: Hex | None = None


@dataclass(frozen=True)
class TransformTerrain:
    """Transform one reachable tile, by default into the faction's home terrain."""

    position: Hex
    to: Terrain | None = None


@dataclass(frozen=True)
class UpgradeBuilding:
    """Upgrade one of the player's structures.

    Mermaids may set `river` to the one river space they ignore for a town.
    """

    position: Hex
    to: BuildingType
    river: Hex | None = None


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
class ChooseStrongholdPriests:
    """The Darklings' stronghold reward: trade up to three workers for priests."""

    workers: int


@dataclass(frozen=True)
class TakeTownTile:
    """Choose one of the remaining town tiles after founding a town."""

    index: int


@dataclass(frozen=True)
class TakeFavorTile:
    """Choose one of the remaining temple favor tiles."""

    index: int


@dataclass(frozen=True)
class PowerAction:
    """Spend charged power for a resource from the shared power actions."""

    kind: PowerActionKind


@dataclass(frozen=True)
class UseCultSpade:
    """Spend available spades to transform a reachable tile."""

    position: Hex
    to: Terrain | None = None


@dataclass(frozen=True)
class SkipCultSpade:
    """Forfeit the rest of this player's spades."""


@dataclass(frozen=True)
class TradeVpForCoin:
    """The Alchemists' free trade: 1 victory point for 1 coin."""


@dataclass(frozen=True)
class TradeCoinsForVp:
    """The Alchemists' free trade: 2 coins for 1 victory point."""


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
    | ChooseStrongholdPriests
    | TakeTownTile
    | TakeFavorTile
    | PowerAction
    | UseCultSpade
    | SkipCultSpade
    | TradeVpForCoin
    | TradeCoinsForVp
    | Pass
)


# --- Helpers ----------------------------------------------------------------


def replace_at[T](items: tuple[T, ...], index: int, value: T) -> tuple[T, ...]:
    return (*items[:index], value, *items[index + 1 :])


def replace_player(
    state: TerraMysticaState, player: PlayerId, new_player: PlayerState
) -> TerraMysticaState:
    return replace(state, players=replace_at(state.players, player, new_player))


def favor_tiles(player: PlayerState) -> tuple[FavorTile, ...]:
    """The player's favor tiles in index order."""
    return tuple(FAVOR_TILES[index] for index in sorted(player.favors))


def available_favors(state: TerraMysticaState) -> tuple[int, ...]:
    """The favor tiles no player has taken."""
    taken = set().union(*(player.favors for player in state.players))
    return tuple(index for index in range(len(FAVOR_TILES)) if index not in taken)


def favor_income(player: PlayerState) -> Income:
    """The extra income from the player's favor tiles."""
    return Income(
        coins=sum(FAVOR_TILES[index].income.coins for index in player.favors),
        workers=sum(FAVOR_TILES[index].income.workers for index in player.favors),
        priests=sum(FAVOR_TILES[index].income.priests for index in player.favors),
        power=sum(FAVOR_TILES[index].income.power for index in player.favors),
    )


def favor_build_vp(player: PlayerState, building: BuildingType) -> int:
    """Victory points a favor tile pays when `building` is built."""
    return sum(
        vp
        for index in player.favors
        for kind, vp in FAVOR_TILES[index].build_vp
        if kind is building
    )


def favor_pass_vp(player: PlayerState, trading_houses: int) -> int:
    """Victory points a favor tile pays when the player passes."""
    total = 0
    for index in player.favors:
        values = FAVOR_TILES[index].pass_vp
        if values:
            total += values[min(trading_houses, len(values) - 1)]
    return total


def town_power(player: PlayerState) -> int:
    """The power a town needs for this player, after favor tile 4."""
    return 7 + sum(FAVOR_TILES[index].town_power for index in player.favors)


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


def power_shortfall(power3: int, amount: int) -> int:
    """How much Bowl II power must burn to pay `amount` from Bowl III."""
    return max(0, amount - power3)


def can_spend_power(resources: Resources, amount: int) -> bool:
    """Whether `amount` power can be taken from Bowl III, burning Bowl II if needed."""
    deficit = power_shortfall(resources.power3, amount)
    return deficit == 0 or resources.power2 >= 2 * deficit


def burn_power(resources: Resources, amount: int) -> Resources | None:
    """Move power from Bowl II to Bowl III, removing one token per step moved."""
    if not can_spend_power(resources, amount):
        return None
    deficit = power_shortfall(resources.power3, amount)
    return replace(
        resources,
        power2=resources.power2 - 2 * deficit,
        power3=resources.power3 + deficit,
    )


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


def add_income(resources: Resources, income: Income) -> Resources:
    return add_resources(resources, income)


def add_costs(first: Cost, second: Cost) -> Cost:
    return Cost(
        coins=first.coins + second.coins,
        workers=first.workers + second.workers,
        priests=first.priests + second.priests,
        power=first.power + second.power,
    )


def _claimed_priests(state: TerraMysticaState, player: PlayerId) -> int:
    return sum(1 for owner in state.used_orders.values() if owner == player)


def priest_capacity(state: TerraMysticaState, player: PlayerId) -> int:
    return PRIEST_SUPPLY - _claimed_priests(state, player)


def cap_priests(
    state: TerraMysticaState, player: PlayerId, resources: Resources
) -> Resources:
    return replace(
        resources, priests=min(resources.priests, priest_capacity(state, player))
    )


def terrain_distance(source: Terrain, target: Terrain) -> int:
    """Shortest number of steps between two land terrains on the wheel."""
    if source is Terrain.RIVER or target is Terrain.RIVER:
        raise ValueError("rivers are not part of the terrain wheel")
    start = TERRAIN_WHEEL.index(source)
    end = TERRAIN_WHEEL.index(target)
    difference = abs(start - end)
    return min(difference, len(TERRAIN_WHEEL) - difference)


def terrain_toward(source: Terrain, target: Terrain, steps: int) -> Terrain:
    """Move `steps` along the shortest wheel path from `source` toward `target`."""
    if source is Terrain.RIVER or target is Terrain.RIVER:
        raise ValueError("rivers are not part of the terrain wheel")
    distance = terrain_distance(source, target)
    if steps >= distance:
        return target
    start = TERRAIN_WHEEL.index(source)
    end = TERRAIN_WHEEL.index(target)
    step = 1 if (end - start) % len(TERRAIN_WHEEL) <= len(TERRAIN_WHEEL) // 2 else -1
    return TERRAIN_WHEEL[(start + step * steps) % len(TERRAIN_WHEEL)]


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


def effective_reach(board: Board, player: PlayerId, profile: FactionProfile) -> int:
    """The faction's tunneling or carpet range, including a stronghold bonus."""
    if profile.reach <= 0:
        return 0
    has_stronghold = board.count(player, BuildingType.STRONGHOLD) > 0
    if has_stronghold and profile.reach_with_stronghold > profile.reach:
        return profile.reach_with_stronghold
    return profile.reach


def effective_reach_cost(
    board: Board, player: PlayerId, profile: FactionProfile
) -> Cost:
    """What one tunnel or carpet flight costs, after a stronghold discount."""
    if profile.reach <= 0:
        return Cost()
    has_stronghold = board.count(player, BuildingType.STRONGHOLD) > 0
    if has_stronghold and profile.reach_cost_with_stronghold is not None:
        return profile.reach_cost_with_stronghold
    return profile.reach_cost


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


def shipping_points(level: int, shipping_start: int) -> int:
    """Victory points on the reached space: 2, 3, 4, ... from the faction's start."""
    return level - shipping_start + 1


def cult_bonus_json(bonus: CultBonus) -> dict[str, JsonValue]:
    """The observation shape of one round tile's cult bonus."""
    return {
        "cult": bonus.cult.value,
        "per": bonus.per,
        "reward": bonus.reward,
        "amount": bonus.amount,
    }


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
    limit = cult_limit(player, top_occupied)
    new = min(current + steps, max(limit, current))
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


def town_ready(board: Board, positions: tuple[Hex, ...], power: int = 7) -> bool:
    minimum = 3 if component_has_sanctuary(board, positions) else 4
    return len(positions) >= minimum and component_power(board, positions) >= power


def mark_town(board: Board, positions: tuple[Hex, ...]) -> Board:
    for position in positions:
        tile = board.tile(position)
        if tile is None or tile.building is None:
            continue
        board = board.replace_tile(
            position, replace(tile, building=replace(tile.building, in_town=True))
        )
    return board


def town_component(
    board: Board,
    position: Hex,
    player: PlayerId,
    river: Hex | None = None,
) -> tuple[Hex, ...]:
    """The structures in a town component, optionally crossing one river."""
    direct = set(board.connected(position, player))
    if river is None:
        return tuple(direct)
    river_tile = board.tile(river)
    if river_tile is None or river_tile.is_land:
        return tuple(direct)
    across = {
        neighbour
        for neighbour in river.neighbours()
        if (tile := board.tile(neighbour)) is not None
        and tile.building is not None
        and tile.building.owner == player
    }
    if not (direct & across):
        return tuple(direct)
    component = set(direct)
    for start in across:
        component |= set(board.connected(start, player))
    return tuple(component)


def settle_town(
    board: Board,
    position: Hex,
    player: PlayerId,
    *,
    towns_left: int,
    power: int = 7,
    river: Hex | None = None,
) -> tuple[Board, bool]:
    """Mark a new or expanded town; True when a new town was founded.

    Towns need direct adjacency; Mermaids may ignore the one river space `river`.
    """
    component = town_component(board, position, player, river)
    already = any(
        (tile := board.tile(hex_position)) is not None
        and tile.building is not None
        and tile.building.in_town
        for hex_position in component
    )
    if already:
        return mark_town(board, component), False
    if towns_left <= 0:
        return board, False
    if town_ready(board, component, power):
        return mark_town(board, component), True
    return board, False


def building_counts(board: Board, player: PlayerId) -> dict[BuildingType, int]:
    return {building: board.count(player, building) for building in BuildingType}


def can_place_building(board: Board, player: PlayerId, building: BuildingType) -> bool:
    return board.count(player, building) < MAX_BUILDINGS[building]
