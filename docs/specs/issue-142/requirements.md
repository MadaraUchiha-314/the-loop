---
type: requirements
phase: requirements-definition
workItem: issue-142
status: approved             # draft | in-review | approved
approvedBy: []               # tier-4: the human gate is the PR review — see execution-log
collaborators: [engineer, technical-writer]
riskTier: 4                  # touches `.the-loop/cli-config.schema.json` (autonomy.sensitivePaths)
overrides: {}
---

# Requirements: `routing` is a top-level concern, not a property of the webhook receiver

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (<https://kiro.dev/docs/specs/>). This phase MUST be reviewed and approved by the
> required collaborators before moving to design.

## Introduction

[Issue #142](https://github.com/MadaraUchiha-314/the-loop/issues/142), split out of
[#139 review feedback](https://github.com/MadaraUchiha-314/the-loop/pull/139#discussion_r3708820245),
asks for one key to move: `webhooks.ghWebhook.routing` → `routing`.

The block is misfiled. `routing` is not the receiver's — it is the **shared dispatch
policy both ingresses run on**. The poller has no routing config of its own; it reads
this exact block, through an import that says so out loud:

```python
# cli/the_loop/commands/poll.py
from .gh_webhook import _load_config_defaults
...
dispatcher, routing = _build_dispatcher(_load_config_defaults().get("routing"))
```

So `control`, `interaction`, `graph`, `workspace`, `tmux`, `webTerminal`, `reactions`,
`announce`, `authorizedUsers`, `harnessArgs`, `harnessTrust` and the rest are declared
once and govern **both** ingresses, while living under a key named `webhooks`.

The cost is not cosmetic, and it is already paid. Reviewing #139, the repository's own
owner read `interaction` sitting under `webhooks` and reasonably concluded it applied to
one ingress. The fix at the time was a **comment** in the template config
(`# NOTE: like everything under routing, this is NOT webhook-only …`) — a note that has
to be re-read on every option, in a block where the misreading is the default. If the
person who wrote the daemon reads the nesting that way, an operator will too, and the
failure mode is silent: they configure it, it works, and they never learn the poller was
covered all along — or they duplicate the block expecting it wasn't, and there is nowhere
for the duplicate to go.

## Analysis

### What is genuinely receiver-specific, and what is not

Every key under `webhooks.ghWebhook`, classified by which ingresses it governs:

| Key | Governs | Belongs under |
|---|---|---|
| `host`, `port`, `path`, `secretEnv` | the HTTP listener: bind address and HMAC verification | `webhooks.ghWebhook` |
| `pidfile` | the receiver process | `webhooks.ghWebhook` |
| `events` | the receiver's event filter — the poller *discovers* work items instead, and never sees a delivery | `webhooks.ghWebhook` |
| `routing.*` (everything) | what happens to an event **once accepted**, by either ingress | **top level** |

The split is clean because the two halves answer different questions. `webhooks.ghWebhook`
answers *how does an event get in through HTTP*. `routing` answers *what does the-loop do
with a work item's event* — a question the poller asks with exactly the same answer, and
`the-loop sessions` asks a third time (`commands/sessions_cmd.py` reads `registryDir`,
`control`, `tmux`, `workspace` and `spawnOnUnmatched` off the same block).

Against its siblings the promoted key reads correctly, one top-level key per concern:

```text
state · webhooks · polling · routing · eventLog · integrations · collaborators · notifications
                   └── two ingresses ──┘   └── the shared policy they both feed
```

### Why the import seam moves with it

`poll.py` and `sessions_cmd.py` both reach the config through
`from .gh_webhook import _load_config_defaults`. That import is the same misfiling
expressed in Python: the poller depends on the receiver's module to read a block that is
not the receiver's. Once `routing` is top-level, `_load_config_defaults` (whose docstring
reads *"Best-effort read of webhooks.ghWebhook"*) is the wrong function to call for it,
and leaving the import in place would preserve exactly the coupling the key move exists to
remove. The reader is the point: someone auditing who may drive their daemon should find
`authorizedUsers` resolved by one shared accessor, not by importing the webhook command.

### Why it needs a migration, not just a rename

A config is an operator's file, on their machine, and this repository has both the
machinery and the precedent for changing one: `cli/the_loop/migrations.py` (issue-109's
`ghBinary` → `integrations.github.cli.binary`, issue-128's `polling.stateFile` →
`state.root`). Its module docstring states four properties, and this change is bound by
all four — most of all the second. Silently ignoring a `routing` block an operator set
would change **which GitHub logins may drive their daemon** (`authorizedUsers` is the
prompt-injection guard, fail-closed by design) without telling them. That is the one thing
this config must never do quietly.

## Requirements

### Requirement 1 — `routing` is a top-level key

**User story:** As an operator, I want the shared dispatch policy to sit at the top level
next to `webhooks` and `polling`, so that its scope is legible from the config's shape
rather than from a comment I have to trust.

#### Acceptance criteria (EARS)

1. WHEN the CLI config schema is read THEN `routing` SHALL be a top-level property, with
   the block's every option under it unchanged in name, type, default and description.
2. WHEN the schema is read THEN `webhooks.ghWebhook` SHALL declare only receiver-specific
   keys (`host`, `port`, `path`, `secretEnv`, `pidfile`, `events`) and SHALL NOT accept a
   `routing` property.
3. WHEN either ingress starts THEN it SHALL read routing policy from the top-level
   `routing` key, AND neither SHALL read `webhooks.ghWebhook.routing`.
4. WHEN the webhook receiver hot-reloads its config THEN it SHALL pick up a change to the
   top-level `routing` block exactly as it previously picked up a change under
   `webhooks.ghWebhook.routing`, AND SHALL keep reading its event filter from
   `webhooks.ghWebhook.events`.
5. WHEN the shipped template config and this repository's own `.the-loop/cli-config.yaml`
   are read THEN both SHALL declare `routing` at the top level, AND the template's
   "this is NOT webhook-only" note SHALL be replaced by the block's own scope statement —
   the nesting now says it.

### Requirement 2 — an un-migrated config is refused, loudly

**User story:** As an operator upgrading the-loop, I want a config that still declares the
old key to stop the daemon with an explanation, so that a policy I set is never silently
ignored.

#### Acceptance criteria (EARS)

1. WHEN a CLI config is loaded that still declares `webhooks.ghWebhook.routing` THEN the
   CLI SHALL refuse to run, raising `ConfigTooOld`.
2. WHEN that refusal is raised THEN its message SHALL name the old key
   (`webhooks.ghWebhook.routing`), its replacement (`routing`), the reason the value is
   not simply ignored, AND the exact command that fixes it
   (`/the-loop:upgrade-the-loop`).
3. WHEN a CLI config declares a `version` older than the current schema version THEN the
   CLI SHALL refuse to run, naming the version it needs.
4. IF a config declares **no** version and carries no removed key THEN it SHALL NOT be
   refused — unchanged from today's "migrate broadly, refuse narrowly" gate.
5. WHEN the schema version constant is read THEN it SHALL be `0.4.0`.

### Requirement 3 — `the-loop migrate-config` performs the move

**User story:** As an operator, I want the upgrade command to move the key for me and tell
me what it moved, so that a breaking change costs me one command and no hand-editing.

#### Acceptance criteria (EARS)

1. WHEN `the-loop migrate-config` runs on a config declaring `webhooks.ghWebhook.routing`
   THEN it SHALL move that block verbatim to the top-level `routing` key, SHALL remove the
   old key, SHALL bump `version` to `0.4.0`, AND SHALL report the move.
2. WHEN the migration removes the last key from `webhooks.ghWebhook` or from `webhooks`
   THEN the emptied container SHALL be removed, so the migration does not leave a
   `webhooks: {ghWebhook: {}}` husk behind.
3. WHEN the migration runs a second time on its own output THEN it SHALL report no change
   and produce a byte-identical config (idempotent).
4. IF a config declares **both** `webhooks.ghWebhook.routing` and a top-level `routing`
   THEN the top-level block SHALL win key by key, the old block SHALL still be removed,
   AND the report SHALL note every key that the old block declared and the new one
   overrode — a hand-edited half-migration is reported, never silently resolved.
5. WHEN `--dry-run` is passed THEN the report and the migrated YAML SHALL be printed and
   the file SHALL NOT be written.

### Requirement 4 — both ingresses behave identically, before and after

**User story:** As an operator, I want this to be a relocation, so that upgrading changes
nothing about how my daemon dispatches.

#### Acceptance criteria (EARS)

1. WHEN a migrated config is loaded THEN every routing option SHALL resolve to the value it
   resolved to before the move — no option changes name, type, default or effect.
2. WHEN the poller and the receiver resolve routing policy THEN they SHALL do so through
   **one shared accessor**, AND `poll.py` and `sessions_cmd.py` SHALL no longer import the
   config-reading helper from `commands/gh_webhook.py`.
3. WHEN `integrations.github.cli.binary` is fanned out to `control`, `reactions` and
   `announce` THEN it SHALL reach them at the block's new location.
4. WHEN the existing routing, poller, control, reactions, announce, interaction and session
   suites run THEN they SHALL pass against the new key.

### Requirement 5 — nothing still names the old path

**User story:** As a reader, I want every document, docstring and error message to name
`routing`, so that the old path survives only where it is deliberately a historical record.

#### Acceptance criteria (EARS)

1. WHEN the CLI documentation is read THEN `docs/config/cli/routing-options.md` SHALL
   declare `configBase: routing`, AND every page, `cli/README.md`, and the skill's
   `reference/automation.md` / `reference/collaboration.md` SHALL name the new path.
2. WHEN `test_docs_parity` runs THEN it SHALL pass — every documented option present in the
   schema (P3) and every schema leaf documented (P4), which is what mechanically proves the
   rename reached both sides.
3. WHEN a module docstring or an operator-facing message names the block THEN it SHALL name
   `routing` — including the `authorizedUsers` fail-closed warnings in `poll.py` and
   `gh_webhook.py`, which are read by an operator who is being told their daemon will act
   on nothing.
4. WHEN `docs/decisions/` and `docs/specs/` are read THEN their existing references to
   `webhooks.ghWebhook.routing` SHALL be left as written — a decision record states what
   was decided when it was decided (the precedent set when `ghBinary` was retired and
   [decision-022](../../decisions/decision-022.md) kept it), and the migration docs point
   forward for anyone who lands there.
5. WHEN `docs/capabilities/webhook-triggers.md` and `docs/capabilities/cli.md` are read
   THEN they SHALL describe the current key and carry a history row for this work item.

## Non-functional requirements

- **One flag day, not two.** The move and the version bump ship together, so an operator
  migrates once. No shadow read of the old location: a compatibility fallback would keep
  the misfiled key alive as a supported spelling, which is the thing being removed.
- **Cheap to verify.** The change is mechanical, and two existing mechanisms already prove
  it: `test_docs_parity` (docs ↔ schema, both directions) and the routing/poller suites
  (behaviour). Neither needs to be weakened.

## Security considerations

> Threat-model-lite (`security.threatModel.required`). This work item moves the key that
> holds the prompt-injection guard, so it is a security question even though it changes no
> security logic.

- **Actors & trust.** Unchanged by this work item. The untrusted inputs are GitHub event
  payloads and comment bodies; the trusted input is the operator's own `cli-config.yaml`
  on their own machine. `routing.authorizedUsers` is the boundary between them.
- **Trust boundaries & data.** The block being moved *is* a trust boundary declaration:
  `authorizedUsers` (which logins the-loop acts on), `harnessTrust` (what a spawned harness
  may do), `control` (who may start a work item), `workspace` (where checkouts land). No
  secret moves — the webhook secret is read from an env var and stays under
  `webhooks.ghWebhook.secretEnv`, which is not part of this move.
- **The whole risk is a silently-ignored guard.** If the runtime simply stopped finding
  `webhooks.ghWebhook.routing`, `resolve_authorized_users([])` would return empty. Today
  that fails **closed** — an empty list means no human-authored event is acted on, and both
  ingresses warn — so the realistic outcome is a daemon that quietly does nothing rather
  than one that acts on strangers. Quietly doing nothing is still a failure the operator
  did not choose, and the `enabled: false` default means a lost block can equally read as
  "routing off". R2's refusal is what prevents both.
- **Abuse cases (EARS).**
  1. WHEN a config still declares `webhooks.ghWebhook.routing` THEN the CLI SHALL refuse
     to start rather than run with an empty `authorizedUsers` — a negative test, not a
     comment.
  2. WHEN a config declares both the old and the new block THEN the migration SHALL NOT
     merge the two `authorizedUsers` lists into a union — the top-level list wins whole,
     and what the old block declared is reported (R3.4), so a stale login cannot be
     silently re-admitted by an upgrade.
- **Fail closed.** Unchanged and reinforced. Missing config → empty `authorizedUsers` →
  nothing acted on, with a warning that now names the correct key to set.
- **Risk tier: 4.** `.the-loop/cli-config.schema.json` matches `autonomy.sensitivePaths`
  (`**/*schema*`), and `inferFromChange` is true, so the tier is raised from the default 3
  even though the change is a relocation. Tier 4 is `human-approves-pr`, and it is at
  `security.review.humanSignOffMinTier`, so a **named human security sign-off** is
  requested on the PR alongside the review.

## Out of scope

- **Any change to what a routing option does.** This is a relocation and a migration.
  Names, types, defaults and behaviour are untouched — that is what makes R4 checkable.
- **Moving anything else.** `events` stays with the receiver (the poller never sees a
  delivery), `polling.*` stays with the poller, and `state`, `eventLog` and `integrations`
  are already where they belong.
- **A compatibility read of the old location.** Deliberately refused, per R2 and the
  migration module's property 2.
- **Rewriting historical decision records and specs** (R5.4).

## Open questions

None. The issue specifies the target shape, the acceptance criteria and the prior art; the
one judgement call it leaves open — what happens when a config declares *both* blocks — is
resolved in R3.4 and design D4, in the direction the migration module's stated properties
already point (deterministic, reported, never a silent merge).

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109).
