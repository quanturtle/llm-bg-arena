"""Typed attempt records: one model call inside a decision trace."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic import JsonValue as PlainJson


class AttemptRejection(BaseModel):
    """Why one answer was not accepted, and what the model was told."""

    model_config = ConfigDict(frozen=True, extra="allow")

    kind: str = ""
    feedback: str = ""


class AttemptToolCall(BaseModel):
    """One tool call of a tools-mode round, with the text it was answered with."""

    model_config = ConfigDict(frozen=True, extra="allow")

    name: str = ""
    arguments: str = ""
    result: str = ""


class AttemptRecord(BaseModel):
    """One model call, as the log stores it.

    Fields have defaults so logs from before a field existed still load.
    Dict-style access keeps older readers and tests working.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    messages: list[PlainJson] = Field(default_factory=list)
    text: str = ""
    tool_arguments: str | None = None
    model_reasoning: str | None = None
    answer: str | None = None
    resolved_by: str | None = None
    rejection: AttemptRejection | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float | None = None
    api_retries: int = 0
    is_cached: bool = False
    extractor_calls: int = 0
    tool_calls: list[AttemptToolCall] | None = None

    def __getitem__(self, key: str) -> Any:
        return dict_value(getattr(self, key))

    def get(self, key: str, default: Any = None) -> Any:
        value = getattr(self, key, default)
        return default if value is default else dict_value(value)


def dict_value(value: Any) -> Any:
    """A value as it looked in the old untyped dict, for dict-style readers."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [dict_value(item) for item in value]
    return value
