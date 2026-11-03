from boardgames.agents import Agent
from boardgames.games.catan import Catan, CatanConfig
from boardgames.games.tic_tac_toe import TicTacToe, TicTacToeConfig
from boardgames.logs.schema import DecisionRecord
from boardgames.web.timeline import build_timeline, outline
from tests.arena.support import ForfeitingAgent, ScriptedAgent, random_agents
from tests.web.support import costly_agents, play_records


def test_one_frame_per_step_with_boards_and_the_decision() -> None:
    records = play_records(TicTacToe(), TicTacToeConfig(), costly_agents(2), 3, "m")
    first_move = next(r for r in records if isinstance(r, DecisionRecord))
    timeline = build_timeline(records)
    frame = timeline.frames[1]
    assert len(timeline.frames) == timeline.match.steps + 1
    assert [b.viewer for b in frame.boards] == [None, 0, 1]
    assert frame.decision is not None
    assert frame.decision.description == f"Place X on {first_move.action}"
    assert outline(timeline).moves[0].action == first_move.action
    return


def test_a_running_log_cut_after_a_decision_drops_that_step() -> None:
    records = play_records(TicTacToe(), TicTacToeConfig(), random_agents(2), 3, "m")
    third = next(
        i for i, r in enumerate(records) if r.type == "decision" and r.step == 3
    )
    timeline = build_timeline(records[: third + 1])
    assert (timeline.match.status, timeline.match.steps) == ("running", 2)
    assert len(timeline.frames) == 3
    return


def test_an_ended_log_that_diverges_shows_its_steps_up_to_there() -> None:
    records = play_records(TicTacToe(), TicTacToeConfig(), random_agents(2), 3, "m")
    first = next(r for r in records if isinstance(r, DecisionRecord))
    diverged = [
        r.model_copy(update={"action": first.action})
        if isinstance(r, DecisionRecord) and r.step == 3
        else r
        for r in records
    ]
    timeline = build_timeline(diverged)
    assert (timeline.match.status, len(timeline.frames)) == ("finished", 3)
    assert timeline.replay_error is not None
    assert outline(timeline).replay_error == timeline.replay_error
    return


def test_private_events_keep_their_audience() -> None:
    config = CatanConfig(num_players=3, victory_points=3)
    timeline = build_timeline(play_records(Catan(), config, random_agents(3), 7, "m"))
    theft = ("stole_card", "card_stolen")
    events = [e for f in timeline.frames for e in f.events if e.kind in theft]
    assert [e.audience for e in events[:2]] == [[1], [2]]
    return


def test_forfeits_are_kept() -> None:
    agents: list[Agent] = [ScriptedAgent(["b2"]), ForfeitingAgent()]
    records = play_records(TicTacToe(), TicTacToeConfig(), agents, 1, "m")
    timeline = build_timeline(records)
    assert [f.player for f in timeline.frames[-1].forfeits] == [1]
    return
