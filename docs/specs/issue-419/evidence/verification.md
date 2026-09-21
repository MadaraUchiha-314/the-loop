---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#419"
---

# Verification: one verbosity switch over the whole trace, defaulting to quiet

> The `verification` node's record, against
> [testing-plan.md](../testing-plan.md). Every command below was run in this
> session from `ui/` after `bun install --frozen-lockfile`.

## Results

| Row | Command | Outcome |
|-----|---------|---------|
| T1 | `bun run test src/api/model.test.ts` | **pass** — 101 tests (37 of them new: the `isReadable` row table and the `isBookkeeping` classification table) |
| T2 | `bun run test src/components/Transcript.test.tsx` | **pass** — 18 tests (10 new, covering both views quiet and verbose, the hidden-count line and its singular) |
| T3 | — | n/a as planned; the diff touches no route, schema or payload |
| T4 | `bun run test src/App.test.tsx` | **pass** — the panel loads with the switch off and no tool group, and the switch restores them |
| T5 | browser pass, below | **pass** — four screenshots committed beside this file |
| T6 | — | n/a as planned |
| T7 | — | n/a as planned |
| T8 | `bun run test src/api/model.test.ts src/components/Transcript.test.tsx` | **pass** — an `error` in a hidden family is never classified as plumbing, and renders in the trail |
| T9 | `bun run test src/App.test.tsx` | **pass** — `role="switch"`, `aria-checked` tracking, `aria-label` no longer `Tool calls`, `Enter` and space both toggling |
| T10 | `bun run test` | **pass** — 266 tests, 16 files. Nothing persisted changed; see the Python note below |
| T11 | — | **not run** — no live service with a long-polled work item exists in this environment; the demo fixture's trail (T5) is the closest available and is committed |
| T12 | `markdownlint-cli2` over the changed Markdown | **pass** — 0 errors over 5 files |

Also run, as the CI `ui` job runs them:

| Command | Outcome |
|---------|---------|
| `bun run lint` (oxlint, type-aware) | **pass**, no findings |
| `bun run build` (runs `tsc --noEmit` first) | **pass** — 59 modules, 311.86 kB |

## The browser pass (T5)

The built app in demo mode behind `bun run preview --port 4173`, driven by Playwright
against the pre-installed Chromium, one capture per state opened fresh. Counts read off
the live DOM:

| State | Item | `aria-checked` at load | Rows |
|-------|------|------------------------|------|
| `trace-quiet-{light,dark}.png` | `loop-lab#214` (transcript served) | `false` | 0 tool groups |
| `trace-verbose-{light,dark}.png` | same, after one click | `true` | 2 tool groups |
| `trail-quiet-{light,dark}.png` | `loop-lab#187` (no transcript) | `false` | 0 event rows, and the hidden-count line in their place |
| `trail-verbose-{light,dark}.png` | same, after one click | `true` | 1 event row (`poll.spawn_failed`) |

The quiet trace screenshot is the acceptance criterion made visible: the human reply, the
agent's two prose turns, the `thinking` disclosure, the `malformed` finding and the
question banner, with no tool group between them. The quiet trail's single hidden row is a
`level=warning` `poll.spawn_failed` — the documented trade-off in `design.md`
§ What it costs, seen working.

The switch returns to its default when another work item is opened, because the panel
remounts per item. That is wanted: quiet is the default per item, not once per tab.

## The Python side

`make check` **could not run here**: this container's `uv` is 0.8.17 and
`pyproject.toml` requires `>=0.12, <0.13`, and `uv self update` is refused by a GitHub
API rate limit. The change touches no Python — `git diff --stat` lists seven files, all
under `ui/` and `docs/` — so no Python behaviour is in scope for this work item. The
repository's CI runs `make check` on the pull request, and that run is the proof.
