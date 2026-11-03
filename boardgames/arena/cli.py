"""Command line for listing games, playing matches and replaying logs.

arena games
arena play k_in_a_row --agent random --agent random --seed 7
arena play k_in_a_row --agent llm:anthropic/claude-haiku-5-5 --agent random
arena play sealed_auction --config '{"num_players": 4}'
arena replay runs/<log>.jsonl

Provider keys come from the environment or a local .env file.
"""

import argparse
import asyncio
import hashlib
import json
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

import boardgames.games  # noqa: F401  (importing registers every game)
from boardgames.agents import Agent, FallbackPolicy, RandomAgent
from boardgames.agents.llm_agent import LlmAgent, LlmAgentSettings
from boardgames.arena.clock import SystemClock
from boardgames.arena.console import ConsoleLog
from boardgames.arena.runner import play_match
from boardgames.core import (
    ArenaError,
    ConfigError,
    JsonObject,
    create_game,
    registered_game_ids,
)
from boardgames.llm.cache import CachedChatModel, DirectoryResponseStore
from boardgames.llm.litellm_model import LiteLLMChatModel
from boardgames.llm.model import ChatModel, ModelSettings, ReasoningEffort
from boardgames.llm.parsing import ActionExtractor
from boardgames.llm.prompting import OutputMode, PromptSettings
from boardgames.llm.retry import RetryingChatModel
from boardgames.logs.replay import read_log, replay_match
from boardgames.logs.sink import Broadcast, JsonlFile, RecordSink
from boardgames.web.app import create_app
from boardgames.web.store import MatchStore

DEFAULT_LOG_DIR = Path("runs")
DEFAULT_CACHE_DIR = Path(".arena_cache")
ENV_FILE = Path(".env")

type Commands = argparse._SubParsersAction[argparse.ArgumentParser]


@dataclass(frozen=True)
class LlmOptions:
    """Settings shared by every LLM seat of a match, read once from the command line."""

    temperature: float | None
    max_tokens: int
    reasoning_effort: ReasoningEffort | None
    timeout_seconds: float
    max_illegal_retries: int
    fallback: FallbackPolicy
    output_mode: OutputMode
    use_cache: bool
    extractor_model: str | None
    persona: str | None


def load_environment() -> None:
    """Load provider keys from ./.env into the environment, if the file exists."""
    load_dotenv(ENV_FILE)
    return


def add_games_command(commands: Commands) -> None:
    """`arena games`: list registered game ids."""
    parser = commands.add_parser("games", help="list available games")
    parser.set_defaults(handler=list_games)
    return


def add_llm_options(parser: argparse.ArgumentParser) -> None:
    """Options for every llm:<model> seat of the match."""
    group = parser.add_argument_group("LLM players")
    group.add_argument("--temperature", type=float, help="sampling temperature")
    group.add_argument("--max-tokens", type=int, default=1024, help="reply token cap")
    group.add_argument("--reasoning-effort", choices=["low", "medium", "high"])
    group.add_argument("--timeout", type=float, default=120.0, help="seconds per call")
    group.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="re-prompts after a rejected answer (default 3)",
    )
    group.add_argument(
        "--fallback",
        choices=["forfeit", "random", "default"],
        default="random",
        help="action after the last rejected answer (default random)",
    )
    group.add_argument(
        "--output-mode",
        choices=["tool", "text"],
        default="tool",
        help="answer by forced tool call or by a 'Final Answer:' line",
    )
    group.add_argument("--cache", action="store_true", help="cache model replies")
    group.add_argument(
        "--extractor", metavar="MODEL", help="model that rescues replies"
    )
    group.add_argument("--persona", help="extra instructions for every LLM player")
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
    add_llm_options(parser)
    parser.set_defaults(handler=play)
    return


def add_replay_command(commands: Commands) -> None:
    """`arena replay LOG`: rebuild a match from its log and check every step."""
    parser = commands.add_parser("replay", help="check a match log by replaying it")
    parser.add_argument("log", type=Path)
    parser.set_defaults(handler=check_replay)
    return


