// Badges for a match's status and a seat's result, and the Live indicator.
import { Badge } from "@/components/ui/badge";
import type { LaunchStatus, MatchStatus } from "@/lib/api";
import { cn } from "@/lib/utils";

export type ShownStatus = MatchStatus | LaunchStatus;

const STATUS_CLASS: Record<ShownStatus, string> = {
  finished: "border-border text-muted-foreground",
  running: "border-amber-500/50 text-amber-600 dark:text-amber-400",
  paused: "border-sky-500/50 text-sky-600 dark:text-sky-400",
  stopped: "border-destructive/50 text-destructive",
  failed: "border-destructive/50 text-destructive",
};

export function StatusBadge({ status }: { status: ShownStatus }) {
  return (
    <Badge variant="outline" className={STATUS_CLASS[status]}>
      {status}
    </Badge>
  );
}

export function WinnerBadge({ label = "winner" }: { label?: string }) {
  return (
    <Badge variant="outline" className="border-emerald-500/50 text-emerald-600 dark:text-emerald-400">
      {label}
    </Badge>
  );
}

export function ForfeitBadge() {
  return (
    <Badge variant="outline" className="border-destructive/50 text-destructive">
      forfeit
    </Badge>
  );
}

/** Red and pulsing while the page shows the step being played now; grey when paused or scrolled back. */
export function LiveIndicator({ on }: { on: boolean }) {
  return (
    <span
      title={on ? "Showing the move being played now" : "Not showing the latest step, or the match is paused"}
      className={cn("inline-flex items-center gap-1.5 text-xs font-semibold", on ? "text-red-600 dark:text-red-500" : "text-muted-foreground")}
    >
      <span className={cn("size-2 rounded-full", on ? "animate-pulse bg-red-600 dark:bg-red-500" : "bg-muted-foreground/50")} />
      Live
    </span>
  );
}
