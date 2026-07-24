import { useEffect, useState } from "react";
import { Check, Copy, KeyRound, Pencil, Plus, ShieldCheck, Trash2, TriangleAlert } from "lucide-react";
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

const EMPTY_FORM = {
  name: "",
  tenant_id: "default",
  team_id: "",
  tags: "",
  allowed_models: "",
  token_budget: "",
  cost_budget_usd: "",
  budget_period: "total",
  rate_limit_per_minute: "",
  tpm_limit: "",
  max_concurrency: "",
  expires_at: "",
};

function formFromKey(k) {
  return {
    name: k.name || "",
    tenant_id: k.tenant_id || "default",
    team_id: k.team_id == null ? "" : String(k.team_id),
    tags: (k.tags || []).join(", "),
    allowed_models: (k.allowed_models || []).join(", "),
    token_budget: k.token_budget ?? "",
    cost_budget_usd: k.cost_budget_usd ?? "",
    budget_period: k.budget_period || "total",
    rate_limit_per_minute: k.rate_limit_per_minute ?? "",
    tpm_limit: k.tpm_limit ?? "",
    max_concurrency: k.max_concurrency ?? "",
    // Trim an ISO string down to what <input type="datetime-local"> expects.
    expires_at: k.expires_at ? String(k.expires_at).slice(0, 16) : "",
  };
}

function bodyFromForm(form, { withTenant = false } = {}) {
  const body = {
    name: form.name || "unnamed",
    team_id: form.team_id === "" ? null : Number(form.team_id),
    tags: form.tags
      ? form.tags.split(",").map((s) => s.trim()).filter(Boolean)
      : [],
    allowed_models: form.allowed_models
      ? form.allowed_models.split(",").map((s) => s.trim()).filter(Boolean)
      : [],
    token_budget: num(form.token_budget),
    cost_budget_usd: num(form.cost_budget_usd),
    budget_period: form.budget_period || "total",
    rate_limit_per_minute: num(form.rate_limit_per_minute),
    tpm_limit: num(form.tpm_limit),
    max_concurrency: num(form.max_concurrency),
    expires_at: form.expires_at ? form.expires_at : null,
  };
  if (withTenant) body.tenant_id = form.tenant_id || "default";
  return body;
}

