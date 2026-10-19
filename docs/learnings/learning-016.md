# Learning 016: a graceful stop must release its own long-polls

- **Date:** 2026-10-19
- **Source:** system-feedback
- **Work item:** issue-496

## What happened

`the-loop gateway restart` reported "did not stop within 15s" during the manual
checklist. uvicorn's graceful shutdown waits for every open request, two instances were
each holding a 20 s long-poll on `POST /fetch`, and the stop verb's 15 s budget was
shorter than the longest poll the server allows (30 s). The verb gave up, the old
process exited on its own two seconds later, and nothing listened until the next
restart. The hermetic tests never saw it: they stop the app with no fetch open.

## Learning

A server that holds requests open on purpose owns their release: on the decision to
exit, wake every waiter so an in-flight long-poll returns empty at once. A stop timeout
sized below the longest request the server itself permits is a latent failure, and a
restart verb inherits it. Test the stop with a request open, in a real process.

## Action

The gateway wakes its long-polls when uvicorn decides to exit (`server.should_exit`)
and at the lifespan's end, the fetch loop returns when the state is stopping, and the
stop verb's timeout covers one full `consume.maxWaitSeconds`; a consume test and a
real-process test (`test_stop_does_not_wait_for_an_open_long_poll`) pin it.
