"""Command line: list games, play matches, replay logs and serve the viewer.

arena games
arena play examples/tic_tac_toe.yaml
arena play examples/catan.yaml --seed 3 --log runs/catan.jsonl
arena replay runs/<log>.jsonl
arena serve

A match config file names the game, its config and the seats; see
docs/ARCHITECTURE.md. The OpenRouter key comes from the environment or a
local .env file.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from boardgames.arena.lineup import (
    API_KEY_VARIABLE,
    openrouter_model,
    prepare_match,
    run_prepared,
)
from boardgames.arena.match_config import load_match_config
from boardgames.core import ArenaError
from boardgames.games import game_ids
from boardgames.llm.model import ChatModel
from boardgames.logs.replay import read_log, replay_match
from boardgames.web.app import create_app
from boardgames.web.launcher import MatchLauncher
from boardgames.web.store import MatchStore

DEFAULT_LOG_DIR = Path("runs")
DEFAULT_EXAMPLES_DIR = Path("examples")
ENV_FILE = Path(".env")

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


def add_serve_command(commands: Commands) -> None:
    """`arena serve`: the web viewer over a directory of logs, able to start matches."""
    parser = commands.add_parser("serve", help="serve the web viewer")
    parser.add_argument(
        "--runs", type=Path, default=DEFAULT_LOG_DIR, help="log directory"
    )
    parser.add_argument(
        "--examples",
        type=Path,
        default=DEFAULT_EXAMPLES_DIR,
        help="match configs offered on the new-match page",
    )
    parser.add_argument("--host", default="127.0.0.1", help="bind address")
    parser.add_argument("--port", type=int, default=8000, help="port (default 8000)")
    parser.set_defaults(handler=serve)
    return


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    """Parsed command line."""
    parser = argparse.ArgumentParser(
        prog="arena", description="Play board games between LLMs and bots."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    add_games_command(commands)
    add_play_command(commands)
    add_replay_command(commands)
    add_serve_command(commands)
    return parser.parse_args(argv)


def list_games(args: argparse.Namespace) -> None:
    """Print one registered game id per line."""
    for game_id in game_ids():
        print(game_id)
    return


def chat_model_from_environment() -> ChatModel | None:
    """OpenRouter with the key `main` loads from .env, or None without a key."""
    api_key = os.environ.get(API_KEY_VARIABLE) or None
    return openrouter_model(api_key) if api_key else None


def play(args: argparse.Namespace) -> None:
    """Play the match a config file describes, print it unless --quiet, log it."""
    config = load_match_config(args.match)
    prepared = prepare_match(
        config,
        chat_model_from_environment(),
        DEFAULT_LOG_DIR,
        seed=args.seed,
        log=args.log,
    )
    console = None if args.quiet else sys.stdout
    result = asyncio.run(run_prepared(prepared, console))
    ranks = ", ".join(f"P{player + 1} #{rank}" for player, rank in result.ranks.items())
    print(f"Ranks: {ranks}")
    print(f"Log: {prepared.log_path}")
    print(f"Thoughts: {prepared.thoughts_path}")
    return


def check_replay(args: argparse.Namespace) -> None:
    """Replay a log and report whether it matches."""
    report = replay_match(read_log(args.log))
    stopped = (
        " The match was stopped before the end." if report.ending == "stopped" else ""
    )
    print(
        f"Replay matches the log: {report.game_id}, {report.steps} steps, "
        f"{report.events} events.{stopped}"
    )
    return


def serve(args: argparse.Namespace) -> None:
    """Serve the web viewer until interrupted; matches started there run in-process."""
    game_ids()
    launcher = MatchLauncher(args.runs, chat_model_from_environment(), args.examples)
    print(f"Serving {args.runs} at http://{args.host}:{args.port}/")
    uvicorn.run(
        create_app(MatchStore(args.runs), launcher), host=args.host, port=args.port
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
