"""Static tables for Puerto Rico: goods, buildings, roles and setup counts.

All values follow the standard base game. Buildings are identified by their
lower-case name; every table here is keyed by that name.
"""

from typing import Literal

type Good = Literal["corn", "indigo", "sugar", "tobacco", "coffee"]
type Role = Literal[
    "settler",
    "mayor",
    "builder",
    "craftsman",
    "trader",
    "captain",
    "prospector",
    "prospector_2",
]

GOODS: tuple[Good, ...] = ("corn", "indigo", "sugar", "tobacco", "coffee")
GOOD_INDEX: dict[Good, int] = {good: index for index, good in enumerate(GOODS)}

# Sale price in the trading house, before markets and the Trader privilege.
GOOD_PRICE: dict[Good, int] = {
    "corn": 0,
    "indigo": 1,
    "sugar": 2,
    "tobacco": 3,
    "coffee": 4,
}

# Goods in the bank at the start of the game.
GOOD_SUPPLY: tuple[int, int, int, int, int] = (10, 11, 11, 9, 9)

# Plantation tiles by type. Quarries are drawn from a separate supply.
PLANTATION_TILES: dict[Good, int] = {
    "corn": 10,
    "indigo": 12,
    "sugar": 11,
    "tobacco": 9,
    "coffee": 8,
}
QUARRY_SUPPLY = 8


class BuildingKind:
    """Categories used by the end-game bonuses."""

    PRODUCTION = "production"
    VIOLET = "violet"


class ProductionSize:
    """Production buildings are small (1 colonist) or large (3 or 2)."""

    SMALL = "small"
    LARGE = "large"


class BuildingSpec:
    """One building: cost, base victory points, colonists and special effect."""

    __slots__ = (
        "copies",
        "cost",
        "kind",
        "max_colonists",
        "name",
        "production",
        "size",
        "victory_points",
    )

    def __init__(
        self,
        name: str,
        cost: int,
        victory_points: int,
        max_colonists: int,
        production: Good | None,
        kind: str,
        size: str | None,
        copies: int,
    ) -> None:
        self.name = name
        self.cost = cost
        self.victory_points = victory_points
        self.max_colonists = max_colonists
        self.production = production
        self.kind = kind
        self.size = size
        self.copies = copies

    @property
    def is_production(self) -> bool:
        return self.production is not None

    @property
    def is_small_production(self) -> bool:
        return self.production is not None and self.size == ProductionSize.SMALL

    @property
    def is_large_production(self) -> bool:
        return self.production is not None and self.size == ProductionSize.LARGE

    @property
    def is_violet(self) -> bool:
        return self.kind == BuildingKind.VIOLET

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"BuildingSpec({self.name!r}, cost={self.cost})"


def _build(
    name: str,
    cost: int,
    vp: int,
    colonists: int,
    production: Good | None,
    kind: str,
    size: str | None,
    copies: int,
) -> BuildingSpec:
    return BuildingSpec(name, cost, vp, colonists, production, kind, size, copies)


# Production buildings.
SMALL_INDIGO = _build(
    "small_indigo_plant",
    1,
    1,
    1,
    "indigo",
    BuildingKind.PRODUCTION,
    ProductionSize.SMALL,
    4,
)
INDIGO_PLANT = _build(
    "indigo_plant", 3, 2, 3, "indigo", BuildingKind.PRODUCTION, ProductionSize.LARGE, 3
)
SMALL_SUGAR = _build(
    "small_sugar_mill",
    2,
    1,
    1,
    "sugar",
    BuildingKind.PRODUCTION,
    ProductionSize.SMALL,
    4,
)
SUGAR_MILL = _build(
    "sugar_mill", 4, 2, 3, "sugar", BuildingKind.PRODUCTION, ProductionSize.LARGE, 3
)
TOBACCO_STORAGE = _build(
    "tobacco_storage",
    5,
    3,
    3,
    "tobacco",
    BuildingKind.PRODUCTION,
    ProductionSize.LARGE,
    3,
)
COFFEE_ROASTER = _build(
    "coffee_roaster",
    6,
    3,
    2,
    "coffee",
    BuildingKind.PRODUCTION,
    ProductionSize.LARGE,
    3,
)

