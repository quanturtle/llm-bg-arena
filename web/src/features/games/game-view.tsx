"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { ErrorAlert, LoadingRows, PageTitle } from "@/components/page";
import { ProviderLogo } from "@/components/provider-logo";
import { agentHref } from "@/components/seat";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ConfigList } from "@/features/games/games-view";
import { RulesMarkdown } from "@/features/games/rules-markdown";
import { listMatches, MatchTable } from "@/features/matches/match-table";
import { playerRange } from "@/features/new-match/form-model";
import { useNow } from "@/hooks/use-now";
import { api, type Leaderboard } from "@/lib/api";
import { formatPercent } from "@/lib/format";

// the game page lists this many of its most recent matches
const RECENT_MATCHES = 50;

function Standings({ board }: { board: Leaderboard }) {
  if (!board.rows.length) return <p className="text-sm text-muted-foreground">No finished matches yet.</p>;
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-8">#</TableHead>
          <TableHead>Agent</TableHead>
          <TableHead className="text-right">Elo</TableHead>
          <TableHead className="text-right">Matches</TableHead>
          <TableHead className="text-right">Win rate</TableHead>
          <TableHead className="text-right">Avg rank</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {board.rows.map((row, index) => (
          <TableRow key={row.agent}>
            <TableCell className="text-muted-foreground tabular-nums">{index + 1}</TableCell>
            <TableCell className="max-w-56">
              <span className="flex min-w-0 items-center gap-2">
                <ProviderLogo model={row.models[0] ?? row.agent} />
                <Link href={agentHref(row.agent)} className="truncate hover:underline">
                  {row.agent}
                </Link>
              </span>
            </TableCell>
            <TableCell className="text-right font-semibold tabular-nums">{row.elo === null ? "" : Math.round(row.elo)}</TableCell>
            <TableCell className="text-right tabular-nums">{row.matches}</TableCell>
            <TableCell className="text-right tabular-nums">{formatPercent(row.win_rate)}</TableCell>
            <TableCell className="text-right tabular-nums">{row.average_rank.toFixed(2)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export function GameView() {
  const id = useSearchParams().get("id") ?? "";
  const game = useQuery({ queryKey: ["game", id], queryFn: () => api.game(id), enabled: Boolean(id) });
  const board = useQuery({ queryKey: ["leaderboard", { game: id, prompt: "" }], queryFn: () => api.leaderboard({ game: id }), enabled: Boolean(id) });
  const catalog = useQuery({ queryKey: ["matches", { game: id, agent: "" }], queryFn: () => api.matches({ game: id }), enabled: Boolean(id) });
  const recent = listMatches((catalog.data?.matches ?? []).slice(0, RECENT_MATCHES), []);
  const now = useNow(recent.some((match) => match.status === "running"));
  if (!id) return <ErrorAlert error="No game named in the address." />;
  return (
    <>
      <PageTitle title={id}>
        <Button asChild variant="outline" size="sm">
          <Link href={`/leaderboard?game=${encodeURIComponent(id)}`}>Full leaderboard</Link>
        </Button>
      </PageTitle>
      {game.error ? <ErrorAlert error={game.error} /> : null}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(320px,2fr)]">
        <Card>
          <CardContent>{game.data ? <RulesMarkdown text={game.data.rules} /> : <LoadingRows />}</CardContent>
        </Card>
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Default config</CardTitle>
              {game.data ? (
                <CardDescription>{playerRange(game.data.player_counts)}</CardDescription>
              ) : null}
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              {game.data ? <ConfigList config={game.data.default_config} /> : null}
              <p className="text-xs text-muted-foreground">
                Change it for one match on the{" "}
                <Link href="/new" className="underline">
                  New match
                </Link>{" "}
                page.
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Standings</CardTitle>
            </CardHeader>
            <CardContent className="px-2">{board.data ? <Standings board={board.data} /> : <LoadingRows rows={3} />}</CardContent>
          </Card>
        </div>
      </div>
      <Card className="mt-6 pb-0">
        <CardHeader>
          <CardTitle>Matches ({catalog.data?.matches.length ?? 0})</CardTitle>
        </CardHeader>
        <CardContent className="px-2">
          {recent.length ? <MatchTable matches={recent} now={now} /> : <p className="p-4 text-sm text-muted-foreground">None yet.</p>}
        </CardContent>
      </Card>
    </>
  );
}
