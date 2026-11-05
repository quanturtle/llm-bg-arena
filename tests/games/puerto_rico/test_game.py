"""Tests for the PuertoRico facade: scores, replayable logs and full random games."""

import asyncio

import pytest

from boardgames.arena.runner import play_match
from boardgames.games.puerto_rico import PuertoRico, PuertoRicoConfig, PuertoRicoState
from boardgames.games.puerto_rico.model import goods_total, total_points
from boardgames.logs.replay import replay_match
from boardgames.logs.schema import LogRecord
from tests.arena.support import FakeClock, MemorySink, random_agents
from tests.games.puerto_rico.support import GAME, start, with_vp_chips
from tests.invariants.playthrough import random_playthrough


def test_scores_match_total_points() -> None:
    state = start(seed=1)
    player = state.order[0]
    state = with_vp_chips(state, player, 6)
    scores = GAME.scores(state)
    assert scores.points[player] == total_points(state.players[player])


def record_match(
    config: PuertoRicoConfig, seed: int, game: PuertoRico
) -> list[LogRecord]:
    sink = MemorySink()
    asyncio.run(
        play_match(
            game,
            config,
            seed,
            random_agents(config.num_players, seed),
            match_id="puerto-rico-test",
            sink=sink,
            clock=FakeClock(),
        )
    )
    return sink.records


def test_same_seed_replays_to_the_same_log() -> None:
    config = PuertoRicoConfig(num_players=3, max_rounds=2)
    first = record_match(config, 4, GAME)
    second = record_match(config, 4, GAME)
    assert first == second
    report = replay_match(first)
    assert report.game_id == "puerto_rico"
    assert report.steps > 0


def total_goods_on_board(state: PuertoRicoState) -> int:
    """Goods in the bank, hands, ships and trading house; must never change."""
    return (
        sum(state.goods_supply)
        + sum(goods_total(player.goods) for player in state.players)
        + sum(ship.filled for ship in state.cargo_ships)
        + len(state.trading_house)
    )


def total_colonists(state: PuertoRicoState) -> int:
    """Colonists in the bank, ship, island, city and San Juan."""
    return (
        state.colonist_supply
        + state.colonist_ship
        + sum(
            player.colonists_unplaced
            + sum(1 for plantation in player.plantations if plantation.colonized)
            + player.occupied_quarries
            + sum(building.colonists for building in player.buildings)
            for player in state.players
        )
    )


def check_playthrough_state(
    state: PuertoRicoState, initial_goods: int, initial_colonists: int
) -> None:
    assert all(count >= 0 for count in state.goods_supply)
    for player in state.players:
        assert all(count >= 0 for count in player.goods)
        assert player.doubloons >= 0
        assert player.vp_chips >= 0
        assert player.occupied_quarries <= player.quarries
    assert total_goods_on_board(state) == initial_goods
    assert total_colonists(state) == initial_colonists


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_random_playthrough_terminates_and_keeps_invariants(seed: int) -> None:
    config = PuertoRicoConfig(num_players=3, max_rounds=2)
    initial = GAME.setup(config, seed).state
    initial_goods = total_goods_on_board(initial)
    initial_colonists = total_colonists(initial)
    final, steps = random_playthrough(
        GAME,
        config,
        seed,
        lambda state: check_playthrough_state(state, initial_goods, initial_colonists),
    )
    assert GAME.is_terminal(final)
    assert final.winner is not None
    assert steps <= 1_000


@pytest.mark.parametrize("seed", [1, 2])
def test_a_natural_full_game_reaches_a_rule_based_end(seed: int) -> None:
    config = PuertoRicoConfig(num_players=3)
    initial = GAME.setup(config, seed).state
    initial_goods = total_goods_on_board(initial)
    initial_colonists = total_colonists(initial)
    final, steps = random_playthrough(
        GAME,
        config,
        seed,
        lambda state: check_playthrough_state(state, initial_goods, initial_colonists),
    )
    assert GAME.is_terminal(final)
    assert final.end_reason is not None
    assert final.end_reason != "round limit reached"
    assert steps <= 2_000
