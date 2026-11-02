"""Time behind an interface, so tests control latency and timestamps."""

import time
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def monotonic(self) -> float:
        """Seconds from an arbitrary origin, for measuring durations."""
        ...

    def now_iso(self) -> str:
        """Current UTC time as ISO 8601, for log timestamps."""
        ...


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def now_iso(self) -> str:
        return datetime.now(UTC).isoformat(timespec="seconds")
