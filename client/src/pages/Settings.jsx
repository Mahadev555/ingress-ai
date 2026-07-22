import { useState } from "react";
import { CheckCircle2, PlugZap, Save, XCircle } from "lucide-react";
import { useSettings } from "../lib/settings.jsx";
import { createApi } from "../lib/api.js";
import { Button, Card, CardHeader, Field, Input } from "../components/ui.jsx";

export default function Settings() {
  const settings = useSettings();
  const [apiBase, setApiBase] = useState(settings.apiBase);
  const [adminToken, setAdminToken] = useState(settings.adminToken);
  const [virtualKey, setVirtualKey] = useState(settings.virtualKey);
  const [saved, setSaved] = useState(false);
  const [test, setTest] = useState(null); // { ok, message }
  const [testing, setTesting] = useState(false);

  const save = () => {
    settings.setApiBase(apiBase.trim());
    settings.setAdminToken(adminToken.trim());
    settings.setVirtualKey(virtualKey.trim());
    setSaved(true);
    setTimeout(() => setSaved(false), 1800);
  };

  const runTest = async () => {
    setTesting(true);
    setTest(null);
    try {
      const api = createApi({ baseUrl: apiBase.trim(), adminToken: adminToken.trim() });
      await api.health();
      if (adminToken.trim()) {
        await api.usage(); // verifies the admin token too
        setTest({ ok: true, message: "Gateway reachable and admin token valid." });
      } else {
        setTest({ ok: true, message: "Gateway reachable. Add an admin token for the admin pages." });
      }
    } catch (e) {
      setTest({ ok: false, message: e.message });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <Card>
        <CardHeader
          title="Connection"
          subtitle="Point the console at your gateway and authenticate the admin API."
        />
        <div className="space-y-4 p-5">
          <Field
            label="Gateway base URL"
            hint="Leave empty to use the dev proxy (same origin → http://localhost:8000)."
          >
            <Input
              placeholder="(empty = dev proxy)  or  https://gateway.example.com"
              value={apiBase}
              onChange={(e) => setApiBase(e.target.value)}
            />
          </Field>

          <Field label="Admin token" hint="Sent as X-Admin-Token. Matches the gateway's ADMIN_API_KEY.">
            <Input
              type="password"
              placeholder="your-admin-token"
              value={adminToken}
              onChange={(e) => setAdminToken(e.target.value)}
            />
          </Field>

          <Field label="Default virtual key" hint="Used to prefill the playground. Stored locally.">
            <Input
              type="password"
              placeholder="sk-ingress-…"
              value={virtualKey}
              onChange={(e) => setVirtualKey(e.target.value)}
            />
          </Field>

          <div className="flex items-center gap-2 pt-1">
            <Button onClick={save}>
              <Save size={15} /> {saved ? "Saved" : "Save"}
            </Button>
            <Button variant="secondary" onClick={runTest} loading={testing}>
              <PlugZap size={15} /> Test connection
            </Button>
          </div>

          {test && (
            <div
              className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm ${
                test.ok
                  ? "border border-emerald-200 bg-emerald-50 text-emerald-700"
                  : "border border-red-200 bg-red-50 text-red-700"
              }`}
            >
              {test.ok ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
              {test.message}
            </div>
          )}
        </div>
      </Card>

      <Card>
        <CardHeader title="About" subtitle="Everything stored here stays in your browser (localStorage)." />
        <div className="space-y-2 p-5 text-sm text-slate-600">
          <p>
            The console talks to the Ingress AI gateway over its OpenAI-compatible and admin APIs.
            No credentials are sent anywhere except your configured gateway.
          </p>
          <p className="text-slate-400">
            Admin endpoints require an admin token; the playground uses a virtual key.
          </p>
        </div>
      </Card>
    </div>
  );
}
