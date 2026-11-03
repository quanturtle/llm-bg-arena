"""From a match config to a running match: seats, agents, model stack, log files.

The command line and the web viewer both start matches through `prepare_match`
and `run_prepared`, so they agree on seeds, log names and the model stack.
"""

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from boardgames.agents import Agent, RandomAgent
from boardgames.agents.llm_agent import LlmAgent
from boardgames.arena.clock import SystemClock
from boardgames.arena.console import ConsoleLog
from boardgames.arena.match_config import (
    LlmDefaults,
    LlmSeat,
    MatchConfig,
    RandomSeat,
    llm_agent_settings,
    merged_options,
    seats_for,
)
from boardgames.arena.runner import MatchResult, play_match
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


def chat_model(use_cache: bool, api_key: str) -> ChatModel:
    """OpenRouter with retries on transient errors, behind the cache if enabled."""
    model: ChatModel = RetryingChatModel(OpenRouterChatModel(api_key))
    if use_cache:
        model = CachedChatModel(model, DirectoryResponseStore(DEFAULT_CACHE_DIR))
    return model


def derive_seed(match_seed: int, seat: int) -> int:
    """Per-seat agent seed, independent across seats."""
    digest = hashlib.sha256(f"{match_seed}/{seat}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def agent_for_seat(
    seat: LlmSeat | RandomSeat,
    defaults: LlmDefaults,
    match_seed: int,
    index: int,
    model: ChatModel | None,
) -> Agent:
    """The agent for one seat; an LLM seat needs the chat model, so a key.

    A seat's `seed` replaces the derived seed for the model only, reduced below 2**31.
    """
    seed = derive_seed(match_seed, index)
    if isinstance(seat, RandomSeat):
        return RandomAgent(seed)
    if model is None:
        raise ConfigError(f"set {API_KEY_VARIABLE} in .env to seat {seat.model!r}")
    options = merged_options(seat, defaults)
    model_seed = (seed if seat.seed is None else seat.seed) % 2**31
    settings = llm_agent_settings(seat, options, model_seed)
    extractor = None
    if options.extractor is not None:
        extractor_settings = ModelSettings(
            model=options.extractor, temperature=0.0, max_tokens=64
        )
        extractor = ActionExtractor(model, extractor_settings)
    return LlmAgent(model, settings, seed, extractor)


def prepare_match(
    config: MatchConfig,
    api_key: str | None,
    runs_dir: Path,
    *,
    seed: int | None = None,
    log: Path | None = None,
) -> PreparedMatch:
    """Agents and log paths for a config; `seed` and `log` override the file."""
    game = create_game(config.game)
    game_config = game.parse_config(config.config)
    match_seed = config.seed if seed is None else seed
    seats = seats_for(config, game_config.num_players)
    model = chat_model(config.llm.cache, api_key) if api_key else None
    agents = [
        agent_for_seat(seat, config.llm, match_seed, index, model)
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


async def run_prepared(prepared: PreparedMatch, console: TextIO | None) -> MatchResult:
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
        )
