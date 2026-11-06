// The table pieces around the map: the round tiles picked for the match, the town-tile bonuses
// and the shared power actions. The cult tracks have their own tab.
import { Check, Zap, type LucideIcon } from "lucide-react";

import { bonusReward, bonusText } from "@/games/terra-mystica/format";
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

// One half of a round tile. The sizes follow the window height, because the cards do.
function RoundTileHalf({ icon: Icon, color, title, detail }: { icon: LucideIcon; color?: string; title: string; detail: string }) {
  return (
    <div className="flex min-w-0 flex-col items-center justify-center gap-0.5 px-0.5 py-1 text-center">
      <Icon className="size-[clamp(0.875rem,1.8dvh,2rem)] shrink-0" style={{ color }} aria-hidden="true" />
      <span className="text-[clamp(0.6875rem,1.05dvh,0.8125rem)] leading-tight font-medium">{title}</span>
      <span className="text-[clamp(0.625rem,0.95dvh,0.75rem)] leading-tight text-muted-foreground tabular-nums">{detail}</span>
    </div>
  );
}

/** The six round tiles, in round order: the scoring action and its points, then the cult bonus. */
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
      <ol className="grid grid-cols-2 gap-1.5 @4xl:flex @4xl:flex-1 @4xl:flex-col-reverse">
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
                "relative grid min-w-0 rounded-md border @4xl:flex-1",
                isCurrent && "border-primary bg-primary/5 ring-1 ring-primary",
                isPast && "opacity-55",
                observation.game_over && "opacity-75",
              )}
              title={`Round ${round}: ${meta.label} scores ${meta.points} VP${bonus ? `; ${bonusText(bonus)}` : ""}`}
            >
              <span className="absolute top-0.5 left-1 text-[clamp(0.5625rem,0.85dvh,0.75rem)] font-semibold text-muted-foreground tabular-nums">
                R{round}
              </span>
              <span className="absolute top-0.5 right-1 text-[clamp(0.5625rem,0.85dvh,0.75rem)]">
                {isCurrent ? (
                  <span className="font-medium text-primary">now</span>
                ) : isPast ? (
                  <Check className="size-3 text-emerald-600 dark:text-emerald-400" aria-label="played" />
                ) : null}
              </span>
              <div className="grid grid-cols-2 divide-x">
                <RoundTileHalf icon={meta.icon} title={meta.label} detail={`${meta.points} VP`} />
                {bonus && cult ? (
                  <RoundTileHalf icon={cult.icon} color={cult.color} title={bonusReward(bonus)} detail={`per ${bonus.per} ${bonus.cult}`} />
                ) : null}
              </div>
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
      <ul className="grid grid-cols-2 gap-1 @lg:grid-cols-3 @3xl:grid-cols-3 @5xl:grid-cols-6">
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
          ? `${active.name} has ${charged} power in Bowl III; Bowl II tokens can be burned to pay. Any player may use each action once per round. Engineers may pay 2 workers for a bridge.`
          : "The game is over."}
      </p>
    </section>
  );
}
