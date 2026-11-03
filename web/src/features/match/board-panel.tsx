"use client";

import { CircleAlert } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { GAMES } from "@/games/registry";
import type { Frame, JsonObject, MatchSummary } from "@/lib/api";
import { cn } from "@/lib/utils";

const POINTS_TAB = "points";
const TEXT_TAB = "text";
// on desktop each tab fills the panel and scrolls inside it when its content is taller
const TAB_BODY = "min-h-0 px-4 xl:overflow-y-auto";

/**
 * The board of the step on screen in tabs: the game's drawn views for the spectator, points over
 * time, and the text rendering. The chosen tab stays chosen as the steps change.
 */
export function BoardPanel({
  match,
  frame,
  viewer,
  layout,
  tab,
  onTab,
  points,
  className,
}: {
  match: MatchSummary;
  frame: Frame;
  viewer: number | null;
  layout: JsonObject | null;
  tab: string;
  onTab: (tab: string) => void;
  points: React.ReactNode;
  className?: string;
}) {
  const view = frame.boards.find((board) => board.viewer === viewer) ?? frame.boards[0];
  const game = GAMES[match.game_id];
  // drawn boards show what a spectator sees; a seat's own view is its text rendering
  const drawn = game && viewer === null && view.observation ? game.draw(view.observation, { layout, frame, match }) : null;
  const tabs = drawn?.ok ? drawn.tabs : [];
  // a game tab chosen earlier falls back to the first one when this view has no drawn tabs
  const ids = [...tabs.map((entry) => entry.id), POINTS_TAB, TEXT_TAB];
  const shown = ids.includes(tab) ? tab : (tabs[0]?.id ?? TEXT_TAB);
  return (
    <Card aria-label="Board" className={cn("gap-3 py-3", className)}>
      <Tabs value={shown} onValueChange={onTab} className="min-h-0 flex-1 gap-3">
        <TabsList className="mx-4">
          {tabs.map((entry) => (
            <TabsTrigger key={entry.id} value={entry.id}>
              {entry.label}
            </TabsTrigger>
          ))}
          <TabsTrigger value={POINTS_TAB}>Points</TabsTrigger>
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
          <TabsContent key={entry.id} value={entry.id} className={TAB_BODY}>
            {entry.node}
          </TabsContent>
        ))}
        <TabsContent value={POINTS_TAB} className={TAB_BODY}>
          {points}
        </TabsContent>
        <TabsContent value={TEXT_TAB} className={TAB_BODY}>
          <pre className="overflow-x-auto font-mono text-xs leading-relaxed">{view.text}</pre>
        </TabsContent>
      </Tabs>
    </Card>
  );
}
