# Evidence — the reader's pass (issue-174)

Testing-plan row **T11**: read the rewritten `README.md` and the three changed site pages as
a first-time reader, and check the three things a build cannot check — that the ordering the
requirements ask for holds, that every link resolves, and that every process statement
agrees with the shipped graph.

## R1/R2 — what the README now leads with, and how much shorter it is

| Requirement | Check | Result |
|-------------|-------|--------|
| R1.1 — the graph leads; the plugins are one surface | First sentence of the README | "an opinionated product-development lifecycle, shipped as an **executable process graph** and a daemon that runs it". The word *plugin* first appears in §The agent plugins, the fifth section |
| R1.2 — both loops named, and the seam stated | §Two loops | `pdlc-work-item-loop` and `pdlc-pr-loop` named with their scopes; the seam is stated as "the outer `implementation` node waits at `await-inner-loops` until every inner loop that was started reaches `complete`", plus the vacuous-pass case |
| R1.3 — four artifacts, `testing-plan.md`'s role stated | §The artifact chain | All four listed in order in a table; `testing-plan.md`'s row states it is written before the task DAG that references its rows, reviewed with the design, and completed at `verification` |
| R1.4 — the phase sequence matches the graph | Compared below | Match |
| R2.2 — shorter than its predecessor | `wc -l` | **265 → 166 lines**, a 37% reduction, while adding the two loops, the seam, the four-artifact table and the regenerated diagram |
| R2.4 — an explicit next step into the site | Second paragraph and every section footer | "**[Read the documentation](…)**" up front, plus per-section link rows |

What was removed, and where the reader now finds it:

| Removed from the README | Now at |
|-------------------------|--------|
| The two per-command tables (13 commands) | `/reference/commands` |
| The full install matrix (terminal, Claude Code, Cursor marketplace, Cursor local) | `/guide/installation` |
| The repository-layout tree | `/guide/how-it-works` |
| The 12-item "Rules the loop enforces" list | `/guide/what-is-the-loop` |
| The "How it works" bullet list (config, manifest, templates, skills) | `/guide/how-it-works` |
| The "v0 foundation" status block and the four-item roadmap | Deleted, not moved — the repository is at v8.0.0 and every roadmap item has shipped or become an issue. A status block that must be re-approved every release is a drift generator |

## R1.4 / R3.3 — the phase sequence, against the shipped graph

```console
$ uv run --project cli python -c "import yaml; print(' -> '.join(
    yaml.safe_load(open('.the-loop/harness-config.yaml'))['workflow']['phases']))"
not-started -> brainstorming -> requirements-definition -> design -> test-planning
  -> tasks-breakdown -> implementation -> verification -> needs-review -> complete
```

`test_p4_the_graph_defines_the_phase_sequence` asserts this list against
`pdlc-work-item-loop.yaml`'s node phases, in both the repository's own config and the
bundled template. The identical sequence appears in `README.md` §Two loops and in
`docs/guide/what-is-the-loop.md` §Two loops — copied from the command above, not retyped.

The node ids behind it, read from the loaded graph:

```console
$ uv run --project cli python -c "from the_loop.graph.model import load_graph; \
    print([(n.id, n.phase) for n in load_graph().nodes])"
[('brainstorming', 'brainstorming'), ('requirements-definition', 'requirements-definition'),
 ('requirements-approval', ''), ('design', 'design'), ('test-planning', 'test-planning'),
 ('design-approval', ''), ('tasks-breakdown', 'tasks-breakdown'),
 ('implementation', 'implementation'), ('verification', 'verification'),
 ('self-review', 'needs-review'), ('critic-review', ''), ('security-review', ''),
 ('evidence', ''), ('capability-docs', ''), ('reviewer-briefing', ''),
 ('human-approval', ''), ('complete', 'complete'), ('escalated', '')]
```

`what-is-the-loop.md`'s mermaid diagram renders these node ids and the three human gates in
this order; the README's Excalidraw diagram is checked the same way in
[`diagram.md`](diagram.md) (T13). The inner loop's sequence is read from
`pdlc-pr-loop.yaml`: `implementation → verification → self-review → critic-review →
security-review → reviewer-briefing → pr-approval → complete`.

