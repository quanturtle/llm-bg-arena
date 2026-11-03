import type { Metadata } from "next";
import { Suspense } from "react";

import { GameView } from "@/features/games/game-view";

export const metadata: Metadata = { title: "Game" };

export default function GamePage() {
  return (
    <Suspense>
      <GameView />
    </Suspense>
  );
}
