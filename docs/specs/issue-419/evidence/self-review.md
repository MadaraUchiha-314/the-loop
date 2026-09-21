---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#419"
---

# Self-review: one verbosity switch over the whole trace, defaulting to quiet

> The `self-review` node's proof, per `reference/reviewing.md`. Critic rounds: no critic
> is configured on this machine (`critics[]` is empty in the checked-in CLI config and no
> critic CLI is installed), so the critic rounds are recorded **unavailable** and do not
> count toward the operator's `criticReviewCount`.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition |
|-------|----------|---------|------------------------|
| 1 | self (this session) | new findings | 4 found, 3 fixed, 1 accepted as designed — below |
| 2 | self (this session) | zero (converged) | re-read the whole diff against the acceptance criteria and the abuse case; no new finding |
| critic 1–3 | — | **unavailable** | no critic configured on this machine |

## Round 1 findings

**F1 — the hidden-count line said "1 bookkeeping events hidden".** Found in the browser
pass, not in a test: the first screenshot of `loop-lab#187` rendered the plural noun over a
count of one. **Fixed**: `HiddenNote` now takes a singular noun and writes
`1 … hidden — turn on Verbose to see it` or `n …s hidden — … to see them`, with a test
for each in both views.

**F2 — hiding the tool groups would have left a bare `the-loop` header.** A turn whose
whole content was `tool_use` blocks projects to an assistant row with no text and no
thinking. Filtering only the meta rows would have left its header line and an empty body —
a new blank row in the fix for blank rows. **Fixed**: `isReadable` is a question about the
**projected row**, so such a turn is dropped whole; asserted in `model.test.ts` and again
end to end in `Transcript.test.tsx`.

**F3 — the trail's row budget was spent before the filter.** The old mapping sliced the
newest 40 events and then rendered them; filtering after that slice would hide 40
bookkeeping rows and show nothing, while a `graph.parked` sat at position 41. **Fixed**:
`EventTrail` filters first and slices second, with a test that puts 50 `poll.cycle` rows
ahead of one `graph.parked` and requires the latter to render.

**F4 — a `warning` in a hidden family is hidden.** `poll.spawn_failed` and a
`spawn-policy` `dispatch.dropped` disappear with the switch off. **Accepted as designed**:
the issue names `dispatch.dropped` as the noise to remove and sets the escape hatch at
`level=error`, and widening it to `warning` would bring the loudest offender straight
back. Recorded in `design.md` § What it costs and visible in the T5 trail screenshots,
where the one hidden row is exactly such a warning.

## Round 2

Re-read the diff whole against `bugfix.md`'s four requirements and the abuse case. Checked
in particular:

- the gate banner and the question banner render **outside** the filtered panel, so R2.3
  holds by construction — and the T5 screenshot shows the question banner with the switch
  off;
- `transcript.data.entries.length === 0` keeps its own empty state, so "the transcript
  holds nothing" and "the filter hid everything" stay distinguishable (R4.3);
- `EventLine` lost its `export` once `WorkItemDetail` stopped importing it — no dead
  public surface left behind;
- two lint findings that appeared mid-session (`useAsync.ts`, `WorkItemDetail.tsx:109`)
  came from an `npm i --no-save playwright` re-resolving oxlint, not from this change.
  With `bun install --frozen-lockfile` — what CI uses — `bun run lint` is clean, and
  `git status` shows no lockfile drift.

No new finding.
