// Turns the flat /admin/usage/timeseries rows into the shapes each chart needs.
// A "row" is { day, model, provider, status, requests, prompt_tokens,
// completion_tokens, total_tokens, cost_usd }.

// A restrained, professional palette (deep + muted) for the per-model lines —
// distinct enough to tell apart, quiet enough to look production-grade.
export const SERIES_COLORS = [
  "#4f46e5", // indigo
  "#0d9488", // teal
  "#64748b", // slate
  "#7c3aed", // violet
  "#0284c7", // blue
  "#be185d", // rose
];

export function statusColor(status) {
  if (status === "429") return "#d97706"; // rate limited (amber)
  if (status.startsWith("5")) return "#dc2626"; // server errors (red)
  return "#94a3b8"; // other 4xx (slate)
}

function utcDay(y, m, d) {
  return new Date(Date.UTC(y, m, d)).toISOString().slice(0, 10);
}

// A continuous list of UTC day labels (YYYY-MM-DD) so charts have no gaps
// even on days with no traffic.
export function dayRange(days) {
  const out = [];
  const now = new Date();
  for (let i = days - 1; i >= 0; i--) {
    out.push(utcDay(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() - i));
  }
  return out;
}

// For "All time": a continuous range spanning the earliest → latest day present
// in the data (capped so the axis never explodes).
export function dayRangeFromData(rows) {
  if (!rows.length) return [];
  const sorted = rows.map((r) => r.day).sort();
  const out = [];
  let d = new Date(`${sorted[0]}T00:00:00Z`);
  const end = new Date(`${sorted[sorted.length - 1]}T00:00:00Z`);
  while (d <= end) {
    out.push(d.toISOString().slice(0, 10));
    d = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() + 1));
  }
  return out.slice(-365);
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
      // Grounded at 0 on no-traffic days so the line rises from the baseline
      // instead of floating as a disconnected segment.
      successRate: b.requests ? Math.round((b.success / b.requests) * 100) : 0,
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
