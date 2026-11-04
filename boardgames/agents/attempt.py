"""Typed attempt records: one model call inside a decision trace."""

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
    # only tools-mode rounds make tool calls; other attempts leave the key out
    tool_calls: list[AttemptToolCall] | None = Field(
        default=None, exclude_if=lambda calls: calls is None
    )
