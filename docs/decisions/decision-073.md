# Decision 073: the-loop adopts an unconfigured repository with a packaged default — except as a guest

- **Status:** proposed — the human gate is the pull request
- **Date:** 2026-08-10
- **Deciders:** MadaraUchiha-314 (approver)
- **Work item:** [issue-193](https://github.com/MadaraUchiha-314/the-loop/issues/193)

## Context

[Issue #193](https://github.com/MadaraUchiha-314/the-loop/issues/193) asks for two things:
that a repository without `.the-loop/` be worked under *a default harness config*, and
that the-loop *create* `.the-loop/harness-config.yaml` when it finds none.

Before this, "the default" was not a thing at all. `harness_config.load` returned `{}` for
an unconfigured repository and each caller supplied its own literal —
`DEFAULT_SPEC_DIR = "docs/specs"` here, `"loop:"` there, an empty `ticketing.github` that
made `originRepo` fail closed. The agent had it worse: the daemon clones the repository,
spawns a session in it, and the session finds no config at all, so the skill has no
workflow, no tooling and no phase list to work from and improvises one.

Three questions had to be settled together.

**Where does the default live?** The CLI ships independently of the plugin
(`pip install the-loopy-one`), so it cannot read `skills/the-loop/templates/`. issue-152
already recorded what happens when runtime data lives only in the plugin: `the-loop check`
failed, advising operators to set `CLAUDE_PLUGIN_ROOT` to a plugin they had never
installed — which is why the process graphs moved into the package.

**Where does adoption happen?** On the ingress path the graph is skipped for a work item
with no spec directory — which is *every* brand-new work item. Adopting only where the
graph moves would leave the ticket's own case unfixed, because the session the daemon just
spawned is already running in that checkout.

**Does a contribution adopt?** PR #187 decided that a repository the-loop is invited into
as a contributor keeps the-loop out of its history: the spec tree is excluded from git and
the plan is published to the thread. A committed `.the-loop/harness-config.yaml` declaring
the-loop's process would be the loudest possible breach of that.

## Decision

**One default, shipped in the CLI package.** `cli/the_loop/harness-config.default.yaml` is
a byte-for-byte copy of `skills/the-loop/templates/harness-config.yaml`, pinned by a test,
and validated against the harness schema by `make validate` in its own right. One
configuration with two writers — the-loop's ingress and `/the-loop:init` — rather than two
configurations sharing a name. `harness_config.defaults()` reads it; the surviving per-key
literals stay for the case where nothing can be written, and a test pins them to it.

**One writer, at two call sites.** `harness_config.scaffold(root, owner, repo)` is the only
function that creates a harness config, in the only module allowed to open that filename
(decision-044). It is called by `GraphLink._guarded` — after the ownership proof, before
the spec-directory gate — and by `core.graphs._runtime(adopt=True)`, which the four
state-changing graph verbs pass and no reader does. `check`'s purity (issue-109 R8.8) is
therefore visible in the call, not promised in prose.

**A guest does not install itself.** `pdlc-contribution-loop` never adopts, at either call
site. Issue-185's behaviours — spec tree excluded from git, artifacts published to the
thread — keep applying to exactly the repositories they were written for.

**An existing config is never opened.** A repository configured under either filename is
left byte-for-byte as it is. Adoption creates; it never migrates. `owner`/`repo` are the
only payload-derived text in the written bytes and must match `^[A-Za-z0-9][A-Za-z0-9._-]*$`
— dropped rather than escaped when they do not, so there is no encoder to get wrong.

## Consequences

**Easier.** Pointing the-loop at a repository that never ran `/the-loop:init` now works:
the session reads a real config, `originRepo` resolves, and "what does the-loop assume
here?" is answered by a file in the repository rather than by reading the source. The
written file says who wrote it and how to replace it, and `the-loop events` records each
write as `harness.config_scaffolded`.

**Harder.** the-loop now creates a file in repositories it works in — a side effect it did
not have before. It is bounded by the ownership proof, by never touching an existing
config, and by the contribution carve-out; an operator who wants none of it can leave the
graph coupling off (`routing.graph.enabled: false`) or configure the repository properly.

**Unchanged.** The CLI's harness-config **read** surface (`READS`) and its four parity
assertions; `load`/`load_strict`'s best-effort contract; the `no-spec-dir` skip; every
`repoInitialized`-driven behaviour, which now simply stops applying to a repository the
moment it has been adopted — on the very run that adopted it, because adoption precedes
`build_runtime`.

## Alternatives considered

- **Defaults in memory only, nothing written.** Answers the ticket's first sentence and not
  its second, and leaves the agent — the harness config's primary reader — with nothing to
  read.
- **Resolve the template through `CLAUDE_PLUGIN_ROOT`.** Rejected on issue-152's evidence:
  that variable is absent in every CI checkout and every `pip` install, which is where
  `check` and the daemon actually run.
- **A Python dict serialized with `yaml.safe_dump`.** Rejected: it destroys the template's
  inline comments, which are most of what the file is worth to the human who opens it, and
  it creates a second "the defaults" that would drift from `/the-loop:init`'s.
- **Adopt inside `build_runtime`.** One choke point, and it would make `the-loop check`
  write to disk — losing the property that lets CI run the real runtime.
- **Adopt in `Runtime.start`.** Never reached on the ingress path for a fresh work item:
  the spec-directory gate returns first, which is precisely the case the ticket describes.
- **Adopt on contributions too, and exclude `.the-loop/` from git like the spec tree.**
  Rejected: an excluded config is invisible to the humans reviewing the contribution, and
  it would leave `repoInitialized` — the flag driving issue-185's whole shape — meaning two
  different things depending on which file it found.
