---
type: design
phase: design
workItem: issue-121
status: approved             # draft | in-review | approved
approvedBy: []               # tier-3: the human gate is the PR review — see execution-log
overrides: {}
---

# Design: one harness-config reader, one recorded rule

> Phase 2 of 3 (requirements → design → tasks). Derived from the approved
> `requirements.md`. MUST be reviewed/approved before the tasks breakdown.

## Architecture

Three changes that reinforce each other: a **module** that is the only place the harness
config is read, a **decision record** that says when reading it is allowed, and **docs**
that stop contradicting both.

### A1. `the_loop.harness_config` — the single reader

A new module beside `cli_config.py`, deliberately its mirror image: `cli_config.py` is
"the operator's file, resolved from four places, never repo-scoped"; `harness_config.py`
is "the repository's file, resolved from one place, always repo-scoped".

```text
cli/the_loop/
  cli_config.py       # the operator's machine  — webhooks / polling / eventLog / integrations
  harness_config.py   # a repository's policy   — workflow / reviews / testing / notifications
```

Surface:

| Name | Purpose |
|---|---|
| `FILENAMES` | `("harness-config.yaml", "config.yaml")` — the rename fallback, expressed **once** (issue-82, decision-035) |
| `config_path(root)` | The first of `FILENAMES` that exists under `root/.the-loop`, else `None` |
| `load(root)` | Best-effort parse → `dict`; `{}` for absent / unparseable / non-mapping |
| `load_strict(root)` | Same, but raises `HarnessConfigError` for unparseable / non-mapping |
| `READS` | The declared read surface: a tuple of `HarnessConfigRead(key, command, why)` |

Two load functions rather than a flag, because the two behaviours are genuinely different
policies and each caller has already chosen one:

