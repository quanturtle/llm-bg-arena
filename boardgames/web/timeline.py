"""Timeline: a match log replayed into one frame per step for the replay viewer.

Frame 0 is the state after setup; frame `n` the state after the n-th applied
action. Every frame carries the spectator's observation, each seat's rendered
view, the step's events with their audience, and the decision that made it.
"""

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic import JsonValue as PlainJson

from boardgames.core import AnyGame, Observation, PlayerId, seats
from boardgames.logs.replay import (
    Replayed,
    ReplayMismatchError,
    events_by_step,
    replay_states,
)
from boardgames.logs.schema import (
    DecisionRecord,
    EventRecord,
    ForfeitRecord,
    LogRecord,
    MatchFinished,
    TraceRecord,
    plain_object,
)
from boardgames.web.store import MatchSummary, summarize


class View(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class BoardView(View):
    """One viewer's rendered text; the spectator view also carries the observation."""

    viewer: int | None
    text: str
    observation: dict[str, PlainJson] | None


class DecisionView(View):
    player: int
    kind: str
    prompt: str
    observed_at_step: int
    action: str
    description: str
    action_json: dict[str, PlainJson]
    latency_seconds: float
    trace: TraceRecord


class ForfeitView(View):
    player: int
    kind: str
    observed_at_step: int
    reason: str
    latency_seconds: float
    trace: TraceRecord


class ScoreView(View):
    player: int
    points: float
    rank: int
    breakdown: dict[str, float]


class Frame(View):
    step: int
    boards: list[BoardView]
    events: list[EventRecord]
    decision: DecisionView | None
    forfeits: list[ForfeitView]
    scores: list[ScoreView]
    pending: list[int]


class Timeline(View):
    match: MatchSummary
    frames: list[Frame]


class MoveView(View):
    """One step as the outline lists it: who did what, without boards or traces."""

    step: int
    player: int
    action: str
    description: str
    illegal_attempts: int
    fallback: str | None


class Outline(View):
    """The light part of a timeline: every move, event and score, but no boards."""

    match: MatchSummary
    frame_count: int
    moves: list[MoveView]
    events: list[EventRecord]
    forfeits: list[ForfeitView]
    scores: list[list[ScoreView]]


def board_views(game: AnyGame, state: Any, num_players: int) -> list[BoardView]:
    """The spectator's view first, then each seat's."""
    views: list[BoardView] = []
    for viewer in (None, *seats(num_players)):
        observation = game.observe(state, viewer)
        views.append(
            BoardView(
                viewer=viewer,
                text=game.render_text(observation),
                observation=plain_object(observation.data) if viewer is None else None,
            )
        )
    return views


def decision_view(game: AnyGame, record: DecisionRecord) -> DecisionView:
    """The logged decision with its human description."""
    action = game.parse_action(record.action)
    observation = Observation(PlayerId(record.player), record.observation)
    return DecisionView(
        player=record.player,
        kind=record.kind,
        prompt=record.prompt,
        observed_at_step=record.observed_at_step,
        action=record.action,
        description=game.describe_action(observation, action),
        action_json=record.action_json,
        latency_seconds=record.latency_seconds,
        trace=record.trace,
    )


def forfeit_view(record: ForfeitRecord) -> ForfeitView:
    return ForfeitView(
        player=record.player,
        kind=record.kind,
        observed_at_step=record.observed_at_step,
        reason=record.reason,
        latency_seconds=record.latency_seconds,
        trace=record.trace,
    )


def score_views(game: AnyGame, state: Any) -> list[ScoreView]:
    """Current points and ranks in seat order."""
    scores = game.scores(state)
    ranks = scores.ranks()
    return [
        ScoreView(
            player=player,
            points=scores.points[player],
            rank=ranks[player],
            breakdown=dict(scores.breakdown.get(player, {})),
        )
        for player in sorted(scores.points)
    ]


def frame(
    replayed: Replayed,
    step: int,
    events: Sequence[EventRecord],
    decision: DecisionRecord | None,
    forfeits: Sequence[ForfeitRecord],
) -> Frame:
    """The frame after `step`, from the replayed state and the step's records."""
    game = replayed.game
    state = replayed.states[step]
    return Frame(
        step=step,
        boards=board_views(game, state, len(replayed.start.seats)),
        events=list(events),
        decision=None if decision is None else decision_view(game, decision),
        forfeits=[forfeit_view(record) for record in forfeits],
        scores=score_views(game, state),
        pending=[d.player for d in game.pending_decisions(state)],
    )


def without_last_decision(records: Sequence[LogRecord]) -> list[LogRecord]:
    """The log cut before its last decision record, or empty when there is none."""
    last = next(
        (
            i
            for i in reversed(range(len(records)))
            if isinstance(records[i], DecisionRecord)
        ),
        None,
    )
    return [] if last is None else list(records[:last])


def replay_complete_steps(
    records: Sequence[LogRecord],
) -> tuple[Replayed, list[LogRecord]]:
    """Replay a log; a running match's last steps, still being written, are dropped.

    A finished log, or one whose cut-off is not at the end, raises ReplayMismatchError.
    """
    remaining = list(records)
    is_finished = any(isinstance(r, MatchFinished) for r in records)
    while True:
        try:
            return replay_states(remaining), remaining
        except ReplayMismatchError:
            trimmed = without_last_decision(remaining)
            if is_finished or not trimmed:
                raise
            remaining = trimmed


def build_timeline(records: Sequence[LogRecord]) -> Timeline:
    """Replay the log and lay out one frame per step; unfinished logs are allowed."""
    replayed, records = replay_complete_steps(records)
    events = events_by_step(records)
    decisions = {r.step: r for r in records if isinstance(r, DecisionRecord)}
    forfeits: dict[int, list[ForfeitRecord]] = {}
    for record in records:
        if isinstance(record, ForfeitRecord):
            forfeits.setdefault(record.step, []).append(record)
    frames = [
        frame(
            replayed,
            step,
            events.get(step, []),
            decisions.get(step),
            forfeits.get(step, []),
        )
        for step in range(replayed.last_step + 1)
    ]
    return Timeline(match=summarize(list(records)), frames=frames)


def move_view(decision: DecisionView, step: int) -> MoveView:
    return MoveView(
        step=step,
        player=decision.player,
        action=decision.action,
        description=decision.description,
        illegal_attempts=decision.trace.illegal_attempts,
        fallback=decision.trace.fallback,
    )


def outline(timeline: Timeline) -> Outline:
    """The timeline without boards and traces, small enough to send whole."""
    return Outline(
        match=timeline.match,
        frame_count=len(timeline.frames),
        moves=[move_view(f.decision, f.step) for f in timeline.frames if f.decision],
        events=[event for f in timeline.frames for event in f.events],
        forfeits=[forfeit for f in timeline.frames for forfeit in f.forfeits],
        scores=[f.scores for f in timeline.frames],
    )
