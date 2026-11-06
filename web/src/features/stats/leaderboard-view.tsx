"use client";

import { useQuery } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { ErrorAlert, LoadingRows, PageTitle } from "@/components/page";
import { Card, CardContent } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { promptText, StatsTable } from "@/features/stats/stats-table";
import { api } from "@/lib/api";

// Radix selects take no empty value, so "all" stands for no filter.
const ALL = "all";

const ELO_NOTE =
  "Elo starts at 1000 with K = 32. In every finished match each pair of seats plays one rated game, ahead or behind by final rank, and a seat's change is the average over its opponents.";
const NO_ELO_NOTE = "Across games there is no shared rating; rows are ordered by win rate, then average rank. Pick a game for Elo.";

export function LeaderboardView() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const game = params.get("game") ?? "";
  const prompt = params.get("prompt") ?? "";
  const setFilters = (next: { game: string; prompt: string }) => {
    const query = new URLSearchParams();
    if (next.game) query.set("game", next.game);
    if (next.prompt) query.set("prompt", next.prompt);
    const text = query.toString();
    router.replace(text ? `${pathname}?${text}` : pathname);
  };
  const games = useQuery({ queryKey: ["games"], queryFn: api.games });
  const board = useQuery({ queryKey: ["leaderboard", { game, prompt }], queryFn: () => api.leaderboard({ game, prompt }) });
  return (
    <>
      <PageTitle
        title="Leaderboard"
        description={
          board.data
            ? `${board.data.finished_matches} finished ${board.data.finished_matches === 1 ? "match" : "matches"}`
            : "How each model plays, from finished matches."
        }
      >
        <Select value={game || ALL} onValueChange={(value) => setFilters({ game: value === ALL ? "" : value, prompt })}>
          <SelectTrigger className="w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All games</SelectItem>
            {(games.data ?? []).map((option) => (
              <SelectItem key={option.id} value={option.id}>
                {option.id}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={prompt || ALL} onValueChange={(value) => setFilters({ game, prompt: value === ALL ? "" : value })}>
          <SelectTrigger className="w-48">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All prompts</SelectItem>
            {(board.data?.prompt_versions ?? []).map((version) => (
              <SelectItem key={version} value={String(version)}>
                {promptText(version)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </PageTitle>
      {board.error ? <ErrorAlert error={board.error} /> : null}
      <Card className="py-0">
        <CardContent className="px-2">
          {board.isPending ? (
            <div className="p-4">
              <LoadingRows />
            </div>
          ) : board.data?.rows.length ? (
            <StatsTable rows={board.data.rows} withElo={Boolean(game)} withGame={!game} />
          ) : (
            <p className="p-6 text-sm text-muted-foreground">No finished matches yet.</p>
          )}
        </CardContent>
      </Card>
      <p className="mt-3 max-w-4xl text-xs text-muted-foreground">
        {game ? ELO_NOTE : NO_ELO_NOTE} Wins count sole first places; illegal is the share of answers rejected before a legal action.
      </p>
    </>
  );
}
