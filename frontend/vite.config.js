import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The backend runs on 5000 and the dev server on 5173. Proxying /api keeps the
// browser on one origin during development, so the app works whether or not
// CORS is configured; the backend also sets CORS headers as a belt-and-braces.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:5000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
