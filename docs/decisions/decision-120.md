# Decision 120: a Slack kickoff's repository is chosen by a first-line prefix resolved against the operator's declared set; unresolvable or ambiguous is refused, an unmatched bare word falls back, and `kickoff.repo` stops being a precondition

- **Status:** proposed
- **Date:** 2026-09-11
- **Work item:** [issue-341](https://github.com/MadaraUchiha-314/the-loop/issues/341)
- **Deciders:** jc1993 (the ask), the-loop (design); MadaraUchiha-314 (owner, at the PR)
- **Refines:** [decision-116](decision-116.md) D4 (a command may name only a repository
  this instance is configured for), [decision-103](decision-103.md) D1 (through the
  ledger, never around it), [decision-111](decision-111.md) D1 (a refusal leaves no mark
  — narrowed here: an *authorized* refusal now answers)

## Context

Kickoff has taken exactly one repository since issue-309: `channels.slack.kickoff.repo`,
with an empty value disabling the path and the code comment saying why — *"there is no
sensible inferred answer to which repository does this DM become an issue in"*.

Issue-341 does not dispute that. It observes that the answer is not being *inferred*: a
the-loop instance already carries a closed, operator-written list of repositories in
`polling.sources[].repos` — twelve, in the reporter's case — read every poll cycle, and
already used by the slash command to bound its target (decision-116 D4). Choosing among
that list is a different question from inferring from prose, and the reporter drives
twelve repositories from a phone, where a hardcoded target means most issues land
somewhere they have to be moved from by hand.

Four questions had to be settled: **what the universe of targets is**; **what happens
when a name resolves to none or to several**; **what an unmatched bare word before a
colon means when a fallback exists**; and **whether the grant is still dead
configuration without `kickoff.repo`**.

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **The universe is the operator's declared set and nothing else**: `channels.slack.kickoff.repo` plus every `repos` entry of every `github` source in `polling.sources`, resolved to `host/owner/repo` keys against this instance's host. One builder (`channels/repos.py`), two callers — `may_target` and the kickoff resolver. | It is the same closed set decision-116 D4 already bounds a slash command to, and bounding two inbound shapes by two different lists is how they drift. It needs no new config key, so nothing new has to be kept in sync, and the set can only shrink under a fault, never widen. What reaches `gh --repo` is the operator's own declared string, never the member's text. |
| D2 | **A prefix that resolves to none (when qualified) or to several is refused, not guessed**: the ⚠️ reaction on the member's own message and a reply in its thread naming the candidates. Nothing is created, recorded or bound. | This is the ticket's own request, and it is what keeps the feature safe to have: a wrong guess writes an issue into a repository the member did not mean, which is exactly the failure they are asking to be rid of. A refusal costs one retype and is visible on the phone where the ❌ is. |
| D3 | **An unmatched *bare* prefix is judged not to be a prefix at all** — the message is handled as prefix-less (the fallback, or a refusal when there is none) with its text intact. A **qualified** one (`owner/repo:`) is still refused. | `fix: flaky teardown` is an ordinary English first line, and under a strict reading of "refuse anything that does not resolve" every conventional-commit-shaped kickoff on every existing install would start being rejected — the ticket asks in the same breath that existing installs behave identically. A word before a colon is ambiguous evidence; `owner/repo:` is not, and has no reading as prose, so that is where refusal starts. The cost is bounded: the message lands in the operator's own fallback repository and the "Opened `owner/repo#N`" reply names it. |
| D4 | **`kickoff.repo` is demoted from precondition to fallback, including for *reading*:** `kickoff_enabled` now requires the grant and a channel, not a target. Grant-without-target becomes prefix-only kickoff, where a message with no prefix is refused with a helpful reply instead of dropped in silence. | `work-item.create` plus no `kickoff.repo` was a configuration that parsed, validated and did nothing — the worst kind. A person who granted the channel the right to open issues has said what they want; what was missing was a way to say *where*, and D1 supplies it. The refusal is only ever sent to a member who has already passed the allow-list, so the repository list is not disclosed by turning this on. |

## Consequences

**Good.** One word puts a kickoff in the right repository, for every repository the
instance already polls. The grant stops having a dead configuration. The slash command
and kickoff now agree on what "a repository this instance is configured for" means, from
one builder. No schema key, no grant, no scope, no state is added, so a 13.11.1 config
upgrades untouched.

**Bad / risk.** A bare prefix that is a typo (`slim-gim:`) lands in the fallback
repository with the typo in the title rather than being refused (D3) — mitigated by the
answer naming the created ref, and by qualified prefixes being strict. Turning the grant
on without a `kickoff.repo` now makes the channel *read* top-level messages where before
it read none; the first-sight baseline still means no backlog becomes issues, and every
unauthorized message is still dropped in silence. A refusal is one more message in the
channel than a silent drop — deliberate, and only for authorized members.

**Neutral.** `kickoff.labels` stays one list for every target; per-repository labels are
a separate ask. The prefix is read from the first line only — a deliberate limit that
keeps the grammar unambiguous.
