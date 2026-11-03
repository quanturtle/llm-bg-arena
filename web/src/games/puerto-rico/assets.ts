// Art and colours for Puerto Rico: one colour and barrel per good, one card per role.
import type { Good } from "@/games/puerto-rico/observation";

const ASSET_ROOT = "/static/puerto_rico";

export function asset(path: string): string {
  return `${ASSET_ROOT}/${path}`;
}

export const GOOD_META: Record<Good, { label: string; color: string; barrel: string; tile: string; occupied: string }> = {
  corn: { label: "Corn", color: "#e2b33b", barrel: "goods/corn_barrel.png", tile: "plantations/corn.png", occupied: "plantations/corn_occupied.png" },
  indigo: { label: "Indigo", color: "#3f5fbf", barrel: "goods/indigo_barrel.png", tile: "plantations/indigo.png", occupied: "plantations/indigo_occupied.png" },
  sugar: { label: "Sugar", color: "#d47f9e", barrel: "goods/sugar_barrel.png", tile: "plantations/sugar.png", occupied: "plantations/sugar_occupied.png" },
  tobacco: { label: "Tobacco", color: "#a9683a", barrel: "goods/tobacco_barrel.png", tile: "plantations/tobacco.png", occupied: "plantations/tobacco_occupied.png" },
  coffee: { label: "Coffee", color: "#5b3a29", barrel: "goods/coffee_barrel.png", tile: "plantations/coffee.png", occupied: "plantations/coffee_occupied.png" },
};
export const QUARRY_COLOR = "#8d8f94";

export const ROLE_META: Record<string, { label: string; art: string }> = {
  settler: { label: "Settler", art: "roles/settler.png" },
  mayor: { label: "Mayor", art: "roles/mayor.png" },
  builder: { label: "Builder", art: "roles/builder.png" },
  craftsman: { label: "Craftsman", art: "roles/craftsman.png" },
  trader: { label: "Trader", art: "roles/trader.png" },
  captain: { label: "Captain", art: "roles/captain.png" },
  prospector: { label: "Prospector", art: "roles/prospector.png" },
  prospector_2: { label: "Prospector II", art: "roles/prospector.png" },
};

/** Building art has one variant per colonist count: name.png, name_1.png, ... up to three. */
export function buildingArt(name: string, colonists: number): string {
  const filled = Math.max(0, Math.min(colonists, 3));
  return `buildings/${name}${filled ? `_${filled}` : ""}.png`;
}

export function buildingLabel(name: string): string {
  const words = name.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export const COIN_1 = "tokens/doubloon_1.png";
export const COIN_5 = "tokens/doubloon_5.png";
export const TRADING_HOUSE_CARD = "boards/trading_house.png";
export const QUARRY_TILE = "plantations/quarry.png";
export const QUARRY_OCCUPIED = "plantations/quarry_occupied.png";
