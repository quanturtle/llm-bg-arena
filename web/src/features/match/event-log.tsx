"use client";

import { Dot, Handshake, Trophy, type LucideIcon } from "lucide-react";
import { memo, useEffect, useRef } from "react";

import { SeatText } from "@/components/seat";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import type { EventRecord, Outline } from "@/lib/api";
import { seatName } from "@/lib/format";
import { cn } from "@/lib/utils";

function isVisible(event: EventRecord, step: number, viewer: number | null, omniscient: boolean): boolean {
  if (event.step > step) return false;
  if (omniscient || event.audience === "everyone") return true;
  return viewer !== null && event.audience.includes(viewer);
}

// One row: the step in a column wide enough for five digits, the kind's icon, then the message.
const EventRow = memo(function EventRow({
  event,
  isCurrent,
  players,
  Icon,
}: {
  event: EventRecord;
  isCurrent: boolean;
  players: number;
  Icon: LucideIcon;
}) {
  const isPrivate = event.audience !== "everyone";
  const seenBy = Array.isArray(event.audience) ? ` (seen by ${event.audience.map((player) => `P${player + 1}`).join(", ")})` : "";
  return (
    <li
      data-current={isCurrent || undefined}
      className={cn(
        "grid grid-cols-[5ch_1rem_minmax(0,1fr)] items-baseline gap-x-2 border-l-2 border-transparent px-2 py-1 text-sm",
        isCurrent && "border-primary bg-muted",
        isPrivate && "text-muted-foreground italic",
      )}
    >
      <span className="text-right text-xs text-muted-foreground tabular-nums">{event.step}</span>
      <Icon className="size-3.5 self-center text-muted-foreground" aria-hidden="true" />
      <span>
        <SeatText text={event.text + seenBy} players={players} />
      </span>
    </li>
  );
});

// The match result, as the log's last line once the final step of a finished match is on screen.
function ResultRow({ outline, step }: { outline: Outline; step: number }) {
  const match = outline.match;
  const final = outline.frame_count - 1;
  if (match.status !== "finished" || step !== final) return null;
  const winners = match.seats.filter((seat) => seat.rank === 1);
  if (!winners.length) return null;
  const names = winners.map((seat) => `P${seat.player + 1} ${seatName(seat)}`).join(" and ");
  const points = winners[0].points ?? 0;
  const pointText = `${points} point${points === 1 ? "" : "s"}`;
  const isDraw = winners.length > 1 && winners.length === match.seats.length;
  const text = winners.length === 1 ? `Winner: ${names}, ${pointText}.` : isDraw ? `Draw: ${names}.` : `Shared first place: ${names}, ${pointText}.`;
  const Icon = isDraw ? Handshake : Trophy;
  return (
    <li
      data-current
      className="grid grid-cols-[5ch_1rem_minmax(0,1fr)] items-baseline gap-x-2 border-l-2 border-emerald-500 bg-emerald-500/10 px-2 py-1 text-sm font-semibold"
    >
      <span className="text-right text-xs tabular-nums">{final}</span>
      <Icon className="size-3.5 self-center text-emerald-600 dark:text-emerald-400" aria-hidden="true" />
      <span>
        <SeatText text={text} players={match.seats.length} />
      </span>
    </li>
  );
}

/** The events up to the step on screen, filtered by audience; the list scrolls itself, never the page. */
export function EventLog({
  outline,
  step,
  viewer,
  omniscient,
  icons,
  className,
}: {
  outline: Outline;
  step: number;
  viewer: number | null;
  omniscient: boolean;
  icons: Record<string, LucideIcon>;
  className?: string;
}) {
  const list = useRef<HTMLDivElement>(null);
  const players = outline.match.seats.length;
  const events = outline.events.filter((event) => isVisible(event, step, viewer, omniscient));
  useEffect(() => {
    const box = list.current;
    const rows = box?.querySelectorAll("[data-current]");
    const target = rows && rows.length ? rows[rows.length - 1] : null;
    if (!box || !(target instanceof HTMLElement)) return;
    // the list box is the rows' offset parent, so offsetTop is measured from its top
    const top = target.offsetTop;
    if (top + target.offsetHeight > box.scrollTop + box.clientHeight) box.scrollTop = top + target.offsetHeight - box.clientHeight;
    else if (top < box.scrollTop) box.scrollTop = top;
  }, [step, events.length]);
  return (
    <Card aria-label="Events" className={cn("gap-2 py-4", className)}>
      <CardHeader className="px-4">
        <CardTitle className="text-sm">Events</CardTitle>
      </CardHeader>
      <div ref={list} className="relative min-h-0 flex-1 overflow-y-auto overscroll-contain px-2">
        <ul>
          {events.map((event, index) => (
            <EventRow key={index} event={event} isCurrent={event.step === step} players={players} Icon={icons[event.kind] ?? Dot} />
          ))}
          <ResultRow outline={outline} step={step} />
        </ul>
      </div>
    </Card>
  );
}
