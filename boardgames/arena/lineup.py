"""From a match config to a running match: seats, agents, model stack, log files.

The command line and the web viewer both start matches through `prepare_match`
and `run_prepared`, so they agree on seeds, log names and the model stack.
"""

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from boardgames.agents import Agent
from boardgames.agents.llm_agent import LlmAgent
from boardgames.arena.clock import SystemClock
from boardgames.arena.console import ConsoleLog
from boardgames.arena.control import MatchControl
from boardgames.arena.match_config import (
    LlmSeat,
    MatchConfig,
    llm_agent_settings,
    seats_for,
)
from boardgames.arena.runner import ALWAYS_RUNNING, MatchResult, play_match
from boardgames.core import AnyGame, ConfigError, GameConfig, create_game
from boardgames.llm.cache import CachedChatModel, DirectoryResponseStore
from boardgames.llm.model import ChatModel, ModelSettings
from boardgames.llm.openrouter_model import OpenRouterChatModel
from boardgames.llm.parsing import ActionExtractor
from boardgames.llm.retry import RetryingChatModel
from boardgames.logs.sink import Broadcast, JsonlFile, RecordSink
from boardgames.logs.thoughts import ThoughtsFile

DEFAULT_CACHE_DIR = Path(".arena_cache")
API_KEY_VARIABLE = "OPENROUTER_API_KEY"


@dataclass(frozen=True)
class PreparedMatch:
    """Everything a match needs before its first step."""

    game: AnyGame
    game_config: GameConfig
    seed: int
    agents: list[Agent]
    match_id: str
    log_path: Path
    thoughts_path: Path


def openrouter_model(api_key: str) -> ChatModel:
    """OpenRouter with retries on transient errors."""
    return RetryingChatModel(OpenRouterChatModel(api_key))


def with_cache(model: ChatModel, use_cache: bool) -> ChatModel:
    """`model` behind the reply cache when the match asks for it."""
    if not use_cache:
        return model
    return CachedChatModel(model, DirectoryResponseStore(DEFAULT_CACHE_DIR))


def derive_seed(match_seed: int, seat: int) -> int:
    """Per-seat agent seed, independent across seats."""
    digest = hashlib.sha256(f"{match_seed}/{seat}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def agent_for_seat(
    seat: LlmSeat,
    match_seed: int,
    index: int,
    model: ChatModel,
) -> Agent:
    """The language model player for one seat.

    A seat's `seed` replaces the derived seed for the model only, reduced below 2**31.
    """
    seed = derive_seed(match_seed, index)
    model_seed = (seed if seat.seed is None else seat.seed) % 2**31
    settings = llm_agent_settings(seat, model_seed)
    extractor = None
    if seat.extractor is not None:
        extractor_settings = ModelSettings(
            model=seat.extractor, temperature=0.0, max_tokens=64
        )
        extractor = ActionExtractor(model, extractor_settings)
    return LlmAgent(model, settings, seed, extractor)


def prepare_match(
    config: MatchConfig,
    model: ChatModel | None,
    runs_dir: Path,
    *,
    seed: int | None = None,
    log: Path | None = None,
) -> PreparedMatch:
    """Agents and log paths for a config; `seed` and `log` override the file.

    `model` serves every seat; None (no API key) is a ConfigError.
    """
    game = create_game(config.game)
    game_config = game.parse_config(config.config)
    match_seed = config.seed if seed is None else seed
    seats = seats_for(config, game_config.num_players)
    if model is None:
        first = llm_agent_settings(seats[0], 0).model.model
        raise ConfigError(f"set {API_KEY_VARIABLE} in .env to seat {first!r}")
    stack = with_cache(model, config.cache)
    agents = [
        agent_for_seat(seat, match_seed, index, stack)
        for index, seat in enumerate(seats)
    ]
    match_id = uuid.uuid4().hex[:12]
    default_log = runs_dir / f"{game.id}-{match_seed}-{match_id}.jsonl"
    log_path = log or config.log or default_log
    return PreparedMatch(
        game=game,
        game_config=game_config,
        seed=match_seed,
        agents=agents,
        match_id=match_id,
        log_path=log_path,
        thoughts_path=log_path.with_suffix(".thoughts.md"),
    )


async def run_prepared(
    prepared: PreparedMatch,
    console: TextIO | None,
    control: MatchControl = ALWAYS_RUNNING,
) -> MatchResult:
    """Play a prepared match into its log and thoughts files, and `console` if given."""
    with (
        JsonlFile(prepared.log_path) as log_file,
        ThoughtsFile(prepared.thoughts_path) as thoughts,
    ):
        sinks: list[RecordSink] = [log_file, thoughts]
        if console is not None:
            sinks.append(ConsoleLog(console))
        return await play_match(
            prepared.game,
            prepared.game_config,
            prepared.seed,
            prepared.agents,
            match_id=prepared.match_id,
            sink=Broadcast(sinks),
            clock=SystemClock(),
            control=control,
        )
