"""From a match config to a running match: seats, agents, model stack, log files.

The command line and the web viewer both start matches through `prepare_match`
and `run_prepared`, so they agree on seeds, log names and the model stack.
"""

import hashlib
import uuid
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TextIO

from boardgames.agents import Agent
from boardgames.agents.llm_agent import LlmAgent
from boardgames.arena.clock import Clock, SystemClock
from boardgames.arena.console import ConsoleLog
from boardgames.arena.control import MatchControl
from boardgames.arena.match_config import (
    ConfigSeat,
    LlmSeat,
    MatchConfig,
    llm_agent_settings,
    seats_for,
)
from boardgames.arena.model_configs import DirectoryModelConfigs, ModelConfigs
from boardgames.arena.runner import ALWAYS_RUNNING, MatchResult, play_match
from boardgames.core import AnyGame, ConfigError, GameConfig, create_game
from boardgames.llm.cache import (
    CachedChatModel,
    DirectoryResponseStore,
    ResponseStore,
)
from boardgames.llm.model import ChatModel, ModelSettings
from boardgames.llm.openrouter_model import OpenRouterChatModel
from boardgames.llm.parsing import ActionExtractor
from boardgames.llm.retry import RetryingChatModel
from boardgames.logs.sink import Broadcast, JsonlFile, RecordSink
from boardgames.logs.thoughts import ThoughtsFile, thoughts_path

DEFAULT_CACHE_DIR = Path(".arena_cache")
DEFAULT_REPLIES = DirectoryResponseStore(DEFAULT_CACHE_DIR)
DEFAULT_MODEL_CONFIGS = DirectoryModelConfigs(Path("models"))
API_KEY_VARIABLE = "OPENROUTER_API_KEY"


def new_match_id() -> str:
    """A fresh short id, injectable so tests can make it deterministic."""
    return uuid.uuid4().hex[:12]


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
    clock: Clock = field(default_factory=SystemClock)


def openrouter_model(api_key: str) -> ChatModel:
    """OpenRouter with retries on transient errors."""
    return RetryingChatModel(OpenRouterChatModel(api_key))


def with_cache(
    model: ChatModel, use_cache: bool, replies: ResponseStore = DEFAULT_REPLIES
) -> ChatModel:
    """`model` behind the reply cache `replies` when the match asks for it."""
    if not use_cache:
        return model
    return CachedChatModel(model, replies)


def derive_seed(match_seed: int, seat: int) -> int:
    """Per-seat agent seed, independent across seats."""
    digest = hashlib.sha256(f"{match_seed}/{seat}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


@dataclass(frozen=True)
class Player:
    """A seat's settings, and the saved model config they came from, if any."""

    seat: LlmSeat
    config: str | None = None


def players_for(
    seats: Sequence[ConfigSeat | LlmSeat], configs: ModelConfigs
) -> list[Player]:
    """Each seat with its settings: a config seat takes the saved config's, under
    the config's name. A seat's own label may not be a saved config's name, which
    would put its results in that config's leaderboard row."""
    saved = set(configs.names())
    players = []
    for index, seat in enumerate(seats):
        if isinstance(seat, ConfigSeat):
            settings = configs.get(seat.config).model_dump()
            named = LlmSeat(**settings, label=seat.config, seed=seat.seed)
            players.append(Player(named, seat.config))
            continue
        if seat.label in saved:
            raise ConfigError(
                f"seats.{index}: the label {seat.label!r} is a saved model config; "
                f"use `config: {seat.label}` or another label"
            )
        players.append(Player(seat))
    return players


def player_names(seats: Sequence[LlmSeat]) -> list[str]:
    """Each seat's label or model; names that repeat get #1, #2... in seat order."""
    bases = [seat.label or llm_agent_settings(seat, 0).model.model for seat in seats]
    counts = Counter(bases)
    taken: Counter[str] = Counter()
    names = []
    for base in bases:
        if counts[base] == 1:
            names.append(base)
            continue
        taken[base] += 1
        names.append(f"{base} #{taken[base]}")
    return names


def agent_for_seat(
    seat: LlmSeat,
    name: str,
    match_seed: int,
    index: int,
    model: ChatModel,
    config: str | None = None,
) -> Agent:
    """The language model player for one seat, called `name` in logs and the viewer.

    `config` is the saved model config the seat plays, recorded with its settings.

    A seat's `seed` replaces the derived seed for the model only, reduced below 2**31.
    """
    seed = derive_seed(match_seed, index)
    model_seed = (seed if seat.seed is None else seat.seed) % 2**31
    settings = replace(llm_agent_settings(seat, model_seed), label=name, config=config)
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
    thoughts: Path | None = None,
    use_config_log: bool = True,
    id_factory: Callable[[], str] = new_match_id,
    replies: ResponseStore = DEFAULT_REPLIES,
    configs: ModelConfigs = DEFAULT_MODEL_CONFIGS,
    clock: Clock | None = None,
) -> PreparedMatch:
    """Agents and log paths for a config; the keyword arguments override defaults.

    `model` serves every seat; None (no API key) is a ConfigError. `configs` holds
    the saved model configs that seats name.
    """
    game = create_game(config.game)
    game_config = game.parse_config(config.config)
    match_seed = config.seed if seed is None else seed
    players = players_for(seats_for(config, game_config.num_players), configs)
    seats = [player.seat for player in players]
    if model is None:
        first = llm_agent_settings(seats[0], 0).model.model
        raise ConfigError(f"set {API_KEY_VARIABLE} in .env to seat {first!r}")
    stack = with_cache(model, config.cache, replies)
    agents = [
        agent_for_seat(player.seat, name, match_seed, index, stack, player.config)
        for index, (player, name) in enumerate(
            zip(players, player_names(seats), strict=True)
        )
    ]
    match_id = id_factory()
    default_log = runs_dir / f"{game.id}-{match_seed}-{match_id}.jsonl"
    # a server turns `use_config_log` off so it always writes into `runs_dir`
    file_log = config.log if use_config_log else None
    log_path = log or file_log or default_log
    return PreparedMatch(
        game=game,
        game_config=game_config,
        seed=match_seed,
        agents=agents,
        match_id=match_id,
        log_path=log_path,
        thoughts_path=thoughts or thoughts_path(log_path),
        clock=clock or SystemClock(),
    )


@contextmanager
def open_match_files(prepared: PreparedMatch) -> Iterator[RecordSink]:
    """The match's JSONL log and thoughts file as one sink, closed afterwards."""
    with (
        JsonlFile(prepared.log_path) as log_file,
        ThoughtsFile(prepared.thoughts_path) as thoughts,
    ):
        yield Broadcast([log_file, thoughts])
    return


async def run_prepared(
    prepared: PreparedMatch,
    console: TextIO | None,
    control: MatchControl = ALWAYS_RUNNING,
    open_files: Callable[
        [PreparedMatch], AbstractContextManager[RecordSink]
    ] = open_match_files,
) -> MatchResult:
    """Play a prepared match into the sink `open_files` gives, and into `console`."""
    with open_files(prepared) as files:
        sinks: list[RecordSink] = [files]
        if console is not None:
            sinks.append(ConsoleLog(console))
        return await play_match(
            prepared.game,
            prepared.game_config,
            prepared.seed,
            prepared.agents,
            match_id=prepared.match_id,
            sink=Broadcast(sinks),
            clock=prepared.clock,
            control=control,
        )
