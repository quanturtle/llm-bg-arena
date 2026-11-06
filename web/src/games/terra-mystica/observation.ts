// The Terra Mystica spectator observation, as boardgames/games/terra_mystica/view.py sends it.
// Parsing fails loudly when the shape changes.
import { z } from "zod";

import { BUILDING_TYPES, CULTS, TERRAINS } from "@/games/terra-mystica/meta";

const terrain = z.enum(TERRAINS);
const cult = z.enum(CULTS);
const buildingType = z.enum(BUILDING_TYPES);

export const tileSchema = z.object({
  q: z.number(),
  r: z.number(),
  terrain,
  building: z
    .object({
      owner: z.number(),
      type: buildingType,
      in_town: z.boolean(),
    })
    .nullable(),
});
export type TerraMysticaTile = z.infer<typeof tileSchema>;

const playerSchema = z.object({
  seat: z.number(),
  faction: z.string(),
  name: z.string(),
  home_terrain: terrain,
  victory_points: z.number(),
  coins: z.number(),
  workers: z.number(),
  priests: z.number(),
  power: z.tuple([z.number(), z.number(), z.number()]),
  cults: z.object({
    fire: z.number(),
    water: z.number(),
    earth: z.number(),
    air: z.number(),
  }),
  shipping: z.number(),
  digging: z.number(),
  keys: z.number(),
  buildings: z.array(
    z.object({
      position: z.string(),
      type: buildingType,
      in_town: z.boolean(),
    }),
  ),
});
export type TerraMysticaPlayer = z.infer<typeof playerSchema>;

const cultBonusSchema = z.object({
  cult,
  per: z.number(),
  reward: z.string(),
  amount: z.number(),
});
export type CultBonus = z.infer<typeof cultBonusSchema>;

export const observationSchema = z.object({
  round: z.number(),
  phase: z.string(),
  active: z.number(),
  order: z.array(z.number()),
  scoring: z.array(z.string()),
  scoring_bonuses: z.array(cultBonusSchema),
  cult_spades: z.array(z.number()),
  spade_return: z.string(),
  town_tiles: z.array(z.number()),
  used_orders: z.array(z.object({ cult, order: z.number(), player: z.number() })),
  passed: z.array(z.number()),
  pass_order: z.array(z.number()),
  used_power_actions: z.array(z.string()),
  setup_queue: z.array(z.number()),
  players: z.array(playerSchema),
  board: z.array(tileSchema),
  game_over: z.boolean(),
  end_reason: z.string().nullable(),
  you: z.number().nullable(),
  final_scores: z
    .array(
      z.object({
        player: z.number(),
        points: z.number(),
        breakdown: z.record(z.string(), z.number()),
      }),
    )
    .nullable(),
});
export type TerraMysticaObservation = z.infer<typeof observationSchema>;
