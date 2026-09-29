---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#433"
---

# Security review: two bugs in the `hooks[]` declaration loader

> The ready-to-ship gate's security item, always required regardless of risk tier
> ([`reference/security.md`](../../../../skills/the-loop/reference/security.md)).
> A checklist read of the branch diff against the seam it touches: the parser of
> executable configuration.

## Scope of the diff

| File | Change | Runtime reach |
|---|---|---|
| `cli/the_loop/lifecycle/declaration.py` | `_normalise_keys` (one key mapped, both spellings refused); the unknown-key refusal sorts and renders with `repr` | every daemon start and every lazy load of the `hooks` declaration |
| `cli/tests/test_lifecycle_declaration.py`, `cli/tests/test_hooks_cmd.py` | regression tests | none |
| `docs/config/cli/hooks-options.md`, `docs/capabilities/lifecycle-hooks.md`, `docs/specs/issue-433/**` | prose | none |

## Findings

**None.**

## Checklist

- **Does the fix widen what a declaration may say?** No. The only key it touches is `on`,
  and only to give the operator's own spelling the name the loader already knew. The
  value still goes through `_read_on`, which still refuses anything outside the seven
  catalog points (`test_on_may_name_only_catalog_points` is unchanged and green). No
  other YAML 1.1 boolean is mapped: `yes:`, `off:` and friends stay unknown keys and are
  refused, now legibly.
- **Trust boundary.** The input is the operator's CLI config, read from the config file's
  own path — the file that already decides which modules the daemon imports
  (decision-123, decision-136). Nothing from a checkout, a session or a ticket reaches
  this parser, and the change does not add a way for it to.
- **Fail-closed posture.** Both bugs failed closed; the fix keeps every refusal a refusal.
  The both-spellings case is refused rather than merged, so an entry can never carry two
  values for `on` with the loader picking one in silence. The refusal path itself is now
  total: `repr` and a `key=repr` sort cannot raise on a hashable key, so the class that
  reaches `configure_from_file`, `_lazy_configure` and `the-loop hooks` is always
  `HooksConfigError`, and `hooks.load_failed` records the message that names the entry.
- **Secrets.** No token, credential or path is read, written or logged. The refusal
  message renders key *names*, never values, so a secret misplaced as a key's value is
  not echoed.
- **Sensitive paths.** None touched: not `**/*schema*` (the schema's `on` description is
  correct as written), not `.the-loop/**` (the commented example now loads as written),
  not `.github/workflows/**`, `**/auth/**`, `**/*secret*`, `**/*credential*`.
- **Supply chain.** No dependency added, removed or re-pinned; `uv.lock` untouched. The
  fix relies on PyYAML's documented YAML 1.1 resolution and pins that premise in a test,
  so a future loader change surfaces as a failing assertion, not a silent behaviour change.
- **Risk tier.** 2, as estimated in `bugfix.md`. No escalation trigger fired, so the
  autonomous review suffices and no named human security sign-off is required (that
  threshold is tier 4).

## Verdict

Passed, with no findings and nothing escalated. The change removes a way for a correct
declaration to be refused and a way for a refusal to lose its message; it adds no way for
an incorrect declaration to load.