## R2.3 — every link resolves

`ignoreDeadLinks: true` means the VitePress build does not catch a broken internal link, so
links are checked by resolving each one to a file.

### README — repository-relative links (source the site does not render)

```console
OK   CLAUDE.md
OK   LICENSE
OK   cli/
OK   cli/the_loop/graph/
OK   docs/assets/the-loop-workflow.excalidraw
OK   docs/assets/the-loop-workflow.svg
OK   skills/the-loop/SKILL.md
```

### README — site links, each resolved to the page that serves it

```console
OK   cli/              -> docs/cli/index.md
OK   cli/commands/     -> docs/cli/commands/index.md
OK   cli/concepts      -> docs/cli/concepts.md
OK   cli/getting-started -> docs/cli/getting-started.md
OK   cli/installation  -> docs/cli/installation.md
OK   config/           -> docs/config/index.md
OK   contributing      -> docs/contributing.md
OK   guide/installation -> docs/guide/installation.md
OK   guide/quickstart  -> docs/guide/quickstart.md
OK   guide/what-is-the-loop -> docs/guide/what-is-the-loop.md
OK   operating-model/  -> docs/operating-model/index.md
OK   reference/commands -> docs/reference/commands.md
```

All 13 are absolute `https://madarauchiha-314.github.io/the-loop/…` URLs, per R2.3 and the
same reasoning that governs `cli/README.md`: the README renders outside this repository,
where a relative site path is dead.

### The three changed site pages

```console
--- docs/index.md ---
OK   /capabilities/process-graph
OK   /cli/
OK   /guide/quickstart
OK   /guide/what-is-the-loop
--- docs/guide/what-is-the-loop.md ---
OK   /capabilities/capabilities
OK   /capabilities/process-graph
OK   /guide/installation
OK   /guide/quickstart
     /operating-model/reference/testing   ← build-time path, see below
--- docs/guide/how-it-works.md ---
OK   /capabilities/process-graph
OK   /cli/commands/graph
OK   /config/
OK   /decisions/decisions
OK   /operating-model/
OK   /specs/
```

`/operating-model/reference/testing` has no file in the source tree **by design**:
`docs/scripts/sync-content.mts` copies `skills/the-loop/reference/` →
`docs/operating-model/reference/` at build time, because that source is read at *runtime* by
the harness from its own path and cannot move.

```console
$ grep -n "reference" docs/scripts/sync-content.mts
2:  // skills/the-loop/reference/*.md is read at RUNTIME by the harness from that exact path,
31:  ["skills/the-loop/reference", "operating-model/reference", rewriteReferenceLinks],
58:  console.log("docs: synced skills/the-loop/reference/ -> docs/operating-model/reference/");
```

The sidebar already links the same path (`docs/.vitepress/config.mts`, "Testing" →
`/operating-model/reference/testing`), and markdownlint excludes the generated directory —
both consistent with it being generated rather than authored.

## R3.1 / R3.2 — the site's entry pages

| Page | Checked | Result |
|------|---------|--------|
| `docs/index.md` | Hero and the four feature cards | The tagline leads with the graph; the cards are *Two loops, one process* · *The process is executable* · *A CLI that drives it* · *Gated, reviewed, documented*. The first card links to `/capabilities/process-graph` |
| `docs/guide/what-is-the-loop.md` | Both loops, four artifacts, no v0 block, the documentation rule | All present. The v0 status block is gone; the rules list gained *testing is planned then executed*, *security is gated not bolted on*, and *the user-facing docs ship with the change too* |
| `docs/guide/how-it-works.md` | "The process is data", the refreshed layout | A new leading section names both graph YAMLs, the node/hook/edge model, and the four consequences (internal to the-loop · gates read artifacts · a force never forges a verdict · the graph assigns). The layout tree gained `cli/the_loop/graph/`, `docs/api-specs/`, `skills/writing/`, `testing-plan.md` and `evidence/` |

## What this pass does not prove

The gate this work item adds is **structural** — it proves a `## Documentation` record
exists, not that the record or the documentation it names is any good. This review is the
judgement half, and it is one reader's; the human approval on the PR is the other half.
