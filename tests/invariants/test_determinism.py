import asyncio

import pytest

from boardgames.arena.runner import play_match
from boardgames.core import AnyGame, GameConfig
from boardgames.games.k_in_a_row import FOUR_IN_A_ROW, KInARow
from boardgames.games.puerto_rico import (
    PuertoRico,
    PuertoRicoConfig,
)
from boardgames.games.sealed_auction import SealedAuction, SealedAuctionConfig
from boardgames.logs.schema import LogRecord
from tests.arena.support import FakeClock, MemorySink, random_agents

CASES: list[tuple[AnyGame, GameConfig]] = [
    (KInARow(), FOUR_IN_A_ROW),
    (SealedAuction(), SealedAuctionConfig(num_players=4)),
    (PuertoRico(), PuertoRicoConfig(num_players=3, max_rounds=2)),
]


def match_log(game: AnyGame, config: GameConfig, seed: int) -> list[LogRecord]:
    sink = MemorySink()
    agents = random_agents(config.num_players, seed)
    asyncio.run(
        play_match(
            game, config, seed, agents, match_id="m", sink=sink, clock=FakeClock()
        )
    )
    return sink.records


@pytest.mark.parametrize(
    ("game", "config"),
    CASES,
    ids=["four_in_a_row", "auction", "puerto_rico"],
)
def test_same_seed_and_agents_give_identical_logs(
    game: AnyGame, config: GameConfig
) -> None:
    for seed in range(10):
        assert match_log(game, config, seed) == match_log(game, config, seed)
    return


@pytest.mark.parametrize(
    ("game", "config"),
    CASES,
    ids=["four_in_a_row", "auction", "puerto_rico"],
)
def test_different_seeds_give_different_logs(game: AnyGame, config: GameConfig) -> None:
    logs = {str(match_log(game, config, seed)) for seed in range(10)}
    assert len(logs) == 10
    return
