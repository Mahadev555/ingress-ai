import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy gateway routes to the backend during dev so the browser makes
// same-origin requests (no CORS needed). Change the target if your gateway
// runs elsewhere.
const GATEWAY = process.env.VITE_GATEWAY_URL || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/v1": { target: GATEWAY, changeOrigin: true },
      "/admin": { target: GATEWAY, changeOrigin: true },
      "/health": { target: GATEWAY, changeOrigin: true },
      "/metrics": { target: GATEWAY, changeOrigin: true },
    },
  },
});
