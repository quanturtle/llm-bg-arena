from boardgames.games.k_in_a_row import TIC_TAC_TOE, KInARow
from boardgames.games.sealed_auction import SealedAuction, SealedAuctionConfig
from boardgames.logs.schema import DecisionRecord, MatchFinished
from boardgames.web.timeline import build_timeline
from tests.arena.support import ForfeitingAgent, random_agents
from tests.web.support import costly_agents, play_records, without_finish

AUCTION = SealedAuctionConfig(num_players=3, lots=2)


def test_one_frame_per_step_with_the_decision_that_made_it() -> None:
    game = KInARow()
    records = play_records(game, TIC_TAC_TOE, costly_agents(2), 3, "m")
    decisions = [r for r in records if isinstance(r, DecisionRecord)]
    finish = next(r for r in records if isinstance(r, MatchFinished))
    timeline = build_timeline(records)
    assert timeline.match.match_id == "m"
    assert len(timeline.frames) == finish.steps + 1
    first = timeline.frames[0]
    assert first.decision is None
    assert [e.kind for e in first.events] == ["started"]
    assert first.pending == [0]
    assert [b.viewer for b in first.boards] == [None, 0, 1]
    assert first.boards[0].observation is not None
    assert first.boards[1].observation is None
    frame = timeline.frames[1]
    assert frame.decision is not None
    assert frame.decision.action == decisions[0].action
    assert frame.decision.description == f"Place X on {decisions[0].action}"
    assert frame.decision.trace.reasoning == f"I pick {decisions[0].action}"
    assert frame.events[0].text.endswith(f"marked {decisions[0].action}.")
    last = timeline.frames[-1]
    assert last.pending == []
    assert [(s.player, s.points, s.rank) for s in last.scores] == [
        (s.player, s.points, s.rank) for s in finish.scores
    ]
    return


def test_boards_are_the_rendered_spectator_and_seat_views() -> None:
    game = SealedAuction()
    records = play_records(game, AUCTION, random_agents(3), 1, "m")
    timeline = build_timeline(records)
    board = timeline.frames[0].boards
    assert "Your secret color" not in board[0].text
    assert "Your secret color" in board[1].text
    private = [e for e in timeline.frames[0].events if e.audience != "everyone"]
    assert [e.audience for e in private] == [[0], [1], [2]]
    return


def test_a_forfeit_is_attached_to_the_frame_it_happened_in() -> None:
    game = SealedAuction()
    agents = [*random_agents(2), ForfeitingAgent()]
    timeline = build_timeline(play_records(game, AUCTION, agents, 1, "m"))
    last = timeline.frames[-1]
    assert [f.player for f in last.forfeits] == [2]
    assert last.forfeits[0].reason == "gave up"
    assert all(not f.forfeits for f in timeline.frames[:-1])
    return


def test_an_unfinished_log_builds_up_to_its_last_step() -> None:
    records = without_finish(
        play_records(KInARow(), TIC_TAC_TOE, random_agents(2), 3, "m")
    )
    timeline = build_timeline(records)
    assert timeline.match.status == "running"
    assert len(timeline.frames) == timeline.match.steps + 1
    return
