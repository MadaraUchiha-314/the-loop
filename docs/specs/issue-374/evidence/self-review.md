# Self-review (issue-374)

Policy: this repository's `reviews` block — up to 3 self rounds and 3 critic rounds,
stop on no new findings, escalate on a repeat. Critic harnesses: `critics: []` in
`.the-loop/cli-config.yaml` — none declared, none run; the self rounds are the
harness's `code-review` recipe over the branch diff (`136b292...HEAD`).

## Round 1 — code-review, medium effort

Four findings, all actionable, all fixed in the same commit:

| # | Finding | Fix | Test |
|---|---------|-----|------|
| C1 | `FleetBroker.tick` stamped every own-log frame in a batch with the batch-end offset (`LogTail.read` advances before yielding), so a client that dropped mid-batch resumed past the rest of it | each own frame carries its record's own offset, the worker's `record.cursor` rule | `test_own_frames_in_one_batch_carry_their_own_offsets` |
| C2 | `serve_fleet` sent every replayed frame with the boundary cursor, so a drop mid-replay skipped the un-replayed records | each replayed frame carries the position after it, per source; sources not yet replayed keep the client's own offsets | `test_replayed_frames_carry_the_position_after_each_record` |
| C3 | `by_ref` resolved holders from the cached probe document, so a keyed call without `instance` answered 404 for up to `probeIntervalSeconds` after a member took a work item | one fresh probe round before answering "nobody manages it" | `test_by_ref_re_probes_once_before_answering_nobody` |
| C4 | the registry refused the manager's own URL but not its own name; a worker registered under it would be stamped as the manager and be unaddressable | the reader skips it by index with a warning; `register_instance` refuses it | `test_the_registry_skips_the_managers_own_name`, `test_register_refuses_an_invalid_entry_and_writes_nothing[hq-…]` |

## Round 2 — code-review, medium effort

See below (appended after the round).
