"use client";

import { useQuery } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { ErrorAlert, LoadingRows, PageTitle } from "@/components/page";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { DeleteMatchButton } from "@/features/matches/delete-match-button";
import { listMatches, MatchTable } from "@/features/matches/match-table";
import { useNow } from "@/hooks/use-now";
import { api } from "@/lib/api";

const ALL_GAMES = "all";
// the list refreshes this often while a match runs
const RUNNING_REFRESH_MS = 3000;

function useFilters() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const game = params.get("game") ?? "";
  const agent = params.get("agent") ?? "";
  const setFilters = (next: { game: string; agent: string }) => {
    const query = new URLSearchParams();
    if (next.game) query.set("game", next.game);
    if (next.agent) query.set("agent", next.agent);
    const text = query.toString();
    router.replace(text ? `${pathname}?${text}` : pathname);
  };
  return { game, agent, setFilters };
}

function AgentFilter({ agent, onChange }: { agent: string; onChange: (agent: string) => void }) {
  const [draft, setDraft] = useState(agent);
  return (
    <Input
      className="w-56"
      placeholder="Filter by agent"
      value={draft}
      onChange={(event) => setDraft(event.target.value)}
      onBlur={() => onChange(draft.trim())}
      onKeyDown={(event) => {
        if (event.key === "Enter") onChange(draft.trim());
      }}
    />
  );
}

export function MatchesView() {
  const { game, agent, setFilters } = useFilters();
  const games = useQuery({ queryKey: ["games"], queryFn: api.games });
  const launches = useQuery({ queryKey: ["launches"], queryFn: api.launches, refetchInterval: RUNNING_REFRESH_MS });
  const catalog = useQuery({
    queryKey: ["matches", { game, agent }],
    queryFn: () => api.matches({ game, agent }),
    refetchInterval: (query) =>
      query.state.data?.matches.some((match) => match.status === "running") ? RUNNING_REFRESH_MS : false,
  });
  const matches = listMatches(catalog.data?.matches ?? [], launches.data ?? []);
  const playing = new Set(
    (launches.data ?? []).filter((launch) => ["running", "paused"].includes(launch.status)).map((launch) => launch.match_id),
  );
  const now = useNow(matches.some((match) => match.status === "running"));
  return (
    <>
      <PageTitle title="Matches" description={catalog.data ? `${catalog.data.matches.length} matches` : "Every match in the log directory."}>
        <Select value={game || ALL_GAMES} onValueChange={(value) => setFilters({ game: value === ALL_GAMES ? "" : value, agent })}>
          <SelectTrigger className="w-48">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_GAMES}>All games</SelectItem>
            {(games.data ?? []).map((option) => (
              <SelectItem key={option.id} value={option.id}>
                {option.id} ({option.matches})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <AgentFilter key={agent} agent={agent} onChange={(value) => setFilters({ game, agent: value })} />
      </PageTitle>
      {catalog.error ? <ErrorAlert error={catalog.error} /> : null}
      {catalog.data?.unreadable.length ? (
        <ErrorAlert
          title={`${catalog.data.unreadable.length} log file(s) could not be read`}
          error={catalog.data.unreadable.map((log) => log.path).join(", ")}
        />
      ) : null}
      <Card className="mt-4 py-0">
        <CardContent className="px-2">
          {catalog.isPending ? (
            <div className="p-4">
              <LoadingRows />
            </div>
          ) : matches.length ? (
            <MatchTable
              matches={matches}
              now={now}
              actions={(match) => (playing.has(match.match_id) ? null : <DeleteMatchButton matchId={match.match_id} />)}
            />
          ) : (
            <p className="p-6 text-sm text-muted-foreground">
              No matches yet. Start one from New match, or play one with <code>arena play</code>.
            </p>
          )}
        </CardContent>
      </Card>
    </>
  );
}
