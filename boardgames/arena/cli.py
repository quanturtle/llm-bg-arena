"""Command line for listing games, playing matches and replaying logs.

arena games
arena play examples/tic_tac_toe.yaml
arena play examples/auction_llms.yaml --seed 3 --log runs/auction.jsonl
arena replay runs/<log>.jsonl

A match config file names the game, its config and the seats; see
docs/ARCHITECTURE.md. The OpenRouter key comes from the environment or a
local .env file.
"""

import argparse
import asyncio
import hashlib
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

import boardgames.games  # noqa: F401  (importing registers every game)
from boardgames.agents import Agent, RandomAgent
from boardgames.agents.llm_agent import LlmAgent
from boardgames.arena.clock import SystemClock
from boardgames.arena.console import ConsoleLog
from boardgames.arena.match_config import (
    LlmDefaults,
    LlmSeat,
    RandomSeat,
    llm_agent_settings,
    load_match_config,
    merged_options,
    seats_for,
)
from boardgames.arena.runner import play_match
from boardgames.core import (
    ArenaError,
    ConfigError,
    create_game,
    registered_game_ids,
)
from boardgames.llm.cache import CachedChatModel, DirectoryResponseStore
from boardgames.llm.model import ChatModel, ModelSettings
from boardgames.llm.openrouter_model import OpenRouterChatModel
from boardgames.llm.parsing import ActionExtractor
from boardgames.llm.retry import RetryingChatModel
from boardgames.logs.replay import read_log, replay_match
from boardgames.logs.sink import Broadcast, JsonlFile, RecordSink

DEFAULT_LOG_DIR = Path("runs")
DEFAULT_CACHE_DIR = Path(".arena_cache")
ENV_FILE = Path(".env")
API_KEY_VARIABLE = "OPENROUTER_API_KEY"

type Commands = argparse._SubParsersAction[argparse.ArgumentParser]


def load_environment() -> None:
    """Load the OpenRouter key from ./.env into the environment, if the file exists."""
    load_dotenv(ENV_FILE)
    return


def add_games_command(commands: Commands) -> None:
    """`arena games`: list registered game ids."""
    parser = commands.add_parser("games", help="list available games")
    parser.set_defaults(handler=list_games)
    return


def add_play_command(commands: Commands) -> None:
    """`arena play CONFIG`: play the match a YAML file describes and write its log."""
    parser = commands.add_parser("play", help="play one match from a config file")
    parser.add_argument(
        "match",
        type=Path,
        metavar="CONFIG",
        help="YAML match config: the game, its config and the seats",
    )
    parser.add_argument(
        "--seed", type=int, help="match seed (default: the file's seed, else 0)"
    )
    parser.add_argument(
        "--log", type=Path, help="log path (default: the file's log, else runs/...)"
    )
    parser.add_argument("--quiet", action="store_true", help="print only the result")
    parser.set_defaults(handler=play)
    return


def add_replay_command(commands: Commands) -> None:
    """`arena replay LOG`: rebuild a match from its log and check every step."""
    parser = commands.add_parser("replay", help="check a match log by replaying it")
    parser.add_argument("log", type=Path)
    parser.set_defaults(handler=check_replay)
    return


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    """Parsed command line."""
    parser = argparse.ArgumentParser(
        prog="arena", description="Play board games between LLMs, bots and humans."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    add_games_command(commands)
    add_play_command(commands)
    add_replay_command(commands)
    return parser.parse_args(argv)


def list_games(args: argparse.Namespace) -> None:
    """Print one registered game id per line."""
    for game_id in registered_game_ids():
        print(game_id)
    return


def openrouter_api_key() -> str | None:
    """The OpenRouter key from the environment, which `main` loads from .env."""
    return os.environ.get(API_KEY_VARIABLE) or None


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
    """The agent for one seat; an LLM seat needs the chat model, so a key."""
    seed = derive_seed(match_seed, index)
    if isinstance(seat, RandomSeat):
        return RandomAgent(seed)
    if model is None:
        raise ConfigError(f"set {API_KEY_VARIABLE} in .env to seat {seat.model!r}")
    options = merged_options(seat, defaults)
    model_seed = seed % 2**31 if seat.seed is None else seat.seed
    settings = llm_agent_settings(seat, options, model_seed)
    extractor = None
    if options.extractor is not None:
        extractor_settings = ModelSettings(
            model=options.extractor, temperature=0.0, max_tokens=64
        )
        extractor = ActionExtractor(model, extractor_settings)
    return LlmAgent(model, settings, seed, extractor)


def play(args: argparse.Namespace) -> None:
    """Play the match a config file describes, print it unless --quiet, log it."""
    config = load_match_config(args.match)
    game = create_game(config.game)
    game_config = game.parse_config(config.config)
    seed = config.seed if args.seed is None else args.seed
    seats = seats_for(config, game_config.num_players)
    api_key = openrouter_api_key()
    model = chat_model(config.llm.cache, api_key) if api_key else None
    agents = [
        agent_for_seat(seat, config.llm, seed, index, model)
        for index, seat in enumerate(seats)
    ]
    match_id = uuid.uuid4().hex[:12]
    default_log = DEFAULT_LOG_DIR / f"{game.id}-{seed}-{match_id}.jsonl"
    log_path = args.log or config.log or default_log
    with JsonlFile(log_path) as log_file:
        sink: RecordSink = log_file
        if not args.quiet:
            sink = Broadcast([log_file, ConsoleLog(sys.stdout)])
        result = asyncio.run(
            play_match(
                game,
                game_config,
                seed,
                agents,
                match_id=match_id,
                sink=sink,
                clock=SystemClock(),
            )
        )
    ranks = ", ".join(f"P{player + 1} #{rank}" for player, rank in result.ranks.items())
    print(f"Ranks: {ranks}")
    print(f"Log: {log_path}")
    return


def check_replay(args: argparse.Namespace) -> None:
    """Replay a log and report whether it matches."""
    report = replay_match(read_log(args.log))
    print(
        f"Replay matches the log: {report.game_id}, {report.steps} steps, "
        f"{report.events} events."
    )
    return


def run_command(args: argparse.Namespace) -> None:
    """Run the chosen command; arena errors print a message and exit with status 1."""
    try:
        args.handler(args)
    except ArenaError as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
    return


def main() -> None:
    load_environment()
    args = parse_arguments(sys.argv[1:])
    run_command(args)
    return


if __name__ == "__main__":
    main()
