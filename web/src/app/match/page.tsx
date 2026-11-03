import type { Metadata } from "next";
import { Suspense } from "react";

import { MatchView } from "@/features/match/match-view";

export const metadata: Metadata = { title: "Match" };

export default function MatchPage() {
  return (
    <Suspense>
      <MatchView />
    </Suspense>
  );
}
