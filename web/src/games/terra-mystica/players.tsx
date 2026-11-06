// One compact card per Terra Mystica player: points, faction, resources, power, cults and keys.
import { Castle, Church, Coins, KeyRound, Ship, Shovel, Users, Zap } from "lucide-react";

import { BorderPill, BorderPills, Stat } from "@/components/board-parts";
import { SeatChip } from "@/components/seat";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { CULTS, CULT_META, TERRAIN_META, factionMeta, type Cult } from "@/games/terra-mystica/meta";
import type { TerraMysticaObservation, TerraMysticaPlayer } from "@/games/terra-mystica/observation";
import type { MatchSummary } from "@/lib/api";
import { cn } from "@/lib/utils";

// A player's final points once the game ends, otherwise their current total; both are public.
function Points({ observation, player }: { observation: TerraMysticaObservation; player: TerraMysticaPlayer }) {
  const final = observation.final_scores?.find((score) => score.player === player.seat);
  const value = final?.points ?? player.victory_points;
  const detail = final
    ? Object.entries(final.breakdown)
        .map(([source, points]) => `${points} ${source.replace(/_/g, " ")}`)
        .join(" + ")
    : "Victory points so far. The final score adds cult, area and resource points.";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="shrink-0 text-lg leading-none font-semibold tabular-nums">
          {value}
          <span className="ml-1 text-xs font-normal text-muted-foreground">VP</span>
        </span>
      </TooltipTrigger>
      <TooltipContent>{detail}</TooltipContent>
    </Tooltip>
  );
}

function CultRow({ player }: { player: TerraMysticaPlayer }) {
  return (
    <div className="grid grid-cols-4 gap-1" aria-label="Cult tracks">
      {CULTS.map((cult: Cult) => {
        const meta = CULT_META[cult];
        return (
          <Tooltip key={cult}>
            <TooltipTrigger asChild>
              <span
                className="flex items-center gap-1 rounded-md border px-1 py-0.5 text-[11px]"
                style={{ borderColor: `color-mix(in oklab, ${meta.color} 45%, transparent)` }}
              >
                <meta.icon className="size-3.5 shrink-0" style={{ color: meta.color }} aria-label={meta.label} />
                <span className="font-medium tabular-nums">{player.cults[cult]}</span>
              </span>
            </TooltipTrigger>
            <TooltipContent>{`${meta.label} cult: space ${player.cults[cult]}`}</TooltipContent>
          </Tooltip>
        );
      })}
    </div>
  );
}

function TaskPill({ children }: { children: React.ReactNode }) {
  return <span className="flex h-5 items-center gap-1 rounded-md border px-1.5 text-[11px] text-muted-foreground">{children}</span>;
}

function PlayerCard({
  observation,
  match,
  player,
  best,
}: {
  observation: TerraMysticaObservation;
  match: MatchSummary;
  player: TerraMysticaPlayer;
  best: number | null;
}) {
  const seat = player.seat;
  const isActive = observation.active === seat && !observation.game_over;
  const passed = observation.passed.includes(seat) && !observation.game_over;
  const final = observation.final_scores?.find((score) => score.player === seat);
  const isWinner = observation.game_over && best !== null && final?.points === best;
  const terrain = TERRAIN_META[player.home_terrain];
  const faction = factionMeta(player.faction);
  const buildingCount = player.buildings.length;
  const towns = player.buildings.filter((building) => building.in_town).length;
  return (
    <section
      aria-label={`Player ${seat + 1}`}
      className={cn("relative flex min-w-0 flex-col gap-2 rounded-xl border bg-card p-2.5", isActive && "border-primary ring-1 ring-primary")}
    >
      <BorderPills>
        {isActive ? <BorderPill tone="active">to act</BorderPill> : null}
        {passed ? <BorderPill tone="neutral">passed</BorderPill> : null}
        {isWinner ? <BorderPill tone="win">winner</BorderPill> : null}
      </BorderPills>
      <header className="flex h-6 items-center gap-2 text-sm">
        <SeatChip seat={match.seats[seat]} className="min-w-0 flex-1" />
        <Points observation={observation} player={player} />
      </header>
      <div className="flex min-w-0 items-center gap-2 text-xs">
        <span className="flex shrink-0 items-center gap-1.5 rounded-md border bg-muted/40 px-1.5 py-0.5 font-medium">
          <span
            className="size-2.5 shrink-0 rounded-sm border"
            style={{ background: faction.color, borderColor: faction.border }}
            title={`${player.name || player.faction} piece colour`}
          />
          {player.name || player.faction}
        </span>
        <span className="flex min-w-0 items-center gap-1 text-muted-foreground">
          <span className="size-2.5 shrink-0 rounded-sm border border-black/20" style={{ background: terrain.fill }} title={`${terrain.label} is this faction's home terrain`} />
          <span className="truncate">home {terrain.label.toLowerCase()}</span>
        </span>
      </div>
      <div className="grid grid-cols-3 gap-x-2 gap-y-1 text-xs">
        <Stat icon={Coins} label="Coins" value={player.coins} />
        <Stat icon={Users} label="Workers" value={player.workers} />
        <Stat icon={Church} label="Priests" value={player.priests} />
        <Stat icon={Zap} label="Power in bowls I / II / III" value={player.power.join(" / ")} />
        <Stat icon={Ship} label="Shipping track" value={player.shipping} />
        <Stat icon={Shovel} label="Digging track" value={player.digging} />
      </div>
      <CultRow player={player} />
      <div className="flex flex-wrap items-center gap-1.5">
        <TaskPill>
          <KeyRound className="size-3" aria-hidden="true" />
          {player.keys} {player.keys === 1 ? "key" : "keys"}
        </TaskPill>
        <TaskPill>
          <Castle className="size-3" aria-hidden="true" />
          {buildingCount} {buildingCount === 1 ? "building" : "buildings"}
        </TaskPill>
        {towns > 0 ? <TaskPill>{towns} in towns</TaskPill> : null}
      </div>
    </section>
  );
}

export function TerraMysticaPlayers({
  observation,
  match,
}: {
  observation: TerraMysticaObservation;
  match: MatchSummary;
}) {
  const best = observation.final_scores?.length
    ? Math.max(...observation.final_scores.map((score) => score.points))
    : null;
  return (
    <div className="grid content-start gap-3 pt-2.5 @lg:grid-cols-2 @3xl:grid-cols-1 xl:min-h-0 xl:overflow-y-auto">
      {observation.players.map((player) => (
        <PlayerCard key={player.seat} observation={observation} match={match} player={player} best={best} />
      ))}
    </div>
  );
}
