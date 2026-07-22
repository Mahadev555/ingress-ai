// Fallback catalog used only if GET /v1/models can't be reached. The live list
// comes from the gateway (driven by the AVAILABLE_MODELS env var).
export const MODEL_CATALOG = [
  { provider: "OpenAI", models: ["gpt-4o-mini", "gpt-4o"] },
  { provider: "Anthropic", models: ["claude-3-5-sonnet", "claude-3-5-haiku"] },
  { provider: "Google Gemini", models: ["gemini-1.5-flash", "gemini-1.5-pro"] },
];

export const PROVIDER_ROUTES = [
  { prefix: "gpt-*", provider: "OpenAI", note: "default" },
  { prefix: "gemini-*", provider: "Google Gemini" },
  { prefix: "claude-*", provider: "Anthropic" },
  { prefix: "azure/<deployment>", provider: "Azure OpenAI" },
];

// Maps the gateway's `owned_by` value to a friendly group label.
const PROVIDER_LABELS = {
  openai: "OpenAI",
  anthropic: "Anthropic",
  gemini: "Google Gemini",
  azure: "Azure OpenAI",
};

// Turn the /v1/models response into [{ provider, models: [...] }] groups.
export function groupModels(data) {
  if (!data?.length) return null;
  const groups = new Map();
  for (const m of data) {
    const label = PROVIDER_LABELS[m.owned_by] ?? m.owned_by ?? "Other";
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label).push(m.id);
  }
  return [...groups.entries()].map(([provider, models]) => ({ provider, models }));
}
