import { useRef, useState } from "react";
import { Bot, Eraser, SendHorizonal, Square, User } from "lucide-react";
import { useSettings } from "../lib/settings.jsx";
import { chatStream, createApi } from "../lib/api.js";
import { MODEL_CATALOG } from "../lib/models.js";
import { Badge, Button, Card, Field, Input, Select, Textarea, cx } from "../components/ui.jsx";

const DEFAULT_SYSTEM = "You are a helpful assistant.";

function Bubble({ role, content }) {
  const isUser = role === "user";
  return (
    <div className={cx("flex gap-3", isUser && "flex-row-reverse")}>
      <div
        className={cx(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
          isUser ? "bg-brand-600 text-white" : "bg-slate-200 text-slate-600"
        )}
      >
        {isUser ? <User size={16} /> : <Bot size={16} />}
      </div>
      <div
        className={cx(
          "max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm",
          isUser
            ? "rounded-tr-sm bg-brand-600 text-white"
            : "rounded-tl-sm border border-slate-200 bg-white text-slate-800"
        )}
      >
        {content || <span className="text-slate-400">…</span>}
      </div>
    </div>
  );
}

export default function Playground() {
  const { apiBase, virtualKey, setVirtualKey } = useSettings();

  const [model, setModel] = useState("gpt-4o-mini");
  const [system, setSystem] = useState(DEFAULT_SYSTEM);
  const [temperature, setTemperature] = useState(0.7);
  const [streaming, setStreaming] = useState(true);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const abortRef = useRef(null);
  const scrollRef = useRef(null);

  const scrollDown = () =>
    requestAnimationFrame(() => {
      const el = scrollRef.current;
      if (el) el.scrollTop = el.scrollHeight;
    });

  const send = async () => {
    if (!input.trim() || busy) return;
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
      model,
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
          { baseUrl: apiBase, apiKey: virtualKey },
          payload,
          { onDelta: pushDelta, signal: abortRef.current.signal }
        );
      } else {
        const api = createApi({ baseUrl: apiBase });
        const res = await api.chat(virtualKey, payload);
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
  const clear = () => {
    setMessages([]);
    setError(null);
  };

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_320px]">
      {/* Chat column */}
      <Card className="flex h-[calc(100vh-11rem)] flex-col">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-slate-900">Chat</span>
            <Badge tone="brand">{model}</Badge>
            {streaming && <Badge tone="green">streaming</Badge>}
          </div>
          <Button variant="ghost" onClick={clear} disabled={!messages.length}>
            <Eraser size={15} /> Clear
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
          <div className="mx-5 mb-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error.message}
          </div>
        )}

        <div className="border-t border-slate-100 p-4">
          <div className="flex items-end gap-2">
            <Textarea
              rows={2}
              placeholder="Type a message…  (Enter to send, Shift+Enter for newline)"
              value={input}
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
              <Button onClick={send} loading={busy} className="h-[42px]">
                <SendHorizonal size={15} /> Send
              </Button>
            )}
          </div>
        </div>
      </Card>

      {/* Config column */}
      <div className="space-y-4">
        <Card className="space-y-4 p-5">
          <Field label="Model">
            <Select value={model} onChange={(e) => setModel(e.target.value)}>
              {MODEL_CATALOG.map((group) => (
                <optgroup key={group.provider} label={group.provider}>
                  {group.models.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </optgroup>
              ))}
            </Select>
          </Field>

          <Field label="Virtual key" hint="Sent as the Bearer token. Stored locally.">
            <Input
              type="password"
              placeholder="sk-ingress-…"
              value={virtualKey}
              onChange={(e) => setVirtualKey(e.target.value)}
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
