"""Match store: a directory of JSONL logs, indexed into per-match summaries.

The store is the viewer's repository. It rereads a log only when its size or
modification time changed, so a running match shows up as it is written.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator
from pydantic import JsonValue as PlainJson

from boardgames.core import ArenaError
from boardgames.logs.replay import LogFormatError, first_record, read_log
from boardgames.logs.schema import (
    DecisionRecord,
    ForfeitRecord,
    LogRecord,
    MatchFinished,
    MatchStarted,
    MatchStopped,
    UnfinishedDecisionRecord,
)
from boardgames.logs.sink import LogFileError
from boardgames.logs.thoughts import thoughts_path

type MatchStatus = Literal["finished", "running", "stopped"]


class UnknownMatchError(ArenaError):
    """No log in the store has this match id."""


class ReadOnlyLogError(ArenaError):
    """The match's log was opened read-only, so the viewer cannot delete it."""


class Summary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SeatSummary(Summary):
    """One seat's result and usage; points and rank are None while the match runs.

    `model` is the model id of a language model seat, None for a bot.
    """

    player: int
    agent: str
    kind: str
    model: str | None
    settings: dict[str, PlainJson]
    points: float | None
    rank: int | None
    forfeited: bool
    decisions: int
    illegal_attempts: int
    api_retries: int
    fallbacks: int
    latency_seconds: float
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float | None


class FinishedSeatSummary(SeatSummary):
    """A finished match's seat, whose points and rank are always known."""

    points: float
    rank: int


class UnscoredSeatSummary(SeatSummary):
    """A running or stopped match's seat, which has no points or rank."""

    points: None = None
    rank: None = None


class MatchSummary(Summary):
    """The common fields of a match, and a factory for the right status variant.

    Use `FinishedMatch` when points and ranks must be present; a running or
    stopped match keeps them optional.
    """

    match_id: str
    game_id: str
    config: dict[str, PlainJson]
    seed: int
    started_at: str
    finished_at: str | None
    steps: int
    status: MatchStatus
    # the prompt templates its model seats used; 0 for logs from before versioning
    prompt_version: int
    seats: Sequence[SeatSummary]

    def __new__(cls, **data: Any) -> Any:
        """Construct the variant that fits `status` when called as `MatchSummary`."""
        if cls is MatchSummary:
            status = data.get("status")
            variants: dict[
                str, type[FinishedMatch] | type[RunningMatch] | type[StoppedMatch]
            ] = {
                "finished": FinishedMatch,
                "running": RunningMatch,
                "stopped": StoppedMatch,
            }
            variant = variants.get(status) if isinstance(status, str) else None
            if variant is not None:
                return object.__new__(variant)
        return object.__new__(cls)

    @property
    def is_finished(self) -> bool:
        return self.status == "finished"

    def winners(self) -> list[int]:
        """Seats ranked first; empty while the match is running."""
        return [seat.player for seat in self.seats if seat.rank == 1]


class FinishedMatch(MatchSummary):
    status: Literal["finished"] = "finished"
    finished_at: str
    seats: Sequence[FinishedSeatSummary]

    @model_validator(mode="before")
    @classmethod
    def _finished_seats(cls, data: Any) -> Any:
        """Accept plain seats built by callers, as long as they have a result."""
        if not isinstance(data, dict):
            return data
        seats = data.get("seats")
        if not isinstance(seats, Sequence) or isinstance(seats, str):
            return data
        return {
            **data,
            "seats": [
                seat.model_dump()
                if isinstance(seat, SeatSummary)
                and not isinstance(seat, FinishedSeatSummary)
                else seat
                for seat in seats
            ],
        }


class RunningMatch(MatchSummary):
    status: Literal["running"] = "running"
    finished_at: None = None
    seats: Sequence[UnscoredSeatSummary]


class StoppedMatch(MatchSummary):
    status: Literal["stopped"] = "stopped"
    finished_at: str
    seats: Sequence[UnscoredSeatSummary]


type AnyMatch = FinishedMatch | RunningMatch | StoppedMatch
MATCH_SUMMARIES = (FinishedMatch, RunningMatch, StoppedMatch)


class UnreadableLog(Summary):
    path: str
    error: str


class Catalog(Summary):
    """Every match in the store, newest first, and the logs that could not be read."""

    matches: list[AnyMatch]
    unreadable: list[UnreadableLog]


def seat_kind(settings: dict[str, PlainJson]) -> str:
    """The agent kind recorded in its settings ("random", "llm"), else "unknown"."""
    kind = settings.get("kind")
    return kind if isinstance(kind, str) else "unknown"


def seat_model(settings: dict[str, PlainJson]) -> str | None:
    """The model id an LLM seat recorded in its settings, else None."""
    model = settings.get("model")
    model_id = model.get("model") if isinstance(model, dict) else None
    return model_id if isinstance(model_id, str) else None


def add_cost(total: float | None, cost: float | None) -> float | None:
    """Sum of costs where one unknown cost makes the total unknown."""
    if total is None or cost is None:
        return None
    return total + cost


