# `channels.slack.read.mode` is hot-reloaded in config but not in the running process

**Kind:** bug · **Source:** e2e Slack test 2026-09-19 (B5) · **Not fixed in issue-393** · filed as [#395](https://github.com/MadaraUchiha-314/the-loop/issues/395), fixed by its spec's PR (the first suggested fix, plus the `status` wording of the second)

## What happens

Changing `channels.slack.read.mode` from `socket` to `off` fires `config.reloaded`,
and `the-loop status` then prints the contradictory
`slack-listener running (hosted in the service, pid …) [disabled]`. The listener
keeps its Socket Mode connection and keeps consuming events until the process is
restarted — so the config says "off" while the process is still on.

This matters when two instances share one Slack app: turning a second listener
`off` to stop it stealing half the events (the B3 workaround) does not actually
stop it until a restart.

## Suggested fix (from the report)

Either:
- stop/start the hosted listener on reload, the way the poller is re-armed; or
- list `read.mode` among the boot-only keys the control plane reports as
  `restartRequired`, and have `status` say "restart to apply" instead of the
  contradictory `running [disabled]`.

## Acceptance

- WHEN `read.mode` changes to `off` on reload THEN the listener stops consuming
  events without a manual restart, OR `status` states plainly that a restart is
  required and does not print `running [disabled]`.
