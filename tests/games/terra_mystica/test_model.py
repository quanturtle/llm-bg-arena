"""Tests for the Terra Mystica model: the board, power bowls, spades and costs."""

from dataclasses import replace

from boardgames.games.terra_mystica import Board
from boardgames.games.terra_mystica.constants import (
    FACTION_BY_TYPE,
    TERRAIN_WHEEL,
    BuildingType,
    Cult,
    FactionType,
    Income,
    Resources,
)
from boardgames.games.terra_mystica.model import (
    PlayerState,
    advance_cult,
    building_cost,
    gain_power,
    income_with_power,
    spade_cost,
    spades_for,
    spend_power,
)


def test_shipping_crosses_a_fixed_river_tile() -> None:
    board = Board.base()
    for tile in board.tiles:
        if tile.is_land:
            continue
        land = [
            neighbour
            for neighbour in tile.position.neighbours()
            if (other := board.tile(neighbour)) is not None and other.is_land
        ]
        for start in land:
            direct = board.reachable_from(start, 0)
            shipped = board.reachable_from(start, 1)
            across = [
                neighbour
                for neighbour in land
                if neighbour != start and neighbour not in direct
            ]
            if across:
                assert across[0] in shipped
                return
    raise AssertionError("no river tile has land on both banks")


def test_power_bowls_keep_twelve_tokens_in_the_cycle() -> None:
    resources = Resources(power1=5, power2=7)
    assert resources.power == 12
    gained = gain_power(resources, 10)
    assert gained.power == 12
    assert (gained.power1, gained.power2, gained.power3) == (0, 7, 5)
    spent = spend_power(gained, 3)
    assert spent is not None
    assert (spent.power1, spent.power2, spent.power3) == (3, 7, 2)
    assert spend_power(spent, 99) is None


def test_income_includes_power_and_resources() -> None:
    resources = Resources(coins=1, workers=1, priests=1, power1=5, power2=7)
    updated = income_with_power(
        resources, Income(coins=2, workers=3, priests=4, power=2)
    )
    assert updated.coins == 3
    assert updated.workers == 4
    assert updated.priests == 5
    assert updated.power == 12


def test_spade_costs_use_workers_and_darklings_use_priests() -> None:
    witches = FACTION_BY_TYPE[FactionType.WITCHES]
    assert spades_for(witches, witches.home_terrain) == 0
    other = next(
        terrain for terrain in TERRAIN_WHEEL if terrain is not witches.home_terrain
    )
    assert spades_for(witches, other) >= 1
    assert spade_cost(witches, 0, 2).workers == 6
    assert spade_cost(witches, 2, 2).workers == 2
    darklings = FACTION_BY_TYPE[
        next(faction for faction in FACTION_BY_TYPE if faction.value == "darklings")
    ]
    assert spade_cost(darklings, 0, 2).priests == 2


def test_advance_cult_grants_power_at_thresholds_and_spends_a_key() -> None:
    owner = PlayerState(
        faction=next(iter(FACTION_BY_TYPE)),
        resources=Resources(power1=5, power2=7),
        cults=(2, 0, 0, 0),
    )
    advanced, gained = advance_cult(owner, Cult.FIRE, 3)
    assert advanced.cult(Cult.FIRE) == 5
    assert gained == 3
    owner = replace(owner, cults=(9, 0, 0, 0), keys=1)
    advanced, gained = advance_cult(owner, Cult.FIRE, 3)
    assert advanced.cult(Cult.FIRE) == 10
    assert advanced.keys == 0
    assert gained == 3


def test_trading_house_costs_less_next_to_an_opponent() -> None:
    swarmlings = FACTION_BY_TYPE[FactionType.SWARMLINGS]
    assert building_cost(swarmlings, BuildingType.TRADING_HOUSE, False).coins == 8
    assert building_cost(swarmlings, BuildingType.TRADING_HOUSE, True).coins == 4
