// Display formats shared by every page: money, durations, dates and seat names.
import type { MatchSummary, SeatSummary } from "@/lib/api";

export function formatCost(cost: number | null | undefined): string {
  if (cost === null || cost === undefined) return "n/a";
  if (cost === 0) return "$0";
  return cost < 0.01 ? `$${cost.toFixed(4)}` : `$${cost.toFixed(2)}`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

export function formatSeconds(seconds: number): string {
  return seconds < 1 ? `${Math.round(seconds * 1000)} ms` : `${seconds.toFixed(1)} s`;
}

/** Milliseconds as m:ss, or h:mm:ss from an hour on. */
export function formatClock(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = String(total % 60).padStart(2, "0");
  return hours ? `${hours}:${String(minutes).padStart(2, "0")}:${seconds}` : `${minutes}:${seconds}`;
}

export function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** The seat's agent name, followed by its model id when the name is a label that hides it. */
export function seatName(seat: Pick<SeatSummary, "agent" | "model">): string {
  return seat.model && !seat.agent.startsWith(seat.model) ? `${seat.agent} (${seat.model})` : seat.agent;
}

/** Version 0 marks a match without a model seat, so no prompt was sent. */
export function promptLabel(version: number | null): string {
  return version ? `prompt v${version}` : "no model prompt";
}

/** The match's total cost, or null as soon as one seat's cost is unknown. */
export function matchCost(match: MatchSummary): number | null {
  let total = 0;
  for (const seat of match.seats) {
    if (seat.cost_usd === null) return null;
    total += seat.cost_usd;
  }
  return total;
}

/** How long a match took from start to end; a running one shows its time so far. */
export function matchDuration(match: MatchSummary, now: number): string {
  const started = Date.parse(match.started_at);
  const ended = match.finished_at ? Date.parse(match.finished_at) : now;
  return Number.isNaN(started) || Number.isNaN(ended) ? "" : formatClock(ended - started);
}

/** Seat mentions such as "P2" in `text`, as [before, player, before, player, ..., rest]. */
export function splitSeatMentions(text: string, players: number): (string | number)[] {
  const parts: (string | number)[] = [];
  let end = 0;
  for (const found of text.matchAll(/\bP(\d+)\b/g)) {
    const player = Number(found[1]) - 1;
    if (player < 0 || player >= players) continue;
    parts.push(text.slice(end, found.index), player);
    end = (found.index ?? 0) + found[0].length;
  }
  parts.push(text.slice(end));
  return parts;
}
