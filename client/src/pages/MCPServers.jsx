import { useEffect, useState } from "react";
import { Pencil, Plug, Plus, Trash2, TriangleAlert } from "lucide-react";
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

const EMPTY = {
  name: "",
  url: "",
  transport: "http",
  auth_header: "",
  auth_value: "",
  description: "",
  enabled: true,
};

function ServerModal({ open, server, onClose, onSaved }) {
  const { api } = useSettings();
  const editing = !!server;
  const [form, setForm] = useState(EMPTY);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (open) {
      setForm(
        server
          ? {
              name: server.name,
              url: server.url,
              transport: server.transport || "http",
              auth_header: server.auth_header ?? "",
              auth_value: "",
              description: server.description ?? "",
              enabled: server.enabled,
            }
          : EMPTY
      );
      setError(null);
    }
  }, [open, server]);

  const set = (patch) => setForm({ ...form, ...patch });

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const body = {
        name: form.name,
        url: form.url,
        transport: form.transport,
        auth_header: form.auth_header || null,
        description: form.description,
        enabled: form.enabled,
      };
      // Omit auth_value when editing and left blank, so the stored secret is kept.
      if (form.auth_value || !editing) body.auth_value = form.auth_value;
      if (editing) await api.updateMcpServer(server.id, body);
      else await api.createMcpServer(body);
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
      title={editing ? `Edit ${server.name}` : "Add MCP server"}
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
          <Field label="Name" hint="Tool namespace prefix — no '__'. e.g. github, filesystem.">
            <Input placeholder="github" value={form.name}
              onChange={(e) => set({ name: e.target.value })} />
          </Field>
          <Field label="Transport" hint="v1 supports remote Streamable HTTP.">
            <Select value={form.transport} onChange={(e) => set({ transport: e.target.value })}>
              <option value="http">Streamable HTTP</option>
            </Select>
          </Field>
        </div>
        <Field label="URL" hint="The upstream MCP endpoint.">
          <Input placeholder="https://mcp.example.com/mcp" value={form.url}
            onChange={(e) => set({ url: e.target.value })} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Auth header" hint="Optional. e.g. Authorization.">
            <Input placeholder="Authorization" value={form.auth_header}
              onChange={(e) => set({ auth_header: e.target.value })} />
          </Field>
          <Field
            label="Auth value"
            hint={editing ? "Leave blank to keep the current value." : "Encrypted at rest, never returned."}
          >
            <Input type="password" placeholder={editing ? "•••••••• (unchanged)" : "Bearer …"}
              value={form.auth_value} onChange={(e) => set({ auth_value: e.target.value })} />
          </Field>
        </div>
        <Field label="Description" hint="Optional. Shown in the registry.">
          <Input placeholder="GitHub issues + PRs" value={form.description}
            onChange={(e) => set({ description: e.target.value })} />
        </Field>
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" className="h-3.5 w-3.5 accent-brand-600"
            checked={form.enabled} onChange={(e) => set({ enabled: e.target.checked })} />
          Enabled (tools from this server are advertised to allowed keys)
        </label>
      </div>
    </Modal>
  );
}

export default function MCPServers() {
  const { api, hasAdmin, mcpEnabled } = useSettings();
  const list = useAsync(() => api.listMcpServers(), [api], { enabled: hasAdmin });
  const [editing, setEditing] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [error, setError] = useState(null);

  if (!hasAdmin) return <ConnectPrompt what="MCP servers" />;

  const remove = async (id) => {
    setDeleting(id);
    setError(null);
    try {
      await api.deleteMcpServer(id);
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
        title="MCP servers"
        subtitle="Upstream MCP servers the gateway fronts. Tools are namespaced {server}__{tool}, scoped per key, and logged to the usage ledger."
        action={
          <Button onClick={() => setEditing({})}>
            <Plus size={15} /> Add server
          </Button>
        }
      />

      {!mcpEnabled && (
        <div className="mx-5 mt-4 flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3">
          <TriangleAlert size={18} className="mt-0.5 shrink-0 text-amber-600" />
          <p className="text-sm text-amber-800">
            The MCP endpoint is <strong>disabled</strong>. You can register servers here, but
            clients can't call <code>POST /mcp</code> until you set <code>MCP_ENABLED=true</code> and
            restart the gateway.
          </p>
        </div>
      )}

      {error && (
        <div className="mx-5 mb-3 mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error.message}
        </div>
      )}

      {list.loading ? (
        <Spinner />
      ) : list.error ? (
        <ErrorState error={list.error} onRetry={list.reload} />
      ) : list.data.length === 0 ? (
        <EmptyState
          icon={Plug}
          title="No MCP servers"
          description="Register a remote MCP server to expose its tools through the gateway."
          action={<Button onClick={() => setEditing({})}>Add server</Button>}
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-xs uppercase tracking-wide text-slate-400">
                <th className="px-5 py-3 font-semibold">Name</th>
                <th className="px-5 py-3 font-semibold">URL</th>
                <th className="px-5 py-3 font-semibold">Auth</th>
                <th className="px-5 py-3 font-semibold">Status</th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {list.data.map((s) => (
                <tr key={s.id} className="hover:bg-slate-50/60">
                  <td className="px-5 py-3">
                    <div className="font-medium text-slate-800">{s.name}</div>
                    {s.description && (
                      <div className="mt-0.5 text-xs text-slate-500">{s.description}</div>
                    )}
                  </td>
                  <td className="px-5 py-3 text-xs text-slate-500"><code>{s.url}</code></td>
                  <td className="px-5 py-3">
                    {s.has_auth ? (
                      <Badge tone="green">{s.auth_header || "set"}</Badge>
                    ) : (
                      <Badge tone="slate">none</Badge>
                    )}
                  </td>
                  <td className="px-5 py-3">
                    {s.enabled ? <Badge tone="green">enabled</Badge> : <Badge tone="slate">disabled</Badge>}
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex items-center justify-end gap-2">
                      <Button variant="secondary" onClick={() => setEditing(s)}>
                        <Pencil size={14} /> Edit
                      </Button>
                      <Button variant="danger" loading={deleting === s.id} onClick={() => remove(s.id)}>
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

      <ServerModal
        open={!!editing}
        server={editing && editing.id ? editing : null}
        onClose={() => setEditing(null)}
        onSaved={list.reload}
      />
    </Card>
  );
}
