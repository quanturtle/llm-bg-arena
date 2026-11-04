"""Static data for Terra Mystica: terrains, factions, costs and the base map.

Everything here is immutable and shared. The mutable match state lives in
``model.py``; the rules live in ``game.py``.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Literal


class Terrain(Enum):
    """The seven land terrains plus river, in wheel order."""

    PLAINS = "plains"
    SWAMP = "swamp"
    LAKE = "lake"
    FOREST = "forest"
    MOUNTAIN = "mountain"
    WASTELAND = "wasteland"
    DESERT = "desert"
    RIVER = "river"


class FactionType(Enum):
    """The fourteen base-game factions."""

    ALCHEMISTS = "alchemists"
    AUREN = "auren"
    CHAOS_MAGICIANS = "chaos_magicians"
    CULTISTS = "cultists"
    DARKLINGS = "darklings"
    DWARVES = "dwarves"
    ENGINEERS = "engineers"
    FAKIRS = "fakirs"
    GIANTS = "giants"
    HALFLINGS = "halflings"
    MERMAIDS = "mermaids"
    NOMADS = "nomads"
    SWARMLINGS = "swarmlings"
    WITCHES = "witches"


class BuildingType(Enum):
    """The five structures."""

    DWELLING = "dwelling"
    TRADING_HOUSE = "trading_house"
    TEMPLE = "temple"
    STRONGHOLD = "stronghold"
    SANCTUARY = "sanctuary"


class Cult(Enum):
    """The four cult tracks."""

    FIRE = "fire"
    WATER = "water"
    EARTH = "earth"
    AIR = "air"


class ScoringAction(Enum):
    """What a round's scoring tile rewards."""

    DWELLING = "dwelling"
    TRADING_HOUSE = "trading_house"
    STRONGHOLD = "stronghold"
    SANCTUARY = "sanctuary"
    SPADE = "spade"
    TOWN = "town"


@dataclass(frozen=True)
class Resources:
    """A player's resources and power bowls."""

    coins: int = 0
    workers: int = 0
    priests: int = 0
    power1: int = 0
    power2: int = 0
    power3: int = 0

    @property
    def power(self) -> int:
        """Total power tokens in the three bowls."""
        return self.power1 + self.power2 + self.power3


@dataclass(frozen=True)
class Cost:
    """A price in resources; power is paid from Bowl III."""

    coins: int = 0
    workers: int = 0
    priests: int = 0
    power: int = 0


@dataclass(frozen=True)
class Income:
    """Resources gained in an income phase."""

    coins: int = 0
    workers: int = 0
    priests: int = 0
    power: int = 0
    victory_points: int = 0


@dataclass(frozen=True)
class BuildingCosts:
    """The five building prices shown on a faction board."""

    dwelling: Cost
    trading_house: Cost
    temple: Cost
    stronghold: Cost
    sanctuary: Cost


type CultPositions = tuple[int, int, int, int]
"""Cult positions ordered Fire, Water, Earth, Air."""


@dataclass(frozen=True)
class FactionProfile:
    """Static identity, starting state and rules exceptions of a faction."""

    type: FactionType
    name: str
    home_terrain: Terrain
    color: str
    description: str
    starting_resources: Resources
    starting_cults: CultPositions
    costs: BuildingCosts = BuildingCosts(
        dwelling=Cost(coins=2, workers=1),
        trading_house=Cost(coins=6, workers=2),
        temple=Cost(coins=5, workers=2),
        stronghold=Cost(coins=6, workers=4),
        sanctuary=Cost(coins=6, workers=4),
    )
    starting_dwellings: int = 2
    shipping_start: int = 0
    shipping_max: int = 3
    can_ship: bool = True
    digging_start: int = 0
    digging_max: int = 2
    can_dig: bool = True
    digging_cost: Cost = Cost(workers=2, coins=5, priests=1)
    terraform_spades: int | None = None
    uses_priests_for_spades: bool = False
    spade_vp_bonus: int = 0
    town_vp_bonus: int = 0
    town_workers_bonus: int = 0
    final_coin_divisor: int = 3
    base_income: Income = Income(workers=1)
    dwelling_income: tuple[Income, ...] = ()
    trading_house_income: tuple[Income, ...] = ()
    temple_income: tuple[Income, ...] = ()
    sanctuary_income: Income = Income(priests=1)
    stronghold_income: Income = Income(power=2)