# an unfinished decision adds its cost and tokens, but is neither a decision nor
# a forfeit
type Answer = DecisionRecord | ForfeitRecord | UnfinishedDecisionRecord


def seat_summary(
    start: MatchStarted,
    player: int,
    answers: list[Answer],
    finish: MatchFinished | None,
) -> SeatSummary:
    """Aggregate one seat's decisions, forfeit and final score."""
    seat = start.seats[player]
    traces = [answer.trace for answer in answers]
    cost: float | None = 0.0
    for trace in traces:
        cost = add_cost(cost, trace.cost_usd)
    score = None
    if finish is not None:
        score = next((s for s in finish.scores if s.player == player), None)
    return SeatSummary(
        player=player,
        agent=seat.agent,
        kind=seat_kind(seat.settings),
        model=seat_model(seat.settings),
        settings=seat.settings,
        points=None if score is None else score.points,
        rank=None if score is None else score.rank,
        forfeited=any(isinstance(answer, ForfeitRecord) for answer in answers),
        decisions=sum(1 for answer in answers if isinstance(answer, DecisionRecord)),
        illegal_attempts=sum(trace.illegal_attempts for trace in traces),
        api_retries=sum(trace.api_retries for trace in traces),
        fallbacks=sum(1 for trace in traces if trace.fallback is not None),
        latency_seconds=sum(answer.latency_seconds for answer in answers),
        prompt_tokens=sum(trace.prompt_tokens for trace in traces),
        completion_tokens=sum(trace.completion_tokens for trace in traces),
        cost_usd=cost,
    )


def finished_seat_summary(
    start: MatchStarted,
    player: int,
    answers: list[Answer],
    finish: MatchFinished,
) -> FinishedSeatSummary:
    """A finished match's seat, with the points and rank its finish recorded."""
    return FinishedSeatSummary(
        **seat_summary(start, player, answers, finish).model_dump()
    )


def unscored_seat_summary(
    start: MatchStarted, player: int, answers: list[Answer]
) -> UnscoredSeatSummary:
    """A running or stopped match's seat, without points or rank."""
    return UnscoredSeatSummary(
        **seat_summary(start, player, answers, None).model_dump()
    )


def summarize(records: list[LogRecord]) -> AnyMatch:
    """Summary of one log; a log with neither match_finished nor match_stopped runs.

    A stopped match has no points or ranks and `finished_at` is when it stopped.
    """
    start = first_record(records, MatchStarted)
    finish = next((r for r in records if isinstance(r, MatchFinished)), None)
    stop = next((r for r in records if isinstance(r, MatchStopped)), None)
    answers: dict[int, list[Answer]] = {s.player: [] for s in start.seats}
    steps = 0
    for record in records:
        if isinstance(
            record, DecisionRecord | ForfeitRecord | UnfinishedDecisionRecord
        ):
            if record.player not in answers:
                raise LogFormatError(
                    f"a record for player {record.player} in a match with "
                    f"{len(start.seats)} seats"
                )
            answers[record.player].append(record)
        if isinstance(record, DecisionRecord | ForfeitRecord):
            steps = max(steps, record.step)
    common: dict[str, Any] = {
        "match_id": start.match_id,
        "game_id": start.game_id,
        "config": start.config,
        "seed": start.seed,
        "started_at": start.started_at,
        "prompt_version": prompt_version_of(start),
    }
    players = sorted(answers)
    if finish is not None:
        return FinishedMatch(
            **common,
            finished_at=finish.finished_at,
            steps=finish.steps,
            seats=[
                finished_seat_summary(start, player, answers[player], finish)
                for player in players
            ],
        )
    seats = [
        unscored_seat_summary(start, player, answers[player]) for player in players
    ]
    if stop is not None:
        return StoppedMatch(
            **common, finished_at=stop.stopped_at, steps=steps, seats=seats
        )
    return RunningMatch(**common, steps=steps, seats=seats)


def prompt_version_of(start: MatchStarted) -> int:
    """The prompt version the match's model seats logged; 0 if none logged one."""
    versions = (seat.settings.get("prompt_version") for seat in start.seats)
    return next((v for v in versions if isinstance(v, int)), 0)


def ended_at(finish: MatchFinished | None, stop: MatchStopped | None) -> str | None:
    """When the match finished or was stopped; None while it runs."""
    if finish is not None:
        return finish.finished_at
    return None if stop is None else stop.stopped_at


def match_status(
    finish: MatchFinished | None, stop: MatchStopped | None
) -> MatchStatus:
    """Finished, stopped, or still running."""
    if finish is not None:
        return "finished"
    return "running" if stop is None else "stopped"


type FileStamp = tuple[int, int]
type Indexed = AnyMatch | UnreadableLog


def index_log(path: Path) -> Indexed:
    """Summary of the log at `path`, or why it could not be read.

    A ValidationError means the records do not fit a summary, such as a missing score.
    """
    try:
        return summarize(read_log(path))
    except (LogFormatError, LogFileError, ValidationError) as error:
        return UnreadableLog(path=path.name, error=str(error))