- `check` / `graph` / `scenarios` are **best-effort** — a repository that has never seen
  the harness config still has to gate, and a broken file must not stop a CI job from
  reporting the phase it can compute (`bootstrap.py`'s existing contract).
- `critic` is **strict** — `load_critics` raises `CriticConfigError` on an unparseable
  file today, and must keep doing so: a review round that silently reviews nothing is a
  false green.

`READS` is the point of the module. It is what turns "which keys does the CLI read?" from
a grep into a lookup, and it is what the test in A3 asserts against:

```python
READS = (
    HarnessConfigRead("workflow.phaseLabelPrefix", "check, graph, daemon", "..."),
    HarnessConfigRead("workflow.specDir",          "check, graph, daemon", "..."),
    HarnessConfigRead("notifications",             "check, graph, daemon", "..."),
    HarnessConfigRead("reviews.critics",           "critic",              "..."),
    HarnessConfigRead("testing.integrationTestGlobs", "scenarios",        "..."),
)
```

Call sites collapse onto it, keeping their existing public names as thin aliases so no
importer or test outside the package changes:

| Call site | Before | After |
|---|---|---|
| `graph/bootstrap.py` | own `load_harness_config`, own 2-name loop | `load_harness_config = harness_config.load` (re-exported, `__all__` unchanged) |
| `critics.py` | own `config_path`, own `yaml.safe_load` + error wrapping | `config_path = harness_config.config_path`; `load_critics` calls `load_strict`, re-raising as `CriticConfigError` |
| `commands/scenarios.py` | own `_load_config_globs` with its own candidate list | `_load_config_globs` reads `harness_config.load(root)` |

Why not one function with a `strict=` flag, like `cli_config._load_cli_config_raw`? Because
`cli_config`'s two modes are the *same* policy at two moments (start-up vs hot-reload),
while these are two different callers' contracts. A flag would let a future caller pick
the wrong one silently; two named functions make the choice legible at the call site.

Why is `notifications` read whole rather than by leaf? Because `build_runtime` passes the
block through to the graph runtime's hooks unexamined. `READS` declares the block, and the
schema assertion resolves it as a block — the honest description of what is read.

### A2. Decision-044 — the invariant

The rule the code has always followed, stated in one line:

> **A repository's harness config may configure work done *on that repository*. It may
> never configure the daemon itself.**

Not "daemons read `cli-config.yaml`, one-shot commands read `harness-config.yaml`". That
framing was never quite right and stopped being true when issue-113 wired `graphlink`
into the shared dispatcher: the daemon reads a work item's own checkout for
`phaseLabelPrefix` / `specDir` / `notifications`, on purpose, *after*
`_checkout_belongs_to` proves the checkout is that repository's.

The record refines decision-032 rather than reversing it. Decision-032's real content was
never "the daemon must not open that file" — it was "**the daemon's own settings** must not
come from a checkout", which is the ⟵ direction and stays absolutely true. The record
states both directions explicitly, with the four rejection reasons from
`requirements.md`, and lists `graph/model.py`'s `.the-loop/graph.yaml` / `pdlc.yaml`
override as the other read that already obeys the same rule.

### A3. `cli/tests/test_harness_config.py` — the pin

Four assertions, in the idiom of `test_docs_parity.py` (pure filesystem reads, no
network, no fixtures, skipped on a source distribution for the doc halves):

| # | Assertion | Catches |
|---|---|---|
| H1 | every `READS` key resolves in `.the-loop/harness-config.schema.json` | a key declared under a name the schema does not have |
| H2 | no module outside `harness_config.py` mentions a harness-config filename in a path expression | a fourth reader added quietly |
| H3 | every `READS` key appears in `docs/config/harness-config.md`'s CLI-read table | reading a key nobody documented |
| H4 | every key in that table appears in `READS` | documenting a read that no longer happens |

H2 is the one that does the work, and it is deliberately a *source* assertion rather than
a behavioural one: there is no runtime signal for "somebody opened this file", and the
failure mode this pins is a contributor adding a fourth reader — which is visible in the
diff, and only in the diff. It matches on the filename constants appearing next to
`.the-loop`, so a docstring that merely *mentions* `harness-config.yaml` (there are
several, and they are good) does not trip it.

### A4. Documentation

| Page | Change |
|---|---|
| `docs/config/index.md` | Replace the `::: warning The daemon never reads…` block with the directional rule; keep the fail-closed `authorizedUsers` / `repos` warning, which is the part that was load-bearing. Rewrite the "three exceptions worth memorising" list, which is now four and is not a list of exceptions. |
| `docs/cli/concepts.md` | Same correction, one paragraph. |
| `docs/cli/commands/index.md` | The daemon/repo-scoped split stays (it is a useful reading of *what the commands are*), but the parenthetical "not any repository's harness config" goes. |
| `docs/cli/index.md` | Mermaid: keep the two halves, add the daemon → work item's checkout edge, so the diagram shows the thing the prose now says. |
| `docs/config/harness-config.md` | New **"What the CLI reads from it"** section — the table H3/H4 assert against, plus the direction rule and a link to decision-044. |
| `docs/cli/extending.md` | The "do not mix them" guidance gains the direction rule, since that page is where a new command's author decides which file to read. |
| `docs/capabilities/cli.md` | The invariant + a history row for issue-121. |

## Alternatives considered

- **Move the keys to `cli-config.yaml`** — the issue's own third question. Rejected for
  the four reasons in `requirements.md` § Analysis: wrong cardinality, a second source of
  truth against the skill, breaking `check`/`scenarios` in a bare CI checkout, and
  inverting a trust argument that only runs one way.
- **Split the difference: keep policy in the harness config but let `cli-config.yaml`
  override per repository.** Rejected — it buys one real use case (an operator who wants
  a different critic than the repository declares) at the cost of making every value's
  provenance ambiguous, and the harness config already has a per-work-item override
  mechanism (spec front-matter `overrides`) that lives next to the work it changes.
- **Fix only the docs.** Tempting — the code is correct as-is, and R5 says nothing about
  behaviour changes. Rejected because the three duplicated readers are *why* the rule was
  never stated: with no single place that reads the file, there was nowhere for the rule
  to live and nothing for a test to pin. The refactor is small (net negative lines) and it
  is what makes R4 possible.
- **Delete the pre-rename `config.yaml` fallback while consolidating.** Rejected — out of
  scope, and it is a real compatibility promise (decision-035). Consolidating it into one
  constant makes the eventual removal a one-line change.
- **Assert H2 with an import hook or a runtime open() shim** instead of a source scan.
  Rejected: it would only catch a read on a path the test happens to execute, which is
  precisely not the failure mode (a new command with no test yet).

## Security design

No trust boundary moves. Restating the requirements' threat model at the level of this
design:

- **The ⟵ direction stays closed.** Nothing in `harness_config.py` is reachable from
  `cli_config.py`, and no ingress/routing key gains a harness-config fallback.
  `authorizedUsers` and `polling.sources[].repos` remain CLI-config-only and fail closed —
  the tests that pin that (`test_trust.py`, `test_poller.py`) are untouched and must stay
  green.
- **The ⟶ direction stays gated where it matters.** The daemon's read is still behind
  `graphlink._checkout_belongs_to` (origin-remote match, fails closed). This design adds
  no new caller of `harness_config.load` on the ingress path.
- **`reviews.critics[]` is unchanged.** The one executable key keeps its strict load, its
  `_validate` fail-closed path, its explicit-by-name invocation and its `shell=False`
  spawn (decision-043). `load_strict` exists specifically so consolidation does not
  quietly downgrade it to best-effort — that downgrade would be the one way this refactor
  could become a security regression, and H2 plus the existing `test_critics.py` cover it.
- **Parsing is unchanged.** Still `yaml.safe_load`, never `yaml.load`. Consolidation
  reduces the number of parse call sites from three to one, which shrinks the surface on
  which that could ever be got wrong.
- **`READS` discloses nothing.** Every key is already in the published schema and the
  shipped template.

## Testing strategy

`tdd.mode: standard` — the pin (A3) is written first and goes red before the module
exists, then the module and the docs turn each assertion green.

| Layer | What |
|---|---|
| New unit | `test_harness_config.py`: `config_path` prefers `harness-config.yaml`, falls back to `config.yaml`, returns `None` for neither; `load` returns `{}` for absent / unparseable / non-mapping / empty; `load_strict` raises for unparseable and non-mapping but returns `{}` for absent. |
| New parity | H1–H4 above. |
| Regression (untouched) | `test_critics.py`, `test_critics_integration.py` (unparseable still raises `CriticConfigError`; duplicate names still raise), `test_cli.py`'s scenarios coverage (config globs, pre-rename fallback), `test_graph_*.py` (`build_runtime` defaults), `test_docs_parity.py`. **No pre-existing test may be edited** — R5.2 makes that the evidence that behaviour did not change. |
| Gates | `make check` — `ruff check`, `ruff format --check`, `pyright`, `markdownlint`, `validate_config.py`, the full pytest suite. |
| Process gate | `uv run the-loop check issue-121 --recompute --fail-on block` — this repository's own graph gate on its own spec. |

Gherkin (`testing.requireGherkinDocstrings`) applies to integration tests; H1–H4 and the
loader unit tests are unit-scoped, matching `test_docs_parity.py`, which is the closest
precedent in the tree.
