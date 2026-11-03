"""Match store: a directory of JSONL logs, indexed into per-match summaries.

The store is the viewer's repository. It rereads a log only when its size or
modification time changed, so a running match shows up as it is written.
"""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic import JsonValue as PlainJson

from boardgames.core import ArenaError
from boardgames.logs.replay import LogFormatError, first_record, read_log
from boardgames.logs.schema import (
    DecisionRecord,
    ForfeitRecord,
    LogRecord,
    MatchFinished,
    MatchStarted,
)


class UnknownMatchError(ArenaError):
    """No log in the store has this match id."""


class Summary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SeatSummary(Summary):
    """One seat's result and usage; points and rank are None while the match runs."""

    player: int
    agent: str
    kind: str
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


class MatchSummary(Summary):
    match_id: str
    game_id: str
    config: dict[str, PlainJson]
    seed: int
    started_at: str
    finished_at: str | None
    steps: int
    status: Literal["finished", "running"]
    seats: list[SeatSummary]

    @property
    def is_finished(self) -> bool:
        return self.status == "finished"

    def winners(self) -> list[int]:
        """Seats ranked first; empty while the match is running."""
        return [seat.player for seat in self.seats if seat.rank == 1]


class UnreadableLog(Summary):
    path: str
    error: str


class Catalog(Summary):
    """Every match in the store, newest first, and the logs that could not be read."""

    matches: list[MatchSummary]
    unreadable: list[UnreadableLog]


def seat_kind(settings: dict[str, PlainJson]) -> str:
    """The agent kind recorded in its settings ("random", "llm"), else "unknown"."""
    kind = settings.get("kind")
    return kind if isinstance(kind, str) else "unknown"


def add_cost(total: float | None, cost: float | None) -> float | None:
    """Sum of costs where one unknown cost makes the total unknown."""
    if total is None or cost is None:
        return None
    return total + cost


type Answer = DecisionRecord | ForfeitRecord


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
        score = next(s for s in finish.scores if s.player == player)
    return SeatSummary(
        player=player,
        agent=seat.agent,
        kind=seat_kind(seat.settings),
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


def summarize(records: list[LogRecord]) -> MatchSummary:
    """Summary of one log; a log without match_finished is a running match."""
    start = first_record(records, MatchStarted)
    finish = next((r for r in records if isinstance(r, MatchFinished)), None)
    answers: dict[int, list[Answer]] = {s.player: [] for s in start.seats}
    steps = 0
    for record in records:
        if isinstance(record, DecisionRecord | ForfeitRecord):
            answers[record.player].append(record)
            steps = max(steps, record.step)
    seats = [
        seat_summary(start, player, answers[player], finish)
        for player in sorted(answers)
    ]
    return MatchSummary(
        match_id=start.match_id,
        game_id=start.game_id,
        config=start.config,
        seed=start.seed,
        started_at=start.started_at,
        finished_at=None if finish is None else finish.finished_at,
        steps=finish.steps if finish is not None else steps,
        status="finished" if finish is not None else "running",
        seats=seats,
    )


type FileStamp = tuple[int, int]
type Indexed = MatchSummary | UnreadableLog


def index_log(path: Path) -> Indexed:
    """Summary of the log at `path`, or why it could not be read."""
    try:
        return summarize(read_log(path))
    except LogFormatError as error:
        return UnreadableLog(path=path.name, error=str(error))


class MatchStore:
    """Repository over `directory/*.jsonl`, rescanned on every call."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._cache: dict[Path, tuple[FileStamp, Indexed]] = {}
        self._paths: dict[str, Path] = {}
        return

    @property
    def directory(self) -> Path:
        return self._directory

    def catalog(self) -> Catalog:
        """Every match, newest first, plus the logs that failed to parse."""
        matches: list[MatchSummary] = []
        unreadable: list[UnreadableLog] = []
        for path in self._log_paths():
            indexed = self._indexed(path)
            if isinstance(indexed, MatchSummary):
                matches.append(indexed)
                self._paths[indexed.match_id] = path
            else:
                unreadable.append(indexed)
        matches.sort(key=lambda m: (m.started_at, m.match_id), reverse=True)
        return Catalog(matches=matches, unreadable=unreadable)

    def match(self, match_id: str) -> MatchSummary:
        """Summary of one match; unknown ids raise UnknownMatchError."""
        indexed = self._indexed(self._path_of(match_id))
        if not isinstance(indexed, MatchSummary):
            raise UnknownMatchError(f"log of match {match_id!r}: {indexed.error}")
        return indexed

    def records(self, match_id: str) -> list[LogRecord]:
        """Every record of one match's log."""
        return read_log(self._path_of(match_id))

    def _log_paths(self) -> list[Path]:
        if not self._directory.is_dir():
            return []
        return sorted(self._directory.glob("*.jsonl"))

    def _path_of(self, match_id: str) -> Path:
        if match_id not in self._paths:
            self.catalog()
        if match_id not in self._paths:
            raise UnknownMatchError(f"unknown match {match_id!r}")
        return self._paths[match_id]

    def _indexed(self, path: Path) -> Indexed:
        """The cached summary of `path`, reread when the file changed."""
        stat = path.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
        cached = self._cache.get(path)
        if cached is not None and cached[0] == stamp:
            return cached[1]
        indexed = index_log(path)
        self._cache[path] = (stamp, indexed)
        return indexed
