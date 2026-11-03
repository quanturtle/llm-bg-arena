from pathlib import Path

import pytest

from boardgames.logs.schema import MatchFinished
from boardgames.web.store import MatchStore, UnknownMatchError, summarize
from tests.web.support import costly_agents, without_finish, write_match


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
