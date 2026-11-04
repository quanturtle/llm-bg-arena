"""Replay: rebuild a match from its seed and actions, checking each step.

Every decision, observation, action and event is recomputed from the game rules,
so a passing replay shows the game is deterministic and the log is complete.
Games must be registered (import `boardgames.games`) before replaying.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from boardgames.core import (
    AnyGame,
    ArenaError,
    Event,
    IllegalActionError,
    NotationError,
    PlayerId,
    create_game,
)
from boardgames.logs.schema import (
    LOG_RECORD,
    DecisionRecord,
    EventRecord,
    ForfeitRecord,
    LogRecord,
    MatchFinished,
    MatchStarted,
    MatchStopped,
    event_json,
    plain_object,
)
from boardgames.logs.sink import LogFileError

type Ending = Literal["finished", "stopped"]


class LogFormatError(ArenaError):
    """A log file does not follow the record schema."""


class ReplayMismatchError(ArenaError):
    """The replayed match differs from its log."""


class RulesVersionError(ReplayMismatchError):
    """The log was recorded under another version of the game's rules."""


@dataclass(frozen=True)
class ReplayReport:
    match_id: str
    game_id: str
    steps: int
    events: int
    ending: Ending


def read_log(path: Path) -> list[LogRecord]:
    """Records of a JSONL log file, validated against the schema."""
    records: list[LogRecord] = []
    try:
        file = path.open(encoding="utf-8")
    except OSError as error:
        raise LogFileError(f"cannot read {path}: {error.strerror}") from error
    with file:
        try:
            for number, line in enumerate(file, start=1):
                if not line.strip():
                    continue
                try:
                    records.append(LOG_RECORD.validate_json(line))
                except ValidationError as error:
                    raise LogFormatError(f"{path}:{number}: {error}") from error
        except UnicodeDecodeError as error:
            raise LogFormatError(f"{path} is not UTF-8 text: {error}") from error
    return records


@dataclass(frozen=True)
class Replayed:
    """The states a log rebuilds to: `states[step]` is the state after `step`."""

    game: AnyGame
    start: MatchStarted
    states: dict[int, Any]
    forfeited: tuple[PlayerId, ...]

    @property
    def last_step(self) -> int:
        return max(self.states)


def replay_states(records: Sequence[LogRecord]) -> Replayed:
    """Every state of a log, checking each decision; the log may be unfinished."""
    start = first_record(records, MatchStarted)
    game = create_game(start.game_id)
    check_rules_version(game, start)
    events = events_by_step(records)
    setup = game.setup(game.parse_config(start.config), start.seed)
    check_events(0, events.get(0, []), setup.events)
    states: dict[int, Any] = {0: setup.state}
    step = 0
    forfeited: list[PlayerId] = []
    for record in records:
        if isinstance(record, DecisionRecord):
            step = check_step(step, record)
            seen = observed_state(states, record)
            check_decision(game, seen, record)
            check_observation(game, seen, record)
            states[step] = replay_decision(game, states[step - 1], record, events)
        elif isinstance(record, ForfeitRecord):
            check_forfeit_step(step, record)
            check_observation(game, observed_state(states, record), record)
            forfeited.append(PlayerId(record.player))
    check_event_steps(events, states)
    return Replayed(game, start, states, tuple(forfeited))


def replay_match(records: Sequence[LogRecord]) -> ReplayReport:
    """Replay a finished or stopped match; any difference raises ReplayMismatchError."""
    end = match_end(records)
    replayed = replay_states(records)
    step = replayed.last_step
    state = replayed.states[step]
    if isinstance(end, MatchFinished):
        check_finish(replayed.game, state, step, replayed.forfeited, end)
    else:
        check_stop(replayed.game, state, step, end)
    return ReplayReport(
        match_id=replayed.start.match_id,
        game_id=replayed.start.game_id,
        steps=step,
        events=sum(1 for record in records if isinstance(record, EventRecord)),
        ending="finished" if isinstance(end, MatchFinished) else "stopped",
    )


