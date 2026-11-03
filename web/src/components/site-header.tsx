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
    <header className="sticky top-0 z-40 border-b bg-background/85 backdrop-blur">
      <div className="mx-auto flex h-14 w-full max-w-[1840px] items-center gap-6 px-4 sm:px-6">
        <Link href="/matches" className="flex items-center gap-2 font-semibold">
          <Dices className="size-5" />
          Boardgames
        </Link>
        <nav className="flex items-center gap-1 text-sm">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "rounded-md px-2.5 py-1.5 text-muted-foreground transition-colors hover:text-foreground",
                item.sections.includes(section) && "bg-muted text-foreground",
              )}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <Button asChild size="sm">
            <Link href="/new">
              <Plus /> New match
            </Link>
          </Button>
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
