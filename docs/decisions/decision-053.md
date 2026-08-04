# Decision 053: a config key is nested under what owns it — `routing` governs both ingresses, so it is top-level

- **Status:** proposed
- **Date:** 2026-08-04
- **Deciders:** @MadaraUchiha-314 (issue #142, from the [PR #139 review](https://github.com/MadaraUchiha-314/the-loop/pull/139#discussion_r3708820245))
- **Work item:** issue-142
- **Spec:** `docs/specs/issue-142/`
- **Builds on:** [decision-032](decision-032.md) — the CLI config is a property of the
  operator's machine — and the migration mechanism established by
  [decision-042](decision-042.md) (`ghBinary`) and [decision-046](decision-046.md)
  (`polling.stateFile`).

## Context

`routing` was declared under `webhooks.ghWebhook`, and it was never the receiver's. The
poller has no routing config of its own: it reads that exact block for dispatch, through
an import (`from .gh_webhook import _load_config_defaults`) that said the quiet part out
loud. `the-loop sessions` read it a third time. So `authorizedUsers`, `control`,
`interaction`, `graph`, `workspace`, `tmux`, `harnessTrust` and the rest were declared
once and governed **both** ingresses, under a key named `webhooks`.

The cost had already been paid, which is what makes this worth a decision rather than a
tidy-up. Reviewing PR #139, the repository's own owner read `interaction` sitting under
`webhooks` and reasonably concluded it applied to one ingress. The remedy at the time was
a **comment** in the template config — *"NOTE: like everything under `routing`, this is
NOT webhook-only"* — attached to one option, in a block where the misreading is the
default. If the person who wrote the daemon reads the nesting that way, an operator will
too, and the failure is silent: they configure it, it works, and they never learn the
poller was covered all along.

## Decision

**1. `routing` is a top-level key.** It sits between `webhooks` and `eventLog`, one
top-level key per concern: `state · webhooks · polling · routing · eventLog ·
integrations · collaborators · notifications`. `webhooks` and `polling` are the two
ingresses; `routing` is the policy they both feed.

**2. `webhooks.ghWebhook` keeps only what is genuinely the receiver's** — `host`, `port`,
`path`, `secretEnv`, `pidfile`, `events`. The event filter stays with it because the
poller never sees a delivery: it *discovers* work items instead.

**3. Nothing inside the block changes.** Same option names, types, defaults, descriptions
and behaviour. The relocation is checkable precisely because it is only a relocation.

**4. The code seam moves with the key.** A shared accessor,
`cli_config.load_routing_config()`, replaces the cross-command import. Leaving `poll.py`
importing from `gh_webhook.py` would have kept the coupling the key move exists to remove
— the config would say `routing` is shared while the code still said it belonged to the
receiver.

**5. It is a breaking change with a migration, not a compatibility fallback.**
`CURRENT_CONFIG_VERSION` goes to `0.4.0`; a config still declaring the old key makes the
CLI **refuse to start**, naming the old key, the new one and
`/the-loop:upgrade-the-loop`; `the-loop migrate-config` performs the move
deterministically and reports it.

**6. A config declaring both blocks resolves to the top-level one, key by key, and says
what it dropped.** Never a deep merge and never a list union: unioning two
`authorizedUsers` lists would silently re-admit a login the operator had removed from the
block they were actually maintaining.

## Consequences

**Positive.**

- The config's **shape** now carries the scope. A reader learns that routing governs both
  ingresses by looking at where it sits, not by finding and trusting a comment.
- The prompt-injection guard is easier to audit: `routing.authorizedUsers` is resolved by
  one accessor that every ingress calls, rather than through the webhook command's module.
- The removed comment stops being a maintenance obligation — it would have had to be
  repeated on every future option in the block.
- `webhooks.ghWebhook` becomes small and honest: a listener, a pid and a filter.

**Negative / accepted costs.**

- **Every operator migrates.** One command, backed up, previewable and idempotent — but a
  flag day nonetheless, and a home-directory config is outside `/upgrade`'s reach unless
  the operator points it there.
- **Old links and old advice go stale.** Every reference to `webhooks.ghWebhook.routing.*`
  written before this — in blog posts, in a colleague's notes, in this repository's own
  decision log — now names a key the runtime refuses.
- **Historical records keep the old spelling.** Decision records and merged specs are
  deliberately left as written (the precedent set when `ghBinary` was retired and
  [decision-022](decision-022.md) kept it). A reader landing there sees a path that no
  longer exists; the live config reference is where the current spelling lives.
- **Three key moves now live in `migrations.py`.** The module is doing its job, but each
  addition is another branch in a function whose correctness matters more than most.

## Alternatives considered

| Option | Why not |
|---|---|
| Keep the nesting; improve the comment | Already tried, and the comment is what failed. A note attached to one option cannot fix a shape that misleads on every option — and the person it failed for wrote the daemon. |
| Read the old location as a fallback when `routing` is absent | Makes the misfiled key a supported spelling forever, which is the thing being removed, and the operator never learns their config is stale. It also breaks the migration module's second stated property. |
| Duplicate the block under `polling` as well | Two declarations of one policy, guaranteed to drift, in a block whose contents include an authorization list. The exact duplication `integrations` was created to remove. |
| Move only the keys that are "obviously" shared (`authorizedUsers`, `interaction`) | Every key in the block is shared — the poller builds its dispatcher from the whole `RoutingConfig`. A partial move would leave the same misreading with a subtler boundary. |
| Rename `webhooks` to something ingress-neutral instead | `webhooks.ghWebhook` genuinely is webhook-specific (a bind address, an HMAC secret, a pidfile). Renaming it would mislabel the half that was correctly named to avoid moving the half that was not. |
| Merge both blocks when a config declares each | A silent union of `authorizedUsers` would re-admit a removed login during an upgrade — a change to who may drive the daemon, made by a migration, without being asked. |
