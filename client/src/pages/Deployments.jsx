import { useEffect, useState } from "react";
import { Network, Pencil, Plus, Trash2 } from "lucide-react";
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

const PROVIDERS = ["openai", "anthropic", "gemini", "azure"];
const num = (v) => (v === "" || v == null ? 1 : Number(v));

const EMPTY = {
  model_name: "",
  provider: "openai",
  api_key: "",
  base_url: "",
  weight: "1",
  enabled: true,
};

function formFromDeployment(d) {
  return {
    model_name: d.model_name,
    provider: d.provider,
    api_key: "", // never returned; blank means "leave unchanged"
    base_url: d.base_url ?? "",
    weight: String(d.weight ?? 1),
    enabled: d.enabled,
  };
}

function DeploymentModal({ open, deployment, models, onClose, onSaved }) {
  const { api } = useSettings();
  const editing = !!deployment;
  const [form, setForm] = useState(EMPTY);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (open) {
      setForm(deployment ? formFromDeployment(deployment) : EMPTY);
      setError(null);
    }
  }, [open, deployment]);

  const set = (patch) => setForm({ ...form, ...patch });

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const body = {
        provider: form.provider,
        base_url: form.base_url ? form.base_url : null,
        weight: num(form.weight),
        enabled: !!form.enabled,
      };
      // Only send the key when the admin typed one (blank leaves it unchanged).
      if (form.api_key) body.api_key = form.api_key;
      if (editing) {
        await api.updateDeployment(deployment.id, body);
      } else {
        await api.createDeployment({ ...body, model_name: form.model_name, api_key: form.api_key });
      }
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
      title={editing ? `Edit deployment for ${deployment.model_name}` : "Add deployment"}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} loading={submitting}>{editing ? "Save" : "Add"}</Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error.message}
          </div>
        )}
        <div className="grid grid-cols-2 gap-3">
          <Field label="Model" hint={editing ? "Immutable." : "A registered model (add one on the Models page)."}>
            {editing ? (
              <Input value={form.model_name} disabled />
            ) : (
              <Select
                value={form.model_name}
                onChange={(e) => {
                  const m = models.find((x) => x.name === e.target.value);
                  set({ model_name: e.target.value, provider: m ? m.provider : form.provider });
                }}
              >
                <option value="">Select a model…</option>
                {models.map((m) => (
                  <option key={m.id} value={m.name}>{m.name}</option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Provider" hint="Auto-set from the model; override if needed.">
            <Select value={form.provider} onChange={(e) => set({ provider: e.target.value })}>
              {PROVIDERS.map((p) => <option key={p} value={p}>{p}</option>)}
            </Select>
          </Field>
        </div>
        {!editing && models.length === 0 && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
            No registered models yet — add one on the Models page first.
          </div>
        )}
        <Field
          label="Upstream API key"
          hint={editing ? "Leave blank to keep the current key." : "Stored server-side, never returned."}
        >
          <Input type="password" placeholder={editing ? "•••••••• (unchanged)" : "sk-…"}
            value={form.api_key} onChange={(e) => set({ api_key: e.target.value })} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Base URL" hint="Optional. Overrides the provider default (e.g. a region).">
            <Input placeholder="https://…" value={form.base_url}
              onChange={(e) => set({ base_url: e.target.value })} />
          </Field>
          <Field label="Weight" hint="Relative share for weighted routing.">
            <Input type="number" min="1" value={form.weight}
              onChange={(e) => set({ weight: e.target.value })} />
          </Field>
        </div>
        <label className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2.5">
          <span className="text-sm font-medium text-slate-700">Enabled (eligible for routing)</span>
          <input type="checkbox" checked={form.enabled}
            onChange={(e) => set({ enabled: e.target.checked })}
            className="h-4 w-4 accent-brand-600" />
        </label>
      </div>
    </Modal>
  );
}

export default function Deployments() {
  const { api, hasAdmin } = useSettings();
  const list = useAsync(() => api.listDeployments(), [api], { enabled: hasAdmin });
  const models = useAsync(() => api.listModelConfigs(), [api], { enabled: hasAdmin });
  const [editing, setEditing] = useState(null);
  const [deleting, setDeleting] = useState(null);

  if (!hasAdmin) return <ConnectPrompt what="deployments" />;

  // Deployments must point at a routable (registered, non-alias) model.
  const routableModels = (models.data ?? []).filter((m) => !m.alias_of);

  const remove = async (id) => {
    setDeleting(id);
    try {
      await api.deleteDeployment(id);
      list.reload();
    } finally {
      setDeleting(null);
    }
  };

  return (
    <Card>
      <CardHeader
        title="Model deployments"
        subtitle="Add multiple backends per model (keys / regions); the gateway load-balances across them and fails over on error."
        action={
          <Button onClick={() => setEditing({})}>
            <Plus size={15} /> Add deployment
          </Button>
        }
      />

      {list.loading ? (
        <Spinner />
      ) : list.error ? (
        <ErrorState error={list.error} onRetry={list.reload} />
      ) : list.data.length === 0 ? (
        <EmptyState
          icon={Network}
          title="No deployments"
          description="Without deployments a model routes to its single env-configured provider key. Add two or more to load-balance."
          action={<Button onClick={() => setEditing({})}>Add deployment</Button>}
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-xs uppercase tracking-wide text-slate-400">
                <th className="px-5 py-3 font-semibold">Model</th>
                <th className="px-5 py-3 font-semibold">Provider</th>
                <th className="px-5 py-3 font-semibold">Key</th>
                <th className="px-5 py-3 font-semibold">Base URL</th>
                <th className="px-5 py-3 text-right font-semibold">Weight</th>
                <th className="px-5 py-3 font-semibold">Status</th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {list.data.map((d) => (
                <tr key={d.id} className="hover:bg-slate-50/60">
                  <td className="px-5 py-3 font-medium text-slate-800"><code>{d.model_name}</code></td>
                  <td className="px-5 py-3"><Badge tone="brand">{d.provider}</Badge></td>
                  <td className="px-5 py-3">
                    {d.has_api_key ? <Badge tone="green">set</Badge> : <Badge tone="amber">missing</Badge>}
                  </td>
                  <td className="px-5 py-3 text-xs text-slate-500">
                    {d.base_url ? <code>{d.base_url}</code> : "provider default"}
                  </td>
                  <td className="px-5 py-3 text-right tabular-nums text-slate-600">{d.weight}</td>
                  <td className="px-5 py-3">
                    {d.enabled ? <Badge tone="green">enabled</Badge> : <Badge tone="slate">disabled</Badge>}
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex items-center justify-end gap-2">
                      <Button variant="secondary" onClick={() => setEditing(d)}>
                        <Pencil size={14} /> Edit
                      </Button>
                      <Button variant="danger" loading={deleting === d.id} onClick={() => remove(d.id)}>
                        <Trash2 size={14} /> Delete
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <DeploymentModal
        open={!!editing}
        deployment={editing && editing.id ? editing : null}
        models={routableModels}
        onClose={() => setEditing(null)}
        onSaved={list.reload}
      />
    </Card>
  );
}