# --- Tables -----------------------------------------------------------------

CULT_ORDER: tuple[Cult, ...] = (Cult.FIRE, Cult.WATER, Cult.EARTH, Cult.AIR)
TERRAIN_WHEEL: tuple[Terrain, ...] = (
    Terrain.PLAINS,
    Terrain.SWAMP,
    Terrain.LAKE,
    Terrain.FOREST,
    Terrain.MOUNTAIN,
    Terrain.WASTELAND,
    Terrain.DESERT,
)

POWER_VALUES: dict[BuildingType, int] = {
    BuildingType.DWELLING: 1,
    BuildingType.TRADING_HOUSE: 2,
    BuildingType.TEMPLE: 2,
    BuildingType.STRONGHOLD: 3,
    BuildingType.SANCTUARY: 3,
}

MAX_BUILDINGS: dict[BuildingType, int] = {
    BuildingType.DWELLING: 8,
    BuildingType.TRADING_HOUSE: 4,
    BuildingType.TEMPLE: 3,
    BuildingType.STRONGHOLD: 1,
    BuildingType.SANCTUARY: 1,
}

CULT_ORDER_STEPS: tuple[int, ...] = (3, 2, 2, 2)
CULT_POWER_THRESHOLDS: dict[int, int] = {3: 1, 5: 2, 7: 2, 10: 3}
PRIEST_SUPPLY = 7
CULT_FINAL_POINTS: tuple[int, ...] = (8, 4, 2)
AREA_FINAL_POINTS: tuple[int, ...] = (18, 12, 6)

SCORING_VALUES: dict[ScoringAction, int] = {
    ScoringAction.DWELLING: 2,
    ScoringAction.TRADING_HOUSE: 3,
    ScoringAction.STRONGHOLD: 5,
    ScoringAction.SANCTUARY: 5,
    ScoringAction.SPADE: 2,
    ScoringAction.TOWN: 5,
}


type CultReward = Literal["priests", "workers", "coins", "power", "spades"]


@dataclass(frozen=True)
class CultBonus:
    """A round tile's end-of-round reward per `per` spaces on one cult track."""

    cult: Cult
    per: int
    reward: CultReward
    amount: int = 1


@dataclass(frozen=True)
class ScoringTile:
    """A round tile: the action it scores and its end-of-round cult bonus."""

    action: ScoringAction
    bonus: CultBonus


SCORING_TILES: tuple[ScoringTile, ...] = (
    ScoringTile(ScoringAction.DWELLING, CultBonus(Cult.WATER, 4, "priests")),
    ScoringTile(ScoringAction.DWELLING, CultBonus(Cult.FIRE, 4, "power", 4)),
    ScoringTile(ScoringAction.TRADING_HOUSE, CultBonus(Cult.AIR, 4, "spades")),
    ScoringTile(ScoringAction.TRADING_HOUSE, CultBonus(Cult.WATER, 4, "spades")),
    ScoringTile(ScoringAction.STRONGHOLD, CultBonus(Cult.AIR, 2, "workers")),
    ScoringTile(ScoringAction.SANCTUARY, CultBonus(Cult.FIRE, 2, "workers")),
    ScoringTile(ScoringAction.SPADE, CultBonus(Cult.EARTH, 1, "coins")),
    ScoringTile(ScoringAction.TOWN, CultBonus(Cult.EARTH, 4, "spades")),
)

STANDARD_DWELLING_INCOME: tuple[Income, ...] = (
    Income(workers=1),
    Income(workers=2),
    Income(workers=3),
    Income(workers=4),
    Income(workers=5),
    Income(workers=6),
    Income(workers=7),
    Income(workers=7),
)

