"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { ErrorAlert, LoadingRows, PageTitle } from "@/components/page";
import { ProviderLogo } from "@/components/provider-logo";
import { agentHref } from "@/components/seat";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { listMatches, MatchTable } from "@/features/matches/match-table";
import { StatsTable } from "@/features/stats/stats-table";
import { useNow } from "@/hooks/use-now";
import { api, type AgentGameStats, type HeadToHead } from "@/lib/api";
import { formatCost, formatPercent, formatSeconds } from "@/lib/format";

// the agent page lists this many of its most recent matches
const RECENT_MATCHES = 50;

function SummaryCards({ row }: { row: AgentGameStats }) {
  const cards: [string, string | number][] = [
    ["Matches", row.matches],
    ["Win rate", formatPercent(row.win_rate)],
    ["Avg rank", row.average_rank.toFixed(2)],
    ["Illegal answers", formatPercent(row.illegal_rate)],
    ["Latency / decision", formatSeconds(row.average_latency_seconds)],
    ["Cost / match", formatCost(row.cost_per_match)],
    ["Total cost", formatCost(row.cost_usd)],
  ];
  return (
    <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-7">
      {cards.map(([label, value]) => (
        <Card key={label} className="gap-1 py-4">
          <CardContent className="px-4">
            <div className="text-xs text-muted-foreground">{label}</div>
            <div className="text-xl font-semibold tabular-nums">{value}</div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function OpponentsTable({ opponents }: { opponents: HeadToHead[] }) {
  if (!opponents.length) return <p className="p-4 text-sm text-muted-foreground">No opponents yet.</p>;
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Opponent</TableHead>
          <TableHead className="text-right">Matches</TableHead>
          <TableHead className="text-right">Ahead</TableHead>
          <TableHead className="text-right">Level</TableHead>
          <TableHead className="text-right">Behind</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {opponents.map((row) => (
          <TableRow key={row.opponent}>
            <TableCell>
              <span className="inline-flex items-center gap-2">
                <ProviderLogo model={row.opponent} />
                <Link href={agentHref(row.opponent)} className="hover:underline">
                  {row.opponent}
                </Link>
              </span>
            </TableCell>
            <TableCell className="text-right tabular-nums">{row.matches}</TableCell>
            <TableCell className="text-right tabular-nums">{row.ahead}</TableCell>
            <TableCell className="text-right tabular-nums">{row.level}</TableCell>
            <TableCell className="text-right tabular-nums">{row.behind}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card className="mb-6 gap-2 pb-0">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="px-2">{children}</CardContent>
    </Card>
  );
}

export function AgentView() {
  const name = useSearchParams().get("name") ?? "";
  const detail = useQuery({ queryKey: ["agent", name], queryFn: () => api.agent(name), enabled: Boolean(name) });
  const catalog = useQuery({ queryKey: ["matches", { agent: name }], queryFn: () => api.matches({ agent: name }), enabled: Boolean(name) });
  const recent = listMatches((catalog.data?.matches ?? []).slice(0, RECENT_MATCHES), []);
  const now = useNow(recent.some((match) => match.status === "running"));
  if (!name) return <ErrorAlert error="No agent named in the address." />;
  return (
    <>
      <PageTitle
        title={
          <span className="inline-flex items-center gap-3">
            <ProviderLogo model={detail.data?.overall?.models[0] ?? name} className="size-6" />
            {name}
          </span>
        }
      >
        {detail.data ? <Badge variant="secondary">{detail.data.kind}</Badge> : null}
      </PageTitle>
      {detail.error ? <ErrorAlert error={detail.error} /> : null}
      {detail.isPending ? <LoadingRows /> : null}
      {detail.data ? (
        <>
          {detail.data.overall ? <SummaryCards row={detail.data.overall} /> : null}
          <Section title="By game">
            <StatsTable rows={detail.data.games} withElo withGame />
          </Section>
          <Section title="By prompt version">
            <StatsTable rows={detail.data.prompts} withPrompt />
          </Section>
          <Section title="Head to head">
            <OpponentsTable opponents={detail.data.opponents} />
          </Section>
          <Section title="Matches">
            <MatchTable matches={recent} now={now} />
          </Section>
        </>
      ) : null}
    </>
  );
}
