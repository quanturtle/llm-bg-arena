"""Command line for listing games and playing matches.

arena games
arena play k_in_a_row --agent random --agent random --seed 7
arena play sealed_auction --config '{"num_players": 4}'
"""

import argparse
import asyncio
import hashlib
import json
import sys
import uuid
from pathlib import Path

import tabletop_arena.games  # noqa: F401  (importing registers every game)
from tabletop_arena.agents import Agent, RandomAgent
from tabletop_arena.arena.clock import SystemClock
from tabletop_arena.arena.console import ConsoleLog
from tabletop_arena.arena.runner import play_match
from tabletop_arena.core import (
    ArenaError,
    ConfigError,
    JsonObject,
    create_game,
    registered_game_ids,
)
from tabletop_arena.logs.sink import Broadcast, JsonlFile, RecordSink

DEFAULT_LOG_DIR = Path("runs")

type Commands = argparse._SubParsersAction[argparse.ArgumentParser]


def add_games_command(commands: Commands) -> None:
    """`arena games`: list registered game ids."""
    parser = commands.add_parser("games", help="list available games")
    parser.set_defaults(handler=list_games)
    return


def add_play_command(commands: Commands) -> None:
    """`arena play GAME`: play one match and write its log."""
    parser = commands.add_parser("play", help="play one match")
    parser.add_argument("game", choices=registered_game_ids())
    parser.add_argument(
        "--config", default="{}", help="game config as JSON (default: game defaults)"
    )
    parser.add_argument("--seed", type=int, default=0, help="match seed (default 0)")
    parser.add_argument(
        "--agent",
        action="append",
        default=[],
        metavar="SPEC",
        help="agent for the next seat; repeat once per seat (default: random)",
    )
    parser.add_argument("--log", type=Path, help="log path (default: runs/...)")
    parser.add_argument("--quiet", action="store_true", help="print only the result")
    parser.set_defaults(handler=play)
    return


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    """Parsed command line."""
    parser = argparse.ArgumentParser(
        prog="arena", description="Play board games between LLMs, bots and humans."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    add_games_command(commands)
    add_play_command(commands)
    return parser.parse_args(argv)


def list_games(args: argparse.Namespace) -> None:
    """Print one registered game id per line."""
    for game_id in registered_game_ids():
        print(game_id)
    return


def parse_config_json(text: str) -> JsonObject:
    """The --config value as a JSON object."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as error:
        raise ConfigError(f"--config is not valid JSON: {error}") from error
    if not isinstance(raw, dict):
        raise ConfigError("--config must be a JSON object")
    return raw


def derive_seed(match_seed: int, seat: int) -> int:
    """Per-seat agent seed, independent across seats."""
    digest = hashlib.sha256(f"{match_seed}/{seat}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def build_agent(spec: str, match_seed: int, seat: int) -> Agent:
    """Agent for an --agent spec."""
    if spec == "random":
        return RandomAgent(derive_seed(match_seed, seat))
    raise ConfigError(f"unknown agent spec {spec!r}; known: random")


def play(args: argparse.Namespace) -> None:
    """Play one match, printing it unless --quiet, and write the JSONL log."""
    game = create_game(args.game)
    config = game.parse_config(parse_config_json(args.config))
    specs = args.agent or ["random"] * config.num_players
    agents = [build_agent(spec, args.seed, seat) for seat, spec in enumerate(specs)]
    match_id = uuid.uuid4().hex[:12]
    log_path = args.log or DEFAULT_LOG_DIR / f"{game.id}-{args.seed}-{match_id}.jsonl"
    with JsonlFile(log_path) as log_file:
        sink: RecordSink = log_file
        if not args.quiet:
            sink = Broadcast([log_file, ConsoleLog(sys.stdout)])
        result = asyncio.run(
            play_match(
                game,
                config,
                args.seed,
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


def run_command(args: argparse.Namespace) -> None:
    """Run the chosen command; arena errors print a message and exit with status 1."""
    try:
        args.handler(args)
    except ArenaError as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
    return


def main() -> None:
    args = parse_arguments(sys.argv[1:])
    run_command(args)
    return


if __name__ == "__main__":
    main()
