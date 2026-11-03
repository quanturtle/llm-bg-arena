from boardgames.games.k_in_a_row import TIC_TAC_TOE, KInARow
from boardgames.games.sealed_auction import SealedAuction, SealedAuctionConfig
from boardgames.logs.schema import DecisionRecord
from boardgames.web.timeline import build_timeline, outline
from tests.arena.support import ForfeitingAgent, random_agents
from tests.web.support import costly_agents, play_records


def test_one_frame_per_step_with_boards_and_the_decision() -> None:
    records = play_records(KInARow(), TIC_TAC_TOE, costly_agents(2), 3, "m")
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
    records = play_records(KInARow(), TIC_TAC_TOE, random_agents(2), 3, "m")
    third = next(
        i for i, r in enumerate(records) if r.type == "decision" and r.step == 3
    )
    timeline = build_timeline(records[: third + 1])
    assert (timeline.match.status, timeline.match.steps) == ("running", 2)
    assert len(timeline.frames) == 3
    return


def test_an_ended_log_that_diverges_shows_its_steps_up_to_there() -> None:
    records = play_records(KInARow(), TIC_TAC_TOE, random_agents(2), 3, "m")
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


def test_private_events_and_forfeits_are_kept() -> None:
    config = SealedAuctionConfig(num_players=3, lots=2)
    agents = [*random_agents(2), ForfeitingAgent()]
    timeline = build_timeline(play_records(SealedAuction(), config, agents, 1, "m"))
    assert [e.audience for e in timeline.frames[0].events[1:4]] == [[0], [1], [2]]
    assert [f.player for f in timeline.frames[-1].forfeits] == [2]
    return
