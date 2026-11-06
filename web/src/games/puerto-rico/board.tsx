import {
  Anchor,
  CircleCheck,
  Coins,
  Crown,
  Drama,
  Factory,
  Flag,
  GraduationCap,
  Hammer,
  Package,
  Pickaxe,
  Ship,
  SkipForward,
  Sprout,
  Trash2,
  UserMinus,
  UserPlus,
  Users,
} from "lucide-react";

import { defineGame, type BoardContext } from "@/games/define";
import { BuildingMarket, ScoreTable } from "@/games/puerto-rico/market";
import { layoutSchema, observationSchema, type BuildingSpec, type PuertoRicoObservation } from "@/games/puerto-rico/observation";
import { PlayerBoards } from "@/games/puerto-rico/player-board";
import { PuertoRicoStatus, RolesStrip, TableStrip } from "@/games/puerto-rico/table";

function buildingSpecs(layout: unknown): Map<string, BuildingSpec> | string {
  const parsed = layoutSchema.safeParse(layout);
  if (!parsed.success) return parsed.error.message;
  return new Map(parsed.data.buildings.map((spec) => [spec.name, spec]));
}

function MissingSpecs({ error }: { error: string }) {
  return <p className="text-sm text-destructive">The Puerto Rico building table did not load: {error}</p>;
}

function PuertoRicoBoard({ observation, context }: { observation: PuertoRicoObservation; context: BoardContext }) {
  const specs = buildingSpecs(context.layout);
  if (typeof specs === "string") return <MissingSpecs error={specs} />;
  return (
    <div className="@container flex flex-col gap-2">
      <PuertoRicoStatus observation={observation} match={context.match} />
      <RolesStrip observation={observation} />
      <TableStrip observation={observation} />
      <PlayerBoards observation={observation} match={context.match} specs={specs} />
    </div>
  );
}

function MarketTab({ observation, context }: { observation: PuertoRicoObservation; context: BoardContext }) {
  const specs = buildingSpecs(context.layout);
  if (typeof specs === "string") return <MissingSpecs error={specs} />;
  return <BuildingMarket observation={observation} specs={specs} />;
}

export const puertoRico = defineGame({
  schema: observationSchema,
  usesLayout: true,
  tabs: [
    { id: "board", label: "Board", render: (observation, context) => <PuertoRicoBoard observation={observation} context={context} /> },
    { id: "market", label: "Building market", render: (observation, context) => <MarketTab observation={observation} context={context} /> },
    { id: "scores", label: "Scores", render: (observation, context) => <ScoreTable observation={observation} match={context.match} /> },
  ],
  eventIcons: {
    game_started: Flag,
    role_selection: Drama,
    role_taken: Drama,
    privilege_good: Crown,
    privilege_declined: Crown,
    settler_passed: SkipForward,
    builder_passed: SkipForward,
    captain_passed: SkipForward,
    trader_passed: SkipForward,
    plantation_taken: Sprout,
    hacienda_plantation: Sprout,
    face_up_refilled: Sprout,
    plantation_discard_reshuffled: Trash2,
    colonist_shortage: Trash2,
    quarry_taken: Pickaxe,
    building_built: Hammer,
    colonists_distributed: Users,
    colonist_placed: UserPlus,
    colonist_picked_up: UserMinus,
    university_colonist: GraduationCap,
    mayor_finished: CircleCheck,
    goods_produced: Package,
    factory_bonus: Factory,
    prospector_bonus: Coins,
    good_sold: Coins,
    goods_shipped: Ship,
    wharf_shipped: Anchor,
    goods_discarded: Trash2,
  },
});
