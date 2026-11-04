// The Puerto Rico spectator observation and building table, as boardgames/games/puerto_rico and
// boardgames/web/layouts.py send them. Parsing fails loudly when either shape changes.
import { z } from "zod";

export const GOODS = ["corn", "indigo", "sugar", "tobacco", "coffee"] as const;
export type Good = (typeof GOODS)[number];
const good = z.enum(GOODS);
const goodCounts = z.partialRecord(good, z.number());

export const layoutSchema = z.object({
  buildings: z.array(
    z.object({
      name: z.string(),
      cost: z.number(),
      victory_points: z.number(),
      max_colonists: z.number(),
      production: good.nullable(),
      kind: z.string(),
      copies: z.number(),
      city_spaces: z.number(),
    }),
  ),
});
export type BuildingSpec = z.infer<typeof layoutSchema>["buildings"][number];

const playerSchema = z.object({
  seat: z.number(),
  doubloons: z.number(),
  goods: goodCounts,
  plantations: z.array(z.object({ good, colonized: z.boolean() })),
  quarries: z.number(),
  occupied_quarries: z.number(),
  buildings: z.array(z.object({ name: z.string(), colonists: z.number(), active: z.boolean() })),
  colonists_unplaced: z.number(),
  city_spaces_used: z.number(),
  island_spaces_used: z.number(),
  building_points: z.number(),
  public_points: z.number(),
});
export type PuertoRicoPlayer = z.infer<typeof playerSchema>;

export const observationSchema = z.object({
  round: z.number(),
  phase: z.string(),
  governor: z.number(),
  order: z.array(z.number()),
  active: z.number().nullable(),
  active_role: z.string().nullable(),
  roles: z.array(z.object({ role: z.string(), doubloons: z.number(), taken_by: z.number().nullable() })),
  colonist_ship: z.number(),
  colonist_supply: z.number(),
  colonist_shortage: z.boolean(),
  vp_supply: z.number(),
  quarry_supply: z.number(),
  plantation_deck_count: z.number(),
  trading_house: z.array(good),
  cargo_ships: z.array(z.object({ capacity: z.number(), good: good.nullable(), filled: z.number() })),
  face_up: z.array(good),
  available_buildings: z.array(z.string()),
  goods_supply: goodCounts,
  players: z.array(playerSchema),
  game_over: z.boolean(),
  winner: z.number().nullable(),
  end_reason: z.string().nullable(),
  final_scores: z
    .array(z.object({ player: z.number(), points: z.number(), vp_chips: z.number(), breakdown: z.record(z.string(), z.number()) }))
    .nullable(),
});
export type PuertoRicoObservation = z.infer<typeof observationSchema>;
