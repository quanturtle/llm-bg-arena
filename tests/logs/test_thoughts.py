from io import StringIO

from boardgames.agents import AttemptRecord
from boardgames.logs.schema import (
    DecisionRecord,
    MatchFinished,
    MatchStarted,
    ScoreRecord,
    SeatRecord,
    TraceRecord,
)
from boardgames.logs.thoughts import ThoughtsLog


def test_thoughts_log_writes_reasoning_tool_calls_and_notes_per_decision() -> None:
    stream = StringIO()
    log = ThoughtsLog(stream)
    log.write(
        MatchStarted(
            match_id="m",
            game_id="tic_tac_toe",
            rules_version=1,
            config={},
            seed=3,
            seats=[
                SeatRecord(player=0, agent="haiku", settings={}),
                SeatRecord(player=1, agent="random", settings={}),
            ],
            started_at="t",
        )
    )
    trace = TraceRecord(
        reasoning="Center is strongest.",
        memory="took center",
        attempts=[
            AttemptRecord.model_validate(
                {
                    "tool_calls": [
                        {"name": "get_rules", "arguments": "", "result": "Rules."}
                    ],
                    "rejection": {"kind": "illegal", "feedback": "b2 is taken."},
                    "answer": "b2",
                }
            )
        ],
        illegal_attempts=1,
        api_retries=0,
        fallback=None,
        prompt_tokens=100,
        completion_tokens=20,
        cost_usd=0.001,
    )
    log.write(
        DecisionRecord(
            step=1,
            observed_at_step=0,
            player=0,
            kind="mark",
            prompt="Choose a cell.",
            observation_digest="d",
            observation={},
            action="a1",
            action_json={},
            latency_seconds=0.5,
            trace=trace,
        )
    )
    log.write(
        MatchFinished(
            steps=1,
            forfeited=[],
            scores=[ScoreRecord(player=0, points=1, rank=1, breakdown={})],
            finished_at="t",
        )
    )
    text = stream.getvalue()
    assert "## Step 1: P1 haiku plays `a1`" in text
    assert "- `get_rules` \n  Rules." in text
    assert "**Rejected** `b2`: b2 is taken." in text
    assert "Center is strongest." in text and "took center" in text
    assert "_120 tokens, $0.0010_" in text
    assert "**Winner: P1 haiku, 1 point.**" in text
    assert "- #1 P1 haiku: 1 points" in text
    return
