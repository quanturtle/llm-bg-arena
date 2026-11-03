"""The match config file: the game, its config, the seats and each LLM seat's settings.

A file is read once into frozen pydantic models. Unknown keys are errors. Every
seat is a language model; with no `seats`, every player is the default model.
Each seat carries its own model and settings; what it leaves unset takes the
built-in default (DEFAULT_MODEL, ModelSettings, PromptSettings, LlmAgentSettings).
"""

from dataclasses import replace
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic import JsonValue as PlainJson
from pydantic_core import ErrorDetails

from boardgames.agents import FallbackPolicy
from boardgames.agents.llm_agent import LlmAgentSettings
from boardgames.core import ConfigError
from boardgames.llm.model import (
    ModelSettings,
    ReasoningEffort,
    Verbosity,
    reasoning_conflict,
)
from boardgames.llm.prompting import OutputMode, PromptSettings

MODEL_FIELDS = frozenset(
    {
        "temperature",
        "top_p",
        "max_tokens",
        "timeout_seconds",
        "reasoning",
        "reasoning_effort",
        "thinking_budget_tokens",
        "verbosity",
        "extra",
    }
)
PROMPT_FIELDS = frozenset({"output_mode", "persona"})
DEFAULT_MODEL = "qwen/qwen3.7-flash"
# cheap OpenRouter models with tool calling, offered by the new-match form
SUGGESTED_MODELS = (
    "qwen/qwen3.7-flash",
    "z-ai/glm-5.3-flash",
    "deepseek/deepseek-v4.1-flash",
    "openai/gpt-5-nano",
    "mistralai/mistral-small-3.2-24b-instruct",
    "google/gemini-2.5-flash-lite",
    "anthropic/claude-haiku-5.5",
)
AGENT_FIELDS = frozenset({"max_illegal_retries", "max_tool_calls", "fallback"})


class ConfigModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class LlmOptions(ConfigModel):
    """Settings an LLM seat may set; None means "use the default"."""

    model: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, ge=1)
    timeout_seconds: float | None = Field(default=None, gt=0)
    reasoning: bool | None = None
    reasoning_effort: ReasoningEffort | None = None
    thinking_budget_tokens: int | None = Field(default=None, ge=1)
    verbosity: Verbosity | None = None
    extra: dict[str, PlainJson] | None = None
    output_mode: OutputMode | None = None
    max_illegal_retries: int | None = Field(default=None, ge=0)
    max_tool_calls: int | None = Field(default=None, ge=1)
    fallback: FallbackPolicy | None = None
    persona: str | None = None
    extractor: str | None = None


class LlmSeat(LlmOptions):
    """A language model seat: its model and settings; unset ones use the defaults."""

    label: str | None = None
    seed: int | None = None


class MatchConfig(ConfigModel):
    """One match: `seats` left out means every player is the default model.

    `cache` reuses stored model replies for identical requests, for reruns.
    """

    game: str
    config: dict[str, PlainJson] = {}
    seed: int = 0
    log: Path | None = None
    cache: bool = False
    seats: list[LlmSeat] | None = None


def load_match_config(path: Path) -> MatchConfig:
    """The match config in a YAML file; an unreadable or invalid file raises."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ConfigError(f"cannot read {path}: {error}") from error
    except UnicodeDecodeError as error:
        raise ConfigError(f"{path} is not UTF-8 text: {error}") from error
    except yaml.YAMLError as error:
        raise ConfigError(f"{path} is not valid YAML: {error}") from error
    return parse_match_config(raw, str(path))


def parse_match_config(raw: object, source: str) -> MatchConfig:
    """A validated match config from loaded YAML; `source` names it in errors."""
    if not isinstance(raw, dict):
        raise ConfigError(f"{source}: the match config must be a mapping")
    try:
        config = MatchConfig.model_validate(raw)
    except ValidationError as error:
        problems = "; ".join(problem_text(problem) for problem in error.errors())
        raise ConfigError(f"{source}: {problems}") from error
    check_reasoning(config, source)
    return config


def problem_text(problem: ErrorDetails) -> str:
    """One validation problem as "path.to.key: message"."""
    location = ".".join(str(part) for part in problem["loc"]) or "file"
    return f"{location}: {problem['msg']}"


def check_reasoning(config: MatchConfig, source: str) -> None:
    """Raise ConfigError if a seat's reasoning settings contradict each other."""
    for index, seat in enumerate(config.seats or []):
        problem = reasoning_conflict(
            seat.reasoning, seat.reasoning_effort, seat.thinking_budget_tokens
        )
        if problem is not None:
            raise ConfigError(f"{source}: seats.{index}: {problem}")
    return


def seats_for(config: MatchConfig, num_players: int) -> list[LlmSeat]:
    """The seats to fill, one per player; with no `seats`, each is the default model."""
    if config.seats is None:
        return [LlmSeat() for _ in range(num_players)]
    if len(config.seats) != num_players:
        raise ConfigError(
            f"{config.game} seats {num_players} players but the file lists "
            f"{len(config.seats)} seats"
        )
    return list(config.seats)


def llm_agent_settings(seat: LlmSeat, seed: int) -> LlmAgentSettings:
    """Agent settings for a seat; what it leaves unset keeps the built-in default,
    and a seat without a model plays DEFAULT_MODEL."""
    model = replace(
        ModelSettings(
            model=seat.model or DEFAULT_MODEL,
            seed=seed,
            reasoning=default_reasoning(seat),
        ),
        **seat.model_dump(include=set(MODEL_FIELDS), exclude_none=True),
    )
    prompt = replace(
        PromptSettings(),
        **seat.model_dump(include=set(PROMPT_FIELDS), exclude_none=True),
    )
    return replace(
        LlmAgentSettings(model=model, prompt=prompt, label=seat.label),
        **seat.model_dump(include=set(AGENT_FIELDS), exclude_none=True),
    )


def default_reasoning(seat: LlmSeat) -> bool:
    """Reasoning when a seat leaves it unset: off, unless it sets effort or budget."""
    return seat.reasoning_effort is not None or seat.thinking_budget_tokens is not None


def builtin_seat_defaults() -> dict[str, PlainJson]:
    """What a seat that sets nothing plays with, per option, from the settings code."""
    settings = llm_agent_settings(LlmSeat(), seed=0)
    values: dict[str, PlainJson] = {"model": DEFAULT_MODEL}
    values |= {key: getattr(settings.model, key) for key in MODEL_FIELDS - {"extra"}}
    values |= {key: getattr(settings.prompt, key) for key in PROMPT_FIELDS}
    values |= {key: getattr(settings, key) for key in AGENT_FIELDS}
    return values
