import { useEffect, useState } from "react";
import { BarChart2, Pencil, Plus, Trash2, Users } from "lucide-react";
import { useSettings } from "../lib/settings.jsx";
import { useAsync } from "../lib/useAsync.js";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  Field,
  Input,
  Modal,
  Select,
  Spinner,
} from "../components/ui.jsx";
import { ConnectPrompt } from "../components/ConnectPrompt.jsx";

const fmt = (n) => new Intl.NumberFormat().format(n ?? 0);
const num = (v) => (v === "" || v == null ? null : Number(v));

const EMPTY = {
  name: "",
  allowed_models: "",
  token_budget: "",
  cost_budget_usd: "",
  budget_period: "total",
};

function formFromTeam(t) {
  return {
    name: t.name || "",
    allowed_models: (t.allowed_models || []).join(", "),
    token_budget: t.token_budget ?? "",
    cost_budget_usd: t.cost_budget_usd ?? "",
    budget_period: t.budget_period || "total",
  };
}

function bodyFromForm(form) {
  return {
    name: form.name || "unnamed",
    allowed_models: form.allowed_models
      ? form.allowed_models.split(",").map((s) => s.trim()).filter(Boolean)
      : [],
    token_budget: num(form.token_budget),
    cost_budget_usd: num(form.cost_budget_usd),
    budget_period: form.budget_period || "total",
  };
}

function TeamModal({ open, team, onClose, onSaved }) {
  const { api, costTracking } = useSettings();
  const editing = !!team;
  const [form, setForm] = useState(EMPTY);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (open) {
      setForm(team ? formFromTeam(team) : EMPTY);
      setError(null);
    }
  }, [open, team]);

  const set = (patch) => setForm({ ...form, ...patch });

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const body = bodyFromForm(form);
      if (editing) await api.updateTeam(team.id, body);
      else await api.createTeam(body);
      onSaved?.();
      onClose();
    } catch (e) {
      setError(e);
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) return null;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={editing ? `Edit ${team.name || "team"}` : "Create team"}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} loading={submitting}>{editing ? "Save" : "Create"}</Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error.message}
          </div>
        )}
        <Field label="Name">
          <Input placeholder="platform-team" value={form.name}
            onChange={(e) => set({ name: e.target.value })} />
        </Field>
        <Field label="Allowed models" hint="Comma-separated. Narrows what member keys may call. Empty = no team restriction.">
          <Input placeholder="gpt-4o-mini, claude-3-5-sonnet" value={form.allowed_models}
            onChange={(e) => set({ allowed_models: e.target.value })} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Token budget" hint="Shared across all member keys.">
            <Input type="number" placeholder="1000000" value={form.token_budget}
              onChange={(e) => set({ token_budget: e.target.value })} />
          </Field>
          {costTracking && (
            <Field label="Cost budget (USD)" hint="Shared across all member keys.">
              <Input type="number" step="0.01" placeholder="200" value={form.cost_budget_usd}
                onChange={(e) => set({ cost_budget_usd: e.target.value })} />
            </Field>
          )}
        </div>
        <Field label="Budget period" hint="When the shared budget resets.">
          <Select value={form.budget_period} onChange={(e) => set({ budget_period: e.target.value })}>
            <option value="total">Total (lifetime)</option>
            <option value="daily">Daily</option>
            <option value="monthly">Monthly</option>
          </Select>
        </Field>
      </div>
    </Modal>
  );
}

function UsageModal({ team, onClose }) {
  const { api, costTracking } = useSettings();
  const usage = useAsync(() => api.teamUsage(team.id), [api, team?.id], { enabled: !!team });
  const tiles = [
    { label: "Requests", value: fmt(usage.data?.requests) },
    { label: "Total tokens", value: fmt(usage.data?.total_tokens) },
    ...(costTracking
      ? [{ label: "Cost", value: `$${(usage.data?.cost_usd ?? 0).toFixed(4)}` }]
      : []),
  ];
  return (
    <Modal open={!!team} onClose={onClose} title={team ? `Usage — ${team.name || "team"}` : ""}>
      {usage.loading ? (
        <Spinner />
      ) : usage.error ? (
        <ErrorState error={usage.error} onRetry={usage.reload} />
      ) : usage.data ? (
        <div className={`grid gap-3 text-center ${costTracking ? "grid-cols-3" : "grid-cols-2"}`}>
          {tiles.map((s) => (
            <div key={s.label} className="rounded-lg bg-slate-50 px-3 py-4">
              <div className="text-[11px] font-medium uppercase tracking-wide text-slate-400">{s.label}</div>
              <div className="mt-1 text-lg font-bold text-slate-900">{s.value}</div>
            </div>
          ))}
        </div>
      ) : null}
    </Modal>
  );
}

