# Security review (issue-374)

Tier 4. The harness's `security-review` skill ran over the PR's diff on 2026-09-30
(head of PR #436 before the fix commit below), as a read-only sub-task with the
skill's own brief and false-positive filter, scoped to `cli/the_loop` and `ui/src`
against the base commit `136b292`. The sub-task's report, the-loop's checklist over
the requirements' abuse cases, and the disposition of every finding follow.

## The skill's verdict

**No High or Medium finding.** Two Low findings, both on the member → manager
response path and both at the edge of the documented model (a registered member is
operator-trusted; its responses are data). Both were fixed the same day rather than
carried:

| # | Finding | Severity | Disposition |
|---|---------|----------|-------------|
| S1 | `urllib.request.urlopen` follows a member's 3xx to any host, so a compromised member could point the manager at a loopback service of the manager's own and have its body served as that member's rows (`fleet.py` transport, `stream.py` opener) | Low (confidence 6/10 under the model) | **Fixed**: one `OpenerDirector` without the redirect handler for every member request and every upstream stream; a 3xx is the member's own status, refused as a non-2xx. `test_the_transport_never_follows_a_redirect` (a real loopback server answering 302) |
| S2 | A member's self-reported `managed` set steers keyed operations: a live member could claim a ref and have an unqualified `sessions/reply` proxied to it, or turn a shared ref into a `409` | Low (5/10; the documented design) | **Accepted as designed** (R2.3, decision-138 D5–D7): a member can only be *sent to* once the operator registered it by a config write; the claim reaches only that member's own routes; the `instance` parameter is the operator's override; and a claim on a ref the manager or another member also manages is refused (`409`), never resolved to the claimant. Recorded in the design's trade-offs |
| S3 (posture note) | `parse_sse` accumulated a frame without a bound although the design cites `MAX_PARTIAL_BYTES` | resource use (excluded by the skill's rules) | **Fixed**: a frame past `MAX_PARTIAL_BYTES` is dropped whole; the upstream reader reads no line longer than that. `test_an_oversized_frame_is_dropped_not_held` |
| S4 (posture note) | `api.request` recorded `instance` from the query string only, so a proxied `POST` (a config write, a restart) was audited without its target, contrary to abuse case 7 | audit (excluded by the skill's rules) | **Fixed**: the manager facade notes the member it reached; the route class records it on the event. `test_a_proxied_config_write_lands_on_the_members_file` asserts it |

What the skill checked and found holding: nothing of the caller (headers, cookies,
raw body) reaches a member; paths are fixed literals and queries go through
`urlencode`; the `instance` parameter is compared with registered names and never
interpolated; a worker refuses a foreign name before any core call; the registry is
validated at read and at write (grammar, `http(s)`, no userinfo, not self) and written
only through `update_config`'s schema-checked atomic write; events name instances,
never URLs; a member's body is bounded, `json.loads`-ed and shape-checked, its
`instance` overwritten; no `yaml.load`, `eval`, `pickle` or shell anywhere in the
diff; the cursor grammar is closed and unregistered names dropped; a host answering
`role: manager` is `mismatched` so the fan-out cannot recurse; the dashboard renders
member text as text nodes and builds every `href` from `hrefFor`.

## The checklist — requirements' abuse cases → mechanism → negative test

| # | Abuse case | Mechanism | Test | Verdict |
|---|------------|-----------|------|---------|
| A1 | a non-the-loop URL registered | the probe sends only `GET /instance`; not live → nothing routed to or aggregated from; no caller header forwarded; no redirect followed (S1) | `test_a_members_error_is_the_managers_error`, `test_nothing_of_the_caller_is_forwarded`, `test_the_transport_never_follows_a_redirect`, `test_a_mismatched_member_is_neither_served_nor_sent_to` | holds |
| A2 | the host answers as another name / unnamed / a manager | `Probe` name + role check → `mismatched`; one `instance.mismatched` | `test_a_member_answering_as_another_name_or_a_manager_is_mismatched`, `test_a_mismatched_member_is_neither_served_nor_sent_to` | holds |
| A3 | oversized / malformed / wrong-shape body | `MAX_MEMBER_BODY`, `json.loads`, the shape check; `instance.malformed`; the rest answer | `test_a_malformed_member_answer_is_dropped_and_the_rest_served` (×3) | holds |
| A4 | a member hangs | per-future deadline; `unreachable`; upstream backoff | `test_a_hung_member_costs_at_most_the_timeout_and_is_bounded`, `test_a_dropped_upstream_reconnects_with_backoff_and_resumes` | holds |
| A5 | a ref two members manage, a mutating verb | `by_ref` → `Conflict` → `409`; sent to neither | `test_an_ambiguous_ref_is_refused_not_sent_twice`, `test_an_ambiguous_ref_is_refused_and_sent_to_neither` | holds |
| A6 | `instance` names an unregistered member / a foreign name on a worker | `by_instance` → `LookupError`; `assert_self` | `test_an_unknown_instance_sends_nothing`, `test_a_worker_accepts_only_its_own_name_as_instance`, `test_assert_self_accepts_empty_and_own_name_and_refuses_a_foreign_one` | holds |
| A7 | a proxied config write / restart | `api.request` names the target on the manager (S4); the member's own `config.updated` | `test_a_proxied_config_write_lands_on_the_members_file`; `manual.md` § 10 | holds |
| A8 | `role: manager` widening what an instance takes on | the worker half is `CoreFacade` untouched; the dispatcher and ingresses never read the role; an unknown role refuses to boot | `test_a_manager_refuses_to_boot_on_an_unknown_role`, `test_a_manager_refuses_to_boot_unnamed`, `test_an_operation_without_instance_is_the_managers_own`; the issue-322 suites unchanged (T10) | holds |
| A9 | a member's row carries its own `instance` | the stamp overwrites | `test_the_registered_name_overwrites_a_members_claim`, `test_frames_are_stamped_and_carry_the_per_member_cursor` | holds |

Fail-closed expectations (requirements § Security): an unknown role or an unnamed
manager refuses to boot (`serve.py`, `strict=True`); an unvalidated registry entry is
skipped by index; a member that has not answered to its name is not served or sent
to; an ambiguous key is `409`; an unreachable member on a keyed operation is `502`;
a cursor outside the grammar is one `desync`. All tested (T1, T8).

## Sign-off

Tier 4 requires a **named human security sign-off**, distinct from the PR approval
(`reference/security.md`). Requested from the owner on PR #436.

- [ ] Security sign-off: *(name, date)*
