# Minimalism reference — counter generation-time bloat

Autonomous agents over-produce: needless abstractions, new dependencies where the
standard library would do, duplicated logic, boilerplate. Reviewing that bloat is exactly
the human cost the-loop exists to reduce. This is **advisory** guidance that informs
generation (`minimalism.enabled` / `minimalism.intensity`); it **does not gate a merge**.

## When it applies

Apply the ladder at the two cheapest points:

1. **Design time** — the cheapest place to remove code is before it exists (a dependency
   never added needs no review). Reflect the outcome in `design.md`.
2. **Implementation self-review** — re-check the diff against the ladder before opening
   the PR.

## The decision ladder

For any new capability, prefer the earliest rung that works:

1. **YAGNI** — does this need to exist at all? Delete the requirement if not.
2. **Standard library** — can the language's stdlib do it?
3. **Native platform feature** — a built-in of the runtime/framework already present.
4. **An already-present dependency** — reuse what the project already pulls in.
5. **A small inline solution** — a few lines local to the call site.
6. **Only then** a new abstraction or a new dependency.

**Every new dependency must be justified in `design.md`** (what rung 1–5 could not do it).

## Guardrail — minimalism never removes necessary code

This is about removing *gratuitous* code, never *necessary* code. Do **not** trade away
input validation, error handling, security, or accessibility in the name of fewer lines.
Correctness and safety win over brevity every time.

`intensity` tunes how aggressively the ladder is applied (`low` / `standard` / `high`);
`enabled: false` turns the pass off entirely.
