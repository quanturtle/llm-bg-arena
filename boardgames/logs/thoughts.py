"""A readable Markdown log of every decision, written while the match runs.

One section per model decision: the seat, the action, the model's reasoning,
each tool call with its result, rejected answers with the feedback, the notes
the model kept, and tokens and cost. Decisions without a model are one line.
"""

from pathlib import Path
from types import TracebackType
from typing import Self, TextIO

from boardgames.agents import AttemptRecord, AttemptToolCall
from boardgames.core import PlayerId, clean_text, seat_label
from boardgames.logs.schema import (
    DecisionRecord,
    ForfeitRecord,
    LogRecord,
    MatchFinished,
    MatchStarted,
    MatchStopped,
    TraceRecord,
)
from boardgames.logs.sink import LogFileError

RESULT_CHARS = 600
THOUGHTS_SUFFIX = ".thoughts.md"


def thoughts_path(log_path: Path) -> Path:
    """The thoughts file that sits next to the JSONL log at `log_path`."""
    return log_path.with_suffix(THOUGHTS_SUFFIX)


class ThoughtsLog:
    """Record sink that appends Markdown to `stream`, flushed after each record."""

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream
        self._agents: dict[int, str] = {}
        return

    def write(self, record: LogRecord) -> None:
        match record:
            case MatchStarted():
                self._agents = {seat.player: seat.agent for seat in record.seats}
                self._write(start_text(record, self._agents))
            case DecisionRecord():
                self._write(decision_text(record, self._seat(record.player)))
            case ForfeitRecord():
                self._write(forfeit_text(record, self._seat(record.player)))
            case MatchFinished():
                self._write(finish_text(record, self._agents))
            case MatchStopped():
                self._write(f"## Stopped after {record.steps} steps\n")
        return

    def _seat(self, player: int) -> str:
        return f"{seat_label(PlayerId(player))} {self._agents.get(player, '?')}"

    def _write(self, text: str) -> None:
        self._stream.write(clean_text(text))
        self._stream.flush()
        return


class ThoughtsFile(ThoughtsLog):
    """ThoughtsLog over a new file; refuses to overwrite, like the JSONL log."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            file = path.open("x", encoding="utf-8")
        except FileExistsError as error:
            raise LogFileError(
                f"{path} already exists; logs are never overwritten"
            ) from error
        super().__init__(file)
        self._file = file
        return

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._file.close()
        return


def start_text(record: MatchStarted, agents: dict[int, str]) -> str:
    """The title and the seats."""
    seats = ", ".join(
        f"{seat_label(PlayerId(player))} {agent}"
        for player, agent in sorted(agents.items())
    )
    return f"# {record.game_id} (seed {record.seed})\n\nSeats: {seats}\n\n"


def decision_text(record: DecisionRecord, seat: str) -> str:
    """One line for a bot; a section with the full trace for a model."""
    if not record.trace.attempts:
        return f"- Step {record.step}: {seat} plays `{record.action}`\n\n"
    title = f"## Step {record.step}: {seat} plays `{record.action}`"
    return f"{title}\n\nAsked: {record.prompt}\n\n" + trace_text(record.trace)


def forfeit_text(record: ForfeitRecord, seat: str) -> str:
    """A forfeit with whatever trace led to it."""
    header = f"## Step {record.step}: {seat} forfeits\n\n{record.reason}\n\n"
    return header + trace_text(record.trace)


def trace_text(trace: TraceRecord) -> str:
    """Reasoning, tool calls, rejections, notes and usage of one decision."""
    parts: list[str] = []
    for attempt in trace.attempts:
        parts.extend(attempt_text(attempt))
    if trace.reasoning:
        parts.append(f"**Reasoning**\n\n{trace.reasoning.strip()}\n")
    if trace.memory:
        parts.append(f"**Notes kept**\n\n{trace.memory.strip()}\n")
    usage = f"{trace.prompt_tokens + trace.completion_tokens} tokens"
    if trace.cost_usd is not None:
        usage += f", ${trace.cost_usd:.4f}"
    if trace.fallback:
        usage += f", fallback: {trace.fallback}"
    parts.append(f"_{usage}_\n")
    return "\n".join(parts) + "\n"


def attempt_text(attempt: AttemptRecord) -> list[str]:
    """The model's own reasoning, its tool calls and any rejection of one call."""
    parts: list[str] = []
    if attempt.model_reasoning and attempt.model_reasoning.strip():
        parts.append(f"**Model reasoning**\n\n{attempt.model_reasoning.strip()}\n")
    if attempt.tool_calls:
        lines = [tool_call_line(call) for call in attempt.tool_calls]
        parts.append("**Tool calls**\n\n" + "\n".join(lines) + "\n")
    if attempt.rejection is not None:
        shown = f"`{attempt.answer}`" if attempt.answer is not None else "the reply"
        parts.append(
            f"**Rejected** {shown}: {attempt.rejection.feedback}\n"
        )
    return parts


def tool_call_line(call: AttemptToolCall) -> str:
    """One bullet per tool call, with its result cut to RESULT_CHARS."""
    result = call.result
    if len(result) > RESULT_CHARS:
        result = result[:RESULT_CHARS] + " […]"
    result = result.replace("\n", "\n  ")
    return f"- `{call.name}` {call.arguments}\n  {result}"


def finish_text(record: MatchFinished, agents: dict[int, str]) -> str:
    """The result in one line, then final ranks and points."""
    lines = [
        f"- #{score.rank} {seat_label(PlayerId(score.player))} "
        f"{agents.get(score.player, '?')}: {score.points:g} points"
        for score in sorted(record.scores, key=lambda score: score.rank)
    ]
    heading = f"## Finished after {record.steps} steps"
    return f"{heading}\n\n{result_line(record, agents)}\n\n" + "\n".join(lines) + "\n"


def result_line(record: MatchFinished, agents: dict[int, str]) -> str:
    """The winner and their points, a shared first place, or a draw."""
    first = [score for score in record.scores if score.rank == 1]
    names = " and ".join(
        f"{seat_label(PlayerId(score.player))} {agents.get(score.player, '?')}"
        for score in first
    )
    points = first[0].points if first else 0
    point_text = f"{points:g} point{'' if points == 1 else 's'}"
    if len(first) == 1:
        return f"**Winner: {names}, {point_text}.**"
    if len(first) == len(record.scores):
        return f"**Draw: {names}.**"
    return f"**Shared first place: {names}, {point_text}.**"
