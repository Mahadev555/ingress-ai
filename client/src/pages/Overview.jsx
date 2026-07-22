import { Link } from "react-router-dom";
import {
  Activity,
  Coins,
  Cpu,
  KeyRound,
  Layers,
  ArrowRight,
  Zap,
  RefreshCw,
  Database,
} from "lucide-react";
import { useSettings } from "../lib/settings.jsx";
import { useAsync } from "../lib/useAsync.js";
import { PROVIDER_ROUTES } from "../lib/models.js";
import { Badge, Button, Card, CardHeader, cx, EmptyState, ErrorState, Spinner } from "../components/ui.jsx";
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

function Stat({ icon: Icon, label, value, sub }) {
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          {label}
        </span>
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100 text-slate-500">
          <Icon size={18} />
        </span>
      </div>
      <div className="mt-3 text-2xl font-bold tracking-tight text-slate-900">{value}</div>
      {sub && <div className="mt-1 text-xs text-slate-400">{sub}</div>}
    </Card>
  );
}

// Tiny bar chart of per-request token totals (oldest → newest, left → right).
function Sparkbars({ values }) {
  if (!values.length) {
    return <div className="h-14 rounded-lg bg-slate-50" />;
  }
  const max = Math.max(1, ...values);
  return (
    <div className="flex h-14 items-end gap-[3px]">
      {values.map((v, i) => (
        <div
          key={i}
          title={`${fmt(v)} tokens`}
          className="flex-1 rounded-sm bg-gradient-to-t from-brand-500/60 to-brand-500"
          style={{ height: `${Math.max(8, (v / max) * 100)}%` }}
        />
      ))}
    </div>
  );
}

export default function Overview() {
  const { api, hasAdmin } = useSettings();

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
  // Oldest → newest for the sparkline (the feed itself is newest-first).
  const spark = [...feed].reverse().map((r) => r.total_tokens);

  const models = (byModel.data ?? []).slice(0, 5);
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

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat icon={Activity} label="Requests" value={fmt(u.total_requests)} sub="all time" />
        <Stat icon={Cpu} label="Tokens" value={fmt(u.total_tokens)} sub="prompt + completion" />
        <Stat
          icon={Coins}
          label="Est. cost"
          value={`$${(u.total_cost_usd ?? 0).toFixed(4)}`}
          sub="across all providers"
        />
        <Stat icon={KeyRound} label="Active keys" value={fmt(activeKeys)} sub={`${keys.data?.length ?? 0} total`} />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Live activity feed */}
        <Card className="lg:col-span-2">
          <CardHeader
            title="Live traffic"
            subtitle="Most recent requests through the gateway"
            action={<Badge tone="brand">last {feed.length}</Badge>}
          />
          <div className="px-5 pt-4">
            <Sparkbars values={spark} />
            <div className="mt-1 text-[11px] text-slate-400">tokens per request · oldest → newest</div>
          </div>

          <div className="mt-2 max-h-[22rem] divide-y divide-slate-100 overflow-y-auto">
            {feed.length === 0 ? (
              <EmptyState
                icon={Zap}
                title="No requests yet"
                description="Send one from the playground to see it stream in here."
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
                    {r.latency_ms}ms
                  </span>
                  <span className="w-16 text-right text-xs text-slate-400">{relTime(r.created_at)}</span>
                </div>
              ))
            )}
          </div>
        </Card>

        {/* Top models + quick actions */}
        <div className="space-y-6">
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
                          width: `${(m.total_tokens / modelMax) * 100}%`,
                          backgroundColor: providerColor(m.provider),
                        }}
                      />
                    </div>
                  </div>
                ))
              )}
            </div>
          </Card>

          <Card className="flex flex-col">
            <CardHeader title="Quick actions" />
            <div className="flex flex-1 flex-col gap-2 p-4">
              <Link to="/keys">
                <Button variant="secondary" className="w-full justify-between">
                  Create an API key <ArrowRight size={15} />
                </Button>
              </Link>
              <Link to="/playground">
                <Button variant="secondary" className="w-full justify-between">
                  Open the playground <ArrowRight size={15} />
                </Button>
              </Link>
              <Link to="/usage">
                <Button variant="secondary" className="w-full justify-between">
                  View usage &amp; metrics <ArrowRight size={15} />
                </Button>
              </Link>
            </div>
          </Card>
        </div>
      </div>

      {/* Provider routing — reference, demoted below the live data */}
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
