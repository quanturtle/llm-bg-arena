import type { Metadata } from "next";
import { Suspense } from "react";

import { AgentView } from "@/features/stats/agent-view";

export const metadata: Metadata = { title: "Agent" };

// The agent's name is a query parameter, since names such as org/model contain slashes.
export default function AgentPage() {
  return (
    <Suspense>
      <AgentView />
    </Suspense>
  );
}
