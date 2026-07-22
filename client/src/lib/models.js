// Models the gateway can route, grouped by provider. Mirrors the backend
// registry's prefix rules (gpt-* -> OpenAI, gemini-* -> Gemini, etc.).
export const MODEL_CATALOG = [
  { provider: "OpenAI", models: ["gpt-4o-mini", "gpt-4o"] },
  { provider: "Anthropic", models: ["claude-3-5-sonnet", "claude-3-5-haiku"] },
  { provider: "Google Gemini", models: ["gemini-1.5-flash", "gemini-1.5-pro"] },
  { provider: "Azure OpenAI", models: ["azure/your-deployment"] },
];

export const PROVIDER_ROUTES = [
  { prefix: "gpt-*", provider: "OpenAI", note: "default" },
  { prefix: "gemini-*", provider: "Google Gemini" },
  { prefix: "claude-*", provider: "Anthropic" },
  { prefix: "azure/<deployment>", provider: "Azure OpenAI" },
];
