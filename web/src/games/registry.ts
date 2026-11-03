// Every game with a drawn board, by game id.
import { catan } from "@/games/catan/board";
import type { GameEntry } from "@/games/define";
import { puertoRico } from "@/games/puerto-rico/board";
import { ticTacToe } from "@/games/tic-tac-toe/board";

export const GAMES: Record<string, GameEntry> = {
  catan,
  puerto_rico: puertoRico,
  tic_tac_toe: ticTacToe,
};
