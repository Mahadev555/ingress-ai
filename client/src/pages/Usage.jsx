import { useState } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowUpFromLine,
  Coins,
  Cpu,
  Gauge,
  KeyRound,
  Layers,
  RefreshCw,
} from "lucide-react";
import { useSettings } from "../lib/settings.jsx";
import { useAsync } from "../lib/useAsync.js";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  cx,
  EmptyState,
  ErrorState,
  Spinner,
} from "../components/ui.jsx";
import { ConnectPrompt } from "../components/ConnectPrompt.jsx";

const fmt = (n) => new Intl.NumberFormat().format(n ?? 0);

function Stat({ icon: Icon, label, value, tone }) {
  const tones = {
    brand: "bg-brand-50 text-brand-600",
    emerald: "bg-emerald-50 text-emerald-600",
    sky: "bg-sky-50 text-sky-600",
    amber: "bg-amber-50 text-amber-600",
  };
  return (
    <Card className="p-5">
      <div className="flex items-center gap-3">
        <span className={cx("flex h-10 w-10 items-center justify-center rounded-lg", tones[tone])}>
          <Icon size={18} />
        </span>
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</div>
          <div className="text-xl font-bold text-slate-900">{value}</div>
        </div>
      </div>
    </Card>
  );
}

function BudgetCell({ used, budget }) {
  if (budget == null) return <span className="text-slate-400">—</span>;
  const pct = Math.min(100, Math.round((used / budget) * 100));
  const over = used >= budget;
  return (
    <div className="min-w-[120px]">
      <div className="mb-1 flex justify-between text-xs">
        <span className={over ? "font-semibold text-red-600" : "text-slate-500"}>{pct}%</span>
        <span className="tabular-nums text-slate-400">{fmt(budget)}</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
        <div
          className={cx("h-full rounded-full", over ? "bg-red-500" : "bg-brand-500")}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

const TOKEN_HEADERS = (
  <>
    <th className="px-5 py-3 text-right font-semibold">Requests</th>
    <th className="px-5 py-3 text-right font-semibold">Input</th>
    <th className="px-5 py-3 text-right font-semibold">Output</th>
    <th className="px-5 py-3 text-right font-semibold">Total</th>
    <th className="px-5 py-3 text-right font-semibold">Cost</th>
  </>
);

function TokenCells({ row }) {
  return (
    <>
      <td className="px-5 py-3 text-right tabular-nums text-slate-700">{fmt(row.requests)}</td>
      <td className="px-5 py-3 text-right tabular-nums text-slate-600">{fmt(row.prompt_tokens)}</td>
      <td className="px-5 py-3 text-right tabular-nums text-slate-600">{fmt(row.completion_tokens)}</td>
      <td className="px-5 py-3 text-right tabular-nums font-semibold text-slate-900">
        {fmt(row.total_tokens)}
      </td>
      <td className="px-5 py-3 text-right tabular-nums text-slate-700">${row.cost_usd.toFixed(4)}</td>
    </>
  );
}

export default function Usage() {
  const { api, hasAdmin } = useSettings();
  const usage = useAsync(() => api.usage(), [api], { enabled: hasAdmin });
  const byKey = useAsync(() => api.usageByKey(), [api], { enabled: hasAdmin });
  const byModel = useAsync(() => api.usageByModel(), [api], { enabled: hasAdmin });
  const [metrics, setMetrics] = useState(null);
  const [loadingMetrics, setLoadingMetrics] = useState(false);

  if (!hasAdmin) return <ConnectPrompt what="usage" />;

  const loadMetrics = async () => {
    setLoadingMetrics(true);
    try {
      setMetrics(await api.metrics());
    } catch (e) {
      setMetrics(`# failed to load metrics: ${e.message}`);
    } finally {
      setLoadingMetrics(false);
    }
  };

  const u = usage.data ?? {};

  return (
    <div className="space-y-6">
      {usage.loading ? (
        <Spinner />
      ) : usage.error ? (
        <ErrorState error={usage.error} onRetry={usage.reload} />
      ) : (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
          <Stat icon={Activity} label="Requests" value={fmt(u.total_requests)} tone="brand" />
          <Stat icon={ArrowDownToLine} label="Input" value={fmt(u.prompt_tokens)} tone="sky" />
          <Stat icon={ArrowUpFromLine} label="Output" value={fmt(u.completion_tokens)} tone="emerald" />
          <Stat icon={Cpu} label="Total tokens" value={fmt(u.total_tokens)} tone="brand" />
          <Stat icon={Coins} label="Est. cost" value={`$${(u.total_cost_usd ?? 0).toFixed(4)}`} tone="amber" />
        </div>
      )}

      <Card>
        <CardHeader
          title="Usage by key"
          subtitle="Input / output / total tokens, cost, and budget per virtual key."
          action={
            <Button variant="ghost" onClick={byKey.reload}>
              <RefreshCw size={14} /> Refresh
            </Button>
          }
        />
        {byKey.loading ? (
          <Spinner />
        ) : byKey.error ? (
          <ErrorState error={byKey.error} onRetry={byKey.reload} />
        ) : byKey.data.length === 0 ? (
          <EmptyState
            icon={KeyRound}
            title="No usage yet"
            description="Send a request with a virtual key to see per-key usage here."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-xs uppercase tracking-wide text-slate-400">
                  <th className="px-5 py-3 font-semibold">Key</th>
                  <th className="px-5 py-3 font-semibold">Name</th>
                  {TOKEN_HEADERS}
                  <th className="px-5 py-3 font-semibold">Budget</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {byKey.data.map((k) => (
                  <tr key={k.key_id} className="hover:bg-slate-50/60">
                    <td className="px-5 py-3">
                      <code className="rounded bg-slate-100 px-2 py-1 font-mono text-xs text-slate-600">
                        {k.key_prefix}…
                      </code>
                    </td>
                    <td className="px-5 py-3 font-medium text-slate-800">{k.name || "—"}</td>
                    <TokenCells row={k} />
                    <td className="px-5 py-3">
                      <BudgetCell used={k.total_tokens} budget={k.token_budget} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card>
        <CardHeader
          title="Usage by model"
          subtitle="Input / output / total tokens and cost per model."
          action={
            <Button variant="ghost" onClick={byModel.reload}>
              <RefreshCw size={14} /> Refresh
            </Button>
          }
        />
        {byModel.loading ? (
          <Spinner />
        ) : byModel.error ? (
          <ErrorState error={byModel.error} onRetry={byModel.reload} />
        ) : byModel.data.length === 0 ? (
          <EmptyState icon={Layers} title="No usage yet" description="Model usage appears once requests are made." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-xs uppercase tracking-wide text-slate-400">
                  <th className="px-5 py-3 font-semibold">Model</th>
                  <th className="px-5 py-3 font-semibold">Provider</th>
                  {TOKEN_HEADERS}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {byModel.data.map((m) => (
                  <tr key={`${m.provider}:${m.model}`} className="hover:bg-slate-50/60">
                    <td className="px-5 py-3 font-medium text-slate-800">{m.model}</td>
                    <td className="px-5 py-3">
                      <Badge tone="brand">{m.provider}</Badge>
                    </td>
                    <TokenCells row={m} />
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card>
        <CardHeader
          title="Prometheus metrics"
          subtitle="Raw /metrics output — scrape this with Prometheus and graph it in Grafana."
          action={
            <Button variant="secondary" onClick={loadMetrics} loading={loadingMetrics}>
              <Gauge size={15} /> {metrics ? "Refresh" : "Load metrics"}
            </Button>
          }
        />
        <div className="p-4">
          {metrics ? (
            <pre className="max-h-[420px] overflow-auto rounded-lg bg-slate-900 p-4 font-mono text-xs leading-relaxed text-slate-200">
              {metrics}
            </pre>
          ) : (
            <div className="flex items-center gap-2 rounded-lg border border-dashed border-slate-200 px-4 py-8 text-sm text-slate-400">
              <RefreshCw size={15} />
              Load the live counters and histograms exposed at <code className="mx-1">/metrics</code>.
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
