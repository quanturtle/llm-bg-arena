import Link from "next/link";

import { ProviderLogo } from "@/components/provider-logo";
import { agentHref } from "@/components/seat";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { AgentGameStats } from "@/lib/api";
import { formatCost, formatPercent, formatSeconds } from "@/lib/format";

/** Version 0 is the logs recorded before prompts were versioned. */
export function promptText(version: number | null): string {
  return version ? `prompt v${version}` : "unversioned prompt";
}

// The models an agent name played with, when the name is a label rather than a model id.
function ModelNote({ row }: { row: AgentGameStats }) {
  const models = row.models.filter((model) => model !== row.agent);
  return models.length ? <span className="ml-1 text-xs text-muted-foreground">{models.join(", ")}</span> : null;
}

const NUMBER = "text-right tabular-nums";

/** One row per agent (and game or prompt version) with its results, errors, latency and cost. */
export function StatsTable({
  rows,
  withElo = false,
  withGame = false,
  withPrompt = false,
}: {
  rows: AgentGameStats[];
  withElo?: boolean;
  withGame?: boolean;
  withPrompt?: boolean;
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-8">#</TableHead>
          <TableHead>Agent</TableHead>
          {withGame ? <TableHead>Game</TableHead> : null}
          {withPrompt ? <TableHead>Prompt</TableHead> : null}
          {withElo ? <TableHead className="text-right">Elo</TableHead> : null}
          <TableHead className="text-right">Matches</TableHead>
          <TableHead className="text-right">Wins</TableHead>
          <TableHead className="text-right">Win rate</TableHead>
          <TableHead className="text-right">Avg rank</TableHead>
          <TableHead className="text-right">Avg points</TableHead>
          <TableHead className="text-right">Forfeits</TableHead>
          <TableHead className="text-right">Illegal</TableHead>
          <TableHead className="text-right">Fallbacks</TableHead>
          <TableHead className="text-right">Latency</TableHead>
          <TableHead className="text-right">Tokens</TableHead>
          <TableHead className="text-right">Cost / match</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row, index) => (
          <TableRow key={`${row.agent}|${row.game_id}|${row.prompt_version}`}>
            <TableCell className="text-muted-foreground tabular-nums">{index + 1}</TableCell>
            <TableCell>
              <span className="inline-flex items-center gap-2">
                <ProviderLogo model={row.models[0] ?? row.agent} />
                <Link href={agentHref(row.agent)} className="font-medium hover:underline">
                  {row.agent}
                </Link>
                <Badge variant="secondary">{row.kind}</Badge>
              </span>
              <ModelNote row={row} />
            </TableCell>
            {withGame ? (
              <TableCell>
                <Link href={`/game?id=${encodeURIComponent(row.game_id ?? "")}`} className="hover:underline">
                  {row.game_id}
                </Link>
              </TableCell>
            ) : null}
            {withPrompt ? <TableCell>{promptText(row.prompt_version)}</TableCell> : null}
            {withElo ? <TableCell className={`${NUMBER} font-semibold`}>{row.elo === null ? "" : Math.round(row.elo)}</TableCell> : null}
            <TableCell className={NUMBER}>{row.matches}</TableCell>
            <TableCell className={NUMBER}>{row.wins}</TableCell>
            <TableCell className={NUMBER}>{formatPercent(row.win_rate)}</TableCell>
            <TableCell className={NUMBER}>{row.average_rank.toFixed(2)}</TableCell>
            <TableCell className={NUMBER}>{row.average_points.toFixed(1)}</TableCell>
            <TableCell className={NUMBER}>{row.forfeits}</TableCell>
            <TableCell className={NUMBER} title={`${row.illegal_attempts} rejected answers over ${row.decisions} decisions`}>
              {formatPercent(row.illegal_rate)}
            </TableCell>
            <TableCell className={NUMBER}>{row.fallbacks}</TableCell>
            <TableCell className={NUMBER}>{formatSeconds(row.average_latency_seconds)}</TableCell>
            <TableCell className={NUMBER}>{(row.prompt_tokens + row.completion_tokens).toLocaleString()}</TableCell>
            <TableCell className={NUMBER}>{formatCost(row.cost_per_match)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
