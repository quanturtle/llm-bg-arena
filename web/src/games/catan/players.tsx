// One card per Catan player, all the same height: points, hand, cards, knights and both awards.
import { Award, Hand, Layers, Route, Shield, Swords } from "lucide-react";

import { BorderPill, BorderPills, points, Stat } from "@/components/board-parts";
import { SeatChip } from "@/components/seat";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { CatanObservation } from "@/games/catan/observation";
import type { MatchSummary } from "@/lib/api";
import { cn } from "@/lib/utils";

const DEV_CARD_NAMES: Record<string, string> = {
  knight: "knight",
  road_building: "road building",
  year_of_plenty: "year of plenty",
  monopoly: "monopoly",
  victory_point: "victory point",
};

// Public points during play, which leave out hidden victory-point cards; final scores once the game ends.
function victoryPoints(observation: CatanObservation, player: number): number | undefined {
  if (observation.final_scores) return observation.final_scores.find((score) => score.player === player)?.points;
  return observation.public_points[player];
}

// A player's card count during play; the kinds once the game ends and reveals them.
function devCardLine(observation: CatanObservation, player: number): string {
  const count = observation.dev_counts[player] ?? 0;
  const revealed = observation.revealed_dev?.[player];
  if (!revealed) return count ? `${count} development card${count === 1 ? "" : "s"}, hidden` : "No development cards";
  const kinds = Object.entries(revealed)
    .filter(([, copies]) => copies > 0)
    .map(([kind, copies]) => `${DEV_CARD_NAMES[kind] ?? kind}${copies > 1 ? ` ×${copies}` : ""}`);
  return kinds.length ? `Revealed: ${kinds.join(", ")}` : "No development cards";
}

// The award's slot is always there; it lights up for its holder.
function AwardSlot({ held, icon: Icon, label }: { held: boolean; icon: typeof Award; label: string }) {
  return (
    <span
      className={cn(
        "flex h-6 items-center gap-1 rounded-md border px-1.5 text-xs whitespace-nowrap",
        held ? "border-amber-500/50 bg-amber-500/10 text-amber-700 dark:text-amber-400" : "border-dashed text-muted-foreground/50",
      )}
    >
      <Icon className="size-3.5" aria-hidden="true" />
      {label}
    </span>
  );
}

function PlayerCard({ observation, match, player }: { observation: CatanObservation; match: MatchSummary; player: number }) {
  const isActive = observation.active === player && !observation.game_over;
  const isWinner = observation.game_over && observation.winner === player;
  const devLine = devCardLine(observation, player);
  return (
    <section
      aria-label={`Player ${player + 1}`}
      className={cn("relative flex h-36 flex-col gap-2 rounded-xl border bg-card p-3", isActive && "border-primary ring-1 ring-primary")}
    >
      <BorderPills>
        {isWinner ? <BorderPill tone="win">winner</BorderPill> : null}
        {isActive ? <BorderPill tone="active">to act</BorderPill> : null}
      </BorderPills>
      <div className="flex items-center gap-2">
        <SeatChip seat={match.seats[player]} className="min-w-0 flex-1" />
        <span className="shrink-0 text-xl leading-none font-semibold tabular-nums" title="Victory points others can see; hidden victory-point cards count once the game ends.">
          {points(victoryPoints(observation, player))}
          <span className="ml-1 text-xs font-normal text-muted-foreground">VP</span>
        </span>
      </div>
      <div className="grid grid-cols-4 gap-2 text-sm">
        <Stat icon={Hand} label="Resource cards in hand" value={observation.hand_sizes[player]} />
        <Stat icon={Layers} label="Development cards in hand" value={observation.dev_counts[player]} />
        <Stat icon={Swords} label="Knights played" value={observation.knights[player]} />
        <Stat icon={Route} label="Longest road length" value={observation.longest_road_lengths[player]} />
      </div>
      <div className="flex gap-1.5">
        <AwardSlot held={observation.longest_road === player} icon={Award} label="Longest road" />
        <AwardSlot held={observation.largest_army === player} icon={Shield} label="Largest army" />
      </div>
      <Tooltip>
        <TooltipTrigger asChild>
          <p className="truncate text-xs text-muted-foreground">{devLine}</p>
        </TooltipTrigger>
        <TooltipContent>{devLine}</TooltipContent>
      </Tooltip>
    </section>
  );
}

export function CatanPlayers({ observation, match }: { observation: CatanObservation; match: MatchSummary }) {
  return (
    <div className="grid content-start gap-4 pt-2.5 @lg:grid-cols-2 @4xl:grid-cols-1">
      {observation.hand_sizes.map((_, player) => (
        <PlayerCard key={player} observation={observation} match={match} player={player} />
      ))}
    </div>
  );
}
