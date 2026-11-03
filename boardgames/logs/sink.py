"""Where log records go: a JSONL file, the console, or several at once."""

from collections.abc import Sequence
from pathlib import Path
from types import TracebackType
from typing import Protocol, Self

from boardgames.logs.schema import LogRecord


class RecordSink(Protocol):
    def write(self, record: LogRecord) -> None:
        """Store or show one record."""
        ...


class JsonlFile:
    """Writes one record per line, flushed at once so a crash keeps the log so far.

    Refuses to overwrite an existing file.
    """

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file = path.open("x", encoding="utf-8")
        return

    def write(self, record: LogRecord) -> None:
        self._file.write(record.model_dump_json() + "\n")
        self._file.flush()
        return

    def close(self) -> None:
        self._file.close()
        return

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
        return


class Broadcast:
    """Writes each record to every sink in order."""

    def __init__(self, sinks: Sequence[RecordSink]) -> None:
        self._sinks = tuple(sinks)
        return

    def write(self, record: LogRecord) -> None:
        for sink in self._sinks:
            sink.write(record)
        return
