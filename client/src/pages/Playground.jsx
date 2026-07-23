import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  AlertCircle,
  Bot,
  Check,
  Copy,
  Eraser,
  SendHorizonal,
  Square,
  User,
  X,
} from "lucide-react";
import { useSettings } from "../lib/settings.jsx";
import { chatStream, createApi } from "../lib/api.js";
import { useAsync } from "../lib/useAsync.js";
import { MODEL_CATALOG, groupModels } from "../lib/models.js";
import { Badge, Button, Card, Field, Input, Select, Textarea, cx } from "../components/ui.jsx";

const DEFAULT_SYSTEM = "You are a helpful assistant.";
const CUSTOM = "__custom__";

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={async () => {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs text-slate-400 hover:bg-slate-100 hover:text-slate-600"
    >
      {copied ? <Check size={12} /> : <Copy size={12} />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

function Bubble({ role, content }) {
  const isUser = role === "user";
  return (
    <div className={cx("group flex gap-3", isUser && "flex-row-reverse")}>
      <div
        className={cx(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
          isUser ? "bg-brand-600 text-white" : "bg-slate-200 text-slate-600"
        )}
      >
        {isUser ? <User size={16} /> : <Bot size={16} />}
      </div>
      <div className="min-w-0 max-w-[80%]">
        <div
          className={cx(
            "rounded-2xl px-4 py-2.5 text-sm",
            isUser
              ? "whitespace-pre-wrap rounded-tr-sm bg-brand-600 text-white"
              : "rounded-tl-sm border border-slate-200 bg-white text-slate-800"
          )}
        >
          {!content ? (
            <span className="text-slate-400">…</span>
          ) : isUser ? (
            content
          ) : (
            <div className="prose prose-sm prose-slate max-w-none break-words prose-pre:bg-slate-900 prose-pre:text-slate-100">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  a: (props) => <a {...props} target="_blank" rel="noopener noreferrer" />,
                }}
              >
                {content}
              </ReactMarkdown>
            </div>
          )}
        </div>
        {!isUser && content && (
          <div className="mt-1 opacity-0 transition-opacity group-hover:opacity-100">
            <CopyButton text={content} />
          </div>
        )}
      </div>
    </div>
  );
}

export default function Playground() {
  const { apiBase, virtualKey, setVirtualKey, api } = useSettings();

  // Model list is fetched from the gateway (GET /v1/models); falls back to a
  // static catalog if the gateway is unreachable.
  const modelsQuery = useAsync(() => api.models(), [api]);
  const groups = useMemo(
    () => groupModels(modelsQuery.data?.data) ?? MODEL_CATALOG,
    [modelsQuery.data]
  );
  const flatModels = useMemo(() => groups.flatMap((g) => g.models), [groups]);

  const [model, setModel] = useState("gpt-4o-mini");
  const [customModel, setCustomModel] = useState("");
  const [customMode, setCustomMode] = useState(false);
  const effectiveModel = customMode ? customModel.trim() : model;

  // Keep the selected model valid as the fetched list arrives.
  useEffect(() => {
    if (!customMode && flatModels.length && !flatModels.includes(model)) {
      setModel(flatModels[0]);
    }
  }, [flatModels, customMode, model]);

  const [system, setSystem] = useState(DEFAULT_SYSTEM);
  const [temperature, setTemperature] = useState(0.7);
  const [streaming, setStreaming] = useState(true);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const abortRef = useRef(null);
  const scrollRef = useRef(null);

  // Conversation window: one id groups all its turns in the audit log; after
  // maxTurns (a backend hint) the user must start a fresh chat.
  const configQuery = useAsync(() => api.config(), [api]);
  const maxTurns = configQuery.data?.max_conversation_turns ?? 5;
  const [conversationId, setConversationId] = useState(() => crypto.randomUUID());
  const turnsUsed = messages.filter((m) => m.role === "user").length;
  const limitReached = turnsUsed >= maxTurns;

  const scrollDown = () =>
    requestAnimationFrame(() => {
      const el = scrollRef.current;
      if (el) el.scrollTop = el.scrollHeight;
    });

  const send = async () => {
    if (!input.trim() || busy || limitReached) return;
    if (!effectiveModel) {
      setError(new Error("Enter a model name."));
      return;
    }
    if (!virtualKey) {
      setError(new Error("Set a virtual key first (the field on the right)."));
      return;
    }
    setError(null);

    const history = [...messages, { role: "user", content: input.trim() }];
    setMessages([...history, { role: "assistant", content: "" }]);
    setInput("");
    setBusy(true);
    scrollDown();

    const payload = {
      model: effectiveModel,
      temperature: Number(temperature),
      messages: [
        ...(system.trim() ? [{ role: "system", content: system.trim() }] : []),
        ...history,
      ],
    };

    const pushDelta = (delta) => {
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = {
          role: "assistant",
          content: next[next.length - 1].content + delta,
        };
        return next;
      });
      scrollDown();
    };

    try {
      if (streaming) {
        abortRef.current = new AbortController();
        await chatStream(
          { baseUrl: apiBase, apiKey: virtualKey, conversationId },
          payload,
          { onDelta: pushDelta, signal: abortRef.current.signal }
        );
      } else {
        const client = createApi({ baseUrl: apiBase });
        const res = await client.chat(virtualKey, payload, conversationId);
        pushDelta(res?.choices?.[0]?.message?.content ?? "");
      }
    } catch (e) {
      if (e.name !== "AbortError") {
        setError(e);
        setMessages((prev) => prev.slice(0, -1)); // drop the empty assistant bubble
      }
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  };

  const stop = () => abortRef.current?.abort();
  const newChat = () => {
    setMessages([]);
    setError(null);
    setConversationId(crypto.randomUUID()); // a fresh conversation id
  };

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_320px]">
      {/* Chat column */}
      <Card className="flex h-[calc(100vh-11rem)] flex-col">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-slate-900">Chat</span>
            <Badge tone="brand">{effectiveModel || "no model"}</Badge>
            {streaming && <Badge tone="green">streaming</Badge>}
            <Badge tone={limitReached ? "amber" : "slate"}>
              {turnsUsed}/{maxTurns} turns
            </Badge>
          </div>
          <Button variant="ghost" onClick={newChat} disabled={!messages.length}>
            <Eraser size={15} /> New chat
          </Button>
        </div>

        <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto px-5 py-5">
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center text-center text-slate-400">
              <Bot size={28} className="mb-2" />
              <p className="text-sm font-medium text-slate-500">Send a message to test the gateway</p>
              <p className="text-xs">Routed by model name to the right provider.</p>
            </div>
          ) : (
            messages.map((m, i) => <Bubble key={i} role={m.role} content={m.content} />)
          )}
        </div>

        {error && (
          <div className="mx-5 mb-2 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
            <AlertCircle size={14} className="shrink-0" />
            {error.status && (
              <span className="rounded bg-red-100 px-1.5 py-0.5 font-semibold tabular-nums">
                {error.status}
              </span>
            )}
            {/* Message comes straight from the backend's normalized error. */}
            <span className="flex-1 truncate" title={error.message}>
              {error.message}
            </span>
            <button
              onClick={() => setError(null)}
              className="shrink-0 text-red-400 hover:text-red-600"
              aria-label="Dismiss"
            >
              <X size={14} />
            </button>
          </div>
        )}

        {limitReached && (
          <div className="mx-5 mb-2 flex items-center justify-between gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
            <span className="flex items-center gap-2">
              <AlertCircle size={14} className="shrink-0" />
              Context length full ({maxTurns} turns). Start a new chat to continue.
            </span>
            <Button variant="secondary" onClick={newChat} className="shrink-0">
              <Eraser size={14} /> New chat
            </Button>
          </div>
        )}

        <div className="border-t border-slate-100 p-4">
          <div className="flex items-end gap-2">
            <Textarea
              rows={2}
              placeholder={
                limitReached
                  ? "Context full — start a new chat to keep going."
                  : "Type a message…  (Enter to send, Shift+Enter for newline)"
              }
              value={input}
              disabled={limitReached}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
            />
            {busy && streaming ? (
              <Button variant="danger" onClick={stop} className="h-[42px]">
                <Square size={15} /> Stop
              </Button>
            ) : (
              <Button
                onClick={send}
                loading={busy}
                disabled={!virtualKey || !input.trim() || limitReached}
                className="h-[42px]"
              >
                <SendHorizonal size={15} /> Send
              </Button>
            )}
          </div>
        </div>
      </Card>

      {/* Config column */}
      <div className="space-y-4">
        <Card className="space-y-4 p-5">
          <Field
            label="Model"
            hint={
              modelsQuery.loading
                ? "Loading models from the gateway…"
                : modelsQuery.error
                ? "Using fallback list (gateway unreachable)."
                : "Live from GET /v1/models."
            }
          >
            <Select
              value={customMode ? CUSTOM : model}
              onChange={(e) => {
                if (e.target.value === CUSTOM) {
                  setCustomMode(true);
                } else {
                  setCustomMode(false);
                  setModel(e.target.value);
                }
              }}
            >
              {groups.map((group) => (
                <optgroup key={group.provider} label={group.provider}>
                  {group.models.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </optgroup>
              ))}
              <option value={CUSTOM}>Custom model…</option>
            </Select>
            {customMode && (
              <Input
                className="mt-2"
                placeholder="e.g. gemini-3.1-flash-lite"
                value={customModel}
                onChange={(e) => setCustomModel(e.target.value)}
              />
            )}
          </Field>

          <Field
            label="Virtual key *"
            hint={
              virtualKey
                ? "Sent as the Bearer token. Stored locally."
                : "Required — create one on the API Keys page (sk-ingress-…)."
            }
          >
            <Input
              type="password"
              placeholder="sk-ingress-…"
              value={virtualKey}
              onChange={(e) => setVirtualKey(e.target.value)}
              className={virtualKey ? "" : "border-amber-300 focus:border-amber-400 focus:ring-amber-400/30"}
            />
          </Field>

          <Field label={`Temperature — ${Number(temperature).toFixed(1)}`}>
            <input
              type="range"
              min="0"
              max="2"
              step="0.1"
              value={temperature}
              onChange={(e) => setTemperature(e.target.value)}
              className="w-full accent-brand-600"
            />
          </Field>

          <label className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2.5">
            <span className="text-sm font-medium text-slate-700">Stream response</span>
            <input
              type="checkbox"
              checked={streaming}
              onChange={(e) => setStreaming(e.target.checked)}
              className="h-4 w-4 accent-brand-600"
            />
          </label>
        </Card>

        <Card className="p-5">
          <Field label="System prompt">
            <Textarea
              rows={4}
              value={system}
              onChange={(e) => setSystem(e.target.value)}
              placeholder="You are a helpful assistant."
            />
          </Field>
        </Card>
      </div>
    </div>
  );
}
