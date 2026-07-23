import { readdirSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitepress";

// srcDir is docs/ itself; this file sits in docs/.vitepress/.
const docsRoot = dirname(dirname(fileURLToPath(import.meta.url)));

// The per-work-item spec artifacts are part of the site too (PR #71 discussion:
// https://github.com/MadaraUchiha-314/the-loop/pull/71). The sidebar for docs/specs/
// is generated from the filesystem so new work items appear automatically — no manual
// nav upkeep. Files are ordered by the loop's own phase order.
const SPEC_FILE_ORDER = [
  ["brainstorm", "Brainstorm"],
  ["requirements", "Requirements"],
  ["bugfix", "Bugfix"],
  ["design", "Design"],
  ["tasks", "Tasks"],
  ["execution-log", "Execution log"],
];

function issueNumber(dir: string): number {
  const m = dir.match(/(\d+)$/);
  return m ? Number(m[1]) : Number.MAX_SAFE_INTEGER;
}

function specSidebarGroups() {
  const specsDir = join(docsRoot, "specs");
  const dirs = readdirSync(specsDir)
    .filter((d) => statSync(join(specsDir, d)).isDirectory())
    .sort((a, b) => issueNumber(a) - issueNumber(b));

  return dirs.map((dir) => {
    const present = new Set(
      readdirSync(join(specsDir, dir))
        .filter((f) => f.endsWith(".md"))
        .map((f) => f.replace(/\.md$/, "")),
    );
    const items = SPEC_FILE_ORDER.filter(([slug]) => present.has(slug)).map(([slug, text]) => ({
      text,
      link: `/specs/${dir}/${slug}`,
    }));
    return { text: dir, collapsed: true, items };
  });
}

const operatingModelItems = [
  { text: "Overview", link: "/operating-model/" },
  { text: "Workflow", link: "/operating-model/reference/workflow" },
  { text: "Context", link: "/operating-model/reference/context" },
  { text: "Onboarding", link: "/operating-model/reference/onboarding" },
  { text: "Instructions", link: "/operating-model/reference/instructions" },
  { text: "Design artifacts", link: "/operating-model/reference/design-artifacts" },
  { text: "Reviewing", link: "/operating-model/reference/reviewing" },
  { text: "Security", link: "/operating-model/reference/security" },
  { text: "Tooling", link: "/operating-model/reference/tooling" },
  { text: "Testing", link: "/operating-model/reference/testing" },
  { text: "Minimalism", link: "/operating-model/reference/minimalism" },
  { text: "Token economy", link: "/operating-model/reference/token-economy" },
  { text: "Collaboration", link: "/operating-model/reference/collaboration" },
  { text: "Observability", link: "/operating-model/reference/observability" },
  { text: "Automation", link: "/operating-model/reference/automation" },
];

const capabilitiesItems = [
  { text: "Overview", link: "/capabilities/capabilities" },
  { text: "Spec workflow", link: "/capabilities/spec-workflow" },
  { text: "Capability docs", link: "/capabilities/capability-docs" },
  { text: "Distribution", link: "/capabilities/distribution" },
  { text: "CLI", link: "/capabilities/cli" },
  { text: "Webhook triggers", link: "/capabilities/webhook-triggers" },
  { text: "Interactive sessions", link: "/capabilities/interactive-sessions" },
  { text: "Observability", link: "/capabilities/observability" },
  { text: "Testing & contracts", link: "/capabilities/testing-and-contracts" },
  { text: "Design artifacts", link: "/capabilities/design-artifacts" },
  { text: "Release & publishing", link: "/capabilities/release-publishing" },
  { text: "Token economy", link: "/capabilities/token-economy" },
];

const developerSidebar = [
  {
    text: "Developer documentation",
    items: [
      { text: "Architecture", link: "/architecture/architecture" },
      { text: "Contributing", link: "/contributing" },
    ],
  },
  { text: "Operating model", collapsed: true, items: operatingModelItems },
  { text: "Capabilities", collapsed: true, items: capabilitiesItems },
  {
    text: "Decisions",
    collapsed: true,
    items: [{ text: "Decision log", link: "/decisions/decisions" }],
  },
  {
    text: "Specs",
    collapsed: true,
    items: [{ text: "Overview", link: "/specs/" }, ...specSidebarGroups()],
  },
  {
    text: "Reports",
    collapsed: true,
    items: [
      { text: "Overview", link: "/reports/" },
      { text: "GitHub queries", link: "/reports/gh-queries" },
    ],
  },
];

export default defineConfig({
  title: "the-loop",
  description: "The loop for everything! An opinionated PDLC harness for Claude Code and Cursor.",
  // Served from https://<owner>.github.io/the-loop/ by the gh-pages deploy workflow.
  base: "/the-loop/",
  cleanUrls: true,
  lastUpdated: true,

  // docs/decisions and docs/capabilities carry a handful of links out to cli/README.md
  // and skills/the-loop/SKILL.md — real files, but outside this site's srcDir (docs/).
  // Rather than rewrite the canonical docs to route around the site's scope, dead-link
  // checking is disabled — those files remain readable straight from the repository
  // either way.
  ignoreDeadLinks: true,

  markdown: {
    // The docs (especially docs/specs/**) are written for GitHub-flavoured Markdown and
    // are full of angle-bracket PLACEHOLDER tokens in prose — `<session-id>`, `<slug>`,
    // `<phase>`, `<id>` — not real HTML (markdownlint's MD033 is off for the same
    // reason). VitePress compiles Markdown as a Vue template, which is far stricter than
    // GitHub's renderer and treats a bare `<session-id>` as an unclosed HTML tag,
    // breaking the build. Disabling raw-HTML passthrough makes markdown-it escape those
    // tokens to literal text (exactly how GitHub renders them). No page authors genuine
    // inline HTML in prose — real diagrams use ```mermaid fences, which are unaffected —
    // so nothing is lost, and future specs can't break the docs deploy with a stray
    // `<placeholder>`.
    html: false,
  },

  themeConfig: {
    nav: [
      { text: "Guide", link: "/guide/what-is-the-loop" },
      { text: "Reference", link: "/reference/commands" },
      { text: "CLI", link: "/cli" },
      {
        text: "Developer",
        items: [
          { text: "Architecture", link: "/architecture/architecture" },
          { text: "Capabilities", link: "/capabilities/capabilities" },
          { text: "Decisions", link: "/decisions/decisions" },
          { text: "Operating model", link: "/operating-model/" },
          { text: "Specs", link: "/specs/" },
          { text: "Reports", link: "/reports/" },
          { text: "Contributing", link: "/contributing" },
        ],
      },
    ],

    sidebar: {
      "/guide/": [
        {
          text: "Guide",
          items: [
            { text: "What is the-loop?", link: "/guide/what-is-the-loop" },
            { text: "Installation", link: "/guide/installation" },
            { text: "Quickstart", link: "/guide/quickstart" },
            { text: "How it works", link: "/guide/how-it-works" },
          ],
        },
      ],

      "/reference/": [
        {
          text: "Reference",
          items: [
            { text: "Commands", link: "/reference/commands" },
            { text: "Configuration", link: "/reference/configuration" },
          ],
        },
      ],

      "/architecture/": developerSidebar,
      "/capabilities/": developerSidebar,
      "/decisions/": developerSidebar,
      "/operating-model/": developerSidebar,
      "/specs/": developerSidebar,
      "/reports/": developerSidebar,
      "/contributing": developerSidebar,
    },

    socialLinks: [{ icon: "github", link: "https://github.com/MadaraUchiha-314/the-loop" }],

    search: {
      provider: "local",
    },

    editLink: {
      pattern: "https://github.com/MadaraUchiha-314/the-loop/edit/main/docs/:path",
      text: "Edit this page on GitHub",
    },

    footer: {
      message: "Released under the MIT License.",
      copyright: "Copyright © MadaraUchiha-314",
    },
  },
});
