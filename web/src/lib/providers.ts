// Model providers by the prefix of an OpenRouter model id ("anthropic/claude-haiku-5.5").

export const PROVIDER_NAMES: Record<string, string> = {
  anthropic: "Anthropic",
  deepseek: "DeepSeek",
  google: "Google",
  "meta-llama": "Meta",
  minimax: "MiniMax",
  mistralai: "Mistral",
  moonshotai: "Moonshot AI",
  nvidia: "NVIDIA",
  openai: "OpenAI",
  qwen: "Qwen",
  "x-ai": "xAI",
  xiaomi: "Xiaomi",
  "z-ai": "Z.ai",
};

/** The provider prefix of a model id, or null for an id without one. */
export function providerOf(modelId: string | null | undefined): string | null {
  if (!modelId) return null;
  const slash = modelId.indexOf("/");
  return slash > 0 ? modelId.slice(0, slash) : null;
}
