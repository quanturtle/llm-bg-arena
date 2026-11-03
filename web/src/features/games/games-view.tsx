"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { ErrorAlert, LoadingRows, PageTitle } from "@/components/page";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";

export function ConfigList({ config }: { config: { [key: string]: unknown } }) {
  return (
    <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
      {Object.entries(config).map(([key, value]) => (
        <div key={key} className="contents">
          <dt className="text-muted-foreground">{key}</dt>
          <dd className="font-mono">{JSON.stringify(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

export function GamesView() {
  const games = useQuery({ queryKey: ["games"], queryFn: api.games });
  return (
    <>
      <PageTitle title="Games" description="Every game the arena can play, with its rules and standings." />
      {games.error ? <ErrorAlert error={games.error} /> : null}
      {games.isPending ? <LoadingRows rows={3} /> : null}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {(games.data ?? []).map((game) => (
          <Link key={game.id} href={`/game?id=${encodeURIComponent(game.id)}`} className="group">
            <Card className="h-full transition-colors group-hover:border-foreground/30">
              <CardHeader>
                <CardTitle>{game.id}</CardTitle>
                <CardDescription>
                  {game.matches} {game.matches === 1 ? "match" : "matches"}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ConfigList config={game.default_config} />
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </>
  );
}
