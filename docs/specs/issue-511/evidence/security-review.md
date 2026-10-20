---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#511"
---

# Security review: de-cluttering the control plane UI (Option C — Minimal)

> The `security-review` node's proof. Required before ready-to-ship unless an authorized
> human declared the phase away at `phase-selection`. See `reference/security.md`.

## Security review (gate)

- **Mechanism:** the-loop checklist (`reference/security.md` § The checklist), run against
  `git diff origin/main` at `1f60a7d` on 2026-10-20, with the abuse-case suites and the
  mechanical checks below as evidence. The harness exposes no built-in security-review
  skill in this session.
- **Outcome:** pass — no finding.
- **Findings:** none. One pre-existing observation recorded, not a finding of this change
  (below).
- **Human sign-off:** n/a (risk tier 3; no fixed sensitive path touched —
  `ui/src/components`, `ui/src/views`, `ui/src/App.tsx`, `ui/scripts`, `ui/README.md`,
  `docs/capabilities/control-plane.md` and `docs/specs/issue-511/` only).

## The checklist against the diff

| # | Item | Result | Evidence |
|---|------|--------|----------|
| 1 | every trust boundary in `design.md` § Security design is enforced where the design says | pass | untrusted text (titles, node names, the note, paths, ids, the attach command, transcript lines) reaches the DOM as React children only, in the relocated positions too — the one-line row and its `aria-label`, the header title and phase chip, the gate banner's reason, the Session details rows, the trace; `renderInline` unchanged. Tests: `Sidebar.test.tsx` "abuse case 1", `WorkItemDetail.test.tsx` "keeps markup … as text", `SessionFacts.test.tsx` "abuse case 2", `Transcript.test.tsx` "attacker-shaped tool text" ([`security.md`](security.md)) |
| 2 | untrusted inputs validated at their ingress; named injection surfaces covered | pass | no new ingress: no route, request, setting or parser; `ui/src/api`, `ui/src/state` (the hash grammar) and `ui/src/demo` are byte-identical to `origin/main` ([`build.md`](build.md)); `grep -rn "dangerouslySetInnerHTML\|innerHTML\|eval(" ui/src ui/index.html` is empty; no `fetch`, `XMLHttpRequest`, `new URL` or `location.*` assignment in the added lines |
| 3 | untrusted content cannot steer privileged behaviour | pass | the verbs call `controlSession(view.ref, verb, true, view.instance)` with the ref from the typed view, never from DOM text — the `work item` kicker is a label, not a target (`SessionFacts.test.tsx`, every verb in every state); Approve still posts `graphComplete` from the typed `parked` record; the composer posts to the viewed ref from the hash as before |
| 4 | no secrets in code, config, logs or fixtures | pass | the diff carries no token-, key- or password-like string; the fixture is unchanged; the committed stills and `capture.log` show the demo fixture's `/Users/you/…` paths only; no absolute workstation path under `docs/specs/issue-511/`; the critic's raw envelope is not committed |
| 5 | AuthZ checks fail closed | pass (n/a for AuthZ) | no identity or authorization path changes; the fail-closed signals — demo banner, connection banner (`role="alert"`), the `degraded` health word, the blocked composer's reason — render in the C layout (`App.test.tsx`, `Sidebar.test.tsx`, `Transcript.test.tsx`) |
| 6 | least privilege | pass | the two clipboard writes are 20.5.1's (`copy ref`, the attach command), on a user gesture, nothing reads the clipboard; no new network, storage key or permission; the `Open on GitHub` links keep `target="_blank" rel="noreferrer"` |
| 7 | every abuse case has a passing negative test | pass | abuse cases 1 and 2 of the requirements: [`security.md`](security.md); all 372 tests pass |
| 8 | new dependencies justified and from trusted sources | pass (none) | `ui/package.json` and `ui/bun.lock` unchanged; Playwright for the capture run is installed without saving, outside the app |

## Observation (pre-existing, unchanged by this work item)

The `Open on GitHub` links — the header icon since issue-327, and now the popover's row
in place of the panel's — take their `href` from the served record's `url`
(`record.url ?? session.url`) without a scheme check in the UI. The service is the
trusted transport and populates the field from the ticketing API, and this change neither
adds nor widens the exposure (R5.5: relocation uses what exists). A UI-side `https:`
guard on record URLs would be a separate, small work item.