def add_serve_command(commands: Commands) -> None:
    """`arena serve`: the web viewer over a directory of logs."""
    parser = commands.add_parser("serve", help="serve the web viewer")
    parser.add_argument(
        "--runs", type=Path, default=DEFAULT_LOG_DIR, help="log directory"
    )
    parser.add_argument("--host", default="127.0.0.1", help="bind address")
    parser.add_argument("--port", type=int, default=8000, help="port (default 8000)")
    parser.set_defaults(handler=serve)
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
    add_serve_command(commands)
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


def llm_options(args: argparse.Namespace) -> LlmOptions:
    """LLM settings from the command line, shared by every LLM seat."""
    return LlmOptions(
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        reasoning_effort=args.reasoning_effort,
        timeout_seconds=args.timeout,
        max_illegal_retries=args.max_retries,
        fallback=args.fallback,
        output_mode=args.output_mode,
        use_cache=args.cache,
        extractor_model=args.extractor,
        persona=args.persona,
    )


def chat_model(options: LlmOptions) -> ChatModel:
    """LiteLLM with retries on transient errors, behind the reply cache if enabled."""
    model: ChatModel = RetryingChatModel(LiteLLMChatModel())
    if options.use_cache:
        model = CachedChatModel(model, DirectoryResponseStore(DEFAULT_CACHE_DIR))
    return model


def build_agent(
    spec: str, match_seed: int, seat: int, options: LlmOptions, model: ChatModel
) -> Agent:
    """Agent for an --agent spec: "random" or "llm:<litellm model id>"."""
    seed = derive_seed(match_seed, seat)
    if spec == "random":
        return RandomAgent(seed)
    if spec.startswith("llm:") and len(spec) > len("llm:"):
        return llm_agent(spec.removeprefix("llm:"), seed, options, model)
    raise ConfigError(f"unknown agent spec {spec!r}; known: random, llm:<model>")


def llm_agent(model_id: str, seed: int, options: LlmOptions, model: ChatModel) -> Agent:
    """An LLM agent for one seat."""
    settings = LlmAgentSettings(
        model=ModelSettings(
            model=model_id,
            temperature=options.temperature,
            max_tokens=options.max_tokens,
            timeout_seconds=options.timeout_seconds,
            reasoning_effort=options.reasoning_effort,
            seed=seed % 2**31,
        ),
        prompt=PromptSettings(output_mode=options.output_mode, persona=options.persona),
        max_illegal_retries=options.max_illegal_retries,
        fallback=options.fallback,
    )
    extractor = None
    if options.extractor_model is not None:
        extractor_settings = ModelSettings(
            model=options.extractor_model, temperature=0.0, max_tokens=64
        )
        extractor = ActionExtractor(model, extractor_settings)
    return LlmAgent(model, settings, seed, extractor)


def play(args: argparse.Namespace) -> None:
    """Play one match, printing it unless --quiet, and write the JSONL log."""
    game = create_game(args.game)
    config = game.parse_config(parse_config_json(args.config))
    options = llm_options(args)
    model = chat_model(options)
    specs = args.agent or ["random"] * config.num_players
    agents = [
        build_agent(spec, args.seed, seat, options, model)
        for seat, spec in enumerate(specs)
    ]
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


def check_replay(args: argparse.Namespace) -> None:
    """Replay a log and report whether it matches."""
    report = replay_match(read_log(args.log))
    print(
        f"Replay matches the log: {report.game_id}, {report.steps} steps, "
        f"{report.events} events."
    )
    return


def serve(args: argparse.Namespace) -> None:
    """Serve the web viewer until interrupted."""
    print(f"Serving {args.runs} at http://{args.host}:{args.port}/")
    uvicorn.run(create_app(MatchStore(args.runs)), host=args.host, port=args.port)
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
