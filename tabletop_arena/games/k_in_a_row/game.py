"""k-in-a-row: players alternate marking cells; k marks in a straight line wins.

Tic-tac-toe is 3 in a row on 3x3. With gravity on, a mark falls to the lowest
empty cell of its column, as in four-in-a-row on 6 rows by 7 columns.
"""

import re
from dataclasses import dataclass
from functools import partial
from importlib.resources import files
from typing import ClassVar

from tabletop_arena.core import (
    ConfigError,
    Decision,
    Event,
    FlatActionSpace,
    IllegalActionError,
    JsonObject,
    JsonValue,
    NotationError,
    Observation,
    PlayerId,
    Scores,
    Transition,
    register_game,
    seat_label,
)
from tabletop_arena.core.actions import ActionSpace
from tabletop_arena.core.json_data import (
    json_bool,
    json_int,
    json_optional_int,
    json_str_list,
)
from tabletop_arena.core.records import (
    dataclass_from_json,
    tagged_json_object,
    to_json_object,
)

MARKS = ("X", "O")
EMPTY = "."
MAX_SIDE = 26
DIRECTIONS = ((0, 1), (1, 0), (1, 1), (1, -1))
CELL_PATTERN = re.compile(r"([a-z])([1-9][0-9]*)")


@dataclass(frozen=True)
class KInARowConfig:
    """A `rows` x `cols` board where `k` in a line wins; `gravity` drops marks down."""

    num_players: int = 2
    rows: int = 3
    cols: int = 3
    k: int = 3
    gravity: bool = False


TIC_TAC_TOE = KInARowConfig()
FOUR_IN_A_ROW = KInARowConfig(rows=6, cols=7, k=4, gravity=True)


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
class KInARowState:
    """`board[row][col]` is the owner of a cell or None; row 0 is the bottom."""

    config: KInARowConfig
    board: Board
    to_move: PlayerId
    outcome: Outcome | None = None


@register_game
class KInARow:
    """k-in-a-row for two players, with optional gravity."""

    id: ClassVar[str] = "k_in_a_row"

    def parse_config(self, raw: JsonObject) -> KInARowConfig:
        config = dataclass_from_json(KInARowConfig, raw)
        check_config(config)
        return config

    def config_json(self, config: KInARowConfig) -> dict[str, JsonValue]:
        return to_json_object(config)

    def setup(self, config: KInARowConfig, seed: int) -> Transition[KInARowState]:
        board: Board = tuple((None,) * config.cols for _ in range(config.rows))
        text = f"{config.k} in a row on {config.rows}x{config.cols}"
        if config.gravity:
            text += ", with gravity"
        started = Event("started", f"New game: {text}.", to_json_object(config))
        return Transition(KInARowState(config, board, PlayerId(0)), (started,))

    def pending_decisions(self, state: KInARowState) -> tuple[Decision, ...]:
        if state.outcome is not None:
            return ()
        prompt = "Choose an empty cell to mark."
        if state.config.gravity:
            prompt = "Choose a column by naming its lowest empty cell."
        return (Decision(state.to_move, "mark", prompt),)

    def legal_actions(
        self, state: KInARowState, decision: Decision
    ) -> ActionSpace[Mark]:
        return FlatActionSpace(
            open_cells(state), cell_name, explain=partial(explain_mark, state)
        )

    def apply(
        self, state: KInARowState, player: PlayerId, action: Mark
    ) -> Transition[KInARowState]:
        check_move(state, player, action)
        board = with_mark(state.board, action, player)
        cell = cell_name(action)
        events = [
            Event(
                "marked",
                f"{player_name(player)} marked {cell}.",
                {"player": player, "cell": cell},
            )
        ]
        outcome = outcome_after(state.config, board, action, player)
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
        next_player = PlayerId(1 - player)
        return Transition(
            KInARowState(state.config, board, next_player, outcome), tuple(events)
        )

    def is_terminal(self, state: KInARowState) -> bool:
        return state.outcome is not None

    def scores(self, state: KInARowState) -> Scores:
        players = (PlayerId(0), PlayerId(1))
        if isinstance(state.outcome, Won):
            winner = state.outcome.player
            return Scores({p: 1.0 if p == winner else 0.0 for p in players})
        if isinstance(state.outcome, Drawn):
            return Scores({p: 0.5 for p in players})
        return Scores({p: 0.0 for p in players})

    def observe(self, state: KInARowState, viewer: PlayerId | None) -> Observation:
        winner = state.outcome.player if isinstance(state.outcome, Won) else None
        line = state.outcome.line if isinstance(state.outcome, Won) else ()
        return Observation(
            viewer,
            {
                "rows": state.config.rows,
                "cols": state.config.cols,
                "k": state.config.k,
                "gravity": state.config.gravity,
                "board": board_lines(state.board),
                "to_move": state.to_move if state.outcome is None else None,
                "winner": winner,
                "line": [cell_name(mark) for mark in line],
                "is_draw": isinstance(state.outcome, Drawn),
            },
        )

    def render_text(self, observation: Observation) -> str:
        data = observation.data
        lines = [header_line(data), *seat_lines(observation.viewer)]
        lines.append(status_line(data))
        lines.append("")
        lines.extend(grid_lines(json_str_list(data, "board"), json_int(data, "cols")))
        lines.append("")
        lines.append(
            "Legend: X = P1, O = P2, . = empty. A cell is column letter + row "
            "number; a1 is bottom left."
        )
        return "\n".join(lines)

    def rules_text(self) -> str:
        rules = files("tabletop_arena.games.k_in_a_row") / "rules.md"
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
        if json_bool(observation.data, "gravity"):
            column = cell_name(action)[0]
            return f"Drop {mark} into column {column}; it lands on {cell_name(action)}"
        return f"Place {mark} on {cell_name(action)}"

    def action_json(self, action: Mark) -> dict[str, JsonValue]:
        return tagged_json_object(action)


