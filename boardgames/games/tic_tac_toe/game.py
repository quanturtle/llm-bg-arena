"""Tic-tac-toe: two players alternate marking cells of a 3x3 board.

Three marks in a straight line win; a full board with no line is a draw.
"""

import re
from dataclasses import dataclass
from functools import partial
from importlib.resources import files
from typing import ClassVar

from boardgames.core import (
    ConfigError,
    Decision,
    Event,
    FlatActionSpace,
    JsonObject,
    JsonValue,
    NotationError,
    Observation,
    PlayerId,
    Scores,
    Transition,
    checked_apply,
    register_game,
    seat_label,
)
from boardgames.core.actions import ActionSpace
from boardgames.core.json_data import (
    json_bool,
    json_int,
    json_optional_int,
    json_str_list,
)
from boardgames.core.records import (
    dataclass_from_json,
    tagged_json_object,
    to_json_object,
)

MARKS = ("X", "O")
EMPTY = "."
SIZE = 3
HEADER = "Three in a row wins on a 3x3 board."
DIRECTIONS = ((0, 1), (1, 0), (1, 1), (1, -1))
CELL_PATTERN = re.compile(r"([a-z])([1-9][0-9]*)")


@dataclass(frozen=True)
class TicTacToeConfig:
    """Tic-tac-toe has no options; `num_players` is always 2."""

    num_players: int = 2


@dataclass(frozen=True)
class Mark:
    """Mark one cell; row 0 is the bottom row (named 1), col 0 is column a."""

    row: int
    col: int


@dataclass(frozen=True)
class Won:
    player: PlayerId
    line: tuple[Mark, ...]


@dataclass(frozen=True)
class Drawn:
    """The board filled up with no line."""


type Outcome = Won | Drawn
type Board = tuple[tuple[PlayerId | None, ...], ...]


@dataclass(frozen=True)
class TicTacToeState:
    """`board[row][col]` is the owner of a cell or None; row 0 is the bottom."""

    board: Board
    outcome: Outcome | None = None

    @property
    def to_move(self) -> PlayerId | None:
        """P1 moves first; a finished game has no player to move."""
        if self.outcome is not None:
            return None
        x_marks = sum(cell == PlayerId(0) for row in self.board for cell in row)
        o_marks = sum(cell == PlayerId(1) for row in self.board for cell in row)
        return PlayerId(0) if x_marks == o_marks else PlayerId(1)


@register_game
class TicTacToe:
    """Tic-tac-toe for two players on a 3x3 board."""

    id: ClassVar[str] = "tic_tac_toe"
    rules_version: ClassVar[int] = 1

    def parse_config(self, raw: JsonObject) -> TicTacToeConfig:
        config = dataclass_from_json(TicTacToeConfig, raw)
        check_config(config)
        return config

    def config_json(self, config: TicTacToeConfig) -> dict[str, JsonValue]:
        return to_json_object(config)

    def setup(self, config: TicTacToeConfig, seed: int) -> Transition[TicTacToeState]:
        board: Board = ((None,) * SIZE,) * SIZE
        started = Event("started", "New game of tic-tac-toe.", to_json_object(config))
        return Transition(TicTacToeState(board), (started,))

    def pending_decisions(self, state: TicTacToeState) -> tuple[Decision, ...]:
        if state.outcome is not None:
            return ()
        assert state.to_move is not None
        return (Decision(state.to_move, "mark", "Choose an empty cell to mark."),)

    def legal_actions(
        self, state: TicTacToeState, decision: Decision
    ) -> ActionSpace[Mark]:
        return FlatActionSpace.from_check(
            all_cells(), cell_name, partial(move_reason, state)
        )

    def apply(
        self, state: TicTacToeState, player: PlayerId, action: Mark
    ) -> Transition[TicTacToeState]:
        if state.outcome is not None:
            no_decision = "the game is over"
        else:
            assert state.to_move is not None
            no_decision = f"it is {player_name(state.to_move)}'s turn"
        return checked_apply(self, state, player, action, no_decision=no_decision)

    def apply_legal(
        self, state: TicTacToeState, player: PlayerId, action: Mark
    ) -> Transition[TicTacToeState]:
        board = with_mark(state.board, action, player)
        cell = cell_name(action)
        events = [
            Event(
                "marked",
                f"{player_name(player)} marked {cell}.",
                {"player": player, "cell": cell},
            )
        ]
        outcome = outcome_after(board, action, player)
        if isinstance(outcome, Won):
            line = [cell_name(mark) for mark in outcome.line]
            events.append(
                Event(
                    "won",
                    f"{player_name(player)} completed a line: {' '.join(line)}.",
                    {"player": player, "line": line},
                )
            )
        elif isinstance(outcome, Drawn):
            events.append(Event("drawn", "The board is full with no line: draw."))
        return Transition(TicTacToeState(board, outcome), tuple(events))

    def is_terminal(self, state: TicTacToeState) -> bool:
        return state.outcome is not None

    def scores(self, state: TicTacToeState) -> Scores:
        players = (PlayerId(0), PlayerId(1))
        if isinstance(state.outcome, Won):
            winner = state.outcome.player
            return Scores({p: 1.0 if p == winner else 0.0 for p in players})
        if isinstance(state.outcome, Drawn):
            return Scores({p: 0.5 for p in players})
        return Scores({p: 0.0 for p in players})

    def public_scores(self, state: TicTacToeState) -> Scores:
        """Nothing is hidden, so these are the scores."""
        return self.scores(state)

    def observe(self, state: TicTacToeState, viewer: PlayerId | None) -> Observation:
        winner = state.outcome.player if isinstance(state.outcome, Won) else None
        line = state.outcome.line if isinstance(state.outcome, Won) else ()
        return Observation(
            viewer,
            {
                "board": board_lines(state.board),
                "to_move": state.to_move,
                "winner": winner,
                "line": [cell_name(mark) for mark in line],
                "is_draw": isinstance(state.outcome, Drawn),
            },
        )

    def render_text(self, observation: Observation) -> str:
        data = observation.data
        lines = [HEADER, *seat_lines(observation.viewer)]
        lines.append(status_line(data))
        lines.append("")
        lines.extend(grid_lines(json_str_list(data, "board")))
        lines.append("")
        lines.append(
            "Legend: X = P1, O = P2, . = empty. A cell is column letter + row "
            "number; a1 is bottom left."
        )
        return "\n".join(lines)

    def rules_text(self) -> str:
        rules = files("boardgames.games.tic_tac_toe") / "rules.md"
        return rules.read_text(encoding="utf-8")

    def format_action(self, action: Mark) -> str:
        return cell_name(action)

    def parse_action(self, text: str) -> Mark:
        match = CELL_PATTERN.fullmatch(text)
        if match is None:
            raise NotationError(f"{text!r} is not a cell like 'b2'")
        letter, number = match.groups()
        return Mark(int(number) - 1, ord(letter) - ord("a"))

    def describe_action(self, observation: Observation, action: Mark) -> str:
        viewer = observation.viewer
        mark = "a mark" if viewer is None else MARKS[viewer]
        return f"Place {mark} on {cell_name(action)}"

    def action_json(self, action: Mark) -> dict[str, JsonValue]:
        return tagged_json_object(action)


