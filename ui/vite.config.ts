import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// /api is proxied to the FastAPI server in dev and preview, so the UI needs
// no configuration and the browser sees a single origin.
const proxy = { "/api": { target: "http://127.0.0.1:18760", changeOrigin: true } };

export default defineConfig({
  plugins: [react()],
  server: { proxy },
  preview: { proxy },
});
