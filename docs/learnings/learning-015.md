# Learning 015: a hook stored on a class is a bound method when read through the instance

- **Date:** 2026-10-19
- **Source:** system-feedback
- **Work item:** issue-496

## What happened

The gateway client published every Slack thread an instance bound by storing a plain
function on `ChannelState.publisher` (a `ClassVar`). `bind` read it with
`getattr(self, "publisher")` — through the instance — so Python handed back a bound
method and the call arrived with one argument too many. The `except Exception` around
the publish swallowed the `TypeError`, the service's stderr is `/dev/null`, and the unit
tests set the hook on an instance, where no binding happens. Only the live run's empty
`bindings` table showed it.

## Learning

A callable stored on a class and read through an instance is a method, not the function.
Read a `ClassVar` hook through the class (`ChannelState.publisher`), or wrap the function
in `staticmethod`, and let the test set the hook the way production does. A catch-all
that logs to a sink nobody reads is where such a bug lives for a long time; a live
end-to-end step reads the state the code should have produced, not only the log.

## Action

`channels/state.py` reads the ClassVar through the class; the loopback hosted test binds
a thread from a plain `ChannelState()` and reads the binding back from the gateway's
store.
