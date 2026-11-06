// The table pieces around the map: the round tiles picked for the match, the town-tile bonuses
// and the shared power actions. The cult tracks have their own tab.
import { Check, Zap } from "lucide-react";

import { bonusText } from "@/games/terra-mystica/format";
import {
  CULT_META,
  POWER_ACTIONS,
  SCORING_META,
  TOWN_TILES,
  UNKNOWN_SCORING,
} from "@/games/terra-mystica/meta";
import type { TerraMysticaObservation } from "@/games/terra-mystica/observation";
import { cn } from "@/lib/utils";

// Bowl III pays directly; otherwise two Bowl II tokens burn into one Bowl III token.
function canAffordPower(power: [number, number, number], cost: number): boolean {
  const [, bowl2, bowl3] = power;
  if (bowl3 >= cost) return true;
  return bowl2 >= 2 * (cost - bowl3);
}

/** The six round tiles, in round order: scoring action, points and end-of-round cult bonus. */
export function TerraMysticaRoundTiles({ observation }: { observation: TerraMysticaObservation }) {
  const current = observation.game_over ? null : observation.round;
  return (
    <section
      aria-label="Round tiles"
      className="flex min-w-0 flex-col gap-1.5 rounded-lg border bg-card px-2 py-2"
      title="Picked for this match. Each scores its action and pays its cult bonus at the end of the round; the last bonus is not paid."
    >
      <header className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <h3 className="text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">Round tiles</h3>
        <p className="text-[10px] text-muted-foreground @4xl:hidden">
          Picked for this match. Each scores its action and pays its cult bonus at the end of the round; the last bonus is not paid.
        </p>
      </header>
      <ol className="grid grid-cols-2 gap-1.5 @4xl:flex @4xl:flex-1 @4xl:flex-col-reverse @4xl:justify-between">
        {observation.scoring.map((action, index) => {
          const round = index + 1;
          const meta = SCORING_META[action] ?? UNKNOWN_SCORING;
          const bonus = observation.scoring_bonuses[index];
          const cult = bonus ? CULT_META[bonus.cult] : null;
          const isCurrent = current === round;
          const isPast = current !== null && round < current;
          return (
            <li
              key={`${round}-${action}`}
              className={cn(
                "flex min-w-0 flex-col gap-0.5 rounded-md border px-1.5 py-1",
                isCurrent && "border-primary bg-primary/5 ring-1 ring-primary",
                isPast && "opacity-55",
                observation.game_over && "opacity-75",
              )}
              title={`Round ${round}: ${meta.label} scores ${meta.points} VP${bonus ? `; ${bonusText(bonus)}` : ""}`}
            >
              <div className="flex items-center gap-1">
                <span className="text-[9px] font-semibold text-muted-foreground tabular-nums">R{round}</span>
                {isCurrent ? (
                  <span className="text-[9px] font-medium text-primary">now</span>
                ) : isPast ? (
                  <Check className="size-3 text-emerald-600 dark:text-emerald-400" aria-label="played" />
                ) : null}
                <span className="ml-auto text-[10px] font-normal text-muted-foreground tabular-nums">{meta.points} VP</span>
              </div>
              <div className="flex min-w-0 items-center gap-1 text-xs font-medium">
                <meta.icon className="size-3.5 shrink-0" aria-hidden="true" />
                <span className="truncate">{meta.label}</span>
              </div>
              {bonus && cult ? (
                <div className="flex min-w-0 items-center gap-1 text-[10px] text-muted-foreground">
                  <cult.icon className="size-3 shrink-0" style={{ color: cult.color }} aria-hidden="true" />
                  <span className="truncate">{bonusText(bonus)}</span>
                </div>
              ) : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

/** The five town tiles and how many copies are still available. */
export function TerraMysticaTownTiles({ observation }: { observation: TerraMysticaObservation }) {
  if (!observation.town_tiles.length) return null;
  return (
    <section aria-label="Town tiles" className="flex shrink-0 flex-col gap-1.5 rounded-lg border bg-card px-2.5 py-2">
      <header className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-0.5">
        <h3 className="text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">Town tiles</h3>
        <p className="text-[10px] text-muted-foreground">picked when a town is founded</p>
      </header>
      <ul className="grid grid-cols-2 gap-1 @lg:grid-cols-3 @3xl:grid-cols-5">
        {TOWN_TILES.map((tile) => {
          const left = observation.town_tiles[tile.index] ?? 0;
          return (
            <li
              key={tile.index}
              className={cn("flex min-w-0 flex-col gap-0.5 rounded-md border px-1.5 py-1 text-xs", left === 0 && "opacity-45")}
              title={`${tile.victory_points} VP and ${tile.reward}${left === 0 ? " (all taken)" : `; ${left} left`}`}
            >
              <div className="flex min-w-0 items-center gap-1">
                <tile.icon className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
                <span className="min-w-0 flex-1 truncate font-medium">{tile.victory_points} VP</span>
                <span className="shrink-0 text-[10px] text-muted-foreground tabular-nums">{left === 0 ? "taken" : `×${left}`}</span>
              </div>
              <span className="truncate text-[10px] text-muted-foreground">+ {tile.reward}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** The five shared power actions, with their costs and whether this round already used them. */
export function TerraMysticaPowerActions({ observation }: { observation: TerraMysticaObservation }) {
  const used = new Set(observation.used_power_actions);
  const active = observation.game_over
    ? undefined
    : observation.players.find((player) => player.seat === observation.active);
  const charged = active?.power[2] ?? 0;
  return (
    <section aria-label="Power actions" className="flex shrink-0 flex-col gap-1.5 rounded-lg border bg-card px-2.5 py-2">
      <header className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-0.5">
        <h3 className="flex items-center gap-1 text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
          <Zap className="size-3" aria-hidden="true" /> Power actions
        </h3>
        <p className="text-[10px] text-muted-foreground">once per round</p>
      </header>
      <ul className="grid grid-cols-2 gap-1 @lg:grid-cols-3 @3xl:grid-cols-5">
        {POWER_ACTIONS.map((action) => {
          const isUsed = used.has(action.kind);
          const affordable = active ? canAffordPower(active.power, action.cost) : false;
          const available = !isUsed && active !== undefined && affordable;
          return (
            <li
              key={action.kind}
              className={cn(
                "flex min-w-0 flex-col gap-0.5 rounded-md border px-1.5 py-1 text-xs",
                isUsed && "bg-muted/50 opacity-60",
                !isUsed && active !== undefined && !affordable && "opacity-45",
                available && "border-primary/40 bg-primary/5",
              )}
              title={`${action.label}: spend ${action.cost} power for ${action.reward}${isUsed ? " (used this round)" : ""}`}
            >
              <div className="flex min-w-0 items-center gap-1">
                <action.icon className="size-3.5 shrink-0" aria-hidden="true" />
                <span className={cn("min-w-0 flex-1 truncate font-medium", isUsed && "line-through")}>{action.label}</span>
                {isUsed ? <Check className="size-3.5 shrink-0 text-emerald-600 dark:text-emerald-400" aria-label="used this round" /> : null}
              </div>
              <div className="flex min-w-0 items-center gap-0.5 text-[10px] text-muted-foreground">
                <Zap className="size-2.5 shrink-0" aria-hidden="true" />
                <span className="shrink-0 tabular-nums">{action.cost}</span>
                <span className="truncate">→ {action.reward}</span>
              </div>
            </li>
          );
        })}
      </ul>
      <p className="text-[10px] leading-snug text-muted-foreground">
        {active
          ? `${active.name} has ${charged} power in Bowl III; Bowl II tokens can be burned to pay. Any player may use each action once per round.`
          : "The game is over."}
      </p>
    </section>
  );
}
