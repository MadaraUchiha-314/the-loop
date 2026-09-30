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

Four new findings, all fixed in the same commit:

| # | Finding | Fix | Test |
|---|---------|-----|------|
| C5 | `_probe_now` caught only `MemberUnavailable`; a registered URL answering an HTTP 4xx on `/api/v1/instance` (an older the-loop, any other app) made `probes()` raise, failing `GET /instances`, every fan-out and `status` | a 4xx on the probe is `mismatched` ("does not answer as a the-loop instance"), never a raised probe | `test_a_member_answering_an_http_error_is_mismatched_not_a_raised_probe` |
| C6 | `_Upstream._run` probed outside its `try`, so the same exception ended the thread, and `reconcile_upstreams` never replaced a dead thread | the probe is caught (retry on the probe cycle); a dead thread is replaced on reconcile | `test_a_dead_upstream_thread_is_replaced_on_reconcile` |
| C7 | `FleetBroker.stop()` kept `_offsets` and the queue, so the next `start()` resumed members from stale ids and old threads still fed the shared queue | `stop()` clears the offsets, the sizes and the queue: the next start is a fresh connection | `test_a_restarted_broker_connects_fresh` |
| C8 | `Fleet.from_config` (what `status` uses) had a fresh cache each run, so a down member recorded an error-level `instance.unreachable` on every `status` | a one-shot fleet announces nothing; the service's fleet still announces once per transition | `test_a_one_shot_fleet_announces_nothing` |

## Round 3 — code-review, medium effort

Six findings, all fixed in the same commit. No round 4 is run: the policy caps self
rounds at three; the final pass is the read-through recorded in
[verification.md](verification.md).

| # | Finding | Fix | Test |
|---|---------|-----|------|
| C9 | `_stamp` overwrote an event row's own `instance` — a fleet event's *subject* (`instance.unreachable` about `ci-box`) read as if about the origin | one `fleet.stamp_origin` for rows and frames: `instance` = the origin, a differing prior value kept as `about` (R6.3 amended) | `test_stamp_origin_keeps_an_events_subject_as_about` |
| C10 | the stream stamped the same way in four places (`_Upstream._deliver`, `tick`, `_replay_member`, own replay), each clobbering the subject | all four call `stamp_origin` | `test_frames_are_stamped_and_carry_the_per_member_cursor` (`about`) |
| C11 | `fan_out`'s deadline was one timeout in all, but a fleet wider than `MAX_WORKERS` is served in waves, so a second wave was "timed out" before it ran | one timeout per wave (`ceil(len(live) / MAX_WORKERS)`) | `test_a_fleet_wider_than_the_pool_gets_one_timeout_per_wave` |
| C12 | `by_ref` resolved from the probe's `managed` set only; a work item a member reached by polling alone (open mode) is in its work-items list and nowhere else, so a keyed call without `instance` answered 404 | after the managed sets and the fresh re-probe, the work-item lists (own via `local_records`, members via one fan-out) are the last word | `test_by_ref_falls_back_to_the_work_item_lists_for_a_polled_item` |
| C13 | `_probe_now`'s health follow-up caught only `MemberUnavailable`; a member whose `/health` answered an HTTP error or a non-object made the probe raise after `/instance` had already answered as itself | the follow-up catches the same set as the probe; the row is live with a blank version | `test_a_broken_health_endpoint_leaves_the_member_live_without_a_version` |
| C14 | `register`/`unregister` copied a hand-edited registry back through the splice; an entry the reader had narrowed with a warning failed the schema on write, with an error naming nothing — and a URL already registered under another name was accepted | the writers validate every entry with the reader's one rule (`member_problem`) and refuse naming `instance.manager.instances[<i>]` before anything is written; a duplicate URL is refused | `test_a_writer_names_a_hand_edited_entry_it_will_not_copy_back`, `test_register_refuses_a_url_already_registered_under_another_name` |
