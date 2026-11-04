from pathlib import Path

import pytest

from boardgames.logs.schema import (
    DecisionRecord,
    LogRecord,
    MatchFinished,
    MatchStarted,
)
from boardgames.web import store
from boardgames.web.store import (
    FinishedMatch,
    MatchStore,
    MatchSummary,
    ReadOnlyLogError,
    RunningMatch,
    UnknownMatchError,
    summarize,
)
from tests.web.support import costly_agents, without_finish, write_match, write_records


def test_summary_has_scores_and_usage_per_seat(tmp_path: Path) -> None:
    records = write_match(tmp_path, "m1", agents=costly_agents(2))
    finish = next(r for r in records if isinstance(r, MatchFinished))
    summary = summarize(records)
    first = summary.seats[0]
    assert (summary.status, summary.steps) == ("finished", finish.steps)
    assert (first.agent, first.kind, first.rank) == (
        "model-0",
        "llm",
        finish.scores[0].rank,
    )
    assert first.cost_usd == pytest.approx(0.001 * first.decisions)
    assert first.illegal_attempts == first.decisions
    return


def test_summary_reads_the_prompt_version_and_old_logs_are_version_0(
    tmp_path: Path,
) -> None:
    records = write_match(tmp_path, "m1", agents=costly_agents(2))
    assert summarize(records).prompt_version == 0
    start = records[0]
    assert isinstance(start, MatchStarted)
    seats = [
        seat.model_copy(update={"settings": {**seat.settings, "prompt_version": 1}})
        for seat in start.seats
    ]
    versioned = [start.model_copy(update={"seats": seats}), *records[1:]]
    assert summarize(versioned).prompt_version == 1
    return


def test_summary_variants_carry_points_and_rank_only_when_finished(
    tmp_path: Path,
) -> None:
    records = write_match(tmp_path, "m1", agents=costly_agents(2))
    finished = summarize(records)
    assert isinstance(finished, FinishedMatch)
    assert finished.seats[0].points is not None
    assert finished.seats[0].rank is not None
    running = summarize(without_finish(records))
    assert isinstance(running, RunningMatch)
    assert running.seats[0].points is None
    assert isinstance(
        MatchSummary(
            match_id="m",
            game_id="tic_tac_toe",
            config={},
            seed=0,
            started_at="t",
            finished_at="t",
            steps=0,
            status="finished",
            prompt_version=0,
            seats=[],
        ),
        FinishedMatch,
    )
    return


def test_running_match_has_no_scores(tmp_path: Path) -> None:
    summary = summarize(without_finish(write_match(tmp_path, "m1")))
    assert summary.status == "running"
    assert summary.seats[0].rank is None
    return


def test_catalog_is_newest_first_and_skips_unreadable_logs(tmp_path: Path) -> None:
    write_match(tmp_path, "a", seed=1)
    write_match(tmp_path, "b", seed=2)
    (tmp_path / "broken.jsonl").write_text("{}\n", encoding="utf-8")
    store = MatchStore(tmp_path)
    catalog = store.catalog()
    assert {m.match_id for m in catalog.matches} == {"a", "b"}
    assert [u.path for u in catalog.unreadable] == ["broken.jsonl"]
    with pytest.raises(UnknownMatchError):
        store.match("nope")
    return


def test_read_only_log_is_listed_and_cannot_be_deleted(tmp_path: Path) -> None:
    write_match(tmp_path, "example")
    log = tmp_path / "example.jsonl"
    store = MatchStore(tmp_path / "runs", read_only=(log,))
    assert [m.match_id for m in store.catalog().matches] == ["example"]
    with pytest.raises(ReadOnlyLogError):
        store.delete("example")
    assert log.exists()
    return


def test_a_log_that_is_not_utf8_is_unreadable_not_an_error(tmp_path: Path) -> None:
    write_match(tmp_path, "good")
    (tmp_path / "bad.jsonl").write_bytes(b'{"type": "match_started", "x": "\xff"}\n')
    catalog = MatchStore(tmp_path).catalog()
    assert [m.match_id for m in catalog.matches] == ["good"]
    assert [u.path for u in catalog.unreadable] == ["bad.jsonl"]
    return


def test_a_log_with_a_player_outside_the_seats_is_unreadable(tmp_path: Path) -> None:
    records = write_match(tmp_path, "bad-player")
    changed = [
        r.model_copy(update={"player": 7}) if isinstance(r, DecisionRecord) else r
        for r in records
    ]
    write_records(tmp_path / "changed.jsonl", changed)
    catalog = MatchStore(tmp_path).catalog()
    assert [u.path for u in catalog.unreadable] == ["changed.jsonl"]
    return


def summarize_with_a_bug(records: list[LogRecord]) -> FinishedMatch:
    raise KeyError("seats")


def test_a_bug_while_summarizing_is_not_reported_as_an_unreadable_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_match(tmp_path, "good")
    monkeypatch.setattr(store, "summarize", summarize_with_a_bug)
    with pytest.raises(KeyError):
        MatchStore(tmp_path).catalog()
    return


def test_a_log_deleted_from_disk_is_unknown_not_an_error(tmp_path: Path) -> None:
    write_match(tmp_path, "gone")
    store = MatchStore(tmp_path)
    store.catalog()
    (tmp_path / "gone.jsonl").unlink()
    with pytest.raises(UnknownMatchError):
        store.match("gone")
    with pytest.raises(UnknownMatchError):
        store.records("gone")
    with pytest.raises(UnknownMatchError):
        store.updated_at("gone")
    return


def test_deleting_a_match_removes_a_duplicate_copy(tmp_path: Path) -> None:
    write_match(tmp_path, "dup")
    (tmp_path / "dup-copy.jsonl").write_bytes((tmp_path / "dup.jsonl").read_bytes())
    store = MatchStore(tmp_path)
    assert [m.match_id for m in store.catalog().matches] == ["dup"]
    store.delete("dup")
    assert not (tmp_path / "dup.jsonl").exists()
    assert not (tmp_path / "dup-copy.jsonl").exists()
    with pytest.raises(UnknownMatchError):
        store.match("dup")
    return


def test_a_read_only_log_deleted_from_disk_disappears_quietly(tmp_path: Path) -> None:
    log = tmp_path / "example.jsonl"
    write_match(tmp_path, "example")
    store = MatchStore(tmp_path / "runs", read_only=(log,))
    assert [m.match_id for m in store.catalog().matches] == ["example"]
    log.unlink()
    assert store.catalog().matches == []
    return
