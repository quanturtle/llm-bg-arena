# k-in-a-row

## Goal
Be the first to line up k of your marks in an unbroken straight line: across, up and down, or diagonal.

## Components
A rectangular board of empty cells. P1 plays X, P2 plays O. The board size, k, and whether gravity is on are shown above the board each turn.

## Turn
P1 moves first, then players alternate. On your turn, put one mark on an empty cell.

With gravity on, a mark falls to the lowest empty cell of its column. Name that lowest empty cell; a cell with an empty cell below it is not legal.

## End and scoring
- A line of k or more of your marks wins at once: 1 point to the winner, 0 to the loser.
- If the board fills with no such line, the game is a draw: 0.5 points each.

## Notation
A cell is its column letter followed by its row number. Columns run a, b, c… from the left; rows run 1, 2, 3… from the bottom. `a1` is the bottom-left cell.

An action is the cell you mark: `b2`.