class MatchStore:
    """Repository over `directory/*.jsonl` and `read_only` logs, rescanned per call."""

    def __init__(self, directory: Path, read_only: tuple[Path, ...] = ()) -> None:
        self._directory = directory
        self._read_only = read_only
        self._cache: dict[Path, tuple[FileStamp, Indexed]] = {}
        self._paths: dict[str, Path] = {}
        return

    @property
    def directory(self) -> Path:
        return self._directory

    def catalog(self) -> Catalog:
        """Every match, newest first, plus the logs that failed to parse.

        Two logs of one match list once, from the first path found."""
        matches: list[AnyMatch] = []
        unreadable: list[UnreadableLog] = []
        listed: set[str] = set()
        for path in self._log_paths():
            indexed = self._indexed(path)
            if isinstance(indexed, MATCH_SUMMARIES):
                if indexed.match_id in listed:
                    continue
                listed.add(indexed.match_id)
                matches.append(indexed)
                self._paths[indexed.match_id] = path
            else:
                unreadable.append(indexed)
        matches.sort(key=lambda m: (m.started_at, m.match_id), reverse=True)
        return Catalog(matches=matches, unreadable=unreadable)

    def match(self, match_id: str) -> AnyMatch:
        """Summary of one match; unknown ids raise UnknownMatchError."""
        indexed = self._indexed(self._path_of(match_id))
        if not isinstance(indexed, MATCH_SUMMARIES):
            raise UnknownMatchError(f"log of match {match_id!r}: {indexed.error}")
        return indexed

    def records(self, match_id: str) -> list[LogRecord]:
        """Every record of one match's log."""
        path = self._path_of(match_id)
        try:
            return read_log(path)
        except (LogFileError, OSError) as error:
            self._paths.pop(match_id, None)
            raise UnknownMatchError(f"log of match {match_id!r} is gone") from error

    def updated_at(self, match_id: str) -> str:
        """When the match's log was last written, UTC ISO 8601.

        While a match runs, its current decision began at about this time."""
        path = self._path_of(match_id)
        try:
            modified = path.stat().st_mtime
        except OSError as error:
            self._paths.pop(match_id, None)
            raise UnknownMatchError(f"log of match {match_id!r} is gone") from error
        return datetime.fromtimestamp(modified, UTC).isoformat(timespec="milliseconds")

    def stamp(self, match_id: str) -> FileStamp:
        """The log's modification time and size, used to notice any new bytes."""
        path = self._path_of(match_id)
        try:
            stat = path.stat()
        except OSError as error:
            self._paths.pop(match_id, None)
            raise UnknownMatchError(f"log of match {match_id!r} is gone") from error
        return (stat.st_mtime_ns, stat.st_size)

    def delete(self, match_id: str) -> None:
        """Remove a match's log and thoughts file; unknown ids raise UnknownMatchError.

        Only files found in the store's directory are removed; read-only logs raise.
        A duplicate copy of the same match in the directory is removed too, so the
        match does not reappear after its deletion.
        """
        path = self._path_of(match_id)
        if path.resolve() in {log.resolve() for log in self._read_only}:
            raise ReadOnlyLogError(f"match {match_id!r} was opened read-only")
        copies = [path]
        if self._directory.is_dir():
            copies.extend(
                other
                for other in self._directory.glob("*.jsonl")
                if other.resolve() != path.resolve()
            )
        for copy in copies:
            indexed = self._indexed(copy)
            if not isinstance(indexed, MATCH_SUMMARIES) or indexed.match_id != match_id:
                continue
            copy.unlink(missing_ok=True)
            thoughts_path(copy).unlink(missing_ok=True)
            self._cache.pop(copy, None)
            self._paths.pop(match_id, None)
        return

    def _log_paths(self) -> list[Path]:
        found = (
            sorted(self._directory.glob("*.jsonl")) if self._directory.is_dir() else []
        )
        listed = {path.resolve() for path in found}
        return found + [
            log
            for log in self._read_only
            if log.is_file() and log.resolve() not in listed
        ]

    def _path_of(self, match_id: str) -> Path:
        if match_id not in self._paths:
            self.catalog()
        path = self._paths.get(match_id)
        if path is None or not path.is_file():
            self._paths.pop(match_id, None)
            raise UnknownMatchError(f"unknown match {match_id!r}")
        return path

    def _indexed(self, path: Path) -> Indexed:
        """The cached summary of `path`, reread when the file changed."""
        try:
            stat = path.stat()
        except OSError as error:
            self._cache.pop(path, None)
            return UnreadableLog(path=path.name, error=str(error))
        stamp = (stat.st_mtime_ns, stat.st_size)
        cached = self._cache.get(path)
        if cached is not None and cached[0] == stamp:
            return cached[1]
        indexed = index_log(path)
        self._cache[path] = (stamp, indexed)
        return indexed
