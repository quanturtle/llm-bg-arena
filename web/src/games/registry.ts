// Every game with a drawn board, by game id.
import type { GameEntry } from "@/games/define";
import { ticTacToe } from "@/games/tic-tac-toe/board";

export const GAMES: Record<string, GameEntry> = {
  tic_tac_toe: ticTacToe,
};
