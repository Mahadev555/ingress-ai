import { Link } from "react-router-dom";
import {
  Activity,
  Coins,
  Cpu,
  KeyRound,
  Layers,
  ArrowRight,
} from "lucide-react";
import { useSettings } from "../lib/settings.jsx";
import { useAsync } from "../lib/useAsync.js";
import { PROVIDER_ROUTES } from "../lib/models.js";
import { Badge, Button, Card, CardHeader, cx, ErrorState, Spinner } from "../components/ui.jsx";
import { ConnectPrompt } from "../components/ConnectPrompt.jsx";

function Stat({ icon: Icon, label, value, sub, tone = "brand" }) {
  const tones = {
    brand: "bg-brand-50 text-brand-600",
    emerald: "bg-emerald-50 text-emerald-600",
    amber: "bg-amber-50 text-amber-600",
    slate: "bg-slate-100 text-slate-500",
  };
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          {label}
        </span>
        <span className={cx("flex h-9 w-9 items-center justify-center rounded-lg", tones[tone])}>
          <Icon size={18} />
        </span>
      </div>
      <div className="mt-3 text-2xl font-bold tracking-tight text-slate-900">{value}</div>
      {sub && <div className="mt-1 text-xs text-slate-400">{sub}</div>}
    </Card>
  );
}

function fmt(n) {
  return new Intl.NumberFormat().format(n ?? 0);
}

export default function Overview() {
  const { api, hasAdmin } = useSettings();

  const usage = useAsync(() => api.usage(), [api], { enabled: hasAdmin });
  const keys = useAsync(() => api.listKeys(), [api], { enabled: hasAdmin });

  if (!hasAdmin) return <ConnectPrompt what="the overview" />;
  if (usage.loading || keys.loading) return <Spinner />;
  if (usage.error) return <ErrorState error={usage.error} onRetry={usage.reload} />;

  const u = usage.data ?? {};
  const activeKeys = (keys.data ?? []).filter((k) => k.active).length;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat icon={Activity} label="Requests" value={fmt(u.total_requests)} sub="all time" />
        <Stat icon={Cpu} label="Tokens" value={fmt(u.total_tokens)} sub="prompt + completion" tone="emerald" />
        <Stat
          icon={Coins}
          label="Est. cost"
          value={`$${(u.total_cost_usd ?? 0).toFixed(4)}`}
          sub="across all providers"
          tone="amber"
        />
        <Stat icon={KeyRound} label="Active keys" value={fmt(activeKeys)} sub={`${keys.data?.length ?? 0} total`} tone="slate" />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Provider routing"
            subtitle="Requests route to a provider purely by model name"
          />
          <div className="divide-y divide-slate-100">
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
  );
}
