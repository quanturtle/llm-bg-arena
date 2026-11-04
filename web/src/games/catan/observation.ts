// The Catan spectator observation and board layout, as boardgames/games/catan and
// boardgames/web/layouts.py send them. Parsing fails loudly when either shape changes.
import { z } from "zod";

const point = z.object({ id: z.number(), x: z.number(), y: z.number() });

export const layoutSchema = z.object({
  hexes: z.array(point),
  vertices: z.array(point),
  edges: z.array(z.object({ id: z.number(), vertices: z.tuple([z.number(), z.number()]) })),
  hex_vertices: z.array(z.array(z.number())),
});
export type CatanLayout = z.infer<typeof layoutSchema>;

export const observationSchema = z.object({
  turn: z.number(),
  phase: z.enum([
    "setup_settlement",
    "setup_road",
    "roll",
    "discard",
    "move_robber",
    "actions",
    "free_road",
    "trade_response",
    "game_over",
  ]),
  active: z.number(),
  dice: z.array(z.number()).nullable(),
  robber: z.number(),
  hexes: z.array(z.object({ terrain: z.string(), number: z.number().nullable() })),
  ports: z.array(z.object({ edge: z.number(), resource: z.string().nullable() })),
  buildings: z.array(z.object({ player: z.number(), kind: z.enum(["settlement", "city"]) }).nullable()),
  roads: z.array(z.number().nullable()),
  hand_sizes: z.array(z.number()),
  dev_counts: z.array(z.number()),
  knights: z.array(z.number()),
  public_points: z.array(z.number()),
  longest_road: z.number().nullable(),
  longest_road_lengths: z.array(z.number()),
  largest_army: z.number().nullable(),
  winner: z.number().nullable(),
  game_over: z.boolean(),
  final_scores: z.array(z.object({ player: z.number(), points: z.number() })).nullable(),
  revealed_dev: z.array(z.record(z.string(), z.number())).nullable(),
});
export type CatanObservation = z.infer<typeof observationSchema>;
