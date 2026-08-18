# Evidence — security review

- **Mechanism:** checklist (`reference/security.md` §The checklist). `security.review.mechanism`
  is `auto`, which prefers the built-in security-review skill; this work item was walked by
  hand in a Claude Code cloud session with no daemon (see the execution log's Deviations),
  and the checklist is the shipped fallback. Recorded as what it is rather than as a skill
  run that did not happen.
- **Effective risk tier:** 3 (`autonomy.defaultTier`). No `autonomy.sensitivePaths` entry is
  touched: no `*schema*` file, no `.the-loop/harness-config.*`, no `.github/workflows/**`.
  Below `security.review.humanSignOffMinTier` (4), so the autonomous review suffices and the
  pull-request approval is the human gate (`tiers."3": human-approves-pr`).
- **Outcome:** pass. No unresolved findings.

## The checklist, against the diff

| # | Item | Verdict | Evidence |
|---|---|---|---|
| 1 | Every trust boundary in `design.md` §Security design is enforced where the design says it is | pass | payload→argv in `linkage.py::WorkItemVerifier.is_missing` (validation before any argv is built); host in `existence_argv`; authorization untouched — the check runs after the router's guards and is strictly subtractive |
| 2 | Untrusted inputs validated at ingress; injection surfaces covered | pass | `is_github_name(owner)`/`is_github_name(repo)` — the project's single definition of "a name GitHub accepts", reused rather than re-expressed — plus an `int` number by construction on `WorkItemRef`; `subprocess.run` with an argv **list**, no shell, no `shell=True` anywhere in the new code |
| 3 | Untrusted content cannot steer privileged behaviour | pass | nothing the new code reads reaches a prompt, a path or a harness invocation; it can only *remove* refs from an event it was handed. The comment body is not read here at all |
| 4 | No secrets in code, config, logs or fixtures | pass | no token is read or written; the check runs the operator's own `gh`, which holds its own credential (decision-023). The new event fields are a ref, a source, a reason and `gh`'s own error text |
| 5 | AuthZ checks fail closed | pass (unchanged) | `is_authorized` / the self-marker guard run **before** this code and are not touched; the check cannot arm, spawn, or widen which events arrive |
| 6 | Least privilege | pass | one read-only REST GET (`repos/{o}/{r}/issues/{n}`), bounded by a 10s timeout and a 256-entry LRU, asked only for a branch-only ref on an event no live record already owns |
| 7 | Every abuse case has a passing negative test | pass | `test_hostile_coordinates_never_reach_a_gh_argv` (3 cases), `test_a_non_github_provider_is_never_asked`, `test_a_non_default_host_is_asked_of_that_host` — see `evidence/unit-and-integration.md` §T8 |
| 8 | New dependencies justified and from trusted sources | pass — none | `linkage.py` is stdlib-only (`logging`, `re`, `shutil`, `subprocess`, `collections.OrderedDict`), consistent with the router's stdlib-only rule |

## The two judgement calls, stated

- **Unknown ⇒ keep the ref (fail-open).** The one direction this guard fails open in
  restores exactly the pre-change behaviour rather than opening anything new; failing closed
  would mean "route nothing while GitHub is unreachable", which is a worse failure than the
  one being fixed. An attacker who can make `gh` fail buys today's behaviour and nothing
  more.
- **A 404 after the spawn reports, it does not kill.** GitHub answers 404 for repositories a
  credential cannot see, so ending a live agent's session — and its checkout, with whatever
  is uncommitted in it — on that signal would destroy work on an ambiguous input. The
  pre-spawn check is where a ghost is stopped; `session.work_item_missing` (error level) is
  the record, and it feeds the cache so the next event acts on it.
