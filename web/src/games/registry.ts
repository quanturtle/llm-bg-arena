// Every game with a drawn board, by game id.
import { catan } from "@/games/catan/board";
import type { GameEntry } from "@/games/define";
import { ticTacToe } from "@/games/tic-tac-toe/board";

export const GAMES: Record<string, GameEntry> = {
  catan,
  tic_tac_toe: ticTacToe,
};
