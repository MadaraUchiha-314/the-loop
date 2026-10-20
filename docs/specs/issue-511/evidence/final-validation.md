---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#511"
---

# Final validation: de-cluttering the control plane UI (Option C — Minimal)

> The `evidence` node's proof: what is presented to the user to show the acceptance
> criteria are met. **Summarised from the executed verification** —
> [`testing-plan.md`](../testing-plan.md) § Verification results (every planned
> activity ran and passed; re-run after the self-review and critic rounds) — and mapped
> onto the acceptance criteria rather than re-derived. Raw captures sit beside this file
> under `evidence/`.

Every acceptance criterion of the approved requirements is met. The three that were
proved by a human decision rather than a test (R1.4, R1.5, R3's pick) are recorded on
PR #513 and in [decision-148](../../../decisions/decision-148.md).

## Final validation evidence

| Acceptance criterion | How it was proved | Where |
|----------------------|-------------------|-------|
| R1.1–R1.3 three nested options, one inventory each | the three prototypes and the 66-row inventory with a verdict per option, generated from one template; the design critic round | [`design.md`](../design.md) § Element inventory, [`design/`](../design/), [`design-critic-review.md`](design-critic-review.md) |
| R1.4, R1.5 presented together; the pick recorded | the design PR with the stills side by side; the owner's choice on PR #513; the design's inventory row marked selected; decision-148; the unchosen prototypes kept | [PR #513](https://github.com/MadaraUchiha-314/the-loop/pull/513), [`design.md`](../design.md) § UI/UX design |
| R2.1 each fact drawn once by default | T2 scenarios: the header meta (ref chip · phase chip · note · age), the node written once (#205: one `human-approval` in the main column), the tmux target only in the attach command, the age only as `updated` | [`integration.md`](integration.md); stills 02, 07, 13 in [`ui-visual.md`](ui-visual.md) |
| R2.2 a row is identity + urgency | T2: one-line row `#n · title · urgent flag`; no flag for paused / merged / closed | [`integration.md`](integration.md) |
| R2.3 identifiers on demand | T2: session id, transcript path and cwd in full inside the closed Session details disclosure | [`integration.md`](integration.md); still 13 |
| R2.4 no bookkeeping | T2: no `n of m`, no tally, no delivery hint; the Needs you count only | [`integration.md`](integration.md) |
| R2.5 one position | T1 `railNote`; T2 the chip as the one statement; the strip without `at <node>` | [`unit.md`](unit.md), [`integration.md`](integration.md) |
| R2.6 one-member chrome not drawn | T2: one-session tab bar hidden; no Standing group; no instance filter on a worker | [`integration.md`](integration.md) |
| R3.3 Option C's removals | every C verdict of the inventory has a T2 scenario; the stills match the prototype's | [`integration.md`](integration.md), [`ui-visual.md`](ui-visual.md) |
| R3.4 one-interaction reachability | T2: the verbs in the header (every verb, every state), Approve on the gate banner, the question with the composer, the title and ref in the header | [`integration.md`](integration.md), [`security.md`](security.md) |
| R4 design system untouched | no token, font, shadow or gradient added; `app.css` unchanged except nothing; only existing primitives (`IconButton` gained an `aria-expanded` prop); CSS smaller than the branch point | [`build.md`](build.md); `git diff origin/main -- ui/src/styles` empty |
| R5.1 api / state / demo untouched | T12 diff empty | [`build.md`](build.md) |
| R5.2 every action has a home | T2 and the verbs scenarios; copy ref and attach command; search behind the toggle; instance filter on a fleet; theme; sidebar collapse/reopen; Standing, Settings, Instances suites unchanged and green | [`integration.md`](integration.md) |
| R5.3 every state still renders | T2: loading, empty board, missing deep link, fallback, truncated tail, blocked composer, connection banner, demo banner, degraded word, empty rail (critic round) | [`integration.md`](integration.md), [`security.md`](security.md) |
| R5.4 every hash lands | T2 hash scenario; `route.test.ts` unchanged | [`integration.md`](integration.md) |
| R5.5 nothing added to compensate | no route, request, setting, dependency or copy control; the disclosure toggles are the existing idiom | [`security-review.md`](security-review.md), [`build.md`](build.md) |
| R6.1–R6.4 accessible, responsive | T9: `aria-expanded`, the named `<summary>`, row names, `aria-current` (including a blocked pointer), `role="log"`, the switch's keys, the 768 px rule, the popover closed at every width and bounded; reduced-motion guard present | [`integration.md`](integration.md); stills 12, 12c |
| R7.1 browser evidence | 32 headless stills, both themes, 1440×900 and 390×844, no page error | [`ui-visual.md`](ui-visual.md), [`ui/`](ui/) |
| R7.2 before/after count | 56 → 27, recounted on the built app by inventory row | [`ui-visual.md`](ui-visual.md) |
| R8 documentation | README and the capability doc describe the C layout | [`documentation.md`](documentation.md) |
| NFR build, tests, bundle, dependency | lint, 372 tests, build clean; JS 336 965 B (was 341 685), CSS 24 350 B (was 24 469); no dependency | [`lint-and-typecheck.md`](lint-and-typecheck.md), [`build.md`](build.md) |
| Security AC1, AC2, fail-closed | the abuse-case tests and the fail-closed signals; the checklist against the diff | [`security.md`](security.md), [`security-review.md`](security-review.md) |
