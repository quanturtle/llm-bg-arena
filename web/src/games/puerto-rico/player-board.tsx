// One Puerto Rico player per row, every row the same height: goods, a 12-space island and a
// 12-space city drawn as fixed grids, so a new plantation or building fills a slot, never a row.
import { Building, Sprout, Users } from "lucide-react";

import { BorderPill, BorderPills, Stat } from "@/components/board-parts";
import { SeatChip } from "@/components/seat";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { buildingArt, buildingLabel } from "@/games/puerto-rico/assets";
import type { BuildingSpec, PuertoRicoObservation, PuertoRicoPlayer } from "@/games/puerto-rico/observation";
import { Art, Coin, GoodCounts, IslandTile, Pips } from "@/games/puerto-rico/pieces";
import type { MatchSummary } from "@/lib/api";
import { cn } from "@/lib/utils";

// both boards have twelve spaces, four across
const ISLAND_SPACES = 12;
const CITY_SPACES = 12;

function Heading({ children }: { children: React.ReactNode }) {
  return <h5 className="mb-1.5 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">{children}</h5>;
}

function IslandGrid({ player }: { player: PuertoRicoPlayer }) {
  const tiles = [
    ...player.plantations.map((plantation, index) => <IslandTile key={`p${index}`} good={plantation.good} colonized={plantation.colonized} />),
    ...Array.from({ length: player.quarries }, (_, index) => <IslandTile key={`q${index}`} quarry colonized={index < player.occupied_quarries} />),
  ];
  while (tiles.length < ISLAND_SPACES) tiles.push(<IslandTile key={`e${tiles.length}`} />);
  return <div className="grid grid-cols-[repeat(4,3.25rem)] gap-1">{tiles.slice(0, ISLAND_SPACES)}</div>;
}

type Built = PuertoRicoPlayer["buildings"][number];

function BuildingCell({ building, spec }: { building: Built; spec: BuildingSpec | undefined }) {
  const label = buildingLabel(building.name);
  const wide = (spec?.city_spaces ?? 1) > 1;
  const detail = spec ? `${label}: ${spec.victory_points} VP, ${building.colonists}/${spec.max_colonists} colonists${building.active ? ", active" : ""}` : label;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          className={cn(
            "flex h-13 min-w-0 items-center gap-1.5 rounded-md border bg-card px-1.5",
            wide && "col-span-2",
            building.active && "border-emerald-500/50 bg-emerald-500/5",
          )}
        >
          <Art path={buildingArt(building.name, building.colonists)} alt={label} size={48} className="h-9 w-11 shrink-0" />
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <span className="truncate text-xs leading-none font-medium">{label}</span>
            <span className="flex items-center gap-1.5 text-[11px] leading-none text-muted-foreground">
              {spec ? <span className="tabular-nums">{spec.victory_points} VP</span> : null}
              <Pips filled={building.colonists} total={spec?.max_colonists ?? building.colonists} />
            </span>
          </div>
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
    <div className="grid grid-cols-4 gap-1">
      {ordered.map((building) => (
        <BuildingCell key={building.name} building={building} spec={specs.get(building.name)} />
      ))}
      {Array.from({ length: Math.max(0, CITY_SPACES - used) }, (_, index) => (
        <div key={index} className="h-13 rounded-md border border-dashed" />
      ))}
    </div>
  );
}

// During play the points leave out VP chips; at the end the breakdown takes the same line.
function ScoreLine({ observation, seat }: { observation: PuertoRicoObservation; seat: number }) {
  const final = observation.final_scores?.find((score) => score.player === seat);
  const text = final
    ? Object.entries(final.breakdown)
        .map(([source, value]) => `${value} ${source.replace(/_/g, " ")}`)
        .join(" + ")
    : "VP chips hidden until the end";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <p className="mt-2 h-4 truncate text-xs text-muted-foreground">{text}</p>
      </TooltipTrigger>
      <TooltipContent>{text}</TooltipContent>
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
  const final = observation.final_scores?.find((score) => score.player === seat);
  return (
    <section aria-label={`Player ${seat + 1}`} className={cn("relative rounded-xl border bg-card p-3", isActive && "border-primary ring-1 ring-primary")}>
      <BorderPills>
        {observation.governor === seat ? <BorderPill tone="neutral">governor</BorderPill> : null}
        {isActive ? <BorderPill tone="active">to act</BorderPill> : null}
        {isWinner ? <BorderPill tone="win">winner</BorderPill> : null}
      </BorderPills>
      <header className="flex h-7 items-center gap-4 text-sm">
        <SeatChip seat={match.seats[seat]} className="min-w-0 flex-1" />
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="flex items-center gap-1.5 font-medium tabular-nums">
              <Coin value={player.doubloons} />
              {player.doubloons}
            </span>
          </TooltipTrigger>
          <TooltipContent>Doubloons</TooltipContent>
        </Tooltip>
        <Stat icon={Users} label="Colonists waiting to be placed" value={player.colonists_unplaced} />
        <Stat icon={Sprout} label="Island spaces used" value={`${player.island_spaces_used}/${ISLAND_SPACES}`} />
        <Stat icon={Building} label="City spaces used" value={`${player.city_spaces_used}/${CITY_SPACES}`} />
        <span className="w-16 text-right text-xl leading-none font-semibold tabular-nums" title={final ? "Final points" : "Points others can see"}>
          {final ? final.points : player.public_points}
          <span className="ml-1 text-xs font-normal text-muted-foreground">VP</span>
        </span>
      </header>
      <div className="mt-3 grid gap-4 @2xl:grid-cols-[auto_minmax(0,1fr)] @4xl:grid-cols-[11rem_auto_minmax(0,1fr)]">
        <div className="@2xl:col-span-2 @4xl:col-span-1">
          <Heading>Goods</Heading>
          <GoodCounts counts={player.goods} />
          <ScoreLine observation={observation} seat={seat} />
        </div>
        <div>
          <Heading>Island</Heading>
          <IslandGrid player={player} />
        </div>
        <div className="min-w-0">
          <Heading>City</Heading>
          <CityGrid player={player} specs={specs} />
        </div>
      </div>
    </section>
  );
}

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
    <div className="flex flex-col gap-5 pt-2.5">
      {observation.players.map((player) => (
        <PlayerBoard key={player.seat} player={player} observation={observation} match={match} specs={specs} />
      ))}
    </div>
  );
}
