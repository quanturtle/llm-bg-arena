// The logo of a model's provider. The marks come from @lobehub/icons-static-svg (MIT); Next copies
// each imported SVG into the build under a hashed name.
import anthropic from "@lobehub/icons-static-svg/icons/anthropic.svg";
import deepseek from "@lobehub/icons-static-svg/icons/deepseek-color.svg";
import google from "@lobehub/icons-static-svg/icons/google-color.svg";
import grok from "@lobehub/icons-static-svg/icons/grok.svg";
import meta from "@lobehub/icons-static-svg/icons/meta-color.svg";
import minimax from "@lobehub/icons-static-svg/icons/minimax-color.svg";
import mistral from "@lobehub/icons-static-svg/icons/mistral-color.svg";
import moonshot from "@lobehub/icons-static-svg/icons/moonshot.svg";
import nvidia from "@lobehub/icons-static-svg/icons/nvidia-color.svg";
import openai from "@lobehub/icons-static-svg/icons/openai.svg";
import qwen from "@lobehub/icons-static-svg/icons/qwen-color.svg";
import xiaomi from "@lobehub/icons-static-svg/icons/xiaomimimo.svg";
import zai from "@lobehub/icons-static-svg/icons/zai.svg";
import { Bot } from "lucide-react";
import type { StaticImageData } from "next/image";

import { PROVIDER_NAMES, providerOf } from "@/lib/providers";
import { cn } from "@/lib/utils";

// A mono mark is drawn in the text colour, so it shows on light and dark backgrounds alike.
// Turbopack imports an SVG as its URL; webpack as image data with `src`.
type Logo = { image: string | StaticImageData; mono: boolean };

function urlOf(image: string | StaticImageData): string {
  return typeof image === "string" ? image : image.src;
}

const LOGOS: Record<string, Logo> = {
  anthropic: { image: anthropic, mono: true },
  deepseek: { image: deepseek, mono: false },
  google: { image: google, mono: false },
  "meta-llama": { image: meta, mono: false },
  minimax: { image: minimax, mono: false },
  mistralai: { image: mistral, mono: false },
  moonshotai: { image: moonshot, mono: true },
  nvidia: { image: nvidia, mono: false },
  openai: { image: openai, mono: true },
  qwen: { image: qwen, mono: false },
  "x-ai": { image: grok, mono: true },
  xiaomi: { image: xiaomi, mono: true },
  "z-ai": { image: zai, mono: true },
};

/** The provider's logo for a model id; a generic bot for an unknown provider or a bare id. */
export function ProviderLogo({ model, className }: { model: string | null | undefined; className?: string }) {
  const provider = providerOf(model);
  const logo = provider ? LOGOS[provider] : undefined;
  const name = provider ? (PROVIDER_NAMES[provider] ?? provider) : "Unknown provider";
  const box = cn("inline-block size-4 shrink-0", className);
  if (!logo) return <Bot aria-label={name} className={cn(box, "text-muted-foreground")} />;
  if (logo.mono) {
    const mask = `url(${urlOf(logo.image)}) center / contain no-repeat`;
    return <span role="img" aria-label={name} title={name} className={cn(box, "bg-current")} style={{ mask, WebkitMask: mask }} />;
  }
  // eslint-disable-next-line @next/next/no-img-element -- a 16px SVG mark needs no image optimization
  return <img src={urlOf(logo.image)} alt={name} title={name} width={16} height={16} className={box} />;
}
