import { useState } from "react";
import { Activity, Coins, Cpu, Gauge, RefreshCw } from "lucide-react";
import { useSettings } from "../lib/settings.jsx";
import { useAsync } from "../lib/useAsync.js";
import { Button, Card, CardHeader, cx, ErrorState, Spinner } from "../components/ui.jsx";
import { ConnectPrompt } from "../components/ConnectPrompt.jsx";

function Stat({ icon: Icon, label, value, tone }) {
  const tones = {
    brand: "bg-brand-50 text-brand-600",
    emerald: "bg-emerald-50 text-emerald-600",
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

export default function Usage() {
  const { api, hasAdmin } = useSettings();
  const usage = useAsync(() => api.usage(), [api], { enabled: hasAdmin });
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
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Stat icon={Activity} label="Requests" value={new Intl.NumberFormat().format(u.total_requests ?? 0)} tone="brand" />
          <Stat icon={Cpu} label="Tokens" value={new Intl.NumberFormat().format(u.total_tokens ?? 0)} tone="emerald" />
          <Stat icon={Coins} label="Est. cost" value={`$${(u.total_cost_usd ?? 0).toFixed(4)}`} tone="amber" />
        </div>
      )}

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
