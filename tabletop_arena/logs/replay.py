"""Replay: rebuild a match from its seed and actions, checking each step.

Every observation digest, action and event is recomputed from the game rules, so
a passing replay shows the game is deterministic and the log is complete.
Games must be registered (import `tabletop_arena.games`) before replaying.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from tabletop_arena.core import (
    AnyGame,
    ArenaError,
    Event,
    IllegalActionError,
    NotationError,
    PlayerId,
    create_game,
)
from tabletop_arena.logs.schema import (
    LOG_RECORD,
    DecisionRecord,
    EventRecord,
    ForfeitRecord,
    LogRecord,
    MatchFinished,
    MatchStarted,
    event_json,
    plain_object,
)


class LogFormatError(ArenaError):
    """A log file does not follow the record schema."""


class ReplayMismatchError(ArenaError):
    """The replayed match differs from its log."""


@dataclass(frozen=True)
class ReplayReport:
    match_id: str
    game_id: str
    steps: int
    events: int


def read_log(path: Path) -> list[LogRecord]:
    """Records of a JSONL log file, validated against the schema."""
    records: list[LogRecord] = []
    with path.open(encoding="utf-8") as file:
        for number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                records.append(LOG_RECORD.validate_json(line))
            except ValidationError as error:
                raise LogFormatError(f"{path}:{number}: {error}") from error
    return records


def replay_match(records: Sequence[LogRecord]) -> ReplayReport:
    """Replay a logged match; any difference raises ReplayMismatchError."""
    start = first_record(records, MatchStarted)
    finish = first_record(records, MatchFinished)
    game = create_game(start.game_id)
    events = events_by_step(records)
    setup = game.setup(game.parse_config(start.config), start.seed)
    check_events(0, events.get(0, []), setup.events)
    states: dict[int, Any] = {0: setup.state}
    step = 0
    forfeited: list[PlayerId] = []
    for record in records:
        if isinstance(record, DecisionRecord):
            step = check_step(step, record)
            check_observation(game, states, record)
            states[step] = replay_decision(game, states[step - 1], record, events)
        elif isinstance(record, ForfeitRecord):
            check_observation(game, states, record)
            forfeited.append(PlayerId(record.player))
    check_finish(game, states[step], step, forfeited, finish)
    return ReplayReport(
        match_id=start.match_id,
        game_id=start.game_id,
        steps=step,
        events=sum(len(logged) for logged in events.values()),
    )


def first_record[R: LogRecord](records: Sequence[LogRecord], kind: type[R]) -> R:
    """The first record of type `kind`; a log without one is malformed."""
    for record in records:
        if isinstance(record, kind):
            return record
    raise LogFormatError(f"log has no {kind.__name__} record")


def events_by_step(records: Sequence[LogRecord]) -> dict[int, list[EventRecord]]:
    """Logged events grouped by the step that emitted them, in log order."""
    grouped: dict[int, list[EventRecord]] = {}
    for record in records:
        if isinstance(record, EventRecord):
            grouped.setdefault(record.step, []).append(record)
    return grouped


def check_events(
    step: int, logged: Sequence[EventRecord], replayed: Sequence[Event]
) -> None:
    """Raise ReplayMismatchError at the first event that differs."""
    expected = [record.model_dump(exclude={"type", "step"}) for record in logged]
    actual = [event_json(event) for event in replayed]
    pairs = zip(expected, actual, strict=False)
    for index, (logged_event, replayed_event) in enumerate(pairs):
        if logged_event != replayed_event:
            raise ReplayMismatchError(
                f"step {step}, event {index}: log has {logged_event!r}, "
                f"replay has {replayed_event!r}"
            )
    if len(expected) != len(actual):
        raise ReplayMismatchError(
            f"step {step}: log has {len(expected)} events, replay has {len(actual)}"
        )
    return


def check_step(previous: int, record: DecisionRecord) -> int:
    """The decision's step, which must follow the previous one."""
    if record.step != previous + 1:
        raise ReplayMismatchError(
            f"decision at step {record.step} follows step {previous}"
        )
    return record.step


def check_observation(
    game: AnyGame, states: dict[int, Any], record: DecisionRecord | ForfeitRecord
) -> None:
    """The player's observation of the state they decided on must match the log."""
    state = states[record.observed_at_step]
    digest = game.observe(state, PlayerId(record.player)).digest()
    if digest != record.observation_digest:
        raise ReplayMismatchError(
            f"step {record.step}: P{record.player + 1} observation differs from the log"
        )
    return


def replay_decision(
    game: AnyGame,
    state: Any,
    record: DecisionRecord,
    events: dict[int, list[EventRecord]],
) -> Any:
    """Parse and apply a logged action, checking its notation, JSON and events."""
    step = record.step
    try:
        action = game.parse_action(record.action)
        transition = game.apply(state, PlayerId(record.player), action)
    except (NotationError, IllegalActionError) as error:
        raise ReplayMismatchError(f"step {step}: {record.action!r}: {error}") from error
    if game.format_action(action) != record.action:
        raise ReplayMismatchError(f"step {step}: notation of {record.action!r} changed")
    if plain_object(game.action_json(action)) != record.action_json:
        raise ReplayMismatchError(f"step {step}: machine form of {record.action!r}")
    check_events(step, events.get(step, []), transition.events)
    return transition.state


def check_finish(
    game: AnyGame,
    state: Any,
    step: int,
    forfeited: list[PlayerId],
    finish: MatchFinished,
) -> None:
    """Final step count, forfeits, terminal state and scores must match the log."""
    if finish.steps != step:
        raise ReplayMismatchError(f"log ends at step {finish.steps}, replay at {step}")
    if sorted(finish.forfeited) != sorted(forfeited):
        raise ReplayMismatchError("forfeits differ from the forfeit records")
    if not forfeited and not game.is_terminal(state):
        raise ReplayMismatchError("the log ends before the game is over")
    scores = game.scores(state)
    ranks = scores.ranks_after_forfeits(forfeited)
    replayed = {p: (scores.points[p], ranks[p]) for p in scores.points}
    logged = {PlayerId(s.player): (s.points, s.rank) for s in finish.scores}
    if replayed != logged:
        raise ReplayMismatchError(f"final scores: log has {logged}, replay {replayed}")
    return
