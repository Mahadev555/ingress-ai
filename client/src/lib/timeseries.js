// Turns the flat /admin/usage/timeseries rows into the shapes each chart needs.
// A "row" is { day, model, provider, status, requests, prompt_tokens,
// completion_tokens, total_tokens, cost_usd }.

// Colors reused across the per-series charts.
export const SERIES_COLORS = [
  "#6366f1", "#10a37f", "#d97757", "#4285f4",
  "#f59e0b", "#ec4899", "#0ea5e9", "#8b5cf6",
];

export function statusColor(status) {
  if (status === "429") return "#f59e0b"; // rate limited
  if (status.startsWith("5")) return "#ef4444"; // server errors
  return "#94a3b8"; // other 4xx
}

// A continuous list of UTC day labels (YYYY-MM-DD) so charts have no gaps
// even on days with no traffic.
export function dayRange(days) {
  const out = [];
  const now = new Date();
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() - i));
    out.push(d.toISOString().slice(0, 10));
  }
  return out;
}

export function shortDay(day) {
  return new Date(`${day}T00:00:00Z`).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

// Requests + success rate per day.
export function pivotRequests(rows, dayList) {
  const byDay = new Map(dayList.map((d) => [d, { requests: 0, success: 0 }]));
  for (const r of rows) {
    const b = byDay.get(r.day);
    if (!b) continue;
    b.requests += r.requests;
    if (r.status < 400) b.success += r.requests;
  }
  return dayList.map((d) => {
    const b = byDay.get(d);
    return {
      day: d,
      requests: b.requests,
      successRate: b.requests ? Math.round((b.success / b.requests) * 100) : null,
    };
  });
}

// Error counts per day, split by HTTP status (only 4xx/5xx).
export function pivotErrors(rows, dayList) {
  const keys = new Set();
  const byDay = new Map(dayList.map((d) => [d, { day: d }]));
  for (const r of rows) {
    if (r.status < 400) continue;
    const key = String(r.status);
    byDay.get(r.day)[key] = (byDay.get(r.day)[key] || 0) + r.requests;
    keys.add(key);
  }
  const list = [...keys].sort();
  const data = dayList.map((d) => {
    const b = byDay.get(d);
    for (const k of list) if (!(k in b)) b[k] = 0;
    return b;
  });
  return { data, keys: list };
}

// A metric (e.g. prompt_tokens) per day, one column per model.
export function pivotByModel(rows, dayList, field) {
  const keys = new Set();
  const byDay = new Map(dayList.map((d) => [d, { day: d }]));
  for (const r of rows) {
    byDay.get(r.day)[r.model] = (byDay.get(r.day)[r.model] || 0) + r[field];
    keys.add(r.model);
  }
  const list = [...keys];
  const data = dayList.map((d) => {
    const b = byDay.get(d);
    for (const m of list) if (!(m in b)) b[m] = 0;
    return b;
  });
  return { data, keys: list };
}
