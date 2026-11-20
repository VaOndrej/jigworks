import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Local development without `vercel dev`: the API runs under uvicorn on :8000.
const api = process.env.HUB_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": { target: api } } },
  preview: { proxy: { "/api": { target: api } } },
});