def check_config(config: KInARowConfig) -> None:
    """Raise ConfigError for a config that cannot produce a playable game."""
    if config.num_players != 2:
        raise ConfigError(f"k-in-a-row needs 2 players, got {config.num_players}")
    if not (1 <= config.rows <= MAX_SIDE and 1 <= config.cols <= MAX_SIDE):
        raise ConfigError(f"rows and cols must be between 1 and {MAX_SIDE}")
    if not 2 <= config.k <= max(config.rows, config.cols):
        raise ConfigError(f"k must be between 2 and the longer side, got {config.k}")
    return


def open_cells(state: KInARowState) -> list[Mark]:
    """Legal cells: top row first, or with gravity the lowest empty cell per column."""
    board = state.board
    if state.config.gravity:
        return [
            Mark(lowest, col)
            for col in range(state.config.cols)
            if (lowest := lowest_empty_row(board, col)) is not None
        ]
    return [
        Mark(row, col)
        for row in reversed(range(state.config.rows))
        for col in range(state.config.cols)
        if board[row][col] is None
    ]


def lowest_empty_row(board: Board, col: int) -> int | None:
    """Index of the lowest empty cell in a column, or None if the column is full."""
    for row, cells in enumerate(board):
        if cells[col] is None:
            return row
    return None


def cell_name(mark: Mark) -> str:
    """Notation of a cell: column letter, then row number from 1."""
    return f"{chr(ord('a') + mark.col)}{mark.row + 1}"


def explain_mark(state: KInARowState, mark: Mark) -> str:
    """Why marking this cell is illegal now."""
    config = state.config
    cell = cell_name(mark)
    if state.outcome is not None:
        return "The game is over."
    if not (0 <= mark.row < config.rows and 0 <= mark.col < config.cols):
        last = cell_name(Mark(config.rows - 1, config.cols - 1))
        return f"{cell} is off the board, which runs from a1 to {last}."
    owner = state.board[mark.row][mark.col]
    if owner is not None:
        return f"{cell} is already taken by {MARKS[owner]}."
    lowest = lowest_empty_row(state.board, mark.col)
    if config.gravity and lowest is not None and lowest != mark.row:
        lowest_cell = cell_name(Mark(lowest, mark.col))
        return f"With gravity, a mark in column {cell[0]} lands on {lowest_cell}."
    return f"{cell} is not a legal cell now."


def check_move(state: KInARowState, player: PlayerId, mark: Mark) -> None:
    """Raise IllegalActionError unless `player` may mark this cell now."""
    if state.outcome is not None:
        raise IllegalActionError("the game is over")
    if player != state.to_move:
        raise IllegalActionError(f"it is {player_name(state.to_move)}'s turn")
    if mark not in open_cells(state):
        raise IllegalActionError(explain_mark(state, mark))
    return


def with_mark(board: Board, mark: Mark, player: PlayerId) -> Board:
    """The board with `player`'s mark added."""
    row = board[mark.row]
    new_row = (*row[: mark.col], player, *row[mark.col + 1 :])
    return (*board[: mark.row], new_row, *board[mark.row + 1 :])


def player_name(player: PlayerId) -> str:
    """Seat label with mark, such as "P1 (X)"."""
    return f"{seat_label(player)} ({MARKS[player]})"


def outcome_after(
    config: KInARowConfig, board: Board, mark: Mark, player: PlayerId
) -> Outcome | None:
    """Won if `mark` completes a line of k, Drawn if the board is full, else None."""
    for direction in DIRECTIONS:
        line = line_through(board, mark, player, direction)
        if len(line) >= config.k:
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


def header_line(data: JsonObject) -> str:
    """Board size, k and gravity."""
    text = (
        f"{json_int(data, 'k')} in a row wins on a "
        f"{json_int(data, 'rows')}x{json_int(data, 'cols')} board"
    )
    if json_bool(data, "gravity"):
        text += "; gravity is on"
    return f"{text}."


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


def grid_lines(rows: list[str], cols: int) -> list[str]:
    """The board with column letters on top and row numbers on the left."""
    letters = " ".join(chr(ord("a") + col) for col in range(cols))
    lines = [f"   {letters}"]
    for index, row in enumerate(rows):
        number = len(rows) - index
        lines.append(f"{number:>2} {' '.join(row)}")
    return lines