STANDARD_TRADING_HOUSE_INCOME: tuple[Income, ...] = (
    Income(coins=2, power=1),
    Income(coins=4, power=2),
    Income(coins=6, power=4),
    Income(coins=8, power=6),
)

STANDARD_TEMPLE_INCOME: tuple[Income, ...] = (
    Income(priests=1),
    Income(priests=2),
    Income(priests=3),
)

POWER_ACTION_COSTS: dict[str, int] = {
    "priest": 3,
    "workers": 4,
    "coins": 4,
}

POWER_ACTION_INCOME: dict[str, Income] = {
    "priest": Income(priests=1),
    "workers": Income(workers=2),
    "coins": Income(coins=7),
}

# Cumulative incomes for factions whose trading houses or temples differ.
NOMAD_TRADING_HOUSE_INCOME: tuple[Income, ...] = (
    Income(coins=2, power=1),
    Income(coins=4, power=2),
    Income(coins=7, power=3),
    Income(coins=11, power=4),
)
DWARF_TRADING_HOUSE_INCOME: tuple[Income, ...] = (
    Income(coins=3, power=1),
    Income(coins=5, power=2),
    Income(coins=7, power=4),
    Income(coins=10, power=6),
)
SWARMLING_TRADING_HOUSE_INCOME: tuple[Income, ...] = (
    Income(coins=2, power=2),
    Income(coins=4, power=4),
    Income(coins=6, power=6),
    Income(coins=9, power=8),
)
ENGINEER_TEMPLE_INCOME: tuple[Income, ...] = (
    Income(priests=1),
    Income(priests=1, power=5),
    Income(priests=2, power=5),
)
ENGINEER_DWELLING_INCOME: tuple[Income, ...] = (
    Income(workers=1),
    Income(workers=2),
    Income(workers=2),
    Income(workers=3),
    Income(workers=4),
    Income(workers=4),
    Income(workers=5),
    Income(workers=5),
)

ENGINEER_COSTS = BuildingCosts(
    dwelling=Cost(coins=1, workers=1),
    trading_house=Cost(coins=4, workers=1),
    temple=Cost(coins=4, workers=1),
    stronghold=Cost(coins=6, workers=3),
    sanctuary=Cost(coins=6, workers=3),
)

SWARMLING_COSTS = BuildingCosts(
    dwelling=Cost(coins=3, workers=2),
    trading_house=Cost(coins=8, workers=3),
    temple=Cost(coins=6, workers=3),
    stronghold=Cost(coins=8, workers=5),
    sanctuary=Cost(coins=8, workers=5),
)

