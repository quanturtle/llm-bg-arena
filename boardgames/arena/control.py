"""Pausing a running match: the runner waits at a gate before every round."""

import asyncio
from typing import Protocol


class MatchControl(Protocol):
    async def wait_until_resumed(self) -> None:
        """Return at once while running; block while paused."""
        ...


class AlwaysRunning:
    """The control of a match nobody pauses."""

    async def wait_until_resumed(self) -> None:
        return


class PauseGate:
    """A gate that is open until `pause` and open again after `resume`."""

    def __init__(self) -> None:
        self._open = asyncio.Event()
        self._open.set()
        return

    @property
    def is_paused(self) -> bool:
        return not self._open.is_set()

    def pause(self) -> None:
        self._open.clear()
        return

    def resume(self) -> None:
        self._open.set()
        return

    async def wait_until_resumed(self) -> None:
        await self._open.wait()
        return
