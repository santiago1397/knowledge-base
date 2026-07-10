import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: proxy API + media to the local FastAPI so `npm run dev` mirrors prod.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/auth": "http://localhost:8000",
      "/media": "http://localhost:8000",
    },
  },
});
