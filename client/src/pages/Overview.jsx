import { Activity, Coins, Cpu, KeyRound, Layers, Zap, RefreshCw, Database } from "lucide-react";
import { useSettings } from "../lib/settings.jsx";
import { useAsync } from "../lib/useAsync.js";
import { PROVIDER_ROUTES } from "../lib/models.js";
import { Badge, Button, Card, CardHeader, EmptyState, ErrorState, Spinner } from "../components/ui.jsx";
import { ConnectPrompt } from "../components/ConnectPrompt.jsx";

// Provider → accent color, used for the feed dots and the top-models bars.
const PROVIDER_COLOR = {
  openai: "#10a37f",
  anthropic: "#d97757",
  gemini: "#4285f4",
  azure: "#0078d4",
};
const providerColor = (p) => PROVIDER_COLOR[p] ?? "#6366f1";

function fmt(n) {
  return new Intl.NumberFormat().format(n ?? 0);
}

function fmtLatency(ms) {
  if (!ms) return "—";
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

function relTime(iso) {
  if (!iso) return "—";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function statusTone(status) {
  if (status >= 500) return "red";
  if (status === 429) return "amber";
  if (status >= 400) return "red";
  return "green";
}

function Stat({ icon: Icon, label, value }) {
  return (
    <Card className="px-4 py-3">
      <div className="flex items-center gap-2.5">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-slate-100 text-slate-500">
          <Icon size={15} />
        </span>
        <div className="min-w-0">
          <div className="text-[11px] font-medium uppercase tracking-wide text-slate-400">{label}</div>
          <div className="text-lg font-bold leading-tight text-slate-900">{value}</div>
        </div>
      </div>
    </Card>
  );
}

export default function Overview() {
  const { api, hasAdmin, costTracking } = useSettings();

  const usage = useAsync(() => api.usage(), [api], { enabled: hasAdmin });
  const keys = useAsync(() => api.listKeys(), [api], { enabled: hasAdmin });
  const recent = useAsync(() => api.usageRecent(24), [api], { enabled: hasAdmin });
  const byModel = useAsync(() => api.usageByModel(), [api], { enabled: hasAdmin });

  if (!hasAdmin) return <ConnectPrompt what="the overview" />;
  if (usage.loading || keys.loading) return <Spinner />;
  if (usage.error) return <ErrorState error={usage.error} onRetry={usage.reload} />;

  const u = usage.data ?? {};
  const activeKeys = (keys.data ?? []).filter((k) => k.active).length;
  const feed = recent.data ?? [];
  const models = (byModel.data ?? []).filter((m) => m.total_tokens > 0).slice(0, 5);
  const modelMax = Math.max(1, ...models.map((m) => m.total_tokens));

  const refreshAll = () => {
    usage.reload();
    keys.reload();
    recent.reload();
    byModel.reload();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-end">
        <Button variant="ghost" onClick={refreshAll}>
          <RefreshCw size={14} /> Refresh
        </Button>
      </div>

      <div className={`grid grid-cols-2 gap-4 ${costTracking ? "lg:grid-cols-4" : "lg:grid-cols-3"}`}>
        <Stat icon={Activity} label="Requests" value={fmt(u.total_requests)} />
        <Stat icon={Cpu} label="Tokens" value={fmt(u.total_tokens)} />
        {costTracking && (
          <Stat icon={Coins} label="Est. cost" value={`$${(u.total_cost_usd ?? 0).toFixed(4)}`} />
        )}
        <Stat icon={KeyRound} label="Active keys" value={fmt(activeKeys)} />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Live activity feed */}
        <Card className="lg:col-span-2">
          <CardHeader
            title="Live traffic"
            subtitle="Most recent requests through the gateway"
          />
          <div className="max-h-[26rem] divide-y divide-slate-100 overflow-y-auto">
            {feed.length === 0 ? (
              <EmptyState
                icon={Zap}
                title="No requests yet"
                description="Send one from the playground to see it appear here."
              />
            ) : (
              feed.map((r) => (
                <div key={r.id} className="flex items-center gap-3 px-5 py-2.5 text-sm">
                  <span
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{ backgroundColor: providerColor(r.provider) }}
                    title={r.provider}
                  />
                  <code className="min-w-0 flex-1 truncate font-medium text-slate-800">
                    {r.model}
                  </code>
                  {r.cache_hit && <Badge tone="slate">cache</Badge>}
                  <Badge tone={statusTone(r.status)}>{r.status}</Badge>
                  <span className="w-16 text-right tabular-nums text-slate-500">
                    {fmt(r.total_tokens)} tok
                  </span>
                  <span className="hidden w-14 text-right tabular-nums text-slate-400 sm:block">
                    {fmtLatency(r.latency_ms)}
                  </span>
                  <span className="w-16 text-right text-xs text-slate-400">{relTime(r.created_at)}</span>
                </div>
              ))
            )}
          </div>
        </Card>

        {/* Top models */}
        <Card>
          <CardHeader title="Top models" subtitle="By total tokens" />
          <div className="space-y-3 p-5">
            {models.length === 0 ? (
              <p className="py-4 text-center text-sm text-slate-400">No usage yet.</p>
            ) : (
              models.map((m) => (
                <div key={`${m.provider}:${m.model}`}>
                  <div className="mb-1 flex items-center justify-between text-xs">
                    <code className="truncate font-medium text-slate-700">{m.model}</code>
                    <span className="shrink-0 tabular-nums text-slate-500">{fmt(m.total_tokens)}</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${Math.max(3, (m.total_tokens / modelMax) * 100)}%`,
                        backgroundColor: providerColor(m.provider),
                      }}
                    />
                  </div>
                </div>
              ))
            )}
          </div>
        </Card>
      </div>

      {/* Provider routing — how model names map to upstream providers */}
      <Card>
        <CardHeader
          title="Provider routing"
          subtitle="Requests route to a provider purely by model name"
          action={<Database size={16} className="text-slate-400" />}
        />
        <div className="grid grid-cols-1 divide-y divide-slate-100 sm:grid-cols-2 sm:divide-y-0">
          {PROVIDER_ROUTES.map((r) => (
            <div key={r.prefix} className="flex items-center justify-between px-5 py-3">
              <div className="flex items-center gap-3">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-100 text-slate-500">
                  <Layers size={16} />
                </span>
                <div>
                  <code className="text-sm font-semibold text-slate-800">{r.prefix}</code>
                  {r.note && (
                    <Badge tone="slate" className="ml-2">
                      {r.note}
                    </Badge>
                  )}
                </div>
              </div>
              <span className="text-sm text-slate-500">{r.provider}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
