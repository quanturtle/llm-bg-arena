// How a game plugs into the match page: a schema for its spectator observation, the tabs that
// draw it, and an icon per event kind. A game without an entry shows its text rendering.
import type { LucideIcon } from "lucide-react";
import { z } from "zod";

import type { Frame, JsonObject, MatchSummary } from "@/lib/api";

export type BoardContext = { layout: JsonObject | null; frame: Frame; match: MatchSummary };

export type BoardTab<Observation> = {
  id: string;
  label: string;
  render: (observation: Observation, context: BoardContext) => React.ReactNode;
};

export type DrawnBoard = { ok: true; tabs: { id: string; label: string; node: React.ReactNode }[] } | { ok: false; error: string };

export type GameEntry = {
  eventIcons: Record<string, LucideIcon>;
  /** Whether its board reads the static geometry at /api/games/{id}/layout. */
  usesLayout: boolean;
  /** Parses the observation once and draws every tab, or says why the observation did not parse. */
  draw: (observation: unknown, context: BoardContext) => DrawnBoard;
};

export function defineGame<Observation>(definition: {
  schema: z.ZodType<Observation>;
  tabs: BoardTab<Observation>[];
  eventIcons: Record<string, LucideIcon>;
  usesLayout: boolean;
}): GameEntry {
  return {
    eventIcons: definition.eventIcons,
    usesLayout: definition.usesLayout,
    draw(observation, context) {
      const parsed = definition.schema.safeParse(observation);
      if (!parsed.success) return { ok: false, error: z.prettifyError(parsed.error) };
      return {
        ok: true,
        tabs: definition.tabs.map((tab) => ({ id: tab.id, label: tab.label, node: tab.render(parsed.data, context) })),
      };
    },
  };
}
