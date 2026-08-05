import { defineConfig } from "vite";

// base "./" keeps every asset reference relative, so the same build is
// hostable at a domain root, under a GitHub Pages project path, or from a
// file server — statically hostable is a requirement (issue-161 R6.1).
export default defineConfig({
  base: "./",
});
