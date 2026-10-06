---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#471"
---

# Self-review: the spec chain as one Claude artifact (issue-471)

> No critics are configured in this cloud checkout (`.the-loop/cli-config.yaml` declares
> none), so the critic rounds could not run. Round 3 found nothing new, which meets the
> stop rule (3 self, 3 critic, stop on no new findings).

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition |
|-------|----------|---------|------------------------|
| 1 | self (scope read) | new findings | (a) The Slack mirror sorts an unknown token into **phases**, so `claude-artifact` would have been offered there as a skippable phase. Added to its non-phase tokens and to the pin test. (b) `test_state_portability.py` requires every state key in `docs/cli/state.md`; documented. (c) Freezing the raw tick would record `true` on a codex work item that never publishes; the gate freezes the effective value instead (design § Alternatives). |
| 2 | self (diff read) | new findings | (d) The Slack *Execute* button composes only the boxes it offers (phases and surface), so a `claude-artifact` tick on GitHub is not carried by a Slack press. That matches harness, model and effort today; the room's note now names the Claude artifact among the choices made on GitHub. (e) A frozen harness the dispatcher later refuses spawns on the default; with `claudeArtifact` already resolved, a fallback to `claude` publishes nothing (fail closed) and a fallback away from `claude` is caught by the prompt line's own guard. No change. |
| 3 | self (adversarial read) | zero (converged) | — |
| — | critic | unavailable | — |

## Questions asked of the diff, and their answers

- **Can the row skip a phase?** No. It is in `_NON_PHASE_TOKENS`, so `_parse_selection`
  skips it before any skip or refusal logic; tested ticked and unticked.
- **Can a hand-edited state file turn it on with a string?** No. Every reader uses
  `is True`; tested with `"true"`, `1`, a list and an object.
- **Does any existing confirmation change?** Yes, by one line for loops that own an
  outer loop: `Spec artifacts: markdown files only (the default).` Named in both
  directions like the model and effort lines. No existing test asserted the full text.
- **Does the prompt change for anyone who did not tick?** No. The line renders only for
  an outer-loop item with `claudeArtifact: true`; tested for PR, contribution, ad-hoc,
  review and `false`.
