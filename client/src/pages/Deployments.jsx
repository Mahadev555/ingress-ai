import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
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

const num = (v) => (v === "" || v == null ? 1 : Number(v));

const EMPTY = { model_name: "", credential_id: "", upstream_model: "", weight: "1", enabled: true };

function formFromDeployment(d) {
  return {
    model_name: d.model_name,
    credential_id: String(d.credential_id),
    upstream_model: d.upstream_model ?? "",
    weight: String(d.weight ?? 1),
    enabled: d.enabled,
  };
}

function DeploymentModal({ open, deployment, models, credentials, onClose, onSaved }) {
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

  // Only offer credentials for the selected model's provider.
  const model = models.find((m) => m.name === form.model_name);
  const credOptions = credentials.filter((c) => !model || c.provider === model.provider);

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const body = {
        credential_id: Number(form.credential_id),
        upstream_model: form.upstream_model ? form.upstream_model : null,
        weight: num(form.weight),
        enabled: !!form.enabled,
      };
      if (editing) {
        await api.updateDeployment(deployment.id, body);
      } else {
        await api.createDeployment({ ...body, model_name: form.model_name });
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

  const noModels = !editing && models.length === 0;
  const noCreds = credentials.length === 0;

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

        <Field label="Model" hint={editing ? "Immutable." : "A registered model (add one on the Models page)."}>
          {editing ? (
            <Input value={form.model_name} disabled />
          ) : (
            <Select value={form.model_name} onChange={(e) => set({ model_name: e.target.value, credential_id: "" })}>
              <option value="">Select a model…</option>
              {models.map((m) => (
                <option key={m.id} value={m.name}>{m.name} ({m.provider})</option>
              ))}
            </Select>
          )}
        </Field>

        <Field label="Credential" hint="The provider key this deployment routes through (Providers page).">
          <Select value={form.credential_id} onChange={(e) => set({ credential_id: e.target.value })}>
            <option value="">Select a credential…</option>
            {credOptions.map((c) => (
              <option key={c.id} value={String(c.id)}>{c.name} ({c.provider})</option>
            ))}
          </Select>
        </Field>

        <Field
          label="Upstream model name"
          hint={
            model?.provider === "azure"
              ? "Azure deployment name if it differs from the model (e.g. gpt-4o-1)."
              : "Optional. Overrides the name sent upstream; leave blank to use the model name."
          }
        >
          <Input placeholder={model?.provider === "azure" ? "gpt-4o-1" : "(same as model)"}
            value={form.upstream_model} onChange={(e) => set({ upstream_model: e.target.value })} />
        </Field>

        <Field label="Weight" hint="Relative share for weighted routing.">
          <Input type="number" min="1" value={form.weight}
            onChange={(e) => set({ weight: e.target.value })} />
        </Field>

        <label className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2.5">
          <span className="text-sm font-medium text-slate-700">Enabled (eligible for routing)</span>
          <input type="checkbox" checked={form.enabled}
            onChange={(e) => set({ enabled: e.target.checked })}
            className="h-4 w-4 accent-brand-600" />
        </label>

        {noCreds && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
            No provider credentials yet — add one on the <Link to="/providers" className="underline">Providers</Link> page first.
          </div>
        )}
        {noModels && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
            No registered models yet — add one on the Models page first.
          </div>
        )}
      </div>
    </Modal>
  );
}

export default function Deployments() {
  const { api, hasAdmin } = useSettings();
  const list = useAsync(() => api.listDeployments(), [api], { enabled: hasAdmin });
  const models = useAsync(() => api.listModelConfigs(), [api], { enabled: hasAdmin });
  const credentials = useAsync(() => api.listProviders(), [api], { enabled: hasAdmin });
  const [editing, setEditing] = useState(null);
  const [deleting, setDeleting] = useState(null);

  if (!hasAdmin) return <ConnectPrompt what="deployments" />;

  // Deployments must point at a routable (registered, non-alias) model whose
  // provider you actually have a credential for.
  const credProviders = new Set((credentials.data ?? []).map((c) => c.provider));
  const routableModels = (models.data ?? []).filter(
    (m) => !m.alias_of && credProviders.has(m.provider)
  );

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
        subtitle="Attach one or more provider credentials to a model; the gateway load-balances across them and fails over on error."
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
          description="Without deployments a model routes to its single env provider key. Attach two or more credentials to load-balance."
          action={<Button onClick={() => setEditing({})}>Add deployment</Button>}
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-xs uppercase tracking-wide text-slate-400">
                <th className="px-5 py-3 font-semibold">Model</th>
                <th className="px-5 py-3 font-semibold">Provider</th>
                <th className="px-5 py-3 font-semibold">Credential</th>
                <th className="px-5 py-3 text-right font-semibold">Weight</th>
                <th className="px-5 py-3 font-semibold">Status</th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {list.data.map((d) => (
                <tr key={d.id} className="hover:bg-slate-50/60">
                  <td className="px-5 py-3 font-medium text-slate-800">
                    <code>{d.model_name}</code>
                    {d.upstream_model && (
                      <span className="ml-1 text-xs font-normal text-slate-400">→ {d.upstream_model}</span>
                    )}
                  </td>
                  <td className="px-5 py-3"><Badge tone="brand">{d.provider}</Badge></td>
                  <td className="px-5 py-3">
                    <Link to="/providers" className="text-slate-600 hover:underline">{d.credential_name}</Link>
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
        credentials={credentials.data ?? []}
        onClose={() => setEditing(null)}
        onSaved={list.reload}
      />
    </Card>
  );
}
