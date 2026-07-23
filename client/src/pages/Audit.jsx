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

function preview(text, n = 70) {
  const t = (text || "").replace(/\s+/g, " ").trim();
  return t.length > n ? `${t.slice(0, n)}…` : t || "—";
}

// Left = Request (prompt), right = Response — a single pair per turn.
function Pair({ turn, index }) {
  return (
    <div>
      <div className="mb-1.5 flex items-center gap-2 text-xs text-slate-400">
        <span className="font-semibold text-slate-500">Turn {index + 1}</span>
        <span>· {when(turn.created_at)}</span>
        {turn.trace_id && <code className="text-[11px]">trace {turn.trace_id}</code>}
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <div>
          <div className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            <span className="h-2 w-2 rounded-full bg-brand-500" /> Request
          </div>
          <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-slate-200 bg-slate-50 p-3 font-mono text-xs text-slate-700">
            {turn.prompt || "—"}
          </pre>
        </div>
        <div>
          <div className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            <span className="h-2 w-2 rounded-full bg-emerald-500" /> Response
          </div>
          <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-slate-200 bg-slate-50 p-3 font-mono text-xs text-slate-700">
            {turn.response || "—"}
          </pre>
        </div>
      </div>
    </div>
  );
}

function ConversationDetail({ convo, onClose }) {
  return (
    <Modal open={!!convo} onClose={onClose} title="Conversation" maxWidth="max-w-4xl">
      {convo && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <Badge tone="brand">{convo.model}</Badge>
            <Badge tone="slate">{convo.provider}</Badge>
            <Badge tone="slate">{convo.turn_count} turns</Badge>
            <span>
              key <code className="text-[11px]">{convo.key_prefix}…</code>
            </span>
            <span>· {convo.tenant_id}</span>
            <span>· {when(convo.started_at)}</span>
            {convo.conversation_id && (
              <code className="text-[11px]">conv {convo.conversation_id}</code>
            )}
          </div>
          <div className="space-y-5">
            {convo.turns.map((t, i) => (
              <Pair key={t.id} turn={t} index={i} />
            ))}
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
        subtitle="Captured conversations (grouped by conversation id). Click a row to inspect all turns."
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
                <th className="px-5 py-3 font-semibold">Last activity</th>
                <th className="px-5 py-3 font-semibold">Model</th>
                <th className="px-5 py-3 font-semibold">Key</th>
                <th className="px-5 py-3 font-semibold">Turns</th>
                <th className="px-5 py-3 font-semibold">Latest request</th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {list.data.map((c, idx) => (
                <tr
                  key={c.conversation_id || `single-${idx}`}
                  className="cursor-pointer hover:bg-slate-50/60"
                  onClick={() => setSelected(c)}
                >
                  <td className="px-5 py-3 whitespace-nowrap text-xs text-slate-500">{when(c.last_at)}</td>
                  <td className="px-5 py-3">
                    <Badge tone="brand">{c.model}</Badge>
                  </td>
                  <td className="px-5 py-3">
                    <code className="rounded bg-slate-100 px-2 py-1 font-mono text-xs text-slate-600">
                      {c.key_prefix}…
                    </code>
                  </td>
                  <td className="px-5 py-3">
                    <Badge tone={c.turn_count > 1 ? "brand" : "slate"}>{c.turn_count}</Badge>
                  </td>
                  <td className="px-5 py-3 max-w-md truncate text-slate-600">
                    {preview(c.turns[c.turns.length - 1]?.prompt)}
                  </td>
                  <td className="px-5 py-3 text-right text-slate-400">
                    <ArrowRight size={15} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ConversationDetail convo={selected} onClose={() => setSelected(null)} />
    </Card>
  );
}
