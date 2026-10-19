# Learning 012: a process that must clean up after uvicorn has to own SIGTERM itself

- **Date:** 2026-10-19
- **Source:** system-feedback
- **Work item:** issue-496

## What happened

The gateway's `main()` wrapped `uvicorn.run(...)` in `try/finally` to record
`gateway.stopped` and release its pidfile. Under `the-loop gateway stop` (SIGTERM) the
server shut down cleanly ("Finished server process") and the `finally` never ran: uvicorn
captures SIGTERM/SIGINT for its graceful shutdown, then **restores the handlers it found
and re-raises the signal**. With the default handler, the re-raised signal ends the
process before the caller's cleanup.

## Learning

Code after `uvicorn.run` is not reached on a signal unless the caller installed a handler
of its own first. The control-plane service never noticed because its `finally` only
released a lock the OS also drops with the process.

## Action

`gateway/serve.py` installs SIGTERM/SIGINT handlers that raise `SystemExit` before
`uvicorn.run`, so the re-raised signal unwinds through the `finally`; the real-process
scenario in `tests/test_gateway_process_integration.py` asserts `gateway.stopped` is
recorded. Apply the same pattern to any future uvicorn host that must write on exit.
