# Decision 069: the outer loop runs in the origin repository, and its surface is declared

- **Status:** proposed
- **Date:** 2026-08-09
- **Deciders:** @MadaraUchiha-314 (issue #183 — the topology and the option are the owner's)
- **Work item:** issue-183
- **Spec:** `docs/specs/issue-183/`
- **Refines:** [decision-065](decision-065.md) (the PDLC is two loops) — this says *where*
  each of them runs when the work spans repositories.
- **Amends:** [decision-051](decision-051.md) §5, whose invariant was "artifact iteration
  happens in pull-request review". It becomes: artifact iteration happens on a **durable,
  reviewable surface** — the pull request or the ticket — never in a terminal.

## Context

Issue #183, verbatim: *"When a work item needs contributions into multiple repos, then the
initial contribution for the outer loop should work only in the repo where the issue was
created … if n number of repos need contribution, then n PRs will be raised for the inner
loop in those respective repos."* And: *"Users should be given an option whether to make
the outer loop on the issue or as PRs … The inner loop has no configurability."* The reason
given is concrete: *"to prevent unnecessary PRs … The-loop PR is open, which never gets
closed or merged in because it was just for brainstorming and requirements."*

decision-065 split the process into two loops but left the *topology* unsaid, and the
shipped harness assumed single-repo in four separate places: a qualified closing reference
to another repository was dropped by the router; an inner loop was keyed by PR number
alone; artifact iteration required a pull request; and `await-inner-loops` could not tell
"no contributions needed" from "the contribution was never opened".

## Decision

| Sub-decision | What was chosen | Why |
|---|---|---|
| **D1 — the outer loop runs in the origin repository** | the repository the ticket was created in (`ticketing.github`); the work item's one spec chain lives there, and every inner loop's state under it | The ticket is the work item's identity, and the spec chain is the work item's. One spec chain in one place is what decision-065 D2/D4 already protect; this says which place. |
| **D2 — one contributing repository, one pull request, one inner loop** | *n* repositories ⇒ *n* PRs; the origin repository gets one only if it also receives code | The ticket's own words. It is also the smallest arrangement that keeps each repository's review where its code is. |
| **D3 — an inner loop is qualified by repository, and the origin's layout does not move** | `pr-loops/<owner>__<repo>/pr-<n>/` for a contributing repository; `pr-loops/pr-<n>/` unchanged for the origin | A PR number is unique within a repository, not between them. Two layouts is the price of not migrating work items that are mid-flight; the shipped path staying byte-identical is worth more than uniformity. |
| **D4 — the repository name is validated, never sanitized** | at least two segments, each `[A-Za-z0-9._-]+`, never `.`/`..`; `ValueError` otherwise, at every path-building call site | The value becomes a directory name and arrives from a webhook payload or an operator's `--pr-repo`. A name quietly rewritten into a valid one files one repository's inner-loop state under another repository's name — worse than a refusal. |
| **D5 — cross-repo closing references route** | a qualified `Closes <owner>/<repo>#<n>` (or URL form, or a `closingIssuesReferences` entry naming its repository) yields a ref in *that* repository; the branch convention stays local | Without it, a PR in a contributing repository cannot reach its own work item at all. The previous rule — "a closing reference to another repository is not ours" — held only while a work item lived in one repository. |
| **D6 — cross-repo linkage is unconditional, not a new toggle** | no config key gates it | Two pre-existing boundaries already bound it: the ingress (an event only arrives from a repository the operator's receiver or poll source covers) and arming (an unstarted work item drops at `_awaiting_start`). A toggle would be a second name for "the operator configured this repository". |
| **D7 — the outer loop's surface is declared; the inner loop's is not** | `workflow.outerLoop.surface`: `issue` \| `pull-request`, default `pull-request`. `pdlc-pr-loop` carries no equivalent, here or anywhere | The ticket's own asymmetry. The default preserves every existing repository's behaviour on upgrade — the ticket asks for the *option*, not for a new default. |
| **D8 — `surface` chooses the review surface, not whether artifacts are checked in** | the spec chain is committed and linked from the ticket in both settings | Every gate in the process graph reads files. A spec that lives only in comments could not be gated, locked, or diffed — and "reference, don't duplicate" would invert. |
| **D9 — with `surface: issue`, a pull request in the origin repository is a *landing* PR** | opened after the chain is locked and the inner loops have finished, or not at all when the origin repository is itself a contributing repository | This is the ticket's actual complaint answered: the PR that exists is one with something to merge, not a discussion that never closes. |
| **D10 — declared repositories are a gate** | `repos:` in `execution-log.md`'s front matter; `await-inner-loops` holds `implementation` until each declared repository has a loop **and** every started loop has finished; declaring nothing keeps the vacuous pass | The vacuous pass is load-bearing for single-repo work and must stay. Across repositories it hides a real failure — a PR that was planned and never opened — so the fix is an explicit declaration rather than a changed default. Inferring the set from `tasks.md` prose would make a gate depend on parsing prose, which the graph exists to avoid. |
| **D11 — a malformed `repos:` entry blocks; a missing loop waits** | `block` for an unusable repository name, `wait` for work in progress | Waiting on `../../etc` waits forever. A fault in a checked-in file is a fault; an unopened PR is patience. |
| **D12 — the session is told, not left to infer** | the assignment and the prompt context name the resolved surface, and a cross-repo claim command carries `--pr-repo` | The same argument decision-051 §4 makes for the interaction directive: a rule the session never reads is a rule that does not hold. A claim without `--pr-repo` would evaluate a *different* loop. |

## Consequences

**Positive.**

- The ticket's shape is now expressible: three repositories, three PRs, one spec chain, no
  discussion-only PR anywhere.
- A PR in a contributing repository can reach its work item at all — previously impossible.
- `pr-loops/pr-7/` cannot mean two different pull requests.
- A planned contribution that never arrives is a held gate naming the repository, instead of
  a pass.
- Nothing existing moves: no state migration, no config migration
  (`CURRENT_CONFIG_VERSION` untouched), and a repository that adds neither `outerLoop` nor
  `repos:` behaves exactly as it did.

**Negative / accepted costs.**

- **Two state layouts.** `pr-loops/pr-<n>/` and `pr-loops/<owner>__<repo>/pr-<n>/` coexist
  forever. Accepted for the back-compat it buys; the reader of a checkout sees the
  qualifier only where it is needed.
- **`__` is a lossy encoding.** `owner/repo` → `owner__repo` cannot be reversed
  unambiguously for a repository name containing `__`. Nothing reverses it: declared
  repositories are matched forward, by key. Anything that later wants the reverse must
  record the repository, not parse the directory name.
- **The origin repository must be configured for the declared-repos gate.** Without
  `ticketing.github`, a top-level `pr-<n>/` cannot be attributed, and a declaration naming
  the origin repository waits. Fail-closed and self-describing, but it is a new way for a
  half-configured repository to hold a gate.
- **Cross-repo routing widens what an event can name.** A hostile PR in a *watched*
  repository can now name a work item in another watched repository, and — if that work
  item is armed — get its comments delivered into that session. This is the same exposure a
  hostile PR in the origin repository already had; the untrusted-excerpt framing in the
  prompt is the mitigation, unchanged.
- **D9 and the surface rules are guidance, not gates.** the-loop opens no pull requests, so
  nothing mechanically prevents a session from opening a discussion PR under
  `surface: issue`. The record is the execution log's `## Pull requests` section, which the
  `reviewer-briefing` node already gates for presence — not for judgement.
- **decision-051's invariant is weaker by one surface.** The configuration it refused —
  specs iterated in a terminal, reasoning dying with the scrollback — is still refused. What
  it did not distinguish, and this does, is that the ticket is as durable and as public as
  the pull request.

## Alternatives considered

| Option | Why not |
|---|---|
| One repo-qualified layout for every inner loop (`pr-loops/<owner>__<repo>/pr-<n>/` always) | Tidier, and it strands every work item mid-flight behind a state migration for a cosmetic gain. |
| Put `surface` in the CLI config beside `interaction.mode` | Different axes. `interaction.mode` says where a *human is sitting* — a property of the operator's machine (decision-032). `surface` says how a *project reviews its specs* — a property of the project, which a daemon watching N repositories cannot know for each of them. |
| Default `surface` to `issue` | It is the better default for multi-repo work and a behaviour change for every existing repository on upgrade. The ticket asks for an option. |
| Infer the contributing repositories from `tasks.md` | A gate that parses prose is the thing decision-041 exists to avoid; and the inference would be wrong exactly when it matters (a repository named in passing). |
| A config toggle for cross-repo linkage | See D6: the ingress and the arming gate already bound it. |
| Record the whole `owner/repo` inside each inner `graph-state.json` instead of in the path | The path has to be unique regardless — two loops cannot share a directory — so the state field would be a second source of the same fact. |
| Let the-loop open the landing PR itself | the-loop opens no pull requests anywhere; adding a first one here would be a new GitHub write path for a rule the agent can follow. |
