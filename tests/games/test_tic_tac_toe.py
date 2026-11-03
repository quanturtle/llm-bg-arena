import pytest

from boardgames.core import (
    ConfigError,
    DuplicateGameError,
    IllegalActionError,
    NotationError,
    PlayerId,
    create_game,
    register_game,
)
from boardgames.games.tic_tac_toe import (
    Mark,
    TicTacToe,
    TicTacToeConfig,
    TicTacToeState,
)

GAME = TicTacToe()
P1 = PlayerId(0)
P2 = PlayerId(1)


def play(cells: list[str]) -> TicTacToeState:
    """Play `cells` alternately from the start, P1 first."""
    state = GAME.setup(TicTacToeConfig(), seed=0).state
    for index, cell in enumerate(cells):
        state = GAME.apply(state, PlayerId(index % 2), GAME.parse_action(cell)).state
    return state


def legal_cells(state: TicTacToeState) -> list[str]:
    (decision,) = GAME.pending_decisions(state)
    listing = GAME.legal_actions(state, decision).listing(100)
    assert listing is not None
    return [GAME.format_action(mark) for mark in listing]


def test_new_game_asks_p1_to_mark_any_cell() -> None:
    state = play([])
    (decision,) = GAME.pending_decisions(state)
    assert decision.player == P1
    assert len(legal_cells(state)) == 9
    return


def test_marked_cell_is_no_longer_legal() -> None:
    state = play(["b2"])
    assert "b2" not in legal_cells(state)
    assert GAME.pending_decisions(state)[0].player == P2
    return


@pytest.mark.parametrize(
    "cells",
    [
        ["a1", "a2", "b1", "b2", "c1"],
        ["a1", "b1", "a2", "b2", "a3"],
        ["a1", "b1", "b2", "c1", "c3"],
        ["c1", "a1", "b2", "a2", "a3"],
    ],
    ids=["row", "column", "diagonal", "anti-diagonal"],
)
def test_three_in_a_line_wins(cells: list[str]) -> None:
    state = play(cells)
    assert GAME.is_terminal(state)
    assert GAME.pending_decisions(state) == ()
    assert GAME.scores(state).points == {P1: 1.0, P2: 0.0}
    return


def test_win_event_lists_the_line() -> None:
    state = play(["a1", "a2", "b1", "b2"])
    events = GAME.apply(state, P1, Mark(0, 2)).events
    assert [event.kind for event in events] == ["marked", "won"]
    assert events[1].data["line"] == ["a1", "b1", "c1"]
    return


def test_full_board_without_line_is_a_draw() -> None:
    state = play(["a1", "b1", "c1", "b2", "a2", "c2", "b3", "a3", "c3"])
    assert GAME.is_terminal(state)
    assert GAME.scores(state).points == {P1: 0.5, P2: 0.5}
    return


def test_taken_cell_raises_with_reason() -> None:
    with pytest.raises(IllegalActionError, match="b2 is already taken by X"):
        GAME.apply(play(["b2"]), P2, Mark(1, 1))
    return


def test_moving_out_of_turn_raises() -> None:
    with pytest.raises(IllegalActionError, match="P1 \\(X\\)'s turn"):
        GAME.apply(play([]), P2, Mark(0, 0))
    return


def test_moving_after_the_end_raises() -> None:
    with pytest.raises(IllegalActionError, match="game is over"):
        GAME.apply(play(["a1", "a2", "b1", "b2", "c1"]), P2, Mark(2, 2))
    return


def test_off_board_cell_is_explained() -> None:
    state = play([])
    (decision,) = GAME.pending_decisions(state)
    space = GAME.legal_actions(state, decision)
    assert space.explain(Mark(3, 0)) == "a4 is off the board, which runs from a1 to c3."
    return


def test_notation_round_trips_on_every_cell() -> None:
    for row in range(3):
        for col in range(3):
            mark = Mark(row, col)
            assert GAME.parse_action(GAME.format_action(mark)) == mark
    return


@pytest.mark.parametrize("text", ["B2", "b0", "bb", "", " b2", "b2 "])
def test_parse_rejects_non_canonical_text(text: str) -> None:
    with pytest.raises(NotationError):
        GAME.parse_action(text)
    return


@pytest.mark.parametrize("raw", [{}, {"num_players": 2}])
def test_parse_config_accepts_two_players(raw: dict[str, int]) -> None:
    assert GAME.parse_config(raw) == TicTacToeConfig()
    return


@pytest.mark.parametrize("raw", [{"num_players": 3}, {"rows": 4}, {"gravity": True}])
def test_parse_config_rejects_other_options(raw: dict[str, int]) -> None:
    with pytest.raises(ConfigError):
        GAME.parse_config(raw)
    return


def test_render_text_shows_grid_and_legend() -> None:
    state = play(["a1", "b2"])
    text = GAME.render_text(GAME.observe(state, P1))
    assert "You are P1 (X)." in text
    assert "P1 (X) to move." in text
    assert " 2 . O ." in text
    assert " 1 X . ." in text
    assert "   a b c" in text
    return


def test_registered_under_its_id() -> None:
    assert isinstance(create_game("tic_tac_toe"), TicTacToe)
    with pytest.raises(DuplicateGameError):
        register_game(TicTacToe)
    return
