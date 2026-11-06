// Names, colours and symbols shared by the Terra Mystica map, player cards and legends.
//
// The terrain palette and colour-blind symbols follow jsnell/terra-mystica (MIT).
// See web/public/terra_mystica/SOURCE.md for the full attribution.
import { Droplet, Flame, Mountain, Wind, type LucideIcon } from "lucide-react";

export const TERRAINS = ["plains", "swamp", "lake", "forest", "mountain", "wasteland", "desert", "river"] as const;
export type Terrain = (typeof TERRAINS)[number];

export type TerrainSymbol = "plains" | "swamp" | "lake" | "forest" | "mountain" | "wasteland" | "desert" | "water";

type TerrainMeta = {
  label: string;
  letter: string;
  fill: string;
  ink: string;
  symbol: TerrainSymbol;
};

export const TERRAIN_META: Record<Terrain, TerrainMeta> = {
  plains: { label: "Plains", letter: "P", fill: "#b08040", ink: "#000000", symbol: "plains" },
  swamp: { label: "Swamp", letter: "S", fill: "#404040", ink: "#c0c0c0", symbol: "swamp" },
  lake: { label: "Lake", letter: "L", fill: "#60c0f0", ink: "#000000", symbol: "lake" },
  forest: { label: "Forest", letter: "F", fill: "#80f080", ink: "#000000", symbol: "forest" },
  mountain: { label: "Mountain", letter: "M", fill: "#c0c0c0", ink: "#000000", symbol: "mountain" },
  wasteland: { label: "Wasteland", letter: "W", fill: "#f08080", ink: "#000000", symbol: "wasteland" },
  desert: { label: "Desert", letter: "D", fill: "#f0f080", ink: "#000000", symbol: "desert" },
  river: { label: "River", letter: "R", fill: "#4a90c8", ink: "#000000", symbol: "water" },
};

export const CULTS = ["fire", "water", "earth", "air"] as const;
export type Cult = (typeof CULTS)[number];

export const CULT_META: Record<Cult, { label: string; color: string; icon: LucideIcon }> = {
  fire: { label: "Fire", color: "#c9583e", icon: Flame },
  water: { label: "Water", color: "#3f86b0", icon: Droplet },
  earth: { label: "Earth", color: "#6d8f45", icon: Mountain },
  air: { label: "Air", color: "#b28b36", icon: Wind },
};

// The fourteen factions use the seven terrain colours; each colour has a contrasting outline
// so a black piece still reads on a dark swamp.
type FactionMeta = { color: string; border: string };

export const FACTION_META: Record<string, FactionMeta> = {
  alchemists: { color: "#000000", border: "#c0c0c0" },
  auren: { color: "#40a040", border: "#000000" },
  chaos_magicians: { color: "#e04040", border: "#000000" },
  cultists: { color: "#a06040", border: "#000000" },
  darklings: { color: "#000000", border: "#c0c0c0" },
  dwarves: { color: "#808080", border: "#000000" },
  engineers: { color: "#808080", border: "#000000" },
  fakirs: { color: "#e0e040", border: "#000000" },
  giants: { color: "#e04040", border: "#000000" },
  halflings: { color: "#a06040", border: "#000000" },
  mermaids: { color: "#2080f0", border: "#000000" },
  nomads: { color: "#e0e040", border: "#000000" },
  swarmlings: { color: "#2080f0", border: "#000000" },
  witches: { color: "#40a040", border: "#000000" },
};

export function factionMeta(faction: string): FactionMeta {
  return FACTION_META[faction] ?? { color: "#808080", border: "#000000" };
}

export const BUILDING_TYPES = ["dwelling", "trading_house", "temple", "stronghold", "sanctuary"] as const;
export type BuildingType = (typeof BUILDING_TYPES)[number];

export const BUILDING_LABEL: Record<BuildingType, string> = {
  dwelling: "Dwelling",
  trading_house: "Trading house",
  temple: "Temple",
  stronghold: "Stronghold",
  sanctuary: "Sanctuary",
};
