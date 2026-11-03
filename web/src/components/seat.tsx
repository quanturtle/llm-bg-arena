// Seats: a colour per player, a chip with the player's name, and text with seat mentions coloured.
import Link from "next/link";

import { ProviderLogo } from "@/components/provider-logo";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { SeatSummary } from "@/lib/api";
import { seatName, splitSeatMentions } from "@/lib/format";
import { cn } from "@/lib/utils";

// Tailwind needs whole class names in the source, so each seat's classes are listed.
const SEAT_BACKGROUND = ["bg-seat-1", "bg-seat-2", "bg-seat-3", "bg-seat-4", "bg-seat-5"];
const SEAT_TEXT = ["text-seat-1", "text-seat-2", "text-seat-3", "text-seat-4", "text-seat-5"];

/** The seat's colour as a CSS value, for SVG fills and chart lines. */
export function seatColor(player: number): string {
  return `var(--seat-${(player % SEAT_BACKGROUND.length) + 1})`;
}

export function seatTextClass(player: number): string {
  return SEAT_TEXT[player % SEAT_TEXT.length];
}

export function seatLabel(player: number): string {
  return `P${player + 1}`;
}

export function agentHref(agent: string): string {
  return `/agent?name=${encodeURIComponent(agent)}`;
}

export function SeatDot({ player, className }: { player: number; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn("inline-block size-2 shrink-0 rounded-full", SEAT_BACKGROUND[player % SEAT_BACKGROUND.length], className)}
    />
  );
}

/** "● P1 [logo] name": the name truncates to its box and the full name shows on hover. */
export function SeatChip({
  seat,
  link = true,
  className,
  children,
}: {
  seat: Pick<SeatSummary, "player" | "agent" | "model">;
  link?: boolean;
  className?: string;
  children?: React.ReactNode;
}) {
  const name = seatName(seat);
  const label = link ? (
    <Link href={agentHref(seat.agent)} className="truncate hover:underline">
      {name}
    </Link>
  ) : (
    <span className="truncate">{name}</span>
  );
  return (
    <span className={cn("inline-flex min-w-0 items-center gap-1.5", className)}>
      <SeatDot player={seat.player} />
      <span className="shrink-0 font-medium tabular-nums">{seatLabel(seat.player)}</span>
      <ProviderLogo model={seat.model ?? seat.agent} />
      <Tooltip>
        <TooltipTrigger asChild>{label}</TooltipTrigger>
        <TooltipContent>{name}</TooltipContent>
      </Tooltip>
      {children}
    </span>
  );
}

/** Text with each seat mention (P1, P2, ...) in that seat's colour. */
export function SeatText({ text, players }: { text: string; players: number }) {
  return (
    <>
      {splitSeatMentions(text, players).map((part, index) =>
        typeof part === "number" ? (
          <span key={index} className={cn("font-semibold", seatTextClass(part))}>
            {seatLabel(part)}
          </span>
        ) : (
          part
        ),
      )}
    </>
  );
}
