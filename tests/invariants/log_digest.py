"""Print the digest of a random-agent match log, one line per seed.

Run as `python -m tests.invariants.log_digest CASE SEEDS` from the repository
root. The determinism tests run it under different PYTHONHASHSEED values and
compare the output.
"""

import asyncio
import hashlib
import sys

from boardgames.arena.runner import play_match
from boardgames.core import AnyGame, GameConfig
from boardgames.games.catan import Catan, CatanConfig
from boardgames.games.k_in_a_row import FOUR_IN_A_ROW, KInARow
from boardgames.games.puerto_rico import PuertoRico, PuertoRicoConfig
from boardgames.games.sealed_auction import SealedAuction, SealedAuctionConfig
from boardgames.logs.schema import LogRecord
from tests.arena.support import FakeClock, MemorySink, random_agents

CASES: dict[str, tuple[AnyGame, GameConfig]] = {
    "four_in_a_row": (KInARow(), FOUR_IN_A_ROW),
    "auction": (SealedAuction(), SealedAuctionConfig(num_players=4)),
    "catan": (Catan(), CatanConfig(num_players=3, victory_points=3)),
    "puerto_rico": (PuertoRico(), PuertoRicoConfig(num_players=3, max_rounds=2)),
}


def parse_arguments(argv: list[str]) -> tuple[str, int]:
    """The case name and how many seeds, counting from 0, to play."""
    case, seeds = argv
    return case, int(seeds)


def match_log(game: AnyGame, config: GameConfig, seed: int) -> list[LogRecord]:
    """The log of one match between random agents seeded from `seed`."""
    sink = MemorySink()
    agents = random_agents(config.num_players, seed)
    asyncio.run(
        play_match(
            game, config, seed, agents, match_id="m", sink=sink, clock=FakeClock()
        )
    )
    return sink.records


def log_digest(records: list[LogRecord]) -> str:
    """SHA-256 of the log as JSONL text."""
    text = "".join(record.model_dump_json() + "\n" for record in records)
    return hashlib.sha256(text.encode()).hexdigest()


def print_digests(case: str, seeds: int) -> None:
    """Print the log digest of each seed's match."""
    game, config = CASES[case]
    for seed in range(seeds):
        print(log_digest(match_log(game, config, seed)))
    return


def main() -> None:
    case, seeds = parse_arguments(sys.argv[1:])
    print_digests(case, seeds)
    return


if __name__ == "__main__":
    main()
