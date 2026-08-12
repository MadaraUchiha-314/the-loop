/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The docs site owns https://<owner>.github.io/the-loop/ and this app is deployed
// beneath it at /the-loop/ui/ by .github/workflows/docs.yml, which copies dist/
// into the VitePress output. `UI_BASE` lets that workflow — or anyone serving the
// bundle from a different prefix — override the prefix without editing this file.
const base = process.env.UI_BASE ?? "/the-loop/ui/";

export default defineConfig({
  base,
  plugins: [react()],
  build: {
    outDir: "dist",
    sourcemap: true,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
