"""The match config file: the game, its config, the seats and each LLM seat's settings.

A file is read once into frozen pydantic models. Unknown keys are errors. An LLM
seat's unset values fall back to the file's `llm` defaults, then to the built-in
defaults of ModelSettings, PromptSettings and LlmAgentSettings.
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
AGENT_FIELDS = frozenset({"max_illegal_retries", "fallback"})
SEAT_ONLY_FIELDS = frozenset({"agent", "model", "label", "seed"})


class ConfigModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class LlmOptions(ConfigModel):
    """Settings an LLM seat may set; None means "use the default"."""

    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    timeout_seconds: float | None = None
    reasoning_effort: ReasoningEffort | None = None
    thinking_budget_tokens: int | None = None
    extra: dict[str, PlainJson] | None = None
    output_mode: OutputMode | None = None
    max_illegal_retries: int | None = None
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
    except yaml.YAMLError as error:
        raise ConfigError(f"{path} is not valid YAML: {error}") from error
    return parse_match_config(raw, str(path))


def parse_match_config(raw: object, source: str) -> MatchConfig:
    """A validated match config from loaded YAML; `source` names it in errors."""
    if not isinstance(raw, dict):
        raise ConfigError(f"{source}: the match config must be a mapping")
    try:
        return MatchConfig.model_validate(raw)
    except ValidationError as error:
        problems = "; ".join(problem_text(problem) for problem in error.errors())
        raise ConfigError(f"{source}: {problems}") from error


def problem_text(problem: ErrorDetails) -> str:
    """One validation problem as "path.to.key: message"."""
    location = ".".join(str(part) for part in problem["loc"]) or "file"
    return f"{location}: {problem['msg']}"


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
    """Seat values over the file defaults; a seat's unset values show the defaults."""
    values = defaults.model_dump(exclude={"cache"})
    values.update(seat.model_dump(exclude_none=True, exclude=set(SEAT_ONLY_FIELDS)))
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