def check_config(config: TicTacToeConfig) -> None:
    """Raise ConfigError unless the config seats exactly two players."""
    if config.num_players != 2:
        raise ConfigError(f"tic-tac-toe needs 2 players, got {config.num_players}")
    return


def all_cells() -> list[Mark]:
    """Every cell, top row first."""
    return [Mark(row, col) for row in reversed(range(SIZE)) for col in range(SIZE)]


def cell_name(mark: Mark) -> str:
    """Notation of a cell: column letter, then row number from 1."""
    return f"{chr(ord('a') + mark.col)}{mark.row + 1}"


def move_reason(state: TicTacToeState, mark: Mark) -> str | None:
    """Why marking this cell is illegal, or None when it is legal."""
    cell = cell_name(mark)
    if not (0 <= mark.row < SIZE and 0 <= mark.col < SIZE):
        return f"{cell} is off the board, which runs from a1 to c3."
    owner = state.board[mark.row][mark.col]
    if owner is not None:
        return f"{cell} is already taken by {MARKS[owner]}."
    return None


def with_mark(board: Board, mark: Mark, player: PlayerId) -> Board:
    """The board with `player`'s mark added."""
    row = board[mark.row]
    new_row = (*row[: mark.col], player, *row[mark.col + 1 :])
    return (*board[: mark.row], new_row, *board[mark.row + 1 :])


def player_name(player: PlayerId) -> str:
    """Seat label with mark, such as "P1 (X)"."""
    return f"{seat_label(player)} ({MARKS[player]})"


def outcome_after(board: Board, mark: Mark, player: PlayerId) -> Outcome | None:
    """Won if `mark` completes a line, Drawn if the board is full, else None."""
    for direction in DIRECTIONS:
        line = line_through(board, mark, player, direction)
        if len(line) == SIZE:
            return Won(player, line)
    if all(cell is not None for row in board for cell in row):
        return Drawn()
    return None


def line_through(
    board: Board, mark: Mark, player: PlayerId, direction: tuple[int, int]
) -> tuple[Mark, ...]:
    """The run of `player`'s marks through `mark` along `direction`, in order."""
    backward = run_from(board, mark, player, (-direction[0], -direction[1]))
    forward = run_from(board, mark, player, direction)
    return (*reversed(backward), mark, *forward)


def run_from(
    board: Board, mark: Mark, player: PlayerId, step: tuple[int, int]
) -> list[Mark]:
    """Consecutive cells owned by `player` after `mark`, moving by `step`."""
    run: list[Mark] = []
    row, col = mark.row + step[0], mark.col + step[1]
    while 0 <= row < len(board) and 0 <= col < len(board[0]):
        if board[row][col] != player:
            break
        run.append(Mark(row, col))
        row, col = row + step[0], col + step[1]
    return run


def board_lines(board: Board) -> list[str]:
    """One string per row, top row first: X, O or "." per cell."""
    return [
        "".join(EMPTY if cell is None else MARKS[cell] for cell in row)
        for row in reversed(board)
    ]


def seat_lines(viewer: PlayerId | None) -> list[str]:
    """Which mark the viewer plays; nothing for a spectator."""
    if viewer is None:
        return []
    return [f"You are {player_name(viewer)}."]


def status_line(data: JsonObject) -> str:
    """Whose move it is, or how the game ended."""
    winner = json_optional_int(data, "winner")
    if winner is not None:
        line = " ".join(json_str_list(data, "line"))
        return f"{player_name(PlayerId(winner))} won with {line}."
    if json_bool(data, "is_draw"):
        return "The game ended in a draw."
    return f"{player_name(PlayerId(json_int(data, 'to_move')))} to move."


def grid_lines(rows: list[str]) -> list[str]:
    """The board with column letters on top and row numbers on the left."""
    letters = " ".join(chr(ord("a") + col) for col in range(SIZE))
    lines = [f"   {letters}"]
    for index, row in enumerate(rows):
        number = len(rows) - index
        lines.append(f"{number:>2} {' '.join(row)}")
    return lines