def match_end(records: Sequence[LogRecord]) -> MatchFinished | MatchStopped:
    """The record that ends the log: match_finished or match_stopped."""
    for record in records:
        if isinstance(record, MatchFinished | MatchStopped):
            return record
    raise LogFormatError("log has no MatchFinished or MatchStopped record")


def first_record[R: LogRecord](records: Sequence[LogRecord], kind: type[R]) -> R:
    """The first record of type `kind`; a log without one is malformed."""
    for record in records:
        if isinstance(record, kind):
            return record
    raise LogFormatError(f"log has no {kind.__name__} record")


def check_rules_version(game: AnyGame, start: MatchStarted) -> None:
    """Raise RulesVersionError unless the log uses the game's current rules."""
    if start.rules_version != game.rules_version:
        raise RulesVersionError(
            f"recorded under {game.id} rules v{start.rules_version}; "
            f"the current rules are v{game.rules_version}; "
            "`arena upgrade-log` re-records it if its moves are still legal"
        )
    return


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


def observed_state(
    states: dict[int, Any], record: DecisionRecord | ForfeitRecord
) -> Any:
    """The replayed state at the record's `observed_at_step`."""
    if record.observed_at_step not in states:
        raise ReplayMismatchError(
            f"step {record.step}: observed_at_step {record.observed_at_step} "
            "is not a state the replay has reached"
        )
    return states[record.observed_at_step]


def check_decision(game: AnyGame, state: Any, record: DecisionRecord) -> None:
    """The player's open decision in the observed state must match the logged one."""
    player = PlayerId(record.player)
    open_decisions = {
        pending.player: pending for pending in game.pending_decisions(state)
    }
    decision = open_decisions.get(player)
    if decision is None:
        raise ReplayMismatchError(
            f"step {record.step}: P{player + 1} has no open decision"
        )
    logged = (record.kind, record.prompt)
    replayed = (decision.kind, decision.prompt)
    if logged != replayed:
        raise ReplayMismatchError(
            f"step {record.step}: P{player + 1} decision: log has {logged!r}, "
            f"replay has {replayed!r}"
        )
    return


def check_observation(
    game: AnyGame, state: Any, record: DecisionRecord | ForfeitRecord
) -> None:
    """The player's observation of the state they decided on must match the log.

    A decision record's full observation is compared, not only its digest.
    """
    observation = game.observe(state, PlayerId(record.player))
    if observation.digest() != record.observation_digest:
        raise ReplayMismatchError(
            f"step {record.step}: P{record.player + 1} observation differs from the log"
        )
    if (
        isinstance(record, DecisionRecord)
        and plain_object(observation.data) != record.observation
    ):
        raise ReplayMismatchError(
            f"step {record.step}: P{record.player + 1} logged observation data "
            "differs from the replay"
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


def check_forfeit_step(step: int, record: ForfeitRecord) -> None:
    """A forfeit is logged at the step the match has reached."""
    if record.step != step:
        raise ReplayMismatchError(f"forfeit at step {record.step} follows step {step}")
    return


def check_event_steps(
    events: dict[int, list[EventRecord]], states: dict[int, Any]
) -> None:
    """Every logged event belongs to setup (step 0) or to a replayed decision."""
    orphans = sorted(set(events) - set(states))
    if orphans:
        raise ReplayMismatchError(f"events at step {orphans[0]} follow no decision")
    return


def check_finish(
    game: AnyGame,
    state: Any,
    step: int,
    forfeited: Sequence[PlayerId],
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


def check_stop(game: AnyGame, state: Any, step: int, stop: MatchStopped) -> None:
    """A stopped match ends at the last replayed step, before the game is over."""
    if stop.steps != step:
        raise ReplayMismatchError(f"log stops at step {stop.steps}, replay at {step}")
    if game.is_terminal(state):
        raise ReplayMismatchError("the log says stopped but the game is over")
    return
