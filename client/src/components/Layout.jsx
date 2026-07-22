import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  BarChart3,
  KeyRound,
  LayoutDashboard,
  Settings as SettingsIcon,
  TerminalSquare,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Logo } from "./Logo.jsx";
import { cx } from "./ui.jsx";
import { useSettings } from "../lib/settings.jsx";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/keys", label: "API Keys", icon: KeyRound },
  { to: "/playground", label: "Playground", icon: TerminalSquare },
  { to: "/usage", label: "Usage", icon: BarChart3 },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
];

const TITLES = {
  "/": "Overview",
  "/keys": "API Keys",
  "/playground": "Playground",
  "/usage": "Usage & Metrics",
  "/settings": "Settings",
};

function HealthPill() {
  const { api, apiBase } = useSettings();
  const [status, setStatus] = useState("checking");

  useEffect(() => {
    let alive = true;
    setStatus("checking");
    api
      .health()
      .then((r) => alive && setStatus(r?.status === "ok" ? "online" : "degraded"))
      .catch(() => alive && setStatus("offline"));
    return () => {
      alive = false;
    };
  }, [api, apiBase]);

  const map = {
    checking: { dot: "bg-slate-300", text: "Checking…", cls: "text-slate-500" },
    online: { dot: "bg-emerald-500", text: "Gateway online", cls: "text-slate-600" },
    degraded: { dot: "bg-amber-500", text: "Degraded", cls: "text-amber-600" },
    offline: { dot: "bg-red-500", text: "Gateway offline", cls: "text-red-600" },
  };
  const s = map[status];

  return (
    <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium">
      <span className={cx("h-2 w-2 rounded-full", s.dot)}>
        {status === "online" && (
          <span className="block h-2 w-2 animate-ping rounded-full bg-emerald-400 opacity-75" />
        )}
      </span>
      <span className={s.cls}>{s.text}</span>
    </div>
  );
}

export default function Layout() {
  const location = useLocation();
  const title = TITLES[location.pathname] ?? "Ingress AI";

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <aside className="hidden w-64 shrink-0 flex-col bg-slate-900 md:flex">
        <div className="px-5 py-5">
          <Logo />
        </div>
        <nav className="flex-1 space-y-1 px-3 py-2">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cx(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-brand-600 text-white"
                    : "text-slate-300 hover:bg-slate-800 hover:text-white"
                )
              }
            >
              <Icon size={18} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="px-5 py-4 text-[11px] text-slate-500">
          <div className="rounded-lg bg-slate-800/60 p-3">
            <p className="font-semibold text-slate-300">Ingress AI</p>
            <p className="mt-0.5">One API across OpenAI, Anthropic, Gemini &amp; Azure.</p>
          </div>
        </div>
      </aside>

      {/* Main */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-slate-200 bg-white/80 px-6 py-3.5 backdrop-blur">
          <div>
            <h1 className="text-lg font-bold text-slate-900">{title}</h1>
          </div>
          <HealthPill />
        </header>

        <main className="flex-1 overflow-y-auto px-6 py-6">
          <div className="mx-auto max-w-6xl animate-fade-in">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
