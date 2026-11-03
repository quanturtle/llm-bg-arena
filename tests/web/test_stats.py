import pytest

from boardgames.agents import Agent
from boardgames.games.tic_tac_toe import TicTacToe, TicTacToeConfig
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
    return summarize(play_records(TicTacToe(), TicTacToeConfig(), agents, 0, match_id))


def test_leaderboard_counts_wins_usage_and_elo() -> None:
    matches = [scripted_match("w", *X_WINS), scripted_match("d", *DRAW)]
    board = leaderboard(matches, "tic_tac_toe")
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


def test_prompt_versions_split_the_leaderboard_and_the_agent_page() -> None:
    old = scripted_match("w", *X_WINS)
    new = scripted_match("d", *DRAW).model_copy(update={"prompt_version": 2})
    board = leaderboard([old, new], "tic_tac_toe", prompt_version=2)
    assert (board.prompt_versions, board.finished_matches) == ([0, 2], 1)
    assert board.rows[0].wins == 0
    rows = agent_detail([old, new], "x-model").prompts
    assert [(row.prompt_version, row.wins) for row in rows] == [(0, 1), (2, 0)]
    return


def test_bots_get_no_leaderboard_row() -> None:
    board = leaderboard([scripted_match("w", *X_WINS, o_is_bot=True)], "tic_tac_toe")
    assert [row.agent for row in board.rows] == ["x-model"]
    return


def test_agent_detail_has_per_game_rows_and_head_to_head() -> None:
    detail = agent_detail([scripted_match("w", *X_WINS)], "x-model")
    assert [row.game_id for row in detail.games] == ["tic_tac_toe"]
    assert detail.overall is not None and detail.overall.matches == 1
    assert detail.opponents[0].model_dump() == {
        "opponent": "o-model",
        "matches": 1,
        "ahead": 1,
        "level": 0,
        "behind": 0,
    }
    return
