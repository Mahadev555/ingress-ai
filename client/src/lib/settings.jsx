import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { createApi } from "./api.js";

const SettingsContext = createContext(null);

function persisted(key, fallback = "") {
  return localStorage.getItem(key) ?? fallback;
}

export function SettingsProvider({ children }) {
  // Empty base URL => same-origin (the Vite dev proxy forwards to the gateway).
  const [apiBase, setApiBase] = useState(() => persisted("ig.apiBase", ""));
  const [adminToken, setAdminToken] = useState(() => persisted("ig.adminToken", ""));
  const [virtualKey, setVirtualKey] = useState(() => persisted("ig.virtualKey", ""));

  useEffect(() => localStorage.setItem("ig.apiBase", apiBase), [apiBase]);
  useEffect(() => localStorage.setItem("ig.adminToken", adminToken), [adminToken]);
  useEffect(() => localStorage.setItem("ig.virtualKey", virtualKey), [virtualKey]);

  const api = useMemo(
    () => createApi({ baseUrl: apiBase, adminToken }),
    [apiBase, adminToken]
  );

  const value = {
    apiBase,
    setApiBase,
    adminToken,
    setAdminToken,
    virtualKey,
    setVirtualKey,
    api,
    hasAdmin: Boolean(adminToken),
  };

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}

export function useSettings() {
  const ctx = useContext(SettingsContext);
  if (!ctx) throw new Error("useSettings must be used within SettingsProvider");
  return ctx;
}
