// The building market and the score table, each in a tab of its own beside the board.
import { SeatChip } from "@/components/seat";
import { WinnerBadge } from "@/components/status";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { buildingArt, buildingLabel, GOOD_META } from "@/games/puerto-rico/assets";
import type { BuildingSpec, PuertoRicoObservation } from "@/games/puerto-rico/observation";
import { Art } from "@/games/puerto-rico/pieces";
import type { MatchSummary } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Every building, cheapest first, with the copies still for sale; sold-out ones are dimmed. */
export function BuildingMarket({ observation, specs }: { observation: PuertoRicoObservation; specs: Map<string, BuildingSpec> }) {
  const left = new Map<string, number>();
  for (const name of observation.available_buildings) left.set(name, (left.get(name) ?? 0) + 1);
  const ordered = [...specs.values()].sort((a, b) => a.cost - b.cost || a.name.localeCompare(b.name));
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-6">
      {ordered.map((spec) => {
        const copies = left.get(spec.name) ?? 0;
        const label = buildingLabel(spec.name);
        return (
          <div key={spec.name} className={cn("flex flex-col gap-1.5 rounded-lg border bg-card p-2", copies === 0 && "opacity-40")}>
            <div className="flex h-16 items-center justify-center rounded-md bg-muted/50">
              <Art path={buildingArt(spec.name, 0)} alt={label} size={96} className="h-14 w-auto" />
            </div>
            <div className="flex items-center gap-1 text-xs">
              <span className="truncate font-semibold">{label}</span>
              <span className="ml-auto shrink-0 text-muted-foreground tabular-nums">{spec.victory_points} VP</span>
            </div>
            <div className="grid grid-cols-2 gap-x-2 text-[11px] text-muted-foreground tabular-nums">
              <span>cost {spec.cost}</span>
              <span>left {copies}</span>
              <span>colonists {spec.max_colonists}</span>
              <span className="truncate">{spec.production ? `makes ${GOOD_META[spec.production].label.toLowerCase()}` : spec.city_spaces > 1 ? "two spaces" : ""}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** Points per player: public points during play, the full breakdown once the game ends. */
export function ScoreTable({ observation, match }: { observation: PuertoRicoObservation; match: MatchSummary }) {
  const finals = observation.final_scores;
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Player</TableHead>
          <TableHead className="text-right">Points</TableHead>
          <TableHead className="text-right">VP chips</TableHead>
          <TableHead className="text-right">Buildings</TableHead>
          <TableHead className="text-right">Bonus</TableHead>
          <TableHead className="text-right">Doubloons</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {observation.players.map((player) => {
          const final = finals?.find((score) => score.player === player.seat);
          const hidden = <span className="text-muted-foreground">hidden</span>;
          return (
            <TableRow key={player.seat}>
              <TableCell>
                <span className="flex items-center gap-2">
                  <SeatChip seat={match.seats[player.seat]} className="max-w-72" />
                  {observation.game_over && observation.winner === player.seat ? <WinnerBadge /> : null}
                </span>
              </TableCell>
              <TableCell className="text-right font-semibold tabular-nums">{final ? final.points : player.public_points}</TableCell>
              <TableCell className="text-right tabular-nums">{final ? final.vp_chips : hidden}</TableCell>
              <TableCell className="text-right tabular-nums">{final ? (final.breakdown.buildings ?? 0) : player.public_points}</TableCell>
              <TableCell className="text-right tabular-nums">{final ? (final.breakdown.bonus ?? 0) : hidden}</TableCell>
              <TableCell className="text-right tabular-nums">{player.doubloons}</TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
