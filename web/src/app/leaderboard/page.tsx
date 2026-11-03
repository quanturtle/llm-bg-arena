import type { Metadata } from "next";
import { Suspense } from "react";

import { LeaderboardView } from "@/features/stats/leaderboard-view";

export const metadata: Metadata = { title: "Leaderboard" };

export default function LeaderboardPage() {
  return (
    <Suspense>
      <LeaderboardView />
    </Suspense>
  );
}
