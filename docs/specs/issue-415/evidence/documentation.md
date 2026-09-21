---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#415"
---

# Documentation: the `/the-loop:init` onboarding a person can finish

> The `documentation` gate's record. RULE: the affected capability docs change in the
> same PR as the change.

| Document | Change |
|---|---|
| `docs/capabilities/distribution.md` | Current-behaviour clauses for the CLI-config walkthrough, the autonomy ladder and its confinement, the deployment shape, the Slack walkthrough and the credential preflight; the `--defaults` clause extended; a history row for issue-415 |
| `docs/guide/onboarding.md` | **New.** The user-facing page: the two questions only they can answer, the ladder as a table, what init walks through, Slack in four sentences, the credential table, and what to do when something is missing |
| `docs/.vitepress/config.mts` | Sidebar entry, between Installation and Quickstart |
| `docs/guide/quickstart.md` | §1 rewritten — init now establishes **both** configs and reports missing credentials; links the new page |
| `docs/guide/installation.md` | "Next" points at the onboarding page before the quickstart |
| `skills/the-loop/reference/onboarding.md` | The procedure itself: two configs one procedure, the deployment shape, the autonomy ladder, the credential preflight, and R7's presentation contract folded into §How to present a group |
| `commands/init.md` | 8 steps → 11, and a statement of what a finished init owes the user |

Not changed, deliberately:

- **`docs/guide/slack.md`** stays the 868-line reference. The walkthrough links it; the
  whole point of R7.5 is that init does not restate it.
- **`docs/config/cli/`** gains no page. `x-onboarding` is metadata about the walkthrough,
  not an operator-settable option — and `additionalProperties: false` would reject it in
  a user's own `cli-config.yaml`, so documenting it as an option would mislead.

The skill's `reference/` tree is synced into `docs/operating-model/reference/` at build
time (`docs/scripts/sync-content.mts`), so the rewritten `onboarding.md` reaches the site
without a second copy.
