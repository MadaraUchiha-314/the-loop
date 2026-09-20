---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#396"
---

# Security review: `graph status` reads the state file the runtime wrote (issue-396)

## Security review (gate)

- **Mechanism:** the-loop checklist (`reference/security.md`), against the diff.
- **Outcome:** pass.
- **Findings:** none.
  - *Trust boundary:* unchanged. The inputs are the operator's positional argument,
    the CLI config the process already loads, and the session registry the same
    process already reads for `sessions list` — all on the operator's own machine.
    `check`/`status` remain pure: no network, no subprocess, no mutation.
  - *Path shapes:* the ref → id translation goes through `WorkItemRef.parse` (the
    number is an `int`) and `graphlink.spec_id_for`, so the derived id is `issue-<int>`
    or the argument itself; an unparsable argument (`../../etc#1`) is passed through
    exactly as before, pinned by `test_work_item_id_translates_a_ref_the_way_the_daemon_does`.
    No new path shape reaches `Runtime.spec_dir`.
  - *The registry's `cwd`:* a path this machine's daemon recorded when it spawned the
    session, already trusted by `sessions resume`/`attach`; used only when it is an
    existing directory, and vetted again at core's boundary by `resolve_repo` as `--repo`
    is. A cleaned-up checkout falls through
    (`test_a_cleaned_up_checkout_falls_through_to_the_working_directory`).
  - *Information disclosure:* `statePath` is under a repository the caller named or the
    registry resolved for them, on the loopback the service already answers with checkout
    contents. The issue-238 rule — a `repo` that does not resolve is answered with no path
    at all — is unchanged and still pinned by
    `test_the_unknown_position_answer_is_not_a_filesystem_oracle`.
  - *Authorization:* none involved; nothing here writes, posts or labels. The mutating
    verbs deliberately do **not** resolve a checkout through the registry
    (`test_a_mutating_verb_keeps_the_working_directory`).
  - *Fail-closed:* every miss — no config, no registry, no record, unreadable record,
    `cwd` gone — degrades to today's behaviour (the working directory), now with the
    `state:` line making the miss visible instead of silent.
- **Human sign-off:** n/a (risk tier 3).
