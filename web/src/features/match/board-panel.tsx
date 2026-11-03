"use client";

import { CircleAlert } from "lucide-react";

import { SeatChip } from "@/components/seat";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { GAMES } from "@/games/registry";
import type { Frame, JsonObject, MatchSummary } from "@/lib/api";

const TEXT_TAB = "text";

function ScoreRow({ match, frame, isFinal }: { match: MatchSummary; frame: Frame; isFinal: boolean }) {
  return (
    <div aria-label="Scores" className="flex flex-wrap gap-x-6 gap-y-1 border-t px-4 pt-3 text-sm">
      {frame.scores.map((score) => (
        <span key={score.player} className="flex min-w-0 items-center gap-1.5">
          <SeatChip seat={match.seats[score.player]} className="max-w-64" />
          <strong className="tabular-nums">{score.points}</strong>
          {isFinal ? <span className="text-muted-foreground tabular-nums">#{score.rank}</span> : null}
        </span>
      ))}
    </div>
  );
}

/**
 * The board of the step on screen in tabs: the game's drawn views for the spectator, and the
 * text rendering for everyone. The chosen tab stays chosen as the steps change.
 */
export function BoardPanel({
  match,
  frame,
  viewer,
  layout,
  tab,
  onTab,
  isFinal,
}: {
  match: MatchSummary;
  frame: Frame;
  viewer: number | null;
  layout: JsonObject | null;
  tab: string;
  onTab: (tab: string) => void;
  isFinal: boolean;
}) {
  const view = frame.boards.find((board) => board.viewer === viewer) ?? frame.boards[0];
  const game = GAMES[match.game_id];
  // drawn boards show what a spectator sees; a seat's own view is its text rendering
  const drawn = game && viewer === null && view.observation ? game.draw(view.observation, { layout, frame, match }) : null;
  const tabs = drawn?.ok ? drawn.tabs : [];
  const shown = tab === TEXT_TAB || tabs.some((entry) => entry.id === tab) ? tab : (tabs[0]?.id ?? TEXT_TAB);
  return (
    <Card aria-label="Board" className="gap-3 pt-3 pb-3">
      <Tabs value={shown} onValueChange={onTab} className="gap-3">
        <TabsList className="mx-4">
          {tabs.map((entry) => (
            <TabsTrigger key={entry.id} value={entry.id}>
              {entry.label}
            </TabsTrigger>
          ))}
          <TabsTrigger value={TEXT_TAB}>Text</TabsTrigger>
        </TabsList>
        {drawn && !drawn.ok ? (
          <Alert variant="destructive" className="mx-4 w-auto">
            <CircleAlert />
            <AlertTitle>This step&apos;s board could not be drawn</AlertTitle>
            <AlertDescription className="font-mono text-xs whitespace-pre-wrap">{drawn.error}</AlertDescription>
          </Alert>
        ) : null}
        {tabs.map((entry) => (
          <TabsContent key={entry.id} value={entry.id} className="px-4">
            {entry.node}
          </TabsContent>
        ))}
        <TabsContent value={TEXT_TAB} className="px-4">
          <pre className="overflow-x-auto font-mono text-xs leading-relaxed">{view.text}</pre>
        </TabsContent>
      </Tabs>
      <ScoreRow match={match} frame={frame} isFinal={isFinal} />
    </Card>
  );
}
