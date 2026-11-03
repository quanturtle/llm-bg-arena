import type { Metadata } from "next";
import { Suspense } from "react";

import { MatchesView } from "@/features/matches/matches-view";

export const metadata: Metadata = { title: "Matches" };

// The filters live in the query string, which only the browser knows in a static export.
export default function MatchesPage() {
  return (
    <Suspense>
      <MatchesView />
    </Suspense>
  );
}
