---
type: evidence
workItem: issue-543
---

# Unit and security tests: PR-scoped specs

> Testing-plan rows T1, T8 and T10, run at commit `08fba802` on 2026-11-19 from `cli/`. The
> daemon's `THE_LOOP_*` variables were unset, as they are in CI.

| Row | Command | Outcome |
|-----|---------|---------|
| T1 | `uv run python -m pytest -q tests/test_pr_spec.py` | 118 passed in 0.88s |
| T8 | `uv run python -m pytest -q tests/test_pr_spec.py -k "abuse or forged"` | 49 passed, 69 deselected in 0.35s |
| T10 | `uv run python -m pytest -q tests/test_graph_skips.py tests/test_graph_loops.py tests/test_graph_multirepo_integration.py` | 138 passed in 1.16s |

## What T8 covers

- **AC1:** private→public refused with no grant, with an unauthorized author's grant, with
  a grant naming another repository, and with a grant on another issue. Recorded with an
  authorized grant.
- **AC2:** a failed visibility read, or a missing or unknown value, is `unknown` and
  refused.
- **AC3:** the verb writes exactly one file (`pr-spec.json`), and the hook writes none.
- **AC4:** `..`, `/`, empty and leading-dot path parts are refused, and so is a
  symlinked `docs/` that escapes the checkout.
- **AC5:** every pattern in the fixed list is a finding, and the finding never repeats
  the secret. SHA digests are not flagged.
- **Forged record:** `required: false` on a multi-PR item still blocks, and so does
  `spec-only` outside the origin or a record naming another PR.

## What T10 covers

`pr-spec` is now the inner loop's one skippable node. Seven existing assertions on the
old start node now name `pr-spec`. An inner state written before `pr-spec` existed,
sitting at `verification`, loads unchanged.