function BudgetBadges({ t }) {
  const { costTracking } = useSettings();
  const bits = [];
  if (t.token_budget) bits.push(`${fmt(t.token_budget)} tok`);
  if (costTracking && t.cost_budget_usd) bits.push(`$${t.cost_budget_usd}`);
  if (!bits.length) return <span className="text-xs text-slate-400">no budget</span>;
  return (
    <span className="text-xs text-slate-500">
      {bits.join(" + ")} <span className="text-slate-400">/ {t.budget_period}</span>
    </span>
  );
}

export default function Teams() {
  const { api, hasAdmin } = useSettings();
  const list = useAsync(() => api.listTeams(), [api], { enabled: hasAdmin });
  const [editing, setEditing] = useState(null);
  const [viewing, setViewing] = useState(null);
  const [deleting, setDeleting] = useState(null);

  if (!hasAdmin) return <ConnectPrompt what="teams" />;

  const remove = async (id) => {
    setDeleting(id);
    try {
      await api.deleteTeam(id);
      list.reload();
    } finally {
      setDeleting(null);
    }
  };

  return (
    <Card>
      <CardHeader
        title="Teams"
        subtitle="Group keys under a shared budget and allowed-model list. A request is blocked if either the key or its team is over budget."
        action={
          <Button onClick={() => setEditing({})}>
            <Plus size={15} /> Create team
          </Button>
        }
      />

      {list.loading ? (
        <Spinner />
      ) : list.error ? (
        <ErrorState error={list.error} onRetry={list.reload} />
      ) : list.data.length === 0 ? (
        <EmptyState
          icon={Users}
          title="No teams"
          description="Create a team, then assign keys to it on the API Keys page to share a budget."
          action={<Button onClick={() => setEditing({})}>Create team</Button>}
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-xs uppercase tracking-wide text-slate-400">
                <th className="px-5 py-3 font-semibold">Team</th>
                <th className="px-5 py-3 font-semibold">Allowed models</th>
                <th className="px-5 py-3 font-semibold">Shared budget</th>
                <th className="px-5 py-3 font-semibold">Status</th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {list.data.map((t) => (
                <tr key={t.id} className="hover:bg-slate-50/60">
                  <td className="px-5 py-3">
                    <span className="font-medium text-slate-800">{t.name || "—"}</span>
                    <span className="ml-2 text-xs text-slate-400">#{t.id}</span>
                  </td>
                  <td className="px-5 py-3 text-slate-600">
                    {t.allowed_models?.length ? (
                      <span className="flex flex-wrap gap-1">
                        {t.allowed_models.map((m) => <Badge key={m} tone="brand">{m}</Badge>)}
                      </span>
                    ) : (
                      <Badge tone="slate">any</Badge>
                    )}
                  </td>
                  <td className="px-5 py-3"><BudgetBadges t={t} /></td>
                  <td className="px-5 py-3">
                    {t.active ? <Badge tone="green">active</Badge> : <Badge tone="red">archived</Badge>}
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex items-center justify-end gap-2">
                      <Button variant="ghost" onClick={() => setViewing(t)}>
                        <BarChart2 size={14} /> Usage
                      </Button>
                      {t.active && (
                        <>
                          <Button variant="secondary" onClick={() => setEditing(t)}>
                            <Pencil size={14} /> Edit
                          </Button>
                          <Button variant="danger" loading={deleting === t.id} onClick={() => remove(t.id)}>
                            <Trash2 size={14} /> Archive
                          </Button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <TeamModal
        open={!!editing}
        team={editing && editing.id ? editing : null}
        onClose={() => setEditing(null)}
        onSaved={list.reload}
      />
      <UsageModal team={viewing} onClose={() => setViewing(null)} />
    </Card>
  );
}
