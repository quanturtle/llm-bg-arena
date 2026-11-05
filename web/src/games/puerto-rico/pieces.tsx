"use client";

// Small Puerto Rico pieces shared by the table and the player boards: art, barrels, tiles, coins.
import Image from "next/image";
import { useState } from "react";

import { asset, COIN_1, COIN_5, COIN_COLOR, GOOD_META, QUARRY_COLOR, QUARRY_OCCUPIED, QUARRY_TILE } from "@/games/puerto-rico/assets";
import { GOODS, type Good } from "@/games/puerto-rico/observation";
import { cn } from "@/lib/utils";

/** The art at `path`, or a placeholder in the same box when the file is missing, as in a fresh clone. */
export function Art({ path, alt, size, color, className }: { path: string; alt: string; size: number; color?: string; className?: string }) {
  const [missingPath, setMissingPath] = useState<string | null>(null);
  if (missingPath === path) {
    return <span role="img" aria-label={alt} title={alt} className={cn("inline-block aspect-square rounded-sm bg-muted", className)} style={color ? { background: color } : undefined} />;
  }
  return <Image src={asset(path)} alt={alt} width={size} height={size} className={cn("object-contain", className)} onError={() => setMissingPath(path)} />;
}

export function Coin({ value }: { value: number }) {
  return <Art path={value >= 5 ? COIN_5 : COIN_1} alt="doubloon" size={16} color={COIN_COLOR} className="size-4" />;
}

/** All five goods in one row, a barrel and its count each; zeros stay in place, dimmed. */
export function GoodRow({ counts, className }: { counts: Partial<Record<Good, number>>; className?: string }) {
  return (
    <ul className={cn("flex h-5 items-center gap-3", className)}>
      {GOODS.map((good) => {
        const count = counts[good] ?? 0;
        return (
          <li
            key={good}
            title={`${GOOD_META[good].label}: ${count}`}
            className={cn("flex w-9 items-center gap-1 text-xs font-medium tabular-nums", count === 0 && "opacity-35")}
          >
            <Art path={GOOD_META[good].barrel} alt={GOOD_META[good].label} size={16} color={GOOD_META[good].color} className="size-4" />
            {count}
          </li>
        );
      })}
    </ul>
  );
}

/** One island space: a plantation, a quarry, or empty. A dot marks a colonist on it. */
export function IslandTile({ good, quarry, colonized }: { good?: Good; quarry?: boolean; colonized?: boolean }) {
  if (!good && !quarry) return <div className="size-8 rounded-md border border-dashed" title="Empty island space" />;
  const label = quarry ? "Quarry" : GOOD_META[good as Good].label;
  const path = quarry ? (colonized ? QUARRY_OCCUPIED : QUARRY_TILE) : colonized ? GOOD_META[good as Good].occupied : GOOD_META[good as Good].tile;
  const color = quarry ? QUARRY_COLOR : GOOD_META[good as Good].color;
  return (
    <div
      className="relative size-8 overflow-hidden rounded-md border"
      style={{ borderColor: `color-mix(in oklab, ${color} 60%, transparent)` }}
      title={`${label}${colonized ? " (colonized)" : ""}`}
    >
      <Art path={path} alt={label} size={48} color={color} className="size-full object-cover" />
      {colonized ? <span className="absolute right-0.5 bottom-0.5 size-1.5 rounded-full bg-foreground ring-2 ring-background" /> : null}
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
