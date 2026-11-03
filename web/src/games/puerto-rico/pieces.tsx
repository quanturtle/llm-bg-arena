// Small Puerto Rico pieces shared by the table and the player boards: art, barrels, tiles, coins.
import Image from "next/image";

import { asset, COIN_1, COIN_5, GOOD_META, QUARRY_COLOR, QUARRY_OCCUPIED, QUARRY_TILE } from "@/games/puerto-rico/assets";
import { GOODS, type Good } from "@/games/puerto-rico/observation";
import { cn } from "@/lib/utils";

export function Art({ path, alt, size, className }: { path: string; alt: string; size: number; className?: string }) {
  return <Image src={asset(path)} alt={alt} width={size} height={size} className={cn("object-contain", className)} />;
}

export function Coin({ value }: { value: number }) {
  return <Art path={value >= 5 ? COIN_5 : COIN_1} alt="doubloon" size={16} className="size-4" />;
}

/** All five goods with their counts; zeros stay in their row, dimmed, so the list never reflows. */
export function GoodCounts({ counts, className }: { counts: Partial<Record<Good, number>>; className?: string }) {
  return (
    <ul className={cn("flex flex-col gap-1", className)}>
      {GOODS.map((good) => {
        const count = counts[good] ?? 0;
        return (
          <li key={good} className={cn("flex h-6 items-center gap-2 text-sm", count === 0 && "opacity-40")}>
            <Art path={GOOD_META[good].barrel} alt="" size={20} className="size-5" />
            <span className="flex-1 truncate">{GOOD_META[good].label}</span>
            <span className="font-medium tabular-nums">{count}</span>
          </li>
        );
      })}
    </ul>
  );
}

/** One island space: a plantation, a quarry, or empty. A dot marks a colonist on it. */
export function IslandTile({ good, quarry, colonized }: { good?: Good; quarry?: boolean; colonized?: boolean }) {
  if (!good && !quarry) return <div className="aspect-square rounded-md border border-dashed" title="Empty island space" />;
  const label = quarry ? "Quarry" : GOOD_META[good as Good].label;
  const path = quarry ? (colonized ? QUARRY_OCCUPIED : QUARRY_TILE) : colonized ? GOOD_META[good as Good].occupied : GOOD_META[good as Good].tile;
  const color = quarry ? QUARRY_COLOR : GOOD_META[good as Good].color;
  return (
    <div
      className="relative aspect-square overflow-hidden rounded-md border"
      style={{ borderColor: `color-mix(in oklab, ${color} 50%, transparent)` }}
      title={`${label}${colonized ? " (colonized)" : ""}`}
    >
      <Art path={path} alt={label} size={64} className="size-full object-cover" />
      <span className="absolute inset-x-0 top-0 truncate bg-background/80 px-0.5 text-center text-[9px] leading-tight font-semibold">{label}</span>
      {colonized ? <span className="absolute right-1 bottom-1 size-2 rounded-full bg-foreground ring-2 ring-background" /> : null}
    </div>
  );
}

/** Filled and empty colonist (or cargo) spaces as small pips. */
export function Pips({ filled, total, color, round = true }: { filled: number; total: number; color?: string; round?: boolean }) {
  return (
    <span className="flex gap-0.5">
      {Array.from({ length: total }, (_, index) => (
        <span
          key={index}
          className={cn("size-1.5 border", round ? "rounded-full" : "rounded-[2px]", index < filled ? "border-foreground bg-foreground" : "border-muted-foreground/50")}
          style={index < filled && color ? { background: color, borderColor: color } : undefined}
        />
      ))}
    </span>
  );
}