FACTION_PROFILES: tuple[FactionProfile, ...] = (
    FactionProfile(
        type=FactionType.ALCHEMISTS,
        name="Alchemists",
        home_terrain=Terrain.SWAMP,
        color="black",
        description="Philosophers who trade victory points and coins.",
        starting_resources=Resources(coins=15, workers=3, power1=5, power2=7),
        starting_cults=(1, 1, 0, 0),
        trading_house_income=NOMAD_TRADING_HOUSE_INCOME,
        stronghold_income=Income(coins=6),
        final_coin_divisor=2,
    ),
    FactionProfile(
        type=FactionType.AUREN,
        name="Auren",
        home_terrain=Terrain.FOREST,
        color="green",
        description="Forest folk who advance on the cult tracks.",
        starting_resources=Resources(coins=15, workers=3, power1=5, power2=7),
        starting_cults=(0, 1, 0, 1),
        costs=BuildingCosts(
            dwelling=Cost(coins=2, workers=1),
            trading_house=Cost(coins=6, workers=2),
            temple=Cost(coins=5, workers=2),
            stronghold=Cost(coins=6, workers=4),
            sanctuary=Cost(coins=8, workers=4),
        ),
    ),
    FactionProfile(
        type=FactionType.CHAOS_MAGICIANS,
        name="Chaos Magicians",
        home_terrain=Terrain.WASTELAND,
        color="red",
        description="Mages who begin with a single dwelling.",
        starting_resources=Resources(coins=15, workers=4, power1=5, power2=7),
        starting_cults=(2, 0, 0, 0),
        starting_dwellings=1,
        costs=BuildingCosts(
            dwelling=Cost(coins=2, workers=1),
            trading_house=Cost(coins=6, workers=2),
            temple=Cost(coins=5, workers=2),
            stronghold=Cost(coins=4, workers=4),
            sanctuary=Cost(coins=8, workers=4),
        ),
        stronghold_income=Income(workers=2),
    ),
    FactionProfile(
        type=FactionType.CULTISTS,
        name="Cultists",
        home_terrain=Terrain.PLAINS,
        color="brown",
        description="Devout people who spread their faith.",
        starting_resources=Resources(coins=15, workers=3, power1=5, power2=7),
        starting_cults=(1, 0, 1, 0),
        costs=BuildingCosts(
            dwelling=Cost(coins=2, workers=1),
            trading_house=Cost(coins=6, workers=2),
            temple=Cost(coins=5, workers=2),
            stronghold=Cost(coins=8, workers=4),
            sanctuary=Cost(coins=8, workers=4),
        ),
    ),
    FactionProfile(
        type=FactionType.DARKLINGS,
        name="Darklings",
        home_terrain=Terrain.SWAMP,
        color="black",
        description="Shadow folk who pay priests to terraform.",
        starting_resources=Resources(
            coins=15, workers=1, priests=1, power1=5, power2=7
        ),
        starting_cults=(0, 1, 1, 0),
        can_dig=False,
        uses_priests_for_spades=True,
        spade_vp_bonus=2,
        costs=BuildingCosts(
            dwelling=Cost(coins=2, workers=1),
            trading_house=Cost(coins=6, workers=2),
            temple=Cost(coins=5, workers=2),
            stronghold=Cost(coins=6, workers=4),
            sanctuary=Cost(coins=10, workers=4),
        ),
        sanctuary_income=Income(priests=2),
    ),
    FactionProfile(
        type=FactionType.DWARVES,
        name="Dwarves",
        home_terrain=Terrain.MOUNTAIN,
        color="grey",
        description="Miners who tunnel through mountains.",
        starting_resources=Resources(coins=15, workers=3, power1=5, power2=7),
        starting_cults=(0, 0, 2, 0),
        can_ship=False,
        trading_house_income=DWARF_TRADING_HOUSE_INCOME,
    ),
    FactionProfile(
        type=FactionType.ENGINEERS,
        name="Engineers",
        home_terrain=Terrain.MOUNTAIN,
        color="grey",
        description="Builders with cheap structures and bridges.",
        starting_resources=Resources(coins=10, workers=2, power1=3, power2=9),
        starting_cults=(0, 0, 0, 0),
        costs=ENGINEER_COSTS,
        base_income=Income(),
        dwelling_income=ENGINEER_DWELLING_INCOME,
        temple_income=ENGINEER_TEMPLE_INCOME,
    ),
    FactionProfile(
        type=FactionType.FAKIRS,
        name="Fakirs",
        home_terrain=Terrain.DESERT,
        color="yellow",
        description="Mystics who fly on carpets.",
        starting_resources=Resources(coins=15, workers=3, power1=7, power2=5),
        starting_cults=(1, 0, 0, 1),
        can_ship=False,
        digging_max=1,
        costs=BuildingCosts(
            dwelling=Cost(coins=2, workers=1),
            trading_house=Cost(coins=6, workers=2),
            temple=Cost(coins=5, workers=2),
            stronghold=Cost(coins=10, workers=4),
            sanctuary=Cost(coins=6, workers=4),
        ),
        stronghold_income=Income(priests=1),
    ),
    FactionProfile(
        type=FactionType.GIANTS,
        name="Giants",
        home_terrain=Terrain.WASTELAND,
        color="red",
        description="Giant folk with fixed terraforming costs.",
        starting_resources=Resources(coins=15, workers=3, power1=5, power2=7),
        starting_cults=(1, 0, 0, 1),
        terraform_spades=2,
        stronghold_income=Income(power=4),
    ),
    FactionProfile(
        type=FactionType.HALFLINGS,
        name="Halflings",
        home_terrain=Terrain.PLAINS,
        color="brown",
        description="Farmers who gain victory points for digging.",
        starting_resources=Resources(coins=15, workers=3, power1=3, power2=9),
        starting_cults=(0, 0, 1, 1),
        digging_cost=Cost(workers=2, coins=1, priests=1),
        spade_vp_bonus=1,
        costs=BuildingCosts(
            dwelling=Cost(coins=2, workers=1),
            trading_house=Cost(coins=6, workers=2),
            temple=Cost(coins=5, workers=2),
            stronghold=Cost(coins=8, workers=4),
            sanctuary=Cost(coins=6, workers=4),
        ),
    ),
    FactionProfile(
        type=FactionType.MERMAIDS,
        name="Mermaids",
        home_terrain=Terrain.LAKE,
        color="blue",
        description="Water creatures who sail far along rivers.",
        starting_resources=Resources(coins=15, workers=3, power1=3, power2=9),
        starting_cults=(0, 2, 0, 0),
        shipping_start=1,
        shipping_max=5,
        costs=BuildingCosts(
            dwelling=Cost(coins=2, workers=1),
            trading_house=Cost(coins=6, workers=2),
            temple=Cost(coins=5, workers=2),
            stronghold=Cost(coins=6, workers=4),
            sanctuary=Cost(coins=8, workers=4),
        ),
        stronghold_income=Income(power=4),
    ),
    FactionProfile(
        type=FactionType.NOMADS,
        name="Nomads",
        home_terrain=Terrain.DESERT,
        color="yellow",
        description="Desert wanderers who start with three dwellings.",
        starting_resources=Resources(coins=15, workers=2, power1=5, power2=7),
        starting_cults=(1, 0, 1, 0),
        starting_dwellings=3,
        costs=BuildingCosts(
            dwelling=Cost(coins=2, workers=1),
            trading_house=Cost(coins=6, workers=2),
            temple=Cost(coins=5, workers=2),
            stronghold=Cost(coins=8, workers=4),
            sanctuary=Cost(coins=6, workers=4),
        ),
        trading_house_income=NOMAD_TRADING_HOUSE_INCOME,
    ),
    FactionProfile(
        type=FactionType.SWARMLINGS,
        name="Swarmlings",
        home_terrain=Terrain.LAKE,
        color="blue",
        description="A numerous people with expensive buildings.",
        starting_resources=Resources(coins=20, workers=8, power1=3, power2=9),
        starting_cults=(1, 1, 1, 1),
        costs=SWARMLING_COSTS,
        base_income=Income(workers=2),
        trading_house_income=SWARMLING_TRADING_HOUSE_INCOME,
        sanctuary_income=Income(priests=2),
        stronghold_income=Income(power=4),
        town_workers_bonus=3,
    ),
    FactionProfile(
        type=FactionType.WITCHES,
        name="Witches",
        home_terrain=Terrain.FOREST,
        color="green",
        description="Forest dwellers who score extra for towns.",
        starting_resources=Resources(coins=15, workers=3, power1=5, power2=7),
        starting_cults=(0, 0, 0, 2),
        town_vp_bonus=5,
    ),
)

