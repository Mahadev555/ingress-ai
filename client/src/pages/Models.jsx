import { useEffect, useState } from "react";
import { Boxes, Pencil, Plus, Trash2 } from "lucide-react";
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
const num = (v) => (v === "" || v == null ? null : Number(v));

const EMPTY = {
  name: "",
  provider: "openai",
  alias_of: "",
  input_price_per_1m: "",
  output_price_per_1m: "",
  default_rate_limit_per_minute: "",
  default_tpm_limit: "",
  enabled: true,
};

function formFromModel(m) {
  return {
    name: m.name,
    provider: m.provider,
    alias_of: m.alias_of ?? "",
    input_price_per_1m: m.input_price_per_1m ?? "",
    output_price_per_1m: m.output_price_per_1m ?? "",
    default_rate_limit_per_minute: m.default_rate_limit_per_minute ?? "",
    default_tpm_limit: m.default_tpm_limit ?? "",
    enabled: m.enabled,
  };
}

function bodyFromForm(form) {
  return {
    name: form.name,
    provider: form.provider,
    alias_of: form.alias_of ? form.alias_of : null,
    input_price_per_1m: num(form.input_price_per_1m),
    output_price_per_1m: num(form.output_price_per_1m),
    default_rate_limit_per_minute: num(form.default_rate_limit_per_minute),
    default_tpm_limit: num(form.default_tpm_limit),
    enabled: !!form.enabled,
  };
}

function ModelModal({ open, model, onClose, onSaved }) {
  const { api } = useSettings();
  const editing = !!model;
  const [form, setForm] = useState(EMPTY);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (open) {
      setForm(model ? formFromModel(model) : EMPTY);
      setError(null);
    }
  }, [open, model]);

  const set = (patch) => setForm({ ...form, ...patch });

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const body = bodyFromForm(form);
      if (editing) {
        // name is immutable on update
        const { name, ...rest } = body;
        await api.updateModelConfig(model.id, rest);
      } else {
        await api.createModelConfig(body);
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
      title={editing ? `Edit ${model.name}` : "Register model"}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} loading={submitting}>{editing ? "Save" : "Register"}</Button>
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
          <Field label="Model name" hint={editing ? "Immutable." : "e.g. gpt-4o-mini or an alias."}>
            <Input value={form.name} disabled={editing}
              onChange={(e) => set({ name: e.target.value })} />
          </Field>
          <Field label="Provider">
            <Select value={form.provider} onChange={(e) => set({ provider: e.target.value })}>
              {PROVIDERS.map((p) => <option key={p} value={p}>{p}</option>)}
            </Select>
          </Field>
        </div>
        <Field label="Alias of" hint="Optional. Route requests for this name to another model.">
          <Input placeholder="gpt-4o-mini" value={form.alias_of}
            onChange={(e) => set({ alias_of: e.target.value })} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Input price / 1M" hint="USD.">
            <Input type="number" step="0.01" placeholder="0.15" value={form.input_price_per_1m}
              onChange={(e) => set({ input_price_per_1m: e.target.value })} />
          </Field>
          <Field label="Output price / 1M" hint="USD.">
            <Input type="number" step="0.01" placeholder="0.60" value={form.output_price_per_1m}
              onChange={(e) => set({ output_price_per_1m: e.target.value })} />
          </Field>
          <Field label="Default rate (req/min)" hint="Used when a key sets none.">
            <Input type="number" value={form.default_rate_limit_per_minute}
              onChange={(e) => set({ default_rate_limit_per_minute: e.target.value })} />
          </Field>
          <Field label="Default TPM" hint="Used when a key sets none.">
            <Input type="number" value={form.default_tpm_limit}
              onChange={(e) => set({ default_tpm_limit: e.target.value })} />
          </Field>
        </div>
        <label className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2.5">
          <span className="text-sm font-medium text-slate-700">Enabled (advertised in /v1/models)</span>
          <input type="checkbox" checked={form.enabled}
            onChange={(e) => set({ enabled: e.target.checked })}
            className="h-4 w-4 accent-brand-600" />
        </label>
      </div>
    </Modal>
  );
}

const price = (v) => (v == null ? "—" : `$${v}`);

export default function Models() {
  const { api, hasAdmin } = useSettings();
  const list = useAsync(() => api.listModelConfigs(), [api], { enabled: hasAdmin });
  const [editing, setEditing] = useState(null); // model object or {} for "new"
  const [deleting, setDeleting] = useState(null);

  if (!hasAdmin) return <ConnectPrompt what="the model registry" />;

  const remove = async (id) => {
    setDeleting(id);
    try {
      await api.deleteModelConfig(id);
      list.reload();
    } finally {
      setDeleting(null);
    }
  };

  return (
    <Card>
      <CardHeader
        title="Model registry"
        subtitle="Override the env model list: pricing, aliases, default limits, and enable/disable."
        action={
          <Button onClick={() => setEditing({})}>
            <Plus size={15} /> Register model
          </Button>
        }
      />

      {list.loading ? (
        <Spinner />
      ) : list.error ? (
        <ErrorState error={list.error} onRetry={list.reload} />
      ) : list.data.length === 0 ? (
        <EmptyState
          icon={Boxes}
          title="No registered models"
          description="Without registry entries the gateway uses the AVAILABLE_MODELS env list and static pricing."
          action={<Button onClick={() => setEditing({})}>Register model</Button>}
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-xs uppercase tracking-wide text-slate-400">
                <th className="px-5 py-3 font-semibold">Model</th>
                <th className="px-5 py-3 font-semibold">Provider</th>
                <th className="px-5 py-3 font-semibold">Alias</th>
                <th className="px-5 py-3 text-right font-semibold">Price /1M (in / out)</th>
                <th className="px-5 py-3 font-semibold">Defaults</th>
                <th className="px-5 py-3 font-semibold">Status</th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {list.data.map((m) => (
                <tr key={m.id} className="hover:bg-slate-50/60">
                  <td className="px-5 py-3 font-medium text-slate-800"><code>{m.name}</code></td>
                  <td className="px-5 py-3"><Badge tone="brand">{m.provider}</Badge></td>
                  <td className="px-5 py-3 text-slate-600">
                    {m.alias_of ? <code className="text-xs">→ {m.alias_of}</code> : "—"}
                  </td>
                  <td className="px-5 py-3 text-right tabular-nums text-slate-600">
                    {price(m.input_price_per_1m)} / {price(m.output_price_per_1m)}
                  </td>
                  <td className="px-5 py-3 text-xs text-slate-500">
                    {m.default_rate_limit_per_minute ? `${m.default_rate_limit_per_minute}/min` : "—"}
                    {m.default_tpm_limit ? ` · ${m.default_tpm_limit} tpm` : ""}
                  </td>
                  <td className="px-5 py-3">
                    {m.enabled ? <Badge tone="green">enabled</Badge> : <Badge tone="slate">disabled</Badge>}
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex items-center justify-end gap-2">
                      <Button variant="secondary" onClick={() => setEditing(m)}>
                        <Pencil size={14} /> Edit
                      </Button>
                      <Button variant="danger" loading={deleting === m.id} onClick={() => remove(m.id)}>
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

      <ModelModal
        open={!!editing}
        model={editing && editing.id ? editing : null}
        onClose={() => setEditing(null)}
        onSaved={list.reload}
      />
    </Card>
  );
}
