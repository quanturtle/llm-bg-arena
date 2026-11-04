"""Command line: list games, play matches, replay logs and serve the viewer.

arena games
arena play examples/tic_tac_toe.yaml
arena play examples/catan.yaml --seed 3 --log runs/catan.jsonl
arena replay runs/<log>.jsonl
arena serve
arena serve examples/catan_game.jsonl

A match config file names the game, its config and the seats. The OpenRouter
key comes from the environment or a local .env file.
"""

import argparse
import asyncio
import os
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import uvicorn
from dotenv import load_dotenv

from boardgames.arena.lineup import (
    API_KEY_VARIABLE,
    openrouter_model,
    prepare_match,
    run_prepared,
)
from boardgames.arena.match_config import load_match_config
from boardgames.arena.viewer import build_viewer, run_build_command, viewer_is_stale
from boardgames.core import ArenaError, ConfigError
from boardgames.games import game_ids
from boardgames.llm.catalog import OpenRouterCatalog
from boardgames.llm.model import ChatModel
from boardgames.logs.replay import first_record, read_log, replay_match
from boardgames.logs.schema import MatchStarted
from boardgames.web.app import create_app
from boardgames.web.launcher import MatchLauncher
from boardgames.web.store import MatchStore

DEFAULT_LOG_DIR = Path("runs")
DEFAULT_EXAMPLES_DIR = Path("examples")
VIEWER_SOURCES = Path("web")
DEFAULT_VIEWER_DIR = VIEWER_SOURCES / "out"
VIEWER_BUILD_COMMAND = "pnpm --dir web install && pnpm --dir web build"
# 8000 is where local model servers listen, and coding tools probe it for /v1/models
DEFAULT_PORT = 8765
# how long to wait for the server to accept connections before opening the browser
BROWSER_WAIT_SECONDS = 10.0
ENV_FILE = Path(".env")

type Commands = argparse._SubParsersAction[argparse.ArgumentParser]


class ServerState(Protocol):
    """The bits of a running server the browser opener needs to see."""

    started: bool
    should_exit: bool


@dataclass(frozen=True)
class AppConfig:
    """Process settings read once at startup, instead of inside each handler."""

    api_key: str | None
    model: ChatModel | None = None

    def chat_model(self) -> ChatModel | None:
        """The configured model, or OpenRouter when only a key was found."""
        if self.model is not None:
            return self.model
        return openrouter_model(self.api_key) if self.api_key else None


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
        "log",
        type=Path,
        nargs="?",
        metavar="LOG",
        help="a match log to open in the browser, read-only",
    )
    parser.add_argument(
        "--runs", type=Path, default=DEFAULT_LOG_DIR, help="log directory"
    )
    parser.add_argument(
        "--examples",
        type=Path,
        default=DEFAULT_EXAMPLES_DIR,
        help="match configs offered on the new-match page",
    )
    parser.add_argument(
        "--viewer",
        type=Path,
        default=DEFAULT_VIEWER_DIR,
        help="built web viewer (default web/out, rebuilt when web/ changes)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="bind address")
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help=f"port (default {DEFAULT_PORT})"
    )
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


def list_games(
    args: argparse.Namespace, config: AppConfig | None = None
) -> None:
    """Print one registered game id per line."""
    for game_id in game_ids():
        print(game_id)
    return


def config_from_environment() -> AppConfig:
    """Process settings from the environment, read once at startup."""
    return AppConfig(os.environ.get(API_KEY_VARIABLE) or None)


def config_for_command() -> AppConfig:
    """Settings for a handler called without startup config, keeping tests able
    to replace the model factory."""
    return AppConfig(api_key=None, model=chat_model_from_environment())


def chat_model_from_environment() -> ChatModel | None:
    """OpenRouter with the key `main` loads from .env, or None without a key."""
    return config_from_environment().chat_model()


def play(args: argparse.Namespace, config: AppConfig | None = None) -> None:
    """Play the match a config file describes, print it unless --quiet, log it."""
    config = config or config_for_command()
    match_config = load_match_config(args.match)
    prepared = prepare_match(
        match_config,
        config.chat_model(),
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


def check_replay(
    args: argparse.Namespace, config: AppConfig | None = None
) -> None:
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


def viewer_build(directory: Path) -> Path:
    """The built viewer in `directory`; when missing, the error says how to build it."""
    if not (directory / "index.html").is_file():
        raise ConfigError(
            f"no web viewer build in {directory}; build it with: {VIEWER_BUILD_COMMAND}"
        )
    return directory


def current_viewer(directory: Path) -> Path:
    """The viewer build to serve; the default one is rebuilt when web/ changed."""
    if directory == DEFAULT_VIEWER_DIR and viewer_is_stale(VIEWER_SOURCES):
        print("Building the viewer; it rebuilds only when web/ changes.", flush=True)
        build_viewer(VIEWER_SOURCES, run_build_command)
    return viewer_build(directory)


def open_replays(
    logs: tuple[Path, ...], host: str, port: int, server: uvicorn.Server
) -> None:
    """Open each log's replay, from its first step, once our server is listening."""
    for log in logs:
        match_id = first_record(read_log(log), MatchStarted).match_id
        url = f"http://{host}:{port}/match/?id={match_id}&step=0"
        print(f"Opening {url}")
        threading.Thread(
            target=open_when_started, args=(url, server), daemon=True
        ).start()
    return


def open_when_started(
    url: str, server: ServerState, wait_seconds: float = BROWSER_WAIT_SECONDS
) -> None:
    """Open `url` only after `server` bound its port, never for another server's."""
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if server.started:
            webbrowser.open(url)
            return
        if server.should_exit:
            return
        time.sleep(0.1)
    return


def serve(args: argparse.Namespace, config: AppConfig | None = None) -> None:
    """Serve the web viewer until interrupted; matches started there run in-process."""
    config = config or config_for_command()
    game_ids()
    viewer = current_viewer(args.viewer)
    opened = () if args.log is None else (args.log,)
    launcher = MatchLauncher(args.runs, config.chat_model(), args.examples)
    print(f"Serving {args.runs} at http://{args.host}:{args.port}/")
    store = MatchStore(args.runs, read_only=opened)
    app = create_app(store, launcher, OpenRouterCatalog(), viewer)
    server = uvicorn.Server(uvicorn.Config(app, host=args.host, port=args.port))
    open_replays(opened, args.host, args.port, server)
    server.run()
    return


def run_command(
    args: argparse.Namespace, config: AppConfig | None = None
) -> None:
    """Run the chosen command; arena errors print a message and exit with status 1."""
    try:
        args.handler(args, config or config_for_command())
    except ArenaError as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
    return


def main() -> None:
    load_environment()
    config = config_from_environment()
    args = parse_arguments(sys.argv[1:])
    run_command(args, config)
    return


if __name__ == "__main__":
    main()
