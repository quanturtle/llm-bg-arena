// Small text helpers shared by the Terra Mystica map, table strips and player cards.
import type { CultBonus } from "@/games/terra-mystica/observation";

export function titleCase(value: string): string {
  const text = value.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function bonusReward(bonus: CultBonus): string {
  const singular: Record<string, string> = {
    priests: "priest",
    workers: "worker",
    coins: "coin",
    power: "power",
    spades: "spade",
  };
  const reward = bonus.amount === 1 ? (singular[bonus.reward] ?? bonus.reward) : bonus.reward;
  return `${bonus.amount} ${reward}`;
}

export function bonusText(bonus: CultBonus): string {
  return `${bonusReward(bonus)} per ${bonus.per} ${bonus.cult}`;
}