FACTIONS: tuple[FactionType, ...] = tuple(profile.type for profile in FACTION_PROFILES)
FACTION_BY_TYPE: dict[FactionType, FactionProfile] = {
    profile.type: profile for profile in FACTION_PROFILES
}
FACTIONS_BY_TERRAIN: dict[Terrain, tuple[FactionType, ...]] = {
    terrain: tuple(
        profile.type for profile in FACTION_PROFILES if profile.home_terrain is terrain
    )
    for terrain in TERRAIN_WHEEL
}


# --- Base map ---------------------------------------------------------------

# Rows are axial hex rows. Odd rows are one tile shorter, matching the
# standard 113-tile base map. River tiles are not buildable.
BASE_MAP_ROWS: tuple[tuple[Terrain, ...], ...] = (
    (
        Terrain.PLAINS,
        Terrain.MOUNTAIN,
        Terrain.FOREST,
        Terrain.LAKE,
        Terrain.DESERT,
        Terrain.WASTELAND,
        Terrain.PLAINS,
        Terrain.SWAMP,
        Terrain.WASTELAND,
        Terrain.FOREST,
        Terrain.LAKE,
        Terrain.WASTELAND,
        Terrain.SWAMP,
    ),
    (
        Terrain.DESERT,
        Terrain.RIVER,
        Terrain.RIVER,
        Terrain.PLAINS,
        Terrain.SWAMP,
        Terrain.RIVER,
        Terrain.RIVER,
        Terrain.DESERT,
        Terrain.SWAMP,
        Terrain.RIVER,
        Terrain.RIVER,
        Terrain.DESERT,
    ),
    (
        Terrain.RIVER,
        Terrain.RIVER,
        Terrain.SWAMP,
        Terrain.RIVER,
        Terrain.MOUNTAIN,
        Terrain.RIVER,
        Terrain.FOREST,
        Terrain.RIVER,
        Terrain.FOREST,
        Terrain.RIVER,
        Terrain.MOUNTAIN,
        Terrain.RIVER,
        Terrain.RIVER,
    ),
    (
        Terrain.FOREST,
        Terrain.LAKE,
        Terrain.DESERT,
        Terrain.RIVER,
        Terrain.RIVER,
        Terrain.WASTELAND,
        Terrain.LAKE,
        Terrain.RIVER,
        Terrain.WASTELAND,
        Terrain.RIVER,
        Terrain.WASTELAND,
        Terrain.PLAINS,
    ),
    (
        Terrain.SWAMP,
        Terrain.PLAINS,
        Terrain.WASTELAND,
        Terrain.LAKE,
        Terrain.SWAMP,
        Terrain.PLAINS,
        Terrain.MOUNTAIN,
        Terrain.DESERT,
        Terrain.RIVER,
        Terrain.RIVER,
        Terrain.FOREST,
        Terrain.SWAMP,
        Terrain.LAKE,
    ),
    (
        Terrain.MOUNTAIN,
        Terrain.FOREST,
        Terrain.RIVER,
        Terrain.RIVER,
        Terrain.DESERT,
        Terrain.FOREST,
        Terrain.RIVER,
        Terrain.RIVER,
        Terrain.RIVER,
        Terrain.PLAINS,
        Terrain.MOUNTAIN,
        Terrain.PLAINS,
    ),
    (
        Terrain.RIVER,
        Terrain.RIVER,
        Terrain.RIVER,
        Terrain.MOUNTAIN,
        Terrain.RIVER,
        Terrain.WASTELAND,
        Terrain.RIVER,
        Terrain.FOREST,
        Terrain.RIVER,
        Terrain.DESERT,
        Terrain.SWAMP,
        Terrain.LAKE,
        Terrain.DESERT,
    ),
    (
        Terrain.DESERT,
        Terrain.LAKE,
        Terrain.PLAINS,
        Terrain.RIVER,
        Terrain.RIVER,
        Terrain.RIVER,
        Terrain.LAKE,
        Terrain.SWAMP,
        Terrain.RIVER,
        Terrain.MOUNTAIN,
        Terrain.PLAINS,
        Terrain.MOUNTAIN,
    ),
    (
        Terrain.WASTELAND,
        Terrain.SWAMP,
        Terrain.MOUNTAIN,
        Terrain.LAKE,
        Terrain.WASTELAND,
        Terrain.FOREST,
        Terrain.DESERT,
        Terrain.PLAINS,
        Terrain.MOUNTAIN,
        Terrain.RIVER,
        Terrain.LAKE,
        Terrain.FOREST,
        Terrain.WASTELAND,
    ),
)
