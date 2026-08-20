# Security review (issue-274)

- **Mechanism:** the checklist in `skills/the-loop/reference/security.md`
  (`security.review.mechanism: auto` → no built-in security-review skill was available in
  this session, so the checklist is the recorded fallback).
- **Effective risk tier:** 3 (`autonomy.defaultTier`; no `sensitivePaths` touched — no
  schema, no `.github/workflows/**`, no `harness-config.yaml`). Below
  `security.review.humanSignOffMinTier: 4`, so no named human security sign-off is
  required; human approval of the pull request still applies (tier 3 = `human-approves-pr`).
- **Reviewed against the diff:** `cli/the_loop/core/sessions.py`,
  `cli/the_loop/commands/sessions_cmd.py`, `cli/the_loop/api/routes.py`,
  `cli/the_loop/api/mcp.py`, `cli/the_loop/sdk/client.py`, `cli/the_loop/eventlog.py`,
  `docs/api-specs/openapi/the-loop.v1.yaml` and the documentation.
- **Outcome:** pass, no findings.

## Checklist

| # | Item | Verdict | Evidence in the diff |
|---|---|---|---|
| 1 | every trust boundary in `design.md` §Security design is enforced where the design says it is | **pass** | one mechanism each, in the order the function runs them: `WorkItemRef.parse` before anything is opened; the self-link refusal before the registry is touched; `find_by_work_item(...) is None` → return, before any write; and the write itself is the unchanged `SessionRegistry.link_pull_request` |
| 2 | untrusted inputs validated/constrained at their ingress; injection surfaces covered | **pass** | no webhook payload reaches this code — the dispatcher's payload-derived binding path (`_record_pr_binding`) is untouched. The two inputs are refs from an operator's shell or an authenticated API client, both parsed by `WorkItemRef.parse` (which is what bounds owner/repo/host/number shape) before the registry is opened; the file name is `WorkItemRef.slug`, the same sanitised derivation the registry has always used. `--pull-request` accepts a bare number only through `^#?(\d+)$`, and a non-positive number is refused |
| 3 | untrusted content cannot steer privileged behaviour | **pass** | the operation writes one endpoint on an **existing, live** record. It cannot create a record, cannot arm a work item, cannot spawn or resume a session, cannot post anything remote, and cannot widen `authorizedUsers`. Every delivery it makes possible still passes the unchanged `routing.control` gate and the unchanged named-actor check on control keywords |
| 4 | no secrets in code, config, logs or fixtures | **pass** | the reused `session.pr_linked` event carries a work-item ref and a pull-request ref — no tokens, no bodies, no hostnames beyond the ref's own host, which is the operator's own GitHub host |
| 5 | AuthZ checks fail closed | **pass** | reachability *is* the authorization here, and it is not widened: local shell access (which already reaches `sessions start`/`stop`/`register --force`) or an API credential on the same authenticated surface as the sibling `register`/`close` routes. On no record, the operation fails **closed** — nothing written, exit 1 |
| 6 | least privilege | **pass** | no new file, network or process access; no `gh` invocation; no filesystem path accepted over HTTP (the body is two refs), matching the deliberate rule on the existing session routes |
| 7 | every abuse case from the requirements has a passing negative test | **pass** | "can it invent a work item?" → `test_link_pull_request_without_a_session_record_writes_nothing`; "can a work item deliver itself?" → `test_link_pull_request_refuses_a_work_item_delivering_itself`; "does a malformed ref reach the filesystem?" → `test_link_pull_request_refuses_malformed_input` (six cases, each asserting nothing was written) |
| 8 | new dependencies justified and from trusted sources | **n/a** | none added |

## Abuse case, stated

An attacker who can call this operation can point a pull request's events at a session
they do not own. They can already do strictly more: the operation requires local shell
access or an API credential, either of which also reaches `sessions start`, `sessions stop`
and `sessions register --force`. It adds no reachability those do not already grant, and
unlike them it performs no remote action and destroys nothing.

## Residual risk, accepted and recorded

There is no `unlink` verb (design.md §Trade-offs, decision-098 D11), so a binding written
in error is corrected with `sessions reset`, which forgets this machine's whole record for
the work item. That is a heavier remedy than the mistake, and it is the existing one —
adding a remover to fix a bug about a missing writer is scope this change has not earned.
