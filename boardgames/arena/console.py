"""Console output of a match: public events, every action, LLM traces, final scores."""

from collections import Counter
from typing import TextIO

from boardgames.core import PlayerId, seat_label
from boardgames.logs.schema import (
    DecisionRecord,
    EventRecord,
    ForfeitRecord,
    LogRecord,
    MatchFinished,
    MatchStarted,
    MatchStopped,
    TraceRecord,
)

REASONING_CHARS = 200


class ConsoleLog:
    """Record sink that prints an operator's view of the match to `stream`."""

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream
        self._agents: dict[int, str] = {}
        self._tokens: Counter[int] = Counter()
        self._cost: dict[int, float | None] = {}
        return

    def write(self, record: LogRecord) -> None:
        match record:
            case MatchStarted():
                self._agents = {seat.player: seat.agent for seat in record.seats}
                players = ", ".join(
                    self._seat(player) for player in sorted(self._agents)
                )
                self._print(f"{record.game_id} (seed {record.seed}): {players}")
            case EventRecord(audience="everyone"):
                self._print(f"    {record.text}")
            case DecisionRecord():
                self._print(
                    f"[{record.step}] {self._seat(record.player)}: {record.action}"
                )
                self._print_trace(record.player, record.trace)
            case ForfeitRecord():
                self._print(f"{self._seat(record.player)} forfeits: {record.reason}")
                self._print_trace(record.player, record.trace)
            case MatchFinished():
                self._print_scores(record)
            case MatchStopped():
                self._print(f"Stopped after {record.steps} steps, before the end.")
        return

    def _seat(self, player: int) -> str:
        return f"{seat_label(PlayerId(player))} {self._agents.get(player, '?')}"

    def _print_trace(self, player: int, trace: TraceRecord) -> None:
        """Reasoning, rejected attempts and cost of a model-backed decision."""
        if not trace.attempts:
            return
        self._tokens[player] += trace.prompt_tokens + trace.completion_tokens
        previous = self._cost.get(player, 0.0)
        self._cost[player] = (
            None
            if previous is None or trace.cost_usd is None
            else previous + trace.cost_usd
        )
        if trace.reasoning:
            reasoning = " ".join(trace.reasoning.split())[:REASONING_CHARS]
            self._print(f"      reasoning: {reasoning}")
        for attempt in trace.attempts:
            rejection = attempt.get("rejection")
            if isinstance(rejection, dict):
                self._print(f"      rejected: {rejection.get('feedback')}")
        if trace.fallback:
            self._print(f"      fallback: {trace.fallback}")
        return

    def _print_scores(self, record: MatchFinished) -> None:
        self._print(f"Finished after {record.steps} steps.")
        for score in sorted(record.scores, key=lambda score: score.rank):
            usage = ""
            if score.player in self._cost:
                cost = self._cost[score.player]
                dollars = "unknown cost" if cost is None else f"${cost:.4f}"
                usage = f" ({self._tokens[score.player]} tokens, {dollars})"
            unit = "point" if score.points == 1 else "points"
            self._print(
                f"  #{score.rank} {self._seat(score.player)}: "
                f"{score.points:g} {unit}{usage}"
            )
        return

    def _print(self, text: str) -> None:
        print(text, file=self._stream)
        return
