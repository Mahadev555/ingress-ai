import { lazy, Suspense, useEffect, useMemo, useState } from "react";
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
  MultiSelect,
  Spinner,
} from "../components/ui.jsx";
import { ConnectPrompt } from "../components/ConnectPrompt.jsx";

// Recharts is heavy, so it's split into its own chunk that only loads when
// the Usage page is opened.
const UsageCharts = lazy(() => import("../components/UsageCharts.jsx"));

const fmt = (n) => new Intl.NumberFormat().format(n ?? 0);

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

function Segmented({ options, value, onChange }) {
  return (
    <div className="inline-flex rounded-lg border border-slate-200 bg-slate-100 p-0.5">
      {options.map((o) => (
        <button
          key={o.label}
          onClick={() => onChange(o.days)}
          className={cx(
            "rounded-md px-3 py-1 text-xs font-semibold transition-colors",
            value === o.days ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// Segmented toggle for the summary boxes (0 = all time).
const SUMMARY_RANGES = [
  { label: "30D", days: 30 },
  { label: "60D", days: 60 },
  { label: "All", days: 0 },
];

// Segmented toggle for the trend charts.
const RANGES = [
  { label: "7D", days: 7 },
  { label: "30D", days: 30 },
  { label: "90D", days: 90 },
];

export default function Usage() {
  const { api, hasAdmin } = useSettings();
  const [summaryDays, setSummaryDays] = useState(30);
  const [days, setDays] = useState(7);
  const [selectedModels, setSelectedModels] = useState([]); // [] = all models
  const usage = useAsync(() => api.usage(summaryDays), [api, summaryDays], { enabled: hasAdmin });
  const byKey = useAsync(() => api.usageByKey(), [api], { enabled: hasAdmin });
  const byModel = useAsync(() => api.usageByModel(), [api], { enabled: hasAdmin });
  const series = useAsync(() => api.usageTimeseries(days), [api, days], { enabled: hasAdmin });
  const [metrics, setMetrics] = useState(null);
  const [loadingMetrics, setLoadingMetrics] = useState(false);

  // Models actually present in the current window, for the chart filter dropdown.
  const usedModels = useMemo(() => {
    const set = new Set((series.data ?? []).map((r) => r.model));
    return [...set].sort();
  }, [series.data]);

  // Drop any selected models that no longer appear in the current window.
  useEffect(() => {
    setSelectedModels((prev) => {
      const next = prev.filter((m) => usedModels.includes(m));
      return next.length === prev.length ? prev : next;
    });
  }, [usedModels]);

  const chartRows =
    selectedModels.length === 0
      ? series.data ?? []
      : (series.data ?? []).filter((r) => selectedModels.includes(r.model));

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
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Summary</h2>
          <p className="text-xs text-slate-500">Totals across all keys and models.</p>
        </div>
        <Segmented options={SUMMARY_RANGES} value={summaryDays} onChange={setSummaryDays} />
      </div>

      {usage.loading ? (
        <Spinner />
      ) : usage.error ? (
        <ErrorState error={usage.error} onRetry={usage.reload} />
      ) : (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
          <Stat icon={Activity} label="Requests" value={fmt(u.total_requests)} />
          <Stat icon={ArrowDownToLine} label="Input" value={fmt(u.prompt_tokens)} />
          <Stat icon={ArrowUpFromLine} label="Output" value={fmt(u.completion_tokens)} />
          <Stat icon={Cpu} label="Total tokens" value={fmt(u.total_tokens)} />
          <Stat icon={Coins} label="Est. cost" value={`$${(u.total_cost_usd ?? 0).toFixed(4)}`} />
        </div>
      )}

      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Usage over time</h2>
          <p className="text-xs text-slate-500">Daily trends, grouped by model and status.</p>
        </div>
        <div className="flex items-center gap-2">
          <MultiSelect
            options={usedModels}
            value={selectedModels}
            onChange={setSelectedModels}
            allLabel="All models"
            className="w-44"
          />
          <Segmented options={RANGES} value={days} onChange={setDays} />
          <Button variant="ghost" onClick={series.reload}>
            <RefreshCw size={14} /> Refresh
          </Button>
        </div>
      </div>

      {series.loading ? (
        <Spinner />
      ) : series.error ? (
        <ErrorState error={series.error} onRetry={series.reload} />
      ) : (
        <Suspense fallback={<Spinner label="Loading charts…" />}>
          <UsageCharts rows={chartRows} days={days} />
        </Suspense>
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
