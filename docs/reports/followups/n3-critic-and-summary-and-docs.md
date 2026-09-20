# follow-ups: critic still unavailable on the deployment; sessions don't use `--summary`/`--default`; mention-less connectors

From [`docs/reports/e2e-slack-test-2026-09-20.md`](../e2e-slack-test-2026-09-20.md)
(B9 remainder, room finding 5, N3). Three smaller items, filed together or split.

## 1. bug/investigation: the configured critic never completes (B9 remainder)

The issue-393 fix removed the misdiagnosed 120 s wrapper cap — confirmed live: the
session ran the round in the background per the new guidance and `critic policy`
printed the 900 s timeout. But `the-loop critic run <critic>` still exited 2 with
"timed out" and **no envelope, twice**, in well under 900 s. The session recorded
the round as *unavailable* in `evidence/critic-review.md` (honest, and the human
gate accepted the gap) — but the deployment has had **zero** completed critic
rounds across both e2e runs. Needs its own investigation on the harness side
(`cursor-agent` invocation, env, or the wrapper's error propagation: the improved
whose-limit-was-hit message did not surface — the output was a bare "timed out").

## 2. enhancement: the spawned session should pass `--summary` and `--default`

The issue-393 machinery for summary-led gate messages (`the-loop ask --summary`)
and the one-tap "Defaults are fine" button (`--default`) shipped, but the live
session used neither, so gate digests still paste the document (cut mid-sentence,
"Answer with…") and the button never appeared. The spawn prompt / skill should
instruct the session to attach a 2–3 sentence summary to every approval hook and a
default to every ask.

## 3. docs: connectors that cannot render a mention

The Slack MCP connector types `@the-loop` as literal text, so `listen: mentions`
(the default) hears nothing from it; raw `<@BOT_USER_ID> …` markup works. One line
in the channels doc: "an integration that cannot render a mention entity should
send `<@BOT_USER_ID> …` verbatim, or declare the room `--listen all`". Related
polish: `session.autoclosed` logged `merged: false` for an issue whose delivering
PR merged three minutes earlier, and the hosted service's process log goes to
`/dev/null` on this deployment, making every `logger.debug` diagnostic
unreachable in operation.

## Fixed (branch `fix/n1-selection-grammar-refusal-reason`)

1. **Critic timeout surfacing** — the round's error now leads with the observed
   duration vs the-loop's limit, and when a round dies well short of the limit it
   says plainly that the cap that fired is the CALLER's tool timeout, not
   the-loop's (run it as a background process). The critic *executable* itself
   failing on the deployment (`cursor-agent` producing no envelope) is a
   deployment-side problem no code change here fixes; the session records an
   unavailable round honestly, which is the right behaviour.
2. **`--summary` / `--default` adoption** — `skills/the-loop/reference/collaboration.md`
   now tells the session to give every `the-loop ask` a `--summary` and, where there
   is a safe one, a `--default`, so the room leads with the agent's account and offers
   the one-tap button.
3. **Connector doc** — `docs/capabilities/channels.md` documents that a mention-less
   integration must send raw `<@BOT_ID>` markup or declare the room `--listen all`.
