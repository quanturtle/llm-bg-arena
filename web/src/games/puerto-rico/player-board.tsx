// One compact column per Puerto Rico player, all the same height: points, stats, the five goods,
// and a 12-space island and city drawn as fixed 4x3 grids, so a new tile fills a slot, never a row.
import { Building, Sprout, Users } from "lucide-react";

import { BorderPill, BorderPills, Stat } from "@/components/board-parts";
import { SeatChip } from "@/components/seat";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { buildingArt, buildingLabel } from "@/games/puerto-rico/assets";
import type { BuildingSpec, PuertoRicoObservation, PuertoRicoPlayer } from "@/games/puerto-rico/observation";
import { Art, Coin, GoodRow, IslandTile, Pips } from "@/games/puerto-rico/pieces";
import type { MatchSummary } from "@/lib/api";
import { cn } from "@/lib/utils";

// both boards have twelve spaces, four across
const ISLAND_SPACES = 12;
const CITY_SPACES = 12;

function IslandGrid({ player }: { player: PuertoRicoPlayer }) {
  const tiles = [
    ...player.plantations.map((plantation, index) => <IslandTile key={`p${index}`} good={plantation.good} colonized={plantation.colonized} />),
    ...Array.from({ length: player.quarries }, (_, index) => <IslandTile key={`q${index}`} quarry colonized={index < player.occupied_quarries} />),
  ];
  while (tiles.length < ISLAND_SPACES) tiles.push(<IslandTile key={`e${tiles.length}`} />);
  return (
    <div aria-label="Island" className="grid w-fit grid-cols-[repeat(4,2rem)] gap-1">
      {tiles.slice(0, ISLAND_SPACES)}
    </div>
  );
}

type Built = PuertoRicoPlayer["buildings"][number];

// A building's art with its name on top and its colonists at the bottom; the tooltip has the rest.
function BuildingCell({ building, spec }: { building: Built; spec: BuildingSpec | undefined }) {
  const label = buildingLabel(building.name);
  const wide = (spec?.city_spaces ?? 1) > 1;
  const detail = spec
    ? `${label}: ${spec.victory_points} VP, ${building.colonists}/${spec.max_colonists} colonists${building.active ? ", active" : ""}`
    : label;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          className={cn(
            "relative h-8 min-w-0 overflow-hidden rounded-md border bg-muted/40",
            wide && "col-span-2",
            building.active && "border-emerald-500/70 ring-1 ring-emerald-500/40",
          )}
        >
          <Art path={buildingArt(building.name, building.colonists)} alt={label} size={64} className="size-full object-cover" />
          <span className="absolute inset-x-0 top-0 truncate bg-background/80 px-1 text-[9px] leading-tight font-semibold">{label}</span>
          <span className="absolute right-0.5 bottom-0.5 rounded-sm bg-background/80 px-0.5">
            <Pips filled={building.colonists} total={spec?.max_colonists ?? building.colonists} />
          </span>
        </div>
      </TooltipTrigger>
      <TooltipContent>{detail}</TooltipContent>
    </Tooltip>
  );
}

// Two-space buildings go first, two to a row, so the rest always fit the twelve spaces.
function CityGrid({ player, specs }: { player: PuertoRicoPlayer; specs: Map<string, BuildingSpec> }) {
  const spaces = (building: Built) => specs.get(building.name)?.city_spaces ?? 1;
  const ordered = [...player.buildings.filter((building) => spaces(building) > 1), ...player.buildings.filter((building) => spaces(building) === 1)];
  const used = ordered.reduce((total, building) => total + spaces(building), 0);
  return (
    <div aria-label="City" className="grid min-w-0 grid-cols-4 gap-1">
      {ordered.map((building) => (
        <BuildingCell key={building.name} building={building} spec={specs.get(building.name)} />
      ))}
      {Array.from({ length: Math.max(0, CITY_SPACES - used) }, (_, index) => (
        <div key={index} className="h-8 rounded-md border border-dashed" />
      ))}
    </div>
  );
}

// During play the points leave out VP chips; at the end they are the final score, with its breakdown.
function Points({ observation, player }: { observation: PuertoRicoObservation; player: PuertoRicoPlayer }) {
  const final = observation.final_scores?.find((score) => score.player === player.seat);
  const detail = final
    ? Object.entries(final.breakdown)
        .map(([source, value]) => `${value} ${source.replace(/_/g, " ")}`)
        .join(" + ")
    : "Points others can see; VP chips stay hidden until the end";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="shrink-0 text-lg leading-none font-semibold tabular-nums">
          {final ? final.points : player.public_points}
          <span className="ml-1 text-xs font-normal text-muted-foreground">VP</span>
        </span>
      </TooltipTrigger>
      <TooltipContent>{detail}</TooltipContent>
    </Tooltip>
  );
}

function PlayerBoard({
  player,
  observation,
  match,
  specs,
}: {
  player: PuertoRicoPlayer;
  observation: PuertoRicoObservation;
  match: MatchSummary;
  specs: Map<string, BuildingSpec>;
}) {
  const seat = player.seat;
  const isActive = observation.active === seat && !observation.game_over;
  const isWinner = observation.game_over && observation.winner === seat;
  return (
    <section
      aria-label={`Player ${seat + 1}`}
      className={cn("@container relative flex min-w-0 flex-col gap-2 rounded-xl border bg-card p-2.5", isActive && "border-primary ring-1 ring-primary")}
    >
      <BorderPills>
        {observation.governor === seat ? <BorderPill tone="neutral">governor</BorderPill> : null}
        {isActive ? <BorderPill tone="active">to act</BorderPill> : null}
        {isWinner ? <BorderPill tone="win">winner</BorderPill> : null}
      </BorderPills>
      <header className="flex h-6 items-center gap-2 text-sm">
        <SeatChip seat={match.seats[seat]} className="min-w-0 flex-1" />
        <Points observation={observation} player={player} />
      </header>
      {/* each value has a fixed width, so the row never shifts as numbers grow */}
      <div className="flex h-5 items-center gap-3 text-xs">
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="flex w-[6ch] shrink-0 items-center gap-1 font-medium tabular-nums">
              <Coin value={player.doubloons} />
              {player.doubloons}
            </span>
          </TooltipTrigger>
          <TooltipContent>Doubloons</TooltipContent>
        </Tooltip>
        <Stat icon={Users} label="Colonists waiting to be placed" value={player.colonists_unplaced} className="w-[6ch] shrink-0" />
        <Stat icon={Sprout} label="Island spaces used" value={`${player.island_spaces_used}/${ISLAND_SPACES}`} className="w-[9ch] shrink-0" />
        <Stat icon={Building} label="City spaces used" value={`${player.city_spaces_used}/${CITY_SPACES}`} className="w-[9ch] shrink-0" />
      </div>
      <GoodRow counts={player.goods} />
      {/* island beside the city in a wide column, above it in a narrow one */}
      <div className="grid gap-2 @md:grid-cols-[auto_minmax(0,1fr)]">
        <IslandGrid player={player} />
        <CityGrid player={player} specs={specs} />
      </div>
    </section>
  );
}

/** Players side by side; a narrow board wraps them onto more rows. */
export function PlayerBoards({
  observation,
  match,
  specs,
}: {
  observation: PuertoRicoObservation;
  match: MatchSummary;
  specs: Map<string, BuildingSpec>;
}) {
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(16rem,1fr))] gap-3 pt-2.5">
      {observation.players.map((player) => (
        <PlayerBoard key={player.seat} player={player} observation={observation} match={match} specs={specs} />
      ))}
    </div>
  );
}
