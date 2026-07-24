import { useEffect, useState } from "react";
import { KeyRound, Pencil, Plus, Trash2 } from "lucide-react";
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

const EMPTY = { name: "", provider: "openai", api_key: "", base_url: "" };

function CredentialModal({ open, credential, onClose, onSaved }) {
  const { api, supportedProviders } = useSettings();
  const editing = !!credential;
  // All providers the gateway supports (from its adapters).
  const providers = supportedProviders.length ? supportedProviders : ["openai", "anthropic", "gemini", "azure"];
  const [form, setForm] = useState(EMPTY);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (open) {
      setForm(
        credential
          ? { name: credential.name, provider: credential.provider, api_key: "", base_url: credential.base_url ?? "" }
          : EMPTY
      );
      setError(null);
    }
  }, [open, credential]);

  const set = (patch) => setForm({ ...form, ...patch });

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const body = { name: form.name, provider: form.provider, base_url: form.base_url || null };
      if (form.api_key) body.api_key = form.api_key; // omit to keep current key
      if (editing) await api.updateProvider(credential.id, body);
      else await api.createProvider({ ...body, api_key: form.api_key });
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
      title={editing ? `Edit ${credential.name}` : "Add credential"}
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
          <Field label="Name" hint="e.g. openai-main, openai-eu">
            <Input placeholder="openai-main" value={form.name}
              onChange={(e) => set({ name: e.target.value })} />
          </Field>
          <Field label="Provider">
            <Select value={form.provider} onChange={(e) => set({ provider: e.target.value })}>
              {providers.map((p) => <option key={p} value={p}>{p}</option>)}
            </Select>
          </Field>
        </div>
        <Field
          label="API key"
          hint={editing ? "Leave blank to keep the current key." : "Stored encrypted, never returned."}
        >
          <Input type="password" placeholder={editing ? "•••••••• (unchanged)" : "sk-…"}
            value={form.api_key} onChange={(e) => set({ api_key: e.target.value })} />
        </Field>
        <Field label="Base URL" hint="Optional. Overrides the provider default (e.g. a region/proxy).">
          <Input placeholder="https://…" value={form.base_url}
            onChange={(e) => set({ base_url: e.target.value })} />
        </Field>
      </div>
    </Modal>
  );
}

export default function Providers() {
  const { api, hasAdmin } = useSettings();
  const list = useAsync(() => api.listProviders(), [api], { enabled: hasAdmin });
  const [editing, setEditing] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [error, setError] = useState(null);

  if (!hasAdmin) return <ConnectPrompt what="provider credentials" />;

  const remove = async (id) => {
    setDeleting(id);
    setError(null);
    try {
      await api.deleteProvider(id);
      list.reload();
    } catch (e) {
      setError(e);
    } finally {
      setDeleting(null);
    }
  };

  return (
    <Card>
      <CardHeader
        title="Provider credentials"
        subtitle="Where upstream keys live — set once per provider/account, encrypted at rest, and referenced by deployments."
        action={
          <Button onClick={() => setEditing({})}>
            <Plus size={15} /> Add credential
          </Button>
        }
      />

      {error && (
        <div className="mx-5 mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error.message}
        </div>
      )}

      {list.loading ? (
        <Spinner />
      ) : list.error ? (
        <ErrorState error={list.error} onRetry={list.reload} />
      ) : list.data.length === 0 ? (
        <EmptyState
          icon={KeyRound}
          title="No credentials"
          description="Add a provider key here (or set it in the env and restart to auto-seed one)."
          action={<Button onClick={() => setEditing({})}>Add credential</Button>}
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-xs uppercase tracking-wide text-slate-400">
                <th className="px-5 py-3 font-semibold">Name</th>
                <th className="px-5 py-3 font-semibold">Provider</th>
                <th className="px-5 py-3 font-semibold">Key</th>
                <th className="px-5 py-3 font-semibold">Base URL</th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {list.data.map((c) => (
                <tr key={c.id} className="hover:bg-slate-50/60">
                  <td className="px-5 py-3 font-medium text-slate-800">{c.name}</td>
                  <td className="px-5 py-3"><Badge tone="brand">{c.provider}</Badge></td>
                  <td className="px-5 py-3">
                    {c.has_api_key ? <Badge tone="green">set</Badge> : <Badge tone="amber">missing</Badge>}
                  </td>
                  <td className="px-5 py-3 text-xs text-slate-500">
                    {c.base_url ? <code>{c.base_url}</code> : "provider default"}
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex items-center justify-end gap-2">
                      <Button variant="secondary" onClick={() => setEditing(c)}>
                        <Pencil size={14} /> Edit
                      </Button>
                      <Button variant="danger" loading={deleting === c.id} onClick={() => remove(c.id)}>
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

      <CredentialModal
        open={!!editing}
        credential={editing && editing.id ? editing : null}
        onClose={() => setEditing(null)}
        onSaved={list.reload}
      />
    </Card>
  );
}
