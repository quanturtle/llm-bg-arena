"""Tests for the Terra Mystica rule tables: factions, cult orders and round tiles."""

from dataclasses import replace

from boardgames.core import PlayerId
from boardgames.games.terra_mystica.constants import (
    CULT_ORDER_STEPS,
    FACTION_BY_TYPE,
    FACTION_PROFILES,
    SCORING_TILES,
    STANDARD_TRADING_HOUSE_INCOME,
    FactionType,
    ScoringAction,
)
from boardgames.games.terra_mystica.model import shipping_points
from boardgames.games.terra_mystica.rounds import income_for
from tests.games.terra_mystica.support import start


def test_faction_profiles_are_hashable_and_have_twelve_power() -> None:
    for profile in FACTION_PROFILES:
        assert hash(profile)
        assert profile.starting_resources.power == 12
        assert len(profile.starting_cults) == 4


def test_standard_rule_tables_match_the_base_game() -> None:
    assert CULT_ORDER_STEPS[0] == 3
    assert all(steps == 2 for steps in CULT_ORDER_STEPS[1:])
    assert [shipping_points(level, 0) for level in (1, 2, 3)] == [2, 3, 4]
    assert shipping_points(2, 1) == 2
    assert FACTION_BY_TYPE[FactionType.WITCHES].base_income.workers == 1
    assert FACTION_BY_TYPE[FactionType.ENGINEERS].base_income.workers == 0
    assert FACTION_BY_TYPE[FactionType.SWARMLINGS].base_income.workers == 2
    state = start(num_players=2, seed=1, rounds=1)
    for faction, workers in (
        (FactionType.WITCHES, 1),
        (FactionType.ENGINEERS, 0),
        (FactionType.SWARMLINGS, 2),
    ):
        owner = replace(state.players[0], faction=faction)
        assert income_for(state.board, PlayerId(0), owner).workers == workers
    trading = tuple(income.power for income in STANDARD_TRADING_HOUSE_INCOME)
    assert trading == (1, 2, 4, 6)


def test_two_round_tiles_use_the_combined_stronghold_or_sanctuary_action() -> None:
    combined = [
        tile
        for tile in SCORING_TILES
        if tile.action is ScoringAction.STRONGHOLD_OR_SANCTUARY
    ]
    assert len(combined) == 2
