"""Starting, pausing and stopping matches from the viewer.

Each started match runs as a task on the server's event loop. A launch
validates the YAML and prepares the match like the command line does, so the
log appears in the store at once. Pausing closes a gate the runner waits at
before every round; stopping cancels the task, and the runner logs
match_stopped.
"""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

from boardgames.arena.control import PauseGate
from boardgames.arena.lineup import PreparedMatch, prepare_match, run_prepared
from boardgames.arena.match_config import parse_match_config
from boardgames.core import ArenaError, ConfigError
from boardgames.llm.model import ChatModel

type LaunchStatus = Literal["running", "paused", "stopped", "finished", "failed"]
type Ending = Literal["stopped", "finished", "failed"]

STOP_TIMEOUT_SECONDS = 5.0


class UnknownLaunchError(ArenaError):
    """No match with this id was started from this server."""


class MatchStillPlayingError(ArenaError):
    """The match is running or paused here; stop it before deleting it."""


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
    """A started match; `ending` is set once its task is over."""

    prepared: PreparedMatch
    gate: PauseGate = field(default_factory=PauseGate)
    ending: Ending | None = None
    error: str | None = None


class MatchLauncher:
    """Starts matches into `runs_dir`, pauses and stops them, and keeps their status."""

    def __init__(
        self, runs_dir: Path, model: ChatModel | None, examples_dir: Path | None
    ) -> None:
        """`model` serves every seat; with None (no API key) each start raises."""
        self._runs_dir = runs_dir
        self._model = model
        self._examples_dir = examples_dir
        self._launched: dict[str, Running] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
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
        running = Running(prepare_match(config, self._model, self._runs_dir))
        match_id = running.prepared.match_id
        self._launched[match_id] = running
        self._tasks[match_id] = asyncio.ensure_future(self._run(running))
        return self.launch(match_id)

    async def _run(self, running: Running) -> None:
        """Play the match and keep how it ended; a failure is kept for the viewer."""
        try:
            await run_prepared(running.prepared, None, running.gate)
        except asyncio.CancelledError:
            running.ending = "stopped"
            raise
        except Exception as error:
            running.ending = "failed"
            running.error = f"{type(error).__name__}: {error}"
            return
        running.ending = "finished"
        return

    def launch(self, match_id: str) -> Launch:
        """The current status of one started match."""
        if match_id not in self._launched:
            raise UnknownLaunchError(f"match {match_id!r} was not started here")
        return launch_of(self._launched[match_id], self._tasks[match_id])

    def launches(self) -> list[Launch]:
        """Every match started through this launcher, newest first."""
        return [self.launch(match_id) for match_id in reversed(self._launched)]

    def pause(self, match_id: str) -> Launch:
        """Hold the match before its next round; a round in progress finishes first."""
        self.launch(match_id)
        self._launched[match_id].gate.pause()
        return self.launch(match_id)

    def resume(self, match_id: str) -> Launch:
        """Let a paused match play on."""
        self.launch(match_id)
        self._launched[match_id].gate.resume()
        return self.launch(match_id)

    async def stop(self, match_id: str) -> Launch:
        """Cancel the match, cutting off any model call in flight, and wait for it."""
        self.launch(match_id)
        task = self._tasks[match_id]
        if not task.done():
            task.cancel()
            await asyncio.wait({task}, timeout=STOP_TIMEOUT_SECONDS)
        return self.launch(match_id)

    def forget(self, match_id: str) -> None:
        """Drop an ended match from the launches, before its log is deleted.

        A match still running or paused raises MatchStillPlayingError; unknown ids pass.
        """
        if match_id not in self._launched:
            return
        if self.launch(match_id).status in ("running", "paused"):
            raise MatchStillPlayingError(
                f"match {match_id!r} is still playing; stop it before deleting it"
            )
        del self._launched[match_id]
        del self._tasks[match_id]
        return

    async def wait(self) -> None:
        """Wait for every started match to end; for tests."""
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        return


def launch_of(running: Running, task: "asyncio.Task[None]") -> Launch:
    """The launch record of a started match.

    A task cancelled before its first step never sets `ending`, so it counts as stopped.
    """
    status: LaunchStatus = "running"
    if running.ending is not None:
        status = running.ending
    elif task.done():
        status = "stopped"
    elif running.gate.is_paused:
        status = "paused"
    return Launch(
        match_id=running.prepared.match_id,
        log=str(running.prepared.log_path),
        status=status,
        error=running.error,
    )
