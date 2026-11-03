"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { SeatChip } from "@/components/seat";
import { ForfeitBadge, StatusBadge, WinnerBadge, type ShownStatus } from "@/components/status";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { Launch, MatchSummary } from "@/lib/api";
import { formatCost, formatDate, matchCost, matchDuration } from "@/lib/format";

/** A match with the status to show: the launcher's paused or failed overrides the log's running. */
export type ListedMatch = MatchSummary & { shownStatus: ShownStatus };

/** The log says running for a paused match; the launcher knows it is paused. */
export function listMatches(matches: MatchSummary[], launches: Launch[]): ListedMatch[] {
  const paused = new Set(launches.filter((launch) => launch.status === "paused").map((launch) => launch.match_id));
  return matches.map((match) => ({
    ...match,
    shownStatus: match.status === "running" && paused.has(match.match_id) ? "paused" : match.status,
  }));
}

export function matchHref(matchId: string): string {
  return `/match?id=${encodeURIComponent(matchId)}`;
}

function SeatList({ match }: { match: MatchSummary }) {
  const finished = match.status === "finished";
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1">
      {match.seats.map((seat) => (
        <SeatChip key={seat.player} seat={seat} className="max-w-72">
          {finished && seat.rank === 1 ? <WinnerBadge label="win" /> : seat.forfeited ? <ForfeitBadge /> : null}
        </SeatChip>
      ))}
    </div>
  );
}

// A click on a link or button inside a row does its own thing instead of opening the replay;
// so does a click in a dialog, which React bubbles to the row through its portal.
function isControlClick(event: React.MouseEvent<HTMLElement>): boolean {
  const target = event.target;
  if (!(target instanceof Element) || !event.currentTarget.contains(target)) return true;
  return target.closest("a, button") !== null;
}

/** One row per match; a row opens its replay. `actions` fills a last column, such as Delete. */
export function MatchTable({
  matches,
  now,
  actions,
}: {
  matches: ListedMatch[];
  now: number;
  actions?: (match: ListedMatch) => React.ReactNode;
}) {
  const router = useRouter();
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Started</TableHead>
          <TableHead>Game</TableHead>
          <TableHead>Seats</TableHead>
          <TableHead className="text-right">Steps</TableHead>
          <TableHead className="text-right">Time</TableHead>
          <TableHead className="text-right">Cost</TableHead>
          <TableHead>Status</TableHead>
          {actions ? <TableHead className="w-10" /> : null}
        </TableRow>
      </TableHeader>
      <TableBody>
        {matches.map((match) => (
          <TableRow
            key={match.match_id}
            className="cursor-pointer"
            onClick={(event) => {
              if (!isControlClick(event)) router.push(matchHref(match.match_id));
            }}
          >
            <TableCell className="whitespace-nowrap text-muted-foreground">{formatDate(match.started_at)}</TableCell>
            <TableCell className="whitespace-nowrap">
              <Link href={`/game?id=${encodeURIComponent(match.game_id)}`} className="font-medium hover:underline">
                {match.game_id}
              </Link>
              <span className="ml-2 font-mono text-xs text-muted-foreground">seed {match.seed}</span>
            </TableCell>
            <TableCell className="min-w-64 whitespace-normal">
              <SeatList match={match} />
            </TableCell>
            <TableCell className="text-right tabular-nums">{match.steps}</TableCell>
            <TableCell className="text-right font-mono tabular-nums" title={match.finished_at ? "From start to end" : "So far"}>
              {matchDuration(match, now)}
            </TableCell>
            <TableCell className="text-right tabular-nums">{formatCost(matchCost(match))}</TableCell>
            <TableCell>
              <StatusBadge status={match.shownStatus} />
            </TableCell>
            {actions ? <TableCell className="text-right">{actions(match)}</TableCell> : null}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
