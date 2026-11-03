import pytest

from boardgames.agents import Agent
from boardgames.games.k_in_a_row import TIC_TAC_TOE, KInARow
from boardgames.web.stats import agent_detail, leaderboard
from boardgames.web.store import MatchSummary, summarize
from tests.arena.support import ScriptedAgent
from tests.web.support import CostlyAgent, play_records

X_WINS = (["a1", "a2", "a3"], ["b1", "b2"])
DRAW = (["b2", "c1", "a2", "b1", "c3"], ["a1", "a3", "c2", "b3"])


def scripted_match(
    match_id: str, x_moves: list[str], o_moves: list[str], o_is_bot: bool = False
) -> MatchSummary:
    o_player: Agent = ScriptedAgent(o_moves)
    if not o_is_bot:
        o_player = CostlyAgent(o_player, "o-model", 0.0)
    agents: list[Agent] = [
        CostlyAgent(ScriptedAgent(x_moves), "x-model", 0.01),
        o_player,
    ]
    return summarize(play_records(KInARow(), TIC_TAC_TOE, agents, 0, match_id))


def test_leaderboard_counts_wins_usage_and_elo() -> None:
    matches = [scripted_match("w", *X_WINS), scripted_match("d", *DRAW)]
    board = leaderboard(matches, "k_in_a_row")
    rows = {row.agent: row for row in board.rows}
    assert board.finished_matches == 2
    assert [row.agent for row in board.rows] == ["x-model", "o-model"]
    assert (rows["x-model"].wins, rows["x-model"].win_rate) == (1, 0.5)
    assert rows["x-model"].illegal_rate == 1.0
    assert rows["x-model"].cost_usd == pytest.approx(0.08)
    assert rows["x-model"].elo is not None and rows["x-model"].elo > 1000
    assert rows["x-model"].elo + rows["o-model"].elo == pytest.approx(2000)  # type: ignore[operator]
    assert leaderboard(matches, None).rows[0].elo is None
    return


def test_bots_get_no_leaderboard_row() -> None:
    board = leaderboard([scripted_match("w", *X_WINS, o_is_bot=True)], "k_in_a_row")
    assert [row.agent for row in board.rows] == ["x-model"]
    return


def test_agent_detail_has_per_game_rows_and_head_to_head() -> None:
    detail = agent_detail([scripted_match("w", *X_WINS)], "x-model")
    assert [row.game_id for row in detail.games] == ["k_in_a_row"]
    assert detail.overall is not None and detail.overall.matches == 1
    assert detail.opponents[0].model_dump() == {
        "opponent": "o-model",
        "matches": 1,
        "ahead": 1,
        "level": 0,
        "behind": 0,
    }
    return
