import type { Metadata } from "next";

import { NewMatchView } from "@/features/new-match/new-match-view";

export const metadata: Metadata = { title: "New match" };

export default function NewMatchPage() {
  return <NewMatchView />;
}
