// The match clock and each player's clock at the step on screen.
import type { Outline } from "@/lib/api";

export type Clocks = {
  matchMs: number;
  seats: { ms: number; thinking: boolean }[];
};

/**
 * The match clock runs from the start to the end, or to now while the match runs. A player's clock
 * adds up its moves to `step`, plus the move it is making while the page shows the match live.
 */
export function clocksAt(outline: Outline, step: number, pending: number[], isLive: boolean, now: number): Clocks {
  const match = outline.match;
  const end = match.finished_at ? Date.parse(match.finished_at) : now;
  const totals = match.seats.map(() => 0);
  for (const move of outline.moves) if (move.step <= step) totals[move.player] += move.latency_seconds * 1000;
  for (const forfeit of outline.forfeits) if (forfeit.observed_at_step < step) totals[forfeit.player] += forfeit.latency_seconds * 1000;
  const thinking = isLive && outline.log_updated_at ? pending : [];
  const since = thinking.length && outline.log_updated_at ? now - Date.parse(outline.log_updated_at) : 0;
  return {
    matchMs: end - Date.parse(match.started_at),
    seats: totals.map((ms, player) => {
      const isThinking = thinking.includes(player);
      return { ms: ms + (isThinking ? since : 0), thinking: isThinking };
    }),
  };
}
