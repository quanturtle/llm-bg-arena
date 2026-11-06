// The four cult tracks: every player's marker on spaces 10 down to 0 and the claimed priest orders.
import { KeyRound, Zap } from "lucide-react";

import { seatLabel } from "@/components/seat";
import { bonusText } from "@/games/terra-mystica/format";
import { CULTS, CULT_META, factionMeta, type Cult } from "@/games/terra-mystica/meta";
import type { TerraMysticaObservation, TerraMysticaPlayer } from "@/games/terra-mystica/observation";
import { cn } from "@/lib/utils";

const SPACES = Array.from({ length: 11 }, (_, space) => space);
const DESCENDING_SPACES = [...SPACES].reverse();
const ORDER_STEPS = [3, 2, 2, 2];
const POWER_THRESHOLDS: Record<number, number> = { 3: 1, 5: 2, 7: 2, 10: 3 };

function PlayerDot({ player, className }: { player: TerraMysticaPlayer; className?: string }) {
  const piece = factionMeta(player.faction);
  const label = `${seatLabel(player.seat)} ${player.name}`;
  return (
    <span
      role="img"
      aria-label={label}
      title={label}
      className={cn("block size-3.5 shrink-0 rounded-full border-2 shadow-sm", className)}
      style={{ background: piece.color, borderColor: piece.border }}
    />
  );
}

function CultTrack({ cult, observation }: { cult: Cult; observation: TerraMysticaObservation }) {
  const meta = CULT_META[cult];
  const claimed = observation.used_orders.filter((order) => order.cult === cult);
  const top = Math.max(...observation.players.map((player) => player.cults[cult]));
  const leaders = observation.players.filter((player) => player.cults[cult] === top);
  return (
    <section
      aria-label={`${meta.label} cult track`}
      className="flex min-w-0 flex-col gap-2 rounded-xl border bg-card p-3"
      style={{ borderColor: `color-mix(in oklab, ${meta.color} 35%, transparent)` }}
    >
      <header className="flex items-center gap-2">
        <meta.icon className="size-6 shrink-0" style={{ color: meta.color }} aria-hidden="true" />
        <div className="min-w-0">
          <h3 className="text-sm font-semibold" style={{ color: meta.color }}>
            {meta.label}
          </h3>
          <p className="truncate text-[10px] text-muted-foreground">
            {top > 0 ? `${leaders.map((player) => seatLabel(player.seat)).join(", ")} at ${top}` : "All markers on 0"}
          </p>
        </div>
      </header>
      <div className="flex flex-1 flex-col gap-0.5">
        {DESCENDING_SPACES.map((space) => {
          const here = observation.players.filter((player) => player.cults[cult] === space);
          const power = POWER_THRESHOLDS[space];
          return (
            <div
              key={space}
              className={cn(
                "flex min-h-5 flex-1 items-center gap-1 rounded-md border px-1",
                space === 10 ? "border-amber-500/50 bg-amber-500/10" : "bg-muted/30",
              )}
              title={space === 10 ? "Space 10: needs a key and grants 3 power" : `Space ${space}`}
            >
              <span className="w-4 shrink-0 text-right text-[10px] leading-none text-muted-foreground tabular-nums">{space}</span>
              <div className="flex min-w-0 flex-1 flex-wrap items-center justify-center gap-0.5">
                {here.map((player) => (
                  <PlayerDot key={player.seat} player={player} />
                ))}
              </div>
              {space === 10 ? (
                <KeyRound className="size-2.5 shrink-0 text-amber-600 dark:text-amber-400" aria-hidden="true" />
              ) : power ? (
                <span title={`Reaching space ${space} grants ${power} power`}>
                  <Zap className="size-2.5 shrink-0 text-muted-foreground/70" aria-hidden="true" />
                </span>
              ) : (
                <span className="size-2.5 shrink-0" />
              )}
            </div>
          );
        })}
      </div>
      <div className="flex flex-col gap-1">
        <span className="text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">Priests</span>
        <div className="grid grid-cols-4 gap-1">
          {ORDER_STEPS.map((steps, order) => {
            const orderPlayer = claimed.find((entry) => entry.order === order);
            const player = orderPlayer
              ? observation.players.find((candidate) => candidate.seat === orderPlayer.player)
              : undefined;
            return (
              <div
                key={order}
                className={cn(
                  "flex h-7 items-center justify-center gap-1 rounded-md border px-1 text-[10px]",
                  player ? "border-solid" : "border-dashed text-muted-foreground/60",
                )}
                style={
                  player
                    ? {
                        borderColor: `color-mix(in oklab, ${factionMeta(player.faction).color} 55%, transparent)`,
                        background: `color-mix(in oklab, ${factionMeta(player.faction).color} 12%, transparent)`,
                      }
                    : undefined
                }
                title={
                  player
                    ? `${seatLabel(player.seat)} ${player.name} claimed the +${steps} order space`
                    : `Open +${steps} order space`
                }
              >
                {player ? <PlayerDot player={player} className="hidden size-3 border @4xl:block" /> : null}
                <span className="tabular-nums">{player ? seatLabel(player.seat) : ""}</span>
                <span className="text-muted-foreground">+{steps}</span>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

/** The four religion tracks, with every player's cult marker and the priest order spaces. */
export function TerraMysticaCults({ observation }: { observation: TerraMysticaObservation }) {
  const bonus = observation.game_over ? undefined : observation.scoring_bonuses[observation.round - 1];
  const bonusCult = bonus ? CULT_META[bonus.cult] : undefined;
  return (
    <div className="@container flex flex-col gap-3 xl:h-full">
      <div className="flex flex-wrap items-center gap-2">
        {observation.players.map((player) => {
          const piece = factionMeta(player.faction);
          return (
            <span
              key={player.seat}
              className={cn(
                "flex items-center gap-1.5 rounded-md border bg-card px-2 py-1 text-xs",
                observation.active === player.seat && !observation.game_over && "border-primary ring-1 ring-primary",
              )}
            >
              <span className="size-2.5 shrink-0 rounded-full border" style={{ background: piece.color, borderColor: piece.border }} />
              <span className="font-medium">{seatLabel(player.seat)}</span>
              <span className="text-muted-foreground">{player.name}</span>
              {observation.passed.includes(player.seat) && !observation.game_over ? (
                <span className="text-[9px] tracking-wide text-muted-foreground uppercase">passed</span>
              ) : null}
            </span>
          );
        })}
      </div>
      {bonus && bonusCult ? (
        <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <bonusCult.icon className="size-3.5 shrink-0" style={{ color: bonusCult.color }} aria-hidden="true" />
          This round&apos;s cult bonus: <span className="text-foreground">{bonusText(bonus)}</span>, paid at cleanup.
        </p>
      ) : null}
      <div className="grid gap-3 @2xl:grid-cols-2 @3xl:grid-cols-4 xl:min-h-0 xl:flex-1 xl:overflow-y-auto">
        {CULTS.map((cult) => (
          <CultTrack key={cult} cult={cult} observation={observation} />
        ))}
      </div>
      <p className="flex items-start gap-1.5 text-[11px] text-muted-foreground">
        <KeyRound className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
        Spaces 3, 5, 7 and 10 grant 1, 2, 2 and 3 power. Space 10 needs a key. The four order spaces advance
        a priest&apos;s cult by 3, 2, 2 or 2.
      </p>
    </div>
  );
}
