import { useState } from "react";
import { Check, Copy, KeyRound, Plus, ShieldCheck, Trash2, TriangleAlert } from "lucide-react";
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
  Spinner,
} from "../components/ui.jsx";
import { ConnectPrompt } from "../components/ConnectPrompt.jsx";

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

function CreateKeyModal({ open, onClose, onCreated }) {
  const { api } = useSettings();
  const [form, setForm] = useState({ name: "", tenant_id: "default", allowed_models: "", token_budget: "" });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [created, setCreated] = useState(null);

  const reset = () => {
    setForm({ name: "", tenant_id: "default", allowed_models: "", token_budget: "" });
    setError(null);
    setCreated(null);
    setSubmitting(false);
  };

  const close = () => {
    reset();
    onClose();
  };

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const body = {
        name: form.name || "unnamed",
        tenant_id: form.tenant_id || "default",
        allowed_models: form.allowed_models
          ? form.allowed_models.split(",").map((s) => s.trim()).filter(Boolean)
          : [],
        token_budget: form.token_budget ? Number(form.token_budget) : null,
      };
      const key = await api.createKey(body);
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
            <Button variant="secondary" onClick={close}>
              Cancel
            </Button>
            <Button onClick={submit} loading={submitting}>
              Create key
            </Button>
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
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="text-xs text-slate-400">Name</dt>
              <dd className="font-medium text-slate-700">{created.name}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-400">Tenant</dt>
              <dd className="font-medium text-slate-700">{created.tenant_id}</dd>
            </div>
          </dl>
        </div>
      ) : (
        <div className="space-y-4">
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {error.message}
            </div>
          )}
          <Field label="Name">
            <Input
              placeholder="e.g. production-app"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </Field>
          <Field label="Tenant ID" hint="Scopes usage and cache to a tenant.">
            <Input
              value={form.tenant_id}
              onChange={(e) => setForm({ ...form, tenant_id: e.target.value })}
            />
          </Field>
          <Field label="Allowed models" hint="Comma-separated. Leave empty to allow any model.">
            <Input
              placeholder="gpt-4o-mini, claude-3-5-sonnet"
              value={form.allowed_models}
              onChange={(e) => setForm({ ...form, allowed_models: e.target.value })}
            />
          </Field>
          <Field label="Token budget" hint="Optional. Reserved for quota enforcement.">
            <Input
              type="number"
              placeholder="e.g. 1000000"
              value={form.token_budget}
              onChange={(e) => setForm({ ...form, token_budget: e.target.value })}
            />
          </Field>
        </div>
      )}
    </Modal>
  );
}

export default function Keys() {
  const { api, hasAdmin } = useSettings();
  const list = useAsync(() => api.listKeys(), [api], { enabled: hasAdmin });
  const [creating, setCreating] = useState(false);
  const [revoking, setRevoking] = useState(null);

  if (!hasAdmin) return <ConnectPrompt what="key management" />;

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
                <th className="px-5 py-3 font-semibold">Tenant</th>
                <th className="px-5 py-3 font-semibold">Models</th>
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
                  <td className="px-5 py-3 font-medium text-slate-800">{k.name || "—"}</td>
                  <td className="px-5 py-3 text-slate-600">{k.tenant_id}</td>
                  <td className="px-5 py-3 text-slate-600">
                    {k.allowed_models?.length ? (
                      <span className="flex flex-wrap gap-1">
                        {k.allowed_models.map((m) => (
                          <Badge key={m} tone="brand">
                            {m}
                          </Badge>
                        ))}
                      </span>
                    ) : (
                      <Badge tone="slate">any</Badge>
                    )}
                  </td>
                  <td className="px-5 py-3">
                    {k.active ? (
                      <Badge tone="green">
                        <ShieldCheck size={12} /> active
                      </Badge>
                    ) : (
                      <Badge tone="red">revoked</Badge>
                    )}
                  </td>
                  <td className="px-5 py-3 text-right">
                    {k.active && (
                      <Button
                        variant="danger"
                        loading={revoking === k.id}
                        onClick={() => revoke(k.id)}
                      >
                        <Trash2 size={14} /> Revoke
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <CreateKeyModal open={creating} onClose={() => setCreating(false)} onCreated={list.reload} />
    </Card>
  );
}
