import { defineConfig } from "vitepress";

// docs/specs/<id>/ are per-work-item historical artifacts (brainstorm/requirements/
// design/tasks/execution-log) and docs/reports/ are internal working notes — real,
// version-controlled content, but not "documentation" in the product-site sense.
// Excluded from the built site (still readable directly in the repository); PR #71
// discussion: https://github.com/MadaraUchiha-314/the-loop/pull/71.
const srcExclude = ["specs/**", "reports/**"];

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
      { text: "Roadmap", link: "/roadmap" },
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
];

export default defineConfig({
  title: "the-loop",
  description: "The loop for everything! An opinionated PDLC harness for Claude Code and Cursor.",
  // Served from https://<owner>.github.io/the-loop/ by the gh-pages deploy workflow.
  base: "/the-loop/",
  cleanUrls: true,
  lastUpdated: true,
  srcExclude,

  // docs/decisions and docs/capabilities carry a handful of links out to cli/README.md
  // and skills/the-loop/SKILL.md — real files, but outside this site's srcDir (docs/),
  // and links into docs/specs/<id>/ (excluded above). Rather than rewrite the canonical
  // docs to route around the site's scope, dead-link checking is disabled — those files
  // remain readable straight from the repository either way.
  ignoreDeadLinks: true,

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
          { text: "Roadmap", link: "/roadmap" },
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
      "/roadmap": developerSidebar,
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
