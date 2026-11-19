/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

// The docs site owns https://<owner>.github.io/the-loop/ and this app is deployed
// beneath it at /the-loop/ui/ by .github/workflows/docs.yml, which copies dist/
// into the VitePress output. `UI_BASE` lets that workflow — or anyone serving the
// bundle from a different prefix — override the prefix without editing this file.
const base = process.env.UI_BASE ?? "/the-loop/ui/";

/**
 * The UI's copy lives in the-loop's one string catalog (issue-540), which also
 * holds every CLI message. Only the `ui.*` entries are the page's, so only those
 * are bundled: the import of `strings/en.json` is narrowed before Vite's JSON
 * plugin turns it into a module.
 */
function uiStringsOnly(): Plugin {
  return {
    name: "the-loop:ui-strings-only",
    enforce: "pre",
    transform(code, id) {
      if (!id.replace(/\\/g, "/").endsWith("/cli/the_loop/strings/en.json")) return null;
      const catalog: unknown = JSON.parse(code);
      if (catalog === null || typeof catalog !== "object") return null;
      const ui = Object.fromEntries(Object.entries(catalog).filter(([key]) => key.startsWith("ui.")));
      return { code: JSON.stringify(ui), map: null };
    },
  };
}

export default defineConfig({
  base,
  plugins: [uiStringsOnly(), react(), tailwindcss()],
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
