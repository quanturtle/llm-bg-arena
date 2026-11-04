"""Match log records: one JSON object per line, discriminated by "type".

A log is: match_started, the setup events (step 0), then per applied decision a
decision record and its events, and finally match_finished, or match_stopped
for a match stopped before the end. A forfeit record replaces the decision
record of a player who gave up.
"""

import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from pydantic import JsonValue as PlainJson

from boardgames.agents import AttemptRecord, DecisionTrace, FallbackPolicy
from boardgames.core import Event, JsonObject, JsonValue, clean_json

LOG_VERSION = 1


class Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SeatRecord(Record):
    player: int
    agent: str
    settings: dict[str, PlainJson]


class MatchStarted(Record):
    type: Literal["match_started"] = "match_started"
    log_version: int = LOG_VERSION
    match_id: str
    game_id: str
    config: dict[str, PlainJson]
    seed: int
    seats: list[SeatRecord]
    started_at: str


class EventRecord(Record):
    type: Literal["event"] = "event"
    step: int
    kind: str
    text: str
    data: dict[str, PlainJson]
    audience: Literal["everyone"] | list[int]


class TraceRecord(Record):
    reasoning: str | None
    memory: str | None
    attempts: list[AttemptRecord]
    illegal_attempts: int
    api_retries: int
    fallback: FallbackPolicy | None
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float | None


class DecisionRecord(Record):
    """`step` is the step this action makes; `observed_at_step` the state it saw.

    Simultaneous decisions share one `observed_at_step`.
    """

    type: Literal["decision"] = "decision"
    step: int
    observed_at_step: int
    player: int
    kind: str
    prompt: str
    observation_digest: str
    observation: dict[str, PlainJson]
    action: str
    action_json: dict[str, PlainJson]
    latency_seconds: float
    trace: TraceRecord


class ForfeitRecord(Record):
    type: Literal["forfeit"] = "forfeit"
    step: int
    observed_at_step: int
    player: int
    kind: str
    reason: str
    observation_digest: str
    latency_seconds: float
    trace: TraceRecord


class ScoreRecord(Record):
    """Game points, and the final rank after forfeits (forfeiters rank last)."""

    player: int
    points: float
    rank: int
    breakdown: dict[str, float]


class MatchFinished(Record):
    type: Literal["match_finished"] = "match_finished"
    steps: int
    forfeited: list[int]
    scores: list[ScoreRecord]
    finished_at: str


class MatchStopped(Record):
    """The last record of a match stopped before the end; it has no scores."""

    type: Literal["match_stopped"] = "match_stopped"
    steps: int
    stopped_at: str


type LogRecord = Annotated[
    MatchStarted
    | EventRecord
    | DecisionRecord
    | ForfeitRecord
    | MatchFinished
    | MatchStopped,
    Field(discriminator="type"),
]

LOG_RECORD = TypeAdapter[LogRecord](LogRecord)


def plain_json(value: JsonValue) -> PlainJson:
    """`value` with every mapping as a dict, every sequence as a list, and no
    lone surrogates that a UTF-8 log could not hold."""
    plain: PlainJson = json.loads(json.dumps(clean_json(value)))
    return plain


def plain_object(value: JsonObject) -> dict[str, PlainJson]:
    """`value` as a plain JSON dict."""
    plain = plain_json(value)
    if not isinstance(plain, dict):
        raise TypeError(f"expected a JSON object, got {value!r}")
    return plain


def event_record(step: int, event: Event) -> EventRecord:
    """Log form of an event emitted at `step`."""
    return EventRecord.model_validate({"step": step, **event_json(event)})


def event_json(event: Event) -> dict[str, PlainJson]:
    """Event as plain JSON, the form replays compare."""
    return plain_object(event.to_json())


def trace_record(trace: DecisionTrace) -> TraceRecord:
    """Log form of an agent's decision trace."""
    return TraceRecord.model_validate(plain_json(trace.to_json()))
