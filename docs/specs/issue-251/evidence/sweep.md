# Evidence: the sweep

The sweep this ticket was left open for. Every wait site in `cli/tests/` was catalogued by
hand first (~190 across 18 files); the catalogue produced suspects, and running the suite
under an injected lag produced the answer. Where the two disagree, the run wins — twice
here, and both times against my reading.

Redaction: this file contains pytest output only. The environment-specific strings in it
are pytest's `/tmp/pytest-of-root/...` paths; there are no tokens, hostnames or personal
data. Commands are shown as run.

## 1. Reading found suspects that the run disproved

The clearest one. `test_labeled_issue_spawns_a_registered_session_once` carries a comment
that reads exactly like the bug — *"registry now has it -> must not spawn again"* — after
a wait on the spawn:

```python
poller.poll_once()
assert wait_until(lambda: len(tmux.spawns) == 1)
poller.poll_once()  # registry now has it -> must not spawn again
```

Test the claim by removing registration altogether:

```python
# scratch pytest plugin
@pytest.fixture(autouse=True)
def _no_register(monkeypatch):
    monkeypatch.setattr(SessionRegistry, "register", lambda self, *a, **kw: None)
```

```console
$ PYTHONPATH=$SCRATCH pytest -q -p noreg \
    cli/tests/test_poller_integration.py::test_labeled_issue_spawns_a_registered_session_once
    assert len(tmux.spawns) == 1          # PASSED even with no registration at all
    session = registry.find_by_work_item(REF)
>   assert session is not None and session.harness_session_id
E   assert (None is not None)
1 failed
```

The spawn-count assertion holds with the registry never written: the second cycle is gated
by the **poller's own state**, not by the registry. The comment is wrong; the test is not
racy. (The assertion that does fail here fails only because registration was deleted — it
sits after `dispatcher.stop()`, which is a real barrier.)

## 2. The lag, over the whole suite

Every write the dispatcher makes *after* the spawn or delivery it was asked for, delayed
0.5s: `SessionRegistry.register/touch/save_endpoint/link_pull_request/close`,
`Deduper.discard`, `SessionAnnouncer.announce`, `GraphLink.on_spawn/on_event`,
`ControlStore.record`. (Run with the option's prototype as a scratch plugin; the shipped
`--dispatch-lag` patches the same list.)

```console
$ PYTHONPATH=$SCRATCH LOOP_LAG=0.5 pytest -q -p lagplugin2 -p no:randomly cli
FAILED cli/tests/test_poller_integration.py::test_an_abandoned_comment_is_reported_on_the_work_item
FAILED cli/tests/test_webhook_routing_integration.py::test_delivery_error_is_isolated_and_redelivery_retries
2 failed, 2221 passed, 1 skipped in 568.60s (0:09:28)
```

An earlier, narrower run (registry + deduper only, 0.3s lag) found the same two and
nothing else — the wider seam list and the higher lag added no findings.

**2224 tests, exactly two instances.** Neither is the variant the ticket describes: both
wait on a failed delivery and then *act* on its outcome.

## 3. The two failures, in detail

### `test_delivery_error_is_isolated_and_redelivery_retries`

```console
    assert wait_until(lambda: len(tmux.delivers) == 1)
    # Failure is isolated: the delivery is not marked processed...
    time.sleep(0.2)
    found = registry.find_by_work_item(REF)
    assert found is not None and "e-1" not in found.recent_deliveries
    # ...so a redelivery of the same id is retried, not deduped away.
    assert (
        post_webhook(port, "issue_comment", issue_comment_payload("boom"), "e-1") == 202
    )
>   assert wait_until(lambda: len(tmux.delivers) == 2)
E   assert False
```

The re-POST is deduped away, because `Deduper.discard("e-1")` — which the dispatcher runs
*after* the failed paste — has not landed inside the test's 0.2s sleep.

### `test_an_abandoned_comment_is_reported_on_the_work_item`

```console
    poller.poll_once()  # attempt 1 (budget = 1)
    assert wait_until(lambda: len(tmux.delivers) >= 1)
    assert poster.bodies == []
    summary = poller.poll_once()  # budget exhausted -> give up + notice
    dispatcher.stop()
>   assert summary.failures == 1
E   assert 0 == 1
E    +  where 0 = PollSummary(items_seen=1, spawns=0, comments_forwarded=0, closures=0,
E                             failures=0, errors=[], interrupted=False).failures
```

Same write, reached through production code instead of an assertion:
`Dispatcher.delivery_status()` answers `"inflight"` while the id is still in the deduper,
and the poller is right not to spend a retry on an in-flight delivery. So the second cycle
gives up on nothing and reports zero failures.

## 4. Red under the shipped flag, before either fix

```console
$ uv run --project cli python -m pytest -q --dispatch-lag=0.5 \
    cli/tests/test_webhook_routing_integration.py::test_delivery_error_is_isolated_and_redelivery_retries \
    cli/tests/test_poller_integration.py::test_an_abandoned_comment_is_reported_on_the_work_item
FAILED cli/tests/test_webhook_routing_integration.py::test_delivery_error_is_isolated_and_redelivery_retries
FAILED cli/tests/test_poller_integration.py::test_an_abandoned_comment_is_reported_on_the_work_item
2 failed in 8.57s
```

Both fail on every run under the lag, and both passed without it — which is the whole
point: this is the flake made deterministic.

## 5. Green, same flag, after the fix

```console
$ uv run --project cli python -m pytest -q --dispatch-lag=0.5 \
    cli/tests/test_webhook_routing_integration.py cli/tests/test_poller_integration.py
42 passed in 70.14s (0:01:10)
```

The whole-suite run is in [`verification.md`](verification.md).
