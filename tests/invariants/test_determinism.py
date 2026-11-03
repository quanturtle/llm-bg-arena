import os
import subprocess
import sys
from pathlib import Path

import pytest

from boardgames.logs.schema import LogRecord, MatchStarted
from tests.invariants.log_digest import CASES, match_log

REPOSITORY = Path(__file__).resolve().parents[2]
SEEDS = 4


def digests_in_subprocess(case: str, hash_seed: str) -> list[str]:
    """Log digests of seeds 0 to SEEDS-1 from a new interpreter with that hash seed."""
    completed = subprocess.run(
        [sys.executable, "-m", "tests.invariants.log_digest", case, str(SEEDS)],
        cwd=REPOSITORY,
        env={**os.environ, "PYTHONHASHSEED": hash_seed},
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.split()


def play_without_start(records: list[LogRecord]) -> str:
    """The log minus match_started, whose `seed` field alone differs per seed."""
    return str([record for record in records if not isinstance(record, MatchStarted)])


@pytest.mark.parametrize("case", CASES)
def test_same_seed_and_agents_give_identical_logs_across_processes(case: str) -> None:
    first = digests_in_subprocess(case, hash_seed="1")
    second = digests_in_subprocess(case, hash_seed="2")
    assert len(first) == SEEDS
    assert first == second
    return


@pytest.mark.parametrize("case", CASES)
def test_different_seeds_give_different_play(case: str) -> None:
    game, config = CASES[case]
    plays = {play_without_start(match_log(game, config, seed)) for seed in range(SEEDS)}
    assert len(plays) == SEEDS
    return
