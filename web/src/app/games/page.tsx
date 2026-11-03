import type { Metadata } from "next";

import { GamesView } from "@/features/games/games-view";

export const metadata: Metadata = { title: "Games" };

export default function GamesPage() {
  return <GamesView />;
}