# Violet buildings.
SMALL_MARKET = _build("small_market", 1, 1, 1, None, BuildingKind.VIOLET, None, 2)
HACIENDA = _build("hacienda", 2, 1, 1, None, BuildingKind.VIOLET, None, 2)
CONSTRUCTION_HUT = _build(
    "construction_hut", 2, 1, 1, None, BuildingKind.VIOLET, None, 2
)
SMALL_WAREHOUSE = _build("small_warehouse", 3, 1, 1, None, BuildingKind.VIOLET, None, 2)
HOSPICE = _build("hospice", 4, 2, 1, None, BuildingKind.VIOLET, None, 2)
OFFICE = _build("office", 5, 2, 1, None, BuildingKind.VIOLET, None, 2)
LARGE_MARKET = _build("large_market", 5, 2, 1, None, BuildingKind.VIOLET, None, 2)
LARGE_WAREHOUSE = _build("large_warehouse", 6, 2, 1, None, BuildingKind.VIOLET, None, 2)
FACTORY = _build("factory", 7, 3, 1, None, BuildingKind.VIOLET, None, 2)
UNIVERSITY = _build("university", 8, 3, 1, None, BuildingKind.VIOLET, None, 2)
HARBOR = _build("harbor", 8, 3, 1, None, BuildingKind.VIOLET, None, 2)
WHARF = _build("wharf", 9, 3, 1, None, BuildingKind.VIOLET, None, 2)
GUILD_HALL = _build("guild_hall", 10, 4, 1, None, BuildingKind.VIOLET, None, 1)
RESIDENCE = _build("residence", 10, 4, 1, None, BuildingKind.VIOLET, None, 1)
FORTRESS = _build("fortress", 10, 4, 1, None, BuildingKind.VIOLET, None, 1)
CUSTOMS_HOUSE = _build("customs_house", 10, 4, 1, None, BuildingKind.VIOLET, None, 1)
CITY_HALL = _build("city_hall", 10, 4, 1, None, BuildingKind.VIOLET, None, 1)

BUILDINGS: dict[str, BuildingSpec] = {
    spec.name: spec
    for spec in (
        SMALL_INDIGO,
        INDIGO_PLANT,
        SMALL_SUGAR,
        SUGAR_MILL,
        TOBACCO_STORAGE,
        COFFEE_ROASTER,
        SMALL_MARKET,
        HACIENDA,
        CONSTRUCTION_HUT,
        SMALL_WAREHOUSE,
        HOSPICE,
        OFFICE,
        LARGE_MARKET,
        LARGE_WAREHOUSE,
        FACTORY,
        UNIVERSITY,
        HARBOR,
        WHARF,
        GUILD_HALL,
        RESIDENCE,
        FORTRESS,
        CUSTOMS_HOUSE,
        CITY_HALL,
    )
}

BUILDING_NAMES: tuple[str, ...] = tuple(BUILDINGS)

# Buildings that count for the Guild Hall bonus.
SMALL_PRODUCTION_NAMES: frozenset[str] = frozenset(
    spec.name for spec in BUILDINGS.values() if spec.is_small_production
)
LARGE_PRODUCTION_NAMES: frozenset[str] = frozenset(
    spec.name for spec in BUILDINGS.values() if spec.is_large_production
)
PRODUCTION_NAMES: frozenset[str] = SMALL_PRODUCTION_NAMES | LARGE_PRODUCTION_NAMES

# Role cards by player count. 3 players use the six base roles, 4 adds one
# prospector and 5 adds a second prospector.
ROLES_BY_PLAYERS: dict[int, tuple[Role, ...]] = {
    3: ("settler", "mayor", "builder", "craftsman", "trader", "captain"),
    4: ("settler", "mayor", "builder", "craftsman", "trader", "captain", "prospector"),
    5: (
        "settler",
        "mayor",
        "builder",
        "craftsman",
        "trader",
        "captain",
        "prospector",
        "prospector_2",
    ),
}

STARTING_DOUBLOONS: dict[int, int] = {3: 2, 4: 3, 5: 4}
COLONIST_SUPPLY: dict[int, int] = {3: 55, 4: 75, 5: 95}
VICTORY_POINT_SUPPLY: dict[int, int] = {3: 75, 4: 100, 5: 122}
SHIP_CAPACITIES: dict[int, tuple[int, int, int]] = {
    3: (4, 5, 6),
    4: (5, 6, 7),
    5: (6, 7, 8),
}

MAX_ISLAND_SPACES = 12
MAX_CITY_SPACES = 12
TRADING_HOUSE_SPACES = 4
