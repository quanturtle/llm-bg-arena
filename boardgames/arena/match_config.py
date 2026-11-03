"""The match config file: the game, its config, the seats and each LLM seat's settings.

A file is read once into frozen pydantic models. Unknown keys are errors. An LLM
seat's unset values fall back to the file's `llm` defaults, then to the built-in
defaults of ModelSettings, PromptSettings and LlmAgentSettings. A seat value set
to null skips the `llm` default and takes the built-in one.
"""

from dataclasses import replace
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic import JsonValue as PlainJson
from pydantic_core import ErrorDetails

from boardgames.agents import FallbackPolicy
from boardgames.agents.llm_agent import LlmAgentSettings
from boardgames.core import ConfigError
from boardgames.llm.model import ModelSettings, ReasoningEffort
from boardgames.llm.prompting import OutputMode, PromptSettings

MODEL_FIELDS = frozenset(
    {
        "temperature",
        "top_p",
        "max_tokens",
        "timeout_seconds",
        "reasoning_effort",
        "thinking_budget_tokens",
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
SEAT_ONLY_FIELDS = frozenset({"agent", "model", "label", "seed"})


class ConfigModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class LlmOptions(ConfigModel):
    """Settings an LLM seat may set; None means "use the default"."""

    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, ge=1)
    timeout_seconds: float | None = Field(default=None, gt=0)
    reasoning_effort: ReasoningEffort | None = None
    thinking_budget_tokens: int | None = Field(default=None, ge=1)
    extra: dict[str, PlainJson] | None = None
    output_mode: OutputMode | None = None
    max_illegal_retries: int | None = Field(default=None, ge=0)
    max_tool_calls: int | None = Field(default=None, ge=1)
    fallback: FallbackPolicy | None = None
    persona: str | None = None
    extractor: str | None = None


class LlmDefaults(LlmOptions):
    """The file's `llm` section: defaults for every LLM seat, plus the reply cache."""

    cache: bool = False


class LlmSeat(LlmOptions):
    agent: Literal["llm"]
    model: str
    label: str | None = None
    seed: int | None = None


class RandomSeat(ConfigModel):
    agent: Literal["random"]


type Seat = Annotated[LlmSeat | RandomSeat, Field(discriminator="agent")]


class MatchConfig(ConfigModel):
    """One match: `seats` left out means every seat is random."""

    game: str
    config: dict[str, PlainJson] = {}
    seed: int = 0
    log: Path | None = None
    llm: LlmDefaults = LlmDefaults()
    seats: list[Seat] | None = None


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
    """Raise ConfigError if an LLM seat's merged options set both kinds of reasoning."""
    for index, seat in enumerate(config.seats or []):
        if not isinstance(seat, LlmSeat):
            continue
        options = merged_options(seat, config.llm)
        if (
            options.reasoning_effort is not None
            and options.thinking_budget_tokens is not None
        ):
            raise ConfigError(
                f"{source}: seats.{index}: set reasoning_effort or "
                "thinking_budget_tokens, not both"
            )
    return


def seats_for(config: MatchConfig, num_players: int) -> list[LlmSeat | RandomSeat]:
    """The seats to fill, one per player; a missing `seats` list seats random bots."""
    if config.seats is None:
        return [RandomSeat(agent="random") for _ in range(num_players)]
    if len(config.seats) != num_players:
        raise ConfigError(
            f"{config.game} seats {num_players} players but the file lists "
            f"{len(config.seats)} seats"
        )
    return list(config.seats)


def merged_options(seat: LlmSeat, defaults: LlmDefaults) -> LlmOptions:
    """Seat values over the file defaults; a seat's unset values show the defaults.

    A seat value set to null stays None, so the built-in default applies.
    """
    values = defaults.model_dump(exclude={"cache"})
    values.update(
        seat.model_dump(include=set(seat.model_fields_set - SEAT_ONLY_FIELDS))
    )
    return LlmOptions.model_validate(values)


def llm_agent_settings(
    seat: LlmSeat, options: LlmOptions, seed: int
) -> LlmAgentSettings:
    """Agent settings for a seat; options still unset keep the built-in defaults."""
    model = replace(
        ModelSettings(model=seat.model, seed=seed),
        **options.model_dump(include=set(MODEL_FIELDS), exclude_none=True),
    )
    prompt = replace(
        PromptSettings(),
        **options.model_dump(include=set(PROMPT_FIELDS), exclude_none=True),
    )
    return replace(
        LlmAgentSettings(model=model, prompt=prompt, label=seat.label),
        **options.model_dump(include=set(AGENT_FIELDS), exclude_none=True),
    )
