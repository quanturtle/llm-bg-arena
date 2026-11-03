"use client";

import { Dices, Plus } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// Each nav link stays highlighted on the pages under it.
const NAV = [
  { href: "/matches", label: "Matches", sections: ["", "matches", "match"] },
  { href: "/leaderboard", label: "Leaderboard", sections: ["leaderboard", "agent"] },
  { href: "/games", label: "Games", sections: ["games", "game"] },
];

function sectionOf(pathname: string): string {
  return pathname.split("/").filter(Boolean)[0] ?? "";
}

export function SiteHeader() {
  const section = sectionOf(usePathname());
  return (
    // the border sits inside the 3.5rem height, which the match page subtracts from the window
    <header className="sticky top-0 z-40 h-14 border-b bg-background/85 backdrop-blur">
      <div className="mx-auto flex h-full w-full max-w-[1840px] items-center gap-3 px-4 sm:gap-6 sm:px-6">
        <Link href="/matches" className="flex items-center gap-2 font-semibold" aria-label="Boardgames">
          <Dices className="size-5" />
          <span className="hidden sm:inline">Boardgames</span>
        </Link>
        <nav className="flex items-center gap-0.5 text-sm sm:gap-1">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "rounded-md px-2 py-1.5 text-muted-foreground transition-colors hover:text-foreground sm:px-2.5",
                item.sections.includes(section) && "bg-muted text-foreground",
              )}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <Button asChild size="sm">
            <Link href="/new" aria-label="New match">
              <Plus />
              <span className="hidden sm:inline">New match</span>
            </Link>
          </Button>
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
