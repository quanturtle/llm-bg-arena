// Pieces the drawn boards share: the one-line status bar, the pill on a card's border, and stat cells.
import type { LucideIcon } from "lucide-react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

/** One line of fixed height; the game-over banner takes the same space as the status it replaces. */
export function StatusBar({ tone = "default", children, aside }: { tone?: "default" | "done"; children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <div
      className={cn(
        "flex h-10 items-center gap-3 rounded-lg border px-3 text-sm",
        tone === "done" ? "border-emerald-500/40 bg-emerald-500/10 font-medium text-emerald-700 dark:text-emerald-400" : "bg-muted/40",
      )}
    >
      <div className="flex min-w-0 flex-1 items-center gap-2 truncate">{children}</div>
      {aside ? <div className="flex shrink-0 items-center gap-1">{aside}</div> : null}
    </div>
  );
}

/** Small labels sitting on a card's top border; absolutely placed, so they never move the card's content. */
export function BorderPills({ children }: { children: React.ReactNode }) {
  return <div className="absolute -top-2.5 right-3 flex gap-1">{children}</div>;
}

export function BorderPill({ tone, children }: { tone: "active" | "neutral" | "win"; children: React.ReactNode }) {
  return (
    <span
      className={cn(
        "rounded-full border bg-card px-2 text-[11px] leading-5 font-medium",
        tone === "active" && "border-primary text-foreground",
        tone === "neutral" && "text-muted-foreground",
        tone === "win" && "border-emerald-500/60 text-emerald-600 dark:text-emerald-400",
      )}
    >
      {children}
    </span>
  );
}

/** An icon and a number with a tooltip naming the stat; tabular digits keep the width steady. */
export function Stat({ icon: Icon, label, value, className }: { icon: LucideIcon; label: string; value: React.ReactNode; className?: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className={cn("flex items-center gap-1.5 text-muted-foreground", className)}>
          <Icon className="size-3.5 shrink-0" aria-hidden="true" />
          <span className="font-medium text-foreground tabular-nums">{value}</span>
        </span>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

/** Whole numbers without decimals: 4.0 shows as 4. */
export function points(value: number | null | undefined): string {
  if (value === null || value === undefined) return "";
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}
