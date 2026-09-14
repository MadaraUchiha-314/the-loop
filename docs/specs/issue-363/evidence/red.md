# Evidence: the red state (issue-363)

> Captured **before any production change**, from a `git worktree --detach` of `HEAD`
> (`88c2ff9`, 16.0.1) with only this work item's test files copied into it and run
> against the same interpreter. Each scenario below is a piece of the reporter's
> machine-loss sequence. A thirteenth scenario — a corrupt `graph-state.json`, which
> `GraphState.load` reads as a fresh state — was added afterwards by self-review pass four;
> it is not in this capture, and its red state is the same `assert 'phase-selection' == ''`
> as the first failure below.

## Setup

```console
$ git worktree add --detach /tmp/loop-head HEAD
$ cp cli/tests/test_recovery.py cli/tests/test_recovery_integration.py \
     cli/tests/conftest.py /tmp/loop-head/cli/tests/
$ cd /tmp/loop-head
```

## The shared vocabulary does not exist

```console
$ PYTHONPATH=cli python -m pytest -q cli/tests/test_recovery.py
cli/tests/test_recovery.py:16: in <module>
    from the_loop import recovery
E   ImportError: cannot import name 'recovery' from 'the_loop'
1 error in 0.10s
```

## The reporter's sequence, reproduced

```console
$ PYTHONPATH=cli python -m pytest -q cli/tests/test_recovery_integration.py
FAILED …::test_a_forgotten_item_is_not_rewound_and_still_gets_a_session
FAILED …::test_an_event_on_a_forgotten_item_does_not_advance_it_either
FAILED …::test_abuse_a_forged_complete_label_never_places_a_pointer
FAILED …::test_a_published_position_is_restored_byte_for_byte
FAILED …::test_the_position_is_published_on_every_graph_write
FAILED …::test_abuse_a_portable_position_never_overwrites_local_state
FAILED …::test_a_forgotten_items_old_commands_are_baselined_and_announced_once
FAILED …::test_a_comment_arriving_during_the_boot_does_not_spawn_a_second_session
8 failed, 4 passed in 0.73s
```

### R1 — the rewind

The pointer is placed on the start node of a work item labelled `loop:implementation`:

```text
E       AssertionError: the pointer must not be placed
E       assert 'phase-selection' == ''
E         + phase-selection
```

…and an event on the same work item does not merely enter the start node, it **walks
past it** on a days-old comment — which is what re-froze thirteen selections:

```text
E       AssertionError: assert NodeReport(node='phase-selection', status='pass',
E         outcome='selected', messages=['advanced to brainstorming'], …) is None
```

A ticket somebody has simply *labelled* `loop:complete` gets the same treatment, which
is the abuse case R1's refusal has to answer without ever placing a pointer.

### R2 — there is nowhere to publish a position to

```text
E       AttributeError: 'ControlStore' object has no attribute 'record_graph_position'
E       AttributeError: 'ControlStore' object has no attribute 'graph_position'
```

### R3 — the replay

A first sight of a work item whose thread the-loop has already posted on forwards the
old `the-loop execute` into a session, as a new instruction:

```text
E       AssertionError: no old comment is forwarded
E       assert [('github:octo/repo#15', '# GitHub webhook event …
E         "body": "the-loop execute" …')] == []
```

### R4 — the double spawn

A delivery into a session registered moments earlier, whose pane is not answering yet:

```text
E       AssertionError: assert 'session.respawned' not in
E         ['session.registered', 'dispatch.queued', 'session.respawned']
```

`session.respawned` here is the first half of the reporter's double spawn — the respawn
then tries `--resume` on an id minted seconds before, finds no transcript, and the fresh
spawn that follows is the second session.

### What already passed, and why it is in the file anyway

Four scenarios pass at `HEAD`: an unlabelled work item entering its graph, a started work
item being judged by its state file, issue-119's pending start command still being
forwarded, and an unauthorized `the-loop stop` still never executing. They are the
regression half — each names a behaviour this change must **not** alter, and each is a
behaviour the refusals above could plausibly have taken away.
