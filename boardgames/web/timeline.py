"""Timeline: a match log replayed into one frame per step for the replay viewer.

Frame 0 is the state after setup; frame `n` the state after the n-th applied
action. Every frame carries the spectator's observation, each seat's rendered
view, the step's events with their audience, and the decision that made it.
"""

from collections.abc import Sequence
from dataclasses import dataclass
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
    MatchStopped,
    TraceRecord,
    plain_object,
)
from boardgames.web.store import AnyMatch, summarize

ERROR_TEXT_LIMIT = 240


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
    """Frames up to the last step that replays; `replay_error` says why it stopped
    early when the log no longer matches the current game rules."""

    match: AnyMatch
    frames: list[Frame]
    replay_error: str | None = None


class MoveView(View):
    """One step as the outline lists it: who did what, without boards or traces."""

    step: int
    player: int
    action: str
    description: str
    illegal_attempts: int
    fallback: str | None
    latency_seconds: float


class Outline(View):
    """The light part of a timeline: every move, event and score, but no boards."""

    match: AnyMatch
    frame_count: int
    moves: list[MoveView]
    events: list[EventRecord]
    forfeits: list[ForfeitView]
    scores: list[list[ScoreView]]
    replay_error: str | None
    # when the log was last written; a running match's current decision began then
    log_updated_at: str | None


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
    """Public points and ranks in seat order; hidden points show once the game ends."""
    scores = game.public_scores(state)
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


@dataclass(frozen=True)
class CompleteSteps:
    """The replayable part of a log; `mismatch` is set when the log diverged from
    the current rules, rather than ending in a step still being written."""

    replayed: Replayed
    records: list[LogRecord]
    mismatch: str | None


def replay_complete_steps(records: Sequence[LogRecord]) -> CompleteSteps:
    """Replay a log, dropping decisions from the end until the rest replays.

    Dropping one decision from a running log is normal: it is still being
    written. Anything more means the log no longer matches the game's rules.
    A log whose setup does not replay raises ReplayMismatchError.
    """
    remaining = list(records)
    first_error: str | None = None
    dropped = 0
    while True:
        try:
            replayed = replay_states(remaining)
        except ReplayMismatchError as error:
            first_error = first_error or str(error)
            remaining = without_last_decision(remaining)
            if not remaining:
                raise
            dropped += 1
            continue
        is_ended = any(isinstance(r, MatchFinished | MatchStopped) for r in records)
        diverged = dropped > 1 or (dropped == 1 and is_ended)
        mismatch = shortened(first_error) if diverged and first_error else None
        return CompleteSteps(replayed, remaining, mismatch)


def shortened(text: str, limit: int = ERROR_TEXT_LIMIT) -> str:
    """`text` cut to `limit` characters, with an ellipsis when cut."""
    return text if len(text) <= limit else text[:limit] + "…"


def build_timeline(records: Sequence[LogRecord]) -> Timeline:
    """Replay the log and lay out one frame per step, up to the last step that
    replays; an ended log's summary covers the whole log, so it keeps its status."""
    complete = replay_complete_steps(records)
    replayed = complete.replayed
    events = events_by_step(complete.records)
    decisions = {r.step: r for r in complete.records if isinstance(r, DecisionRecord)}
    forfeits: dict[int, list[ForfeitRecord]] = {}
    for record in complete.records:
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
    is_ended = any(isinstance(r, MatchFinished | MatchStopped) for r in records)
    finish = next((r for r in records if isinstance(r, MatchFinished)), None)
    if finish is not None and replayed.last_step == finish.steps:
        frames[-1] = frames[-1].model_copy(
            update={
                "scores": [
                    ScoreView(
                        player=score.player,
                        points=score.points,
                        rank=score.rank,
                        breakdown=score.breakdown,
                    )
                    for score in finish.scores
                ]
            }
        )
    summarized = list(records) if is_ended else complete.records
    return Timeline(
        match=summarize(summarized),
        frames=frames,
        replay_error=complete.mismatch,
    )


def move_view(decision: DecisionView, step: int) -> MoveView:
    return MoveView(
        step=step,
        player=decision.player,
        action=decision.action,
        description=decision.description,
        illegal_attempts=decision.trace.illegal_attempts,
        fallback=decision.trace.fallback,
        latency_seconds=decision.latency_seconds,
    )


def outline(timeline: Timeline, log_updated_at: str | None = None) -> Outline:
    """The timeline without boards and traces, small enough to send whole."""
    return Outline(
        log_updated_at=log_updated_at,
        match=timeline.match,
        frame_count=len(timeline.frames),
        moves=[move_view(f.decision, f.step) for f in timeline.frames if f.decision],
        events=[event for f in timeline.frames for event in f.events],
        forfeits=[forfeit for f in timeline.frames for forfeit in f.forfeits],
        scores=[f.scores for f in timeline.frames],
        replay_error=timeline.replay_error,
    )
