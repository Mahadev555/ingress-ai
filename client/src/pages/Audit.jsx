import { useState } from "react";
import { ScrollText, ArrowRight } from "lucide-react";
import { useSettings } from "../lib/settings.jsx";
import { useAsync } from "../lib/useAsync.js";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  Modal,
  Spinner,
} from "../components/ui.jsx";
import { ConnectPrompt } from "../components/ConnectPrompt.jsx";

function when(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

function preview(text, n = 80) {
  const t = (text || "").replace(/\s+/g, " ").trim();
  return t.length > n ? `${t.slice(0, n)}…` : t || "—";
}

// Left = Request (prompt), right = Response — a single pair, not a thread.
function Pane({ title, tone, text }) {
  return (
    <div className="flex min-h-0 flex-col">
      <div className="mb-2 flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${tone}`} />
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</span>
      </div>
      <pre className="min-h-0 flex-1 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-slate-200 bg-slate-50 p-3 font-mono text-xs leading-relaxed text-slate-700">
        {text || "—"}
      </pre>
    </div>
  );
}

function AuditDetail({ entry, onClose }) {
  return (
    <Modal open={!!entry} onClose={onClose} title="Audit entry" maxWidth="max-w-4xl">
      {entry && (
        <div className="flex h-[60vh] flex-col gap-4">
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <Badge tone="brand">{entry.model}</Badge>
            <Badge tone="slate">{entry.provider}</Badge>
            <span>key #{entry.key_id}</span>
            <span>· {entry.tenant_id}</span>
            <span>· {when(entry.created_at)}</span>
            {entry.trace_id && <code className="text-[11px]">trace {entry.trace_id}</code>}
          </div>
          <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 md:grid-cols-2">
            <Pane title="Request" tone="bg-brand-500" text={entry.prompt} />
            <Pane title="Response" tone="bg-emerald-500" text={entry.response} />
          </div>
        </div>
      )}
    </Modal>
  );
}

export default function Audit() {
  const { api, hasAdmin } = useSettings();
  const list = useAsync(() => api.audit(100), [api], { enabled: hasAdmin });
  const [selected, setSelected] = useState(null);

  if (!hasAdmin) return <ConnectPrompt what="audit logs" />;

  return (
    <Card>
      <CardHeader
        title="Audit logs"
        subtitle="Captured request/response pairs. Click a row to inspect."
        action={
          <Button variant="ghost" onClick={list.reload}>
            Refresh
          </Button>
        }
      />

      {list.loading ? (
        <Spinner />
      ) : list.error ? (
        <ErrorState error={list.error} onRetry={list.reload} />
      ) : list.data.length === 0 ? (
        <EmptyState
          icon={ScrollText}
          title="No audit entries"
          description="Enable AUDIT_CAPTURE_CONTENT=true in the gateway to record redacted prompt/response pairs here."
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-xs uppercase tracking-wide text-slate-400">
                <th className="px-5 py-3 font-semibold">Time</th>
                <th className="px-5 py-3 font-semibold">Model</th>
                <th className="px-5 py-3 font-semibold">Request</th>
                <th className="px-5 py-3 font-semibold">Response</th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {list.data.map((e) => (
                <tr
                  key={e.id}
                  className="cursor-pointer hover:bg-slate-50/60"
                  onClick={() => setSelected(e)}
                >
                  <td className="px-5 py-3 whitespace-nowrap text-xs text-slate-500">{when(e.created_at)}</td>
                  <td className="px-5 py-3">
                    <Badge tone="brand">{e.model}</Badge>
                  </td>
                  <td className="px-5 py-3 max-w-xs truncate text-slate-600">{preview(e.prompt)}</td>
                  <td className="px-5 py-3 max-w-xs truncate text-slate-500">{preview(e.response)}</td>
                  <td className="px-5 py-3 text-right text-slate-400">
                    <ArrowRight size={15} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <AuditDetail entry={selected} onClose={() => setSelected(null)} />
    </Card>
  );
}
