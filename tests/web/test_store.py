import os
from pathlib import Path

import pytest

from boardgames.games.sealed_auction import SealedAuction, SealedAuctionConfig
from boardgames.logs.schema import MatchFinished
from boardgames.web.store import MatchStore, UnknownMatchError, summarize
from tests.arena.support import ForfeitingAgent, random_agents
from tests.web.support import (
    costly_agents,
    play_records,
    without_finish,
    write_match,
    write_records,
)


def test_summary_of_a_finished_match_has_scores_and_usage(tmp_path: Path) -> None:
    records = write_match(tmp_path, "m1", agents=costly_agents(2))
    finish = next(r for r in records if isinstance(r, MatchFinished))
    summary = summarize(records)
    assert (summary.match_id, summary.game_id) == ("m1", "k_in_a_row")
    assert summary.status == "finished"
    assert summary.steps == finish.steps
    assert summary.finished_at == "2026-01-01T00:00:00+00:00"
    first = summary.seats[0]
    assert (first.agent, first.kind) == ("model-0", "llm")
    assert (first.points, first.rank) == (
        finish.scores[0].points,
        finish.scores[0].rank,
    )
    assert first.decisions == len(
        [r for r in records if r.type == "decision" and r.player == 0]
    )
    assert first.illegal_attempts == first.decisions
    assert first.api_retries == 2 * first.decisions
    assert first.prompt_tokens == 100 * first.decisions
    assert first.cost_usd == pytest.approx(0.001 * first.decisions)
    assert first.latency_seconds == pytest.approx(0.5 * first.decisions)
    assert summary.winners() == [s.player for s in finish.scores if s.rank == 1]
    return


def test_unknown_cost_on_one_decision_makes_the_seat_cost_unknown(
    tmp_path: Path,
) -> None:
    records = write_match(tmp_path, "m1", agents=costly_agents(2, cost=None))
    assert summarize(records).seats[0].cost_usd is None
    return


def test_summary_of_a_running_match_has_no_scores(tmp_path: Path) -> None:
    records = without_finish(write_match(tmp_path, "m1"))
    summary = summarize(records)
    assert summary.status == "running"
    assert summary.finished_at is None
    assert summary.steps == max(r.step for r in records if r.type == "decision")
    assert all(seat.points is None and seat.rank is None for seat in summary.seats)
    assert summary.winners() == []
    return


def test_forfeits_are_counted_apart_from_decisions() -> None:
    game = SealedAuction()
    config = SealedAuctionConfig(num_players=3, lots=2)
    agents = [*random_agents(2), ForfeitingAgent()]
    summary = summarize(play_records(game, config, agents, 1, "m"))
    quitter = summary.seats[2]
    assert quitter.forfeited is True
    assert quitter.decisions == 0
    assert quitter.illegal_attempts == 3
    assert quitter.rank == 3
    return


def test_catalog_lists_matches_newest_first_and_reports_unreadable_logs(
    tmp_path: Path,
) -> None:
    write_match(tmp_path, "older", seed=1)
    records = write_match(tmp_path, "newer", seed=2)
    newer_start = records[0].model_copy(
        update={"started_at": "2026-02-01T00:00:00+00:00"}
    )
    (tmp_path / "newer.jsonl").unlink()
    write_records(tmp_path / "newer.jsonl", [newer_start, *records[1:]])
    (tmp_path / "broken.jsonl").write_text('{"type": "nonsense"}\n', encoding="utf-8")
    (tmp_path / "empty.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")
    catalog = MatchStore(tmp_path).catalog()
    assert [m.match_id for m in catalog.matches] == ["newer", "older"]
    assert sorted(u.path for u in catalog.unreadable) == ["broken.jsonl", "empty.jsonl"]
    assert "no MatchStarted record" in next(
        u.error for u in catalog.unreadable if u.path == "empty.jsonl"
    )
    return


def test_store_rereads_a_log_that_grew(tmp_path: Path) -> None:
    records = write_match(tmp_path, "m1")
    path = tmp_path / "m1.jsonl"
    path.unlink()
    write_records(path, without_finish(records))
    store = MatchStore(tmp_path)
    assert store.match("m1").status == "running"
    with path.open("a", encoding="utf-8") as file:
        file.write(records[-1].model_dump_json() + "\n")
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    assert store.match("m1").status == "finished"
    assert store.records("m1")[-1] == records[-1]
    return


def test_unknown_match_raises(tmp_path: Path) -> None:
    store = MatchStore(tmp_path / "missing")
    assert store.catalog().matches == []
    with pytest.raises(UnknownMatchError, match="unknown match 'nope'"):
        store.match("nope")
    return
