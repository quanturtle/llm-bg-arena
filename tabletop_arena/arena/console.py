"""Console output of a match: public events, every action, and final scores."""

from typing import TextIO

from tabletop_arena.core import PlayerId, seat_label
from tabletop_arena.logs.schema import (
    DecisionRecord,
    EventRecord,
    ForfeitRecord,
    LogRecord,
    MatchFinished,
    MatchStarted,
)


class ConsoleLog:
    """Record sink that prints an operator's view of the match to `stream`."""

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream
        self._agents: dict[int, str] = {}
        return

    def write(self, record: LogRecord) -> None:
        match record:
            case MatchStarted():
                self._agents = {seat.player: seat.agent for seat in record.seats}
                players = ", ".join(
                    f"{self._seat(player)}" for player in sorted(self._agents)
                )
                self._print(f"{record.game_id} (seed {record.seed}): {players}")
            case EventRecord(audience="everyone"):
                self._print(f"    {record.text}")
            case DecisionRecord():
                self._print(
                    f"[{record.step}] {self._seat(record.player)}: {record.action}"
                )
            case ForfeitRecord():
                self._print(f"{self._seat(record.player)} forfeits: {record.reason}")
            case MatchFinished():
                self._print_scores(record)
        return

    def _seat(self, player: int) -> str:
        return f"{seat_label(PlayerId(player))} {self._agents.get(player, '?')}"

    def _print_scores(self, record: MatchFinished) -> None:
        self._print(f"Finished after {record.steps} steps.")
        for score in sorted(record.scores, key=lambda score: score.rank):
            self._print(
                f"  #{score.rank} {self._seat(score.player)}: {score.points:g} points"
            )
        return

    def _print(self, text: str) -> None:
        print(text, file=self._stream)
        return
