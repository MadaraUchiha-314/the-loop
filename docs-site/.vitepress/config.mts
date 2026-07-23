import { defineConfig } from "vitepress";

export default defineConfig({
  title: "the-loop",
  description: "The loop for everything! An opinionated PDLC harness for Claude Code and Cursor.",
  // Served from https://<owner>.github.io/the-loop/ by the gh-pages deploy workflow.
  base: "/the-loop/",
  cleanUrls: true,
  lastUpdated: true,

  // Ported content (developer/decisions, developer/capabilities, developer/operating-model)
  // carries plain-text and same-directory cross-references written for the repo's own
  // docs/ tree, including links into docs/specs/<id>/ (per-work-item historical specs)
  // that this site intentionally does not mirror. Rather than hand-rewrite every such
  // reference (and re-break it every time upstream content changes), dead-link checking
  // is disabled — the canonical files remain readable straight from the repository.
  ignoreDeadLinks: true,

  themeConfig: {
    logo: undefined,
    nav: [
      { text: "Guide", link: "/guide/what-is-the-loop" },
      { text: "Reference", link: "/reference/commands" },
      { text: "CLI", link: "/cli/" },
      { text: "Developer", link: "/developer/architecture" },
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

      "/cli/": [
        {
          text: "CLI",
          items: [{ text: "the-loop CLI", link: "/cli/" }],
        },
      ],

      "/developer/": [
        {
          text: "Developer documentation",
          items: [
            { text: "Architecture", link: "/developer/architecture" },
            { text: "Roadmap", link: "/developer/roadmap" },
            { text: "Contributing", link: "/developer/contributing" },
          ],
        },
        {
          text: "Operating model",
          collapsed: true,
          items: [
            { text: "Overview", link: "/developer/operating-model/" },
            { text: "Workflow", link: "/developer/operating-model/reference/workflow" },
            { text: "Context", link: "/developer/operating-model/reference/context" },
            { text: "Onboarding", link: "/developer/operating-model/reference/onboarding" },
            { text: "Instructions", link: "/developer/operating-model/reference/instructions" },
            { text: "Design artifacts", link: "/developer/operating-model/reference/design-artifacts" },
            { text: "Reviewing", link: "/developer/operating-model/reference/reviewing" },
            { text: "Security", link: "/developer/operating-model/reference/security" },
            { text: "Tooling", link: "/developer/operating-model/reference/tooling" },
            { text: "Testing", link: "/developer/operating-model/reference/testing" },
            { text: "Minimalism", link: "/developer/operating-model/reference/minimalism" },
            { text: "Token economy", link: "/developer/operating-model/reference/token-economy" },
            { text: "Collaboration", link: "/developer/operating-model/reference/collaboration" },
            { text: "Observability", link: "/developer/operating-model/reference/observability" },
            { text: "Automation", link: "/developer/operating-model/reference/automation" },
          ],
        },
        {
          text: "Capabilities",
          collapsed: true,
          items: [
            { text: "Overview", link: "/developer/capabilities/capabilities" },
            { text: "Spec workflow", link: "/developer/capabilities/spec-workflow" },
            { text: "Capability docs", link: "/developer/capabilities/capability-docs" },
            { text: "Distribution", link: "/developer/capabilities/distribution" },
            { text: "CLI", link: "/developer/capabilities/cli" },
            { text: "Webhook triggers", link: "/developer/capabilities/webhook-triggers" },
            { text: "Interactive sessions", link: "/developer/capabilities/interactive-sessions" },
            { text: "Observability", link: "/developer/capabilities/observability" },
            { text: "Testing & contracts", link: "/developer/capabilities/testing-and-contracts" },
            { text: "Design artifacts", link: "/developer/capabilities/design-artifacts" },
            { text: "Release & publishing", link: "/developer/capabilities/release-publishing" },
            { text: "Token economy", link: "/developer/capabilities/token-economy" },
          ],
        },
        {
          text: "Decisions",
          collapsed: true,
          items: [{ text: "Decision log", link: "/developer/decisions/decisions" }],
        },
      ],
    },

    socialLinks: [{ icon: "github", link: "https://github.com/MadaraUchiha-314/the-loop" }],

    search: {
      provider: "local",
    },

    editLink: {
      pattern: "https://github.com/MadaraUchiha-314/the-loop/edit/main/docs-site/:path",
      text: "Edit this page on GitHub",
    },

    footer: {
      message: "Released under the MIT License.",
      copyright: "Copyright © MadaraUchiha-314",
    },
  },
});
