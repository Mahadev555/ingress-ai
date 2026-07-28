// Thin client over the Ingress AI gateway API. Every gateway endpoint the
// dashboard uses is bound here in one place.

export class ApiError extends Error {
  constructor(status, data) {
    const err = data?.detail?.error || data?.error || null;
    const message =
      err?.message ||
      (typeof data?.detail === "string" ? data.detail : null) ||
      `Request failed (${status})`;
    super(message);
    this.status = status;
    this.type = err?.type || null; // e.g. rate_limit_exceeded, budget_exceeded, upstream_rate_limit
    this.data = data;
  }
}

function safeJson(text) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

async function request(url, { method = "GET", body, headers = {} } = {}) {
  const res = await fetch(url, {
    method,
    headers: {
      ...(body ? { "Content-Type": "application/json" } : {}),
      ...headers,
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  const data = text ? safeJson(text) : null;
  if (!res.ok) throw new ApiError(res.status, data);
  return data;
}

export function createApi({ baseUrl = "", adminToken = "" } = {}) {
  const admin = () => ({ "X-Admin-Token": adminToken });

  return {
    // Public
    health: () => request(`${baseUrl}/health`),
    metrics: () => fetch(`${baseUrl}/metrics`).then((r) => r.text()),
    models: () => request(`${baseUrl}/v1/models`),
    config: () => request(`${baseUrl}/v1/config`),

    // Admin — keys
    listKeys: () => request(`${baseUrl}/admin/keys`, { headers: admin() }),
    createKey: (body) =>
      request(`${baseUrl}/admin/keys`, { method: "POST", body, headers: admin() }),
    updateKey: (id, body) =>
      request(`${baseUrl}/admin/keys/${id}`, { method: "PATCH", body, headers: admin() }),
    revokeKey: (id) =>
      request(`${baseUrl}/admin/keys/${id}`, { method: "DELETE", headers: admin() }),

    // Admin — usage
    usage: (days = 0) =>
      request(`${baseUrl}/admin/usage${days ? `?days=${days}` : ""}`, { headers: admin() }),
    usageByKey: () => request(`${baseUrl}/admin/usage/by-key`, { headers: admin() }),
    usageByModel: () => request(`${baseUrl}/admin/usage/by-model`, { headers: admin() }),
    usageRecent: (limit = 20) =>
      request(`${baseUrl}/admin/usage/recent?limit=${limit}`, { headers: admin() }),
    usageTimeseries: (days = 14) =>
      request(`${baseUrl}/admin/usage/timeseries?days=${days}`, { headers: admin() }),
    usageByTag: (days = 0) =>
      request(`${baseUrl}/admin/usage/by-tag${days ? `?days=${days}` : ""}`, { headers: admin() }),
    audit: (limit = 50) =>
      request(`${baseUrl}/admin/audit?limit=${limit}`, { headers: admin() }),

    // Admin — model registry
    listModelConfigs: () => request(`${baseUrl}/admin/models`, { headers: admin() }),
    createModelConfig: (body) =>
      request(`${baseUrl}/admin/models`, { method: "POST", body, headers: admin() }),
    updateModelConfig: (id, body) =>
      request(`${baseUrl}/admin/models/${id}`, { method: "PATCH", body, headers: admin() }),
    deleteModelConfig: (id) =>
      request(`${baseUrl}/admin/models/${id}`, { method: "DELETE", headers: admin() }),

    // Admin — provider credentials (where keys live)
    listProviders: () => request(`${baseUrl}/admin/providers`, { headers: admin() }),
    createProvider: (body) =>
      request(`${baseUrl}/admin/providers`, { method: "POST", body, headers: admin() }),
    updateProvider: (id, body) =>
      request(`${baseUrl}/admin/providers/${id}`, { method: "PATCH", body, headers: admin() }),
    deleteProvider: (id) =>
      request(`${baseUrl}/admin/providers/${id}`, { method: "DELETE", headers: admin() }),

    // Admin — model deployments (load balancing)
    listDeployments: () => request(`${baseUrl}/admin/deployments`, { headers: admin() }),
    createDeployment: (body) =>
      request(`${baseUrl}/admin/deployments`, { method: "POST", body, headers: admin() }),
    updateDeployment: (id, body) =>
      request(`${baseUrl}/admin/deployments/${id}`, { method: "PATCH", body, headers: admin() }),
    deleteDeployment: (id) =>
      request(`${baseUrl}/admin/deployments/${id}`, { method: "DELETE", headers: admin() }),

    // Admin — MCP servers (the MCP gateway registry)
    listMcpServers: () => request(`${baseUrl}/admin/mcp/servers`, { headers: admin() }),
    createMcpServer: (body) =>
      request(`${baseUrl}/admin/mcp/servers`, { method: "POST", body, headers: admin() }),
    updateMcpServer: (id, body) =>
      request(`${baseUrl}/admin/mcp/servers/${id}`, { method: "PATCH", body, headers: admin() }),
    deleteMcpServer: (id) =>
      request(`${baseUrl}/admin/mcp/servers/${id}`, { method: "DELETE", headers: admin() }),

    // Admin — teams (tenancy)
    listTeams: () => request(`${baseUrl}/admin/teams`, { headers: admin() }),
    createTeam: (body) =>
      request(`${baseUrl}/admin/teams`, { method: "POST", body, headers: admin() }),
    updateTeam: (id, body) =>
      request(`${baseUrl}/admin/teams/${id}`, { method: "PATCH", body, headers: admin() }),
    deleteTeam: (id) =>
      request(`${baseUrl}/admin/teams/${id}`, { method: "DELETE", headers: admin() }),
    teamUsage: (id) => request(`${baseUrl}/admin/teams/${id}/usage`, { headers: admin() }),

    // Chat (playground) — non-streaming
    chat: (apiKey, body, conversationId) =>
      request(`${baseUrl}/v1/chat/completions`, {
        method: "POST",
        body,
        headers: {
          Authorization: `Bearer ${apiKey}`,
          ...(conversationId ? { "X-Conversation-ID": conversationId } : {}),
        },
      }),
  };
}

// Streaming chat: reads the SSE response and calls onDelta with each token.
export async function chatStream(
  { baseUrl = "", apiKey, conversationId },
  body,
  { onDelta, signal } = {}
) {
  const res = await fetch(`${baseUrl}/v1/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
      ...(conversationId ? { "X-Conversation-ID": conversationId } : {}),
    },
    body: JSON.stringify({ ...body, stream: true }),
    signal,
  });

  if (!res.ok || !res.body) {
    const text = await res.text();
    throw new ApiError(res.status, safeJson(text));
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let boundary;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const chunk = buffer.slice(0, boundary).trim();
      buffer = buffer.slice(boundary + 2);
      if (!chunk.startsWith("data:")) continue;

      const data = chunk.slice(5).trim();
      if (data === "[DONE]") return;

      const json = safeJson(data);
      if (!json) continue;
      if (json.error) {
        onDelta?.(`\n\n[stream error: ${json.error.message}]`);
        return;
      }
      const delta = json.choices?.[0]?.delta?.content;
      if (delta) onDelta?.(delta);
    }
  }
}