function CopyButton({ value }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      variant="secondary"
      onClick={async () => {
        await navigator.clipboard.writeText(value);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
    >
      {copied ? <Check size={15} /> : <Copy size={15} />}
      {copied ? "Copied" : "Copy"}
    </Button>
  );
}

// Shared policy inputs used by both the create and edit modals.
function KeyFields({ form, setForm, teams = [] }) {
  const { costTracking } = useSettings();
  const set = (patch) => setForm({ ...form, ...patch });
  return (
    <>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Team" hint="Shares a budget + allowed models.">
          <Select value={form.team_id} onChange={(e) => set({ team_id: e.target.value })}>
            <option value="">No team</option>
            {teams.map((t) => (
              <option key={t.id} value={String(t.id)}>{t.name || `team #${t.id}`}</option>
            ))}
          </Select>
        </Field>
        <Field label="Tags" hint="Comma-separated. For spend attribution.">
          <Input placeholder="prod, billing" value={form.tags}
            onChange={(e) => set({ tags: e.target.value })} />
        </Field>
      </div>

      <Field label="Allowed models" hint="Comma-separated. Leave empty to allow any model.">
        <Input
          placeholder="gpt-4o-mini, claude-3-5-sonnet"
          value={form.allowed_models}
          onChange={(e) => set({ allowed_models: e.target.value })}
        />
      </Field>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Rate limit (req/min)" hint="Empty = global default.">
          <Input type="number" placeholder="60" value={form.rate_limit_per_minute}
            onChange={(e) => set({ rate_limit_per_minute: e.target.value })} />
        </Field>
        <Field label="TPM limit (tokens/min)" hint="Empty = unlimited.">
          <Input type="number" placeholder="100000" value={form.tpm_limit}
            onChange={(e) => set({ tpm_limit: e.target.value })} />
        </Field>
        <Field label="Max concurrency" hint="Max in-flight requests.">
          <Input type="number" placeholder="unlimited" value={form.max_concurrency}
            onChange={(e) => set({ max_concurrency: e.target.value })} />
        </Field>
        <Field label="Expires at" hint="Optional.">
          <Input type="datetime-local" value={form.expires_at}
            onChange={(e) => set({ expires_at: e.target.value })} />
        </Field>
        <Field label="Token budget" hint="Blocks over this many tokens.">
          <Input type="number" placeholder="1000000" value={form.token_budget}
            onChange={(e) => set({ token_budget: e.target.value })} />
        </Field>
        {costTracking && (
          <Field label="Cost budget (USD)" hint="Blocks over this spend.">
            <Input type="number" step="0.01" placeholder="50" value={form.cost_budget_usd}
              onChange={(e) => set({ cost_budget_usd: e.target.value })} />
          </Field>
        )}
      </div>

      <Field label="Budget period" hint="When token/cost budgets reset.">
        <Select value={form.budget_period} onChange={(e) => set({ budget_period: e.target.value })}>
          <option value="total">Total (lifetime)</option>
          <option value="daily">Daily</option>
          <option value="monthly">Monthly</option>
        </Select>
      </Field>
    </>
  );
}

function CreateKeyModal({ open, onClose, onCreated, teams }) {
  const { api } = useSettings();
  const [form, setForm] = useState(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [created, setCreated] = useState(null);

  const close = () => {
    setForm(EMPTY_FORM);
    setError(null);
    setCreated(null);
    setSubmitting(false);
    onClose();
  };

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const key = await api.createKey(bodyFromForm(form, { withTenant: true }));
      setCreated(key);
      onCreated?.();
    } catch (e) {
      setError(e);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={close}
      title={created ? "Key created" : "Create API key"}
      footer={
        created ? (
          <Button onClick={close}>Done</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={close}>Cancel</Button>
            <Button onClick={submit} loading={submitting}>Create key</Button>
          </>
        )
      }
    >
      {created ? (
        <div className="space-y-4">
          <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3">
            <TriangleAlert size={18} className="mt-0.5 shrink-0 text-amber-600" />
            <p className="text-sm text-amber-800">
              Copy this key now — it is shown <strong>once</strong> and stored only as a hash.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <code className="flex-1 overflow-x-auto rounded-lg bg-slate-900 px-3 py-2.5 font-mono text-sm text-emerald-300">
              {created.key}
            </code>
            <CopyButton value={created.key} />
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {error.message}
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Name">
              <Input placeholder="production-app" value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </Field>
            <Field label="Tenant ID" hint="Scopes usage and cache.">
              <Input value={form.tenant_id}
                onChange={(e) => setForm({ ...form, tenant_id: e.target.value })} />
            </Field>
          </div>
          <KeyFields form={form} setForm={setForm} teams={teams} />
        </div>
      )}
    </Modal>
  );
}

function EditKeyModal({ open, keyData, onClose, onSaved, teams }) {
  const { api } = useSettings();
  const [form, setForm] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (keyData) {
      setForm(formFromKey(keyData));
      setError(null);
    }
  }, [keyData]);

  if (!open || !form) return null;

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await api.updateKey(keyData.id, bodyFromForm(form));
      onSaved?.();
      onClose();
    } catch (e) {
      setError(e);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Edit key ${keyData?.key_prefix}…`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} loading={submitting}>Save changes</Button>
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
          <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </Field>
        <KeyFields form={form} setForm={setForm} teams={teams} />
      </div>
    </Modal>
  );
}

function LimitsCell({ k }) {
  const { costTracking } = useSettings();
  const bits = [];
  bits.push(k.rate_limit_per_minute ? `${k.rate_limit_per_minute}/min` : "default rate");
  if (k.tpm_limit) bits.push(`${fmt(k.tpm_limit)} tpm`);
  if (k.max_concurrency) bits.push(`${k.max_concurrency} conc`);
  const budgets = [];
  if (k.token_budget) budgets.push(`${fmt(k.token_budget)} tok`);
  if (costTracking && k.cost_budget_usd) budgets.push(`$${k.cost_budget_usd}`);
  return (
    <div className="flex flex-col gap-0.5 text-xs text-slate-500">
      <span>{bits.join(" · ")}</span>
      <span>
        {budgets.length ? `${budgets.join(" + ")} / ${k.budget_period}` : "no budget"}
      </span>
    </div>
  );
}

export default function Keys() {
  const { api, hasAdmin } = useSettings();
  const list = useAsync(() => api.listKeys(), [api], { enabled: hasAdmin });
  const teams = useAsync(() => api.listTeams(), [api], { enabled: hasAdmin });
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState(null);
  const [revoking, setRevoking] = useState(null);

  if (!hasAdmin) return <ConnectPrompt what="key management" />;

  const teamList = teams.data ?? [];
  const teamName = (id) => teamList.find((t) => t.id === id)?.name || `team #${id}`;

  const revoke = async (id) => {
    setRevoking(id);
    try {
      await api.revokeKey(id);
      list.reload();
    } finally {
      setRevoking(null);
    }
  };

  return (
    <Card>
      <CardHeader
        title="Virtual keys"
        subtitle="Clients authenticate with these — real provider keys stay server-side."
        action={
          <Button onClick={() => setCreating(true)}>
            <Plus size={15} /> Create key
          </Button>
        }
      />

      {list.loading ? (
        <Spinner />
      ) : list.error ? (
        <ErrorState error={list.error} onRetry={list.reload} />
      ) : list.data.length === 0 ? (
        <EmptyState
          icon={KeyRound}
          title="No keys yet"
          description="Create your first virtual key to start routing requests."
          action={<Button onClick={() => setCreating(true)}>Create key</Button>}
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-xs uppercase tracking-wide text-slate-400">
                <th className="px-5 py-3 font-semibold">Key</th>
                <th className="px-5 py-3 font-semibold">Name</th>
                <th className="px-5 py-3 font-semibold">Models</th>
                <th className="px-5 py-3 font-semibold">Limits &amp; budget</th>
                <th className="px-5 py-3 font-semibold">Status</th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {list.data.map((k) => (
                <tr key={k.id} className="hover:bg-slate-50/60">
                  <td className="px-5 py-3">
                    <code className="rounded bg-slate-100 px-2 py-1 font-mono text-xs text-slate-600">
                      {k.key_prefix}…
                    </code>
                  </td>
                  <td className="px-5 py-3">
                    <div className="font-medium text-slate-800">{k.name || "—"}</div>
                    <div className="mt-1 flex flex-wrap items-center gap-1">
                      {k.team_id != null && <Badge tone="violet">{teamName(k.team_id)}</Badge>}
                      {(k.tags || []).map((t) => (
                        <Badge key={t} tone="slate">#{t}</Badge>
                      ))}
                    </div>
                  </td>
                  <td className="px-5 py-3 text-slate-600">
                    {k.allowed_models?.length ? (
                      <span className="flex flex-wrap gap-1">
                        {k.allowed_models.map((m) => (
                          <Badge key={m} tone="brand">{m}</Badge>
                        ))}
                      </span>
                    ) : (
                      <Badge tone="slate">any</Badge>
                    )}
                  </td>
                  <td className="px-5 py-3"><LimitsCell k={k} /></td>
                  <td className="px-5 py-3">
                    {k.active ? (
                      <Badge tone="green">
                        <ShieldCheck size={12} /> active
                      </Badge>
                    ) : (
                      <Badge tone="red">revoked</Badge>
                    )}
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex items-center justify-end gap-2">
                      {k.active && (
                        <>
                          <Button variant="secondary" onClick={() => setEditing(k)}>
                            <Pencil size={14} /> Edit
                          </Button>
                          <Button variant="danger" loading={revoking === k.id} onClick={() => revoke(k.id)}>
                            <Trash2 size={14} /> Revoke
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

      <CreateKeyModal
        open={creating}
        onClose={() => setCreating(false)}
        onCreated={list.reload}
        teams={teamList}
      />
      <EditKeyModal
        open={!!editing}
        keyData={editing}
        onClose={() => setEditing(null)}
        onSaved={list.reload}
        teams={teamList}
      />
    </Card>
  );
}
