// The common table: status line, role cards, supply, goods bank, trading house, ships and
// face-up plantations. Every slot count is fixed for the match, so the table keeps its size.
import { Trophy } from "lucide-react";

import { StatusBar } from "@/components/board-parts";
import { SeatChip, SeatDot, seatLabel } from "@/components/seat";
import { GOOD_META, ROLE_META, TRADING_HOUSE_CARD } from "@/games/puerto-rico/assets";
import type { PuertoRicoObservation } from "@/games/puerto-rico/observation";
import { Art, Coin, GoodCounts, IslandTile, Pips } from "@/games/puerto-rico/pieces";
import type { MatchSummary } from "@/lib/api";
import { cn } from "@/lib/utils";

// the trading house holds at most four goods
const TRADING_HOUSE_SPACES = 4;

export function PuertoRicoStatus({ observation, match }: { observation: PuertoRicoObservation; match: MatchSummary }) {
  if (observation.game_over) {
    const winner = observation.winner === null ? null : match.seats[observation.winner];
    return (
      <StatusBar tone="done">
        <Trophy className="size-4 shrink-0" />
        {winner ? (
          <>
            Game over: <SeatChip seat={winner} link={false} className="min-w-0" /> won
          </>
        ) : (
          "Game over"
        )}
        {observation.end_reason ? <span className="truncate font-normal">({observation.end_reason})</span> : null}
      </StatusBar>
    );
  }
  const active = observation.active === null ? null : match.seats[observation.active];
  return (
    <StatusBar
      aside={
        <span className="text-xs text-muted-foreground" title="Player order this round, governor first">
          order {observation.order.map(seatLabel).join(" → ")}
        </span>
      }
    >
      <span className="font-semibold tabular-nums">Round {observation.round}</span>
      <span className="text-muted-foreground">·</span>
      <span className="truncate text-muted-foreground">{observation.phase.replace(/_/g, " ")}</span>
      {active ? (
        <>
          <span className="text-muted-foreground">·</span>
          <SeatChip seat={active} link={false} className="min-w-0" />
          <span className="shrink-0 text-muted-foreground">{observation.active_role ? `in ${observation.active_role}` : "chooses a role"}</span>
        </>
      ) : null}
    </StatusBar>
  );
}

/** Every role card in one row of equal columns; the doubloons and the taker keep their own lines. */
export function RolesStrip({ observation }: { observation: PuertoRicoObservation }) {
  return (
    <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${observation.roles.length}, minmax(0, 1fr))` }}>
      {observation.roles.map((role) => {
        const meta = ROLE_META[role.role] ?? { label: role.role, art: "" };
        const isActive = observation.active_role === role.role;
        return (
          <div
            key={role.role}
            className={cn(
              "flex h-36 min-w-0 flex-col items-center gap-1 rounded-lg border bg-card p-2 text-center",
              role.taken_by !== null && "bg-muted/50",
              isActive && "border-primary ring-1 ring-primary",
            )}
          >
            {meta.art ? <Art path={meta.art} alt={meta.label} size={64} className="h-16 w-auto rounded-sm shadow-sm" /> : null}
            <span className="w-full truncate text-xs font-semibold">{meta.label}</span>
            <span className="flex h-4 items-center gap-1 text-xs font-semibold text-amber-600 tabular-nums dark:text-amber-400">
              {role.doubloons ? (
                <>
                  <Coin value={role.doubloons} />
                  {role.doubloons}
                </>
              ) : null}
            </span>
            <span className="flex h-4 items-center gap-1 text-xs">
              {role.taken_by === null ? (
                <span className="text-muted-foreground">open</span>
              ) : (
                <>
                  <SeatDot player={role.taken_by} />
                  {seatLabel(role.taken_by)}
                </>
              )}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function Section({ title, children, className }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={cn("flex min-w-0 flex-col gap-2 rounded-lg border bg-card p-3", className)}>
      <h4 className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">{title}</h4>
      {children}
    </section>
  );
}

function SupplyStats({ observation }: { observation: PuertoRicoObservation }) {
  const stats: [string, number][] = [
    ["Colonist ship", observation.colonist_ship],
    ["Colonists", observation.colonist_supply],
    ["VP chips", observation.vp_supply],
    ["Quarries", observation.quarry_supply],
    ["Plantation deck", observation.plantation_deck_count],
  ];
  return (
    <dl className="flex flex-col gap-1 text-sm">
      {stats.map(([label, value]) => (
        <div key={label} className="flex h-6 items-center justify-between gap-2">
          <dt className="truncate text-muted-foreground">{label}</dt>
          <dd className="font-medium tabular-nums">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function TradingHouse({ observation }: { observation: PuertoRicoObservation }) {
  return (
    <div className="flex items-start gap-3">
      <div className="grid grid-cols-2 gap-1.5">
        {Array.from({ length: TRADING_HOUSE_SPACES }, (_, index) => {
          const good = observation.trading_house[index];
          return (
            <div
              key={index}
              className={cn("flex size-10 items-center justify-center rounded-md border", !good && "border-dashed")}
              style={good ? { background: `color-mix(in oklab, ${GOOD_META[good].color} 18%, transparent)` } : undefined}
              title={good ? GOOD_META[good].label : "Empty trading-house space"}
            >
              {good ? <Art path={GOOD_META[good].barrel} alt={GOOD_META[good].label} size={28} className="size-7" /> : null}
            </div>
          );
        })}
      </div>
      <Art path={TRADING_HOUSE_CARD} alt="Trading house prices" size={64} className="h-20 w-auto rounded-sm" />
    </div>
  );
}

function CargoShips({ observation }: { observation: PuertoRicoObservation }) {
  return (
    <ul className="flex flex-col gap-1.5">
      {observation.cargo_ships.map((ship, index) => {
        const meta = ship.good ? GOOD_META[ship.good] : null;
        return (
          <li key={index} className="flex h-6 items-center gap-2 text-sm" title={`Cargo ship ${index + 1}`}>
            {meta ? <Art path={meta.barrel} alt={meta.label} size={20} className="size-5" /> : <span className="size-5 rounded-full border border-dashed" />}
            <span className={cn("w-16 truncate", !meta && "text-muted-foreground")}>{meta ? meta.label : "empty"}</span>
            <Pips filled={ship.filled} total={ship.capacity} color={meta?.color} round={false} />
            <span className="ml-auto text-xs text-muted-foreground tabular-nums">
              {ship.filled}/{ship.capacity}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/** The face-up plantations, in num_players + 1 slots: the most a round deals. */
function FaceUp({ observation }: { observation: PuertoRicoObservation }) {
  const slots = observation.players.length + 1;
  return (
    <div className="grid grid-cols-[repeat(3,2.75rem)] gap-1.5">
      {Array.from({ length: slots }, (_, index) => {
        const good = observation.face_up[index];
        return good ? <IslandTile key={index} good={good} /> : <IslandTile key={index} />;
      })}
    </div>
  );
}

export function TableStrip({ observation }: { observation: PuertoRicoObservation }) {
  return (
    <div className="grid gap-2 @2xl:grid-cols-3 @4xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto_minmax(0,1.2fr)_auto]">
      <Section title="Supply">
        <SupplyStats observation={observation} />
      </Section>
      <Section title="Goods bank">
        <GoodCounts counts={observation.goods_supply} />
      </Section>
      <Section title="Trading house">
        <TradingHouse observation={observation} />
      </Section>
      <Section title="Cargo ships">
        <CargoShips observation={observation} />
      </Section>
      <Section title="Face-up plantations">
        <FaceUp observation={observation} />
      </Section>
    </div>
  );
}
