"""Starting matches from the viewer: each runs as a task on the server's event loop.

A launch validates the YAML, prepares the match like the command line does,
and starts it; the log appears in the store at once, so the viewer follows it.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

from boardgames.arena.lineup import PreparedMatch, prepare_match, run_prepared
from boardgames.arena.match_config import parse_match_config
from boardgames.core import ConfigError

type LaunchStatus = Literal["running", "finished", "failed"]


class Example(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    text: str


class Launch(BaseModel):
    """A match started from the viewer and how it is going."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    match_id: str
    log: str
    status: LaunchStatus
    error: str | None = None


@dataclass
class Running:
    prepared: PreparedMatch
    done: bool = False
    error: str | None = None


class MatchLauncher:
    """Starts matches into `runs_dir` and remembers how each one ended."""

    def __init__(
        self, runs_dir: Path, api_key: str | None, examples_dir: Path | None
    ) -> None:
        self._runs_dir = runs_dir
        self._api_key = api_key
        self._examples_dir = examples_dir
        self._launched: dict[str, Running] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        return

    def examples(self) -> list[Example]:
        """The YAML files of the examples directory, by name."""
        if self._examples_dir is None or not self._examples_dir.is_dir():
            return []
        return [
            Example(name=path.stem, text=path.read_text(encoding="utf-8"))
            for path in sorted(self._examples_dir.glob("*.yaml"))
        ]

    def start(self, yaml_text: str) -> Launch:
        """Validate a match config and start it; must be called on the event loop."""
        try:
            raw = yaml.safe_load(yaml_text)
        except yaml.YAMLError as error:
            raise ConfigError(f"the config is not valid YAML: {error}") from error
        config = parse_match_config(raw, "config")
        running = Running(prepare_match(config, self._api_key, self._runs_dir))
        task = asyncio.ensure_future(self._run(running))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        self._launched[running.prepared.match_id] = running
        return launch_of(running)

    async def _run(self, running: Running) -> None:
        """Play the match; a failure is kept for the viewer, as nothing else sees it."""
        try:
            await run_prepared(running.prepared, None)
        except Exception as error:
            running.error = f"{type(error).__name__}: {error}"
        running.done = True
        return

    async def wait(self) -> None:
        """Wait for every started match to end; for tests."""
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        return

    def launches(self) -> list[Launch]:
        """Every match started through this launcher, newest first."""
        return [launch_of(running) for running in reversed(self._launched.values())]


def launch_of(running: Running) -> Launch:
    """The launch record of a started match."""
    status: LaunchStatus = "running"
    if running.error is not None:
        status = "failed"
    elif running.done:
        status = "finished"
    return Launch(
        match_id=running.prepared.match_id,
        log=str(running.prepared.log_path),
        status=status,
        error=running.error,
    )
