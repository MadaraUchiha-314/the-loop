---
configBase: ""
---

# Repositories

One list says which GitHub repositories this instance of the-loop works with, and
**every** ingress reads it.

```yaml
repositories:
  - octo/hello
  - ghe.corp.example/team/service
```

Until 13.12.0 the list lived in `polling.sources[].repos` — named after the one ingress
that happened to read it. Twenty modules read it; the `gh-webhook` receiver was not one of
them. So the poller was bounded by an operator-declared list and the receiver was bounded
by nothing of the kind: a delivery for a repository nobody had listed was judged on its
signature and its actor alone, and then dispatched. Issue-348 moved the list to the top
level and pointed all four readers at it.

## The declaration

### `repositories`

- **Type:** `string[]`
- **Default:** `[]` — **unset bounds nothing**; see below

Every GitHub repository this instance works with, as `[HOST/]OWNER/REPO` — `gh`'s own
`--repo` grammar. A bare `OWNER/REPO` is on the GitHub the-loop resolves (issue-331):
[`integrations.github.host`](/config/cli/integrations-options#github-host), else an
enterprise `github.api.baseUrl`, else `$GH_HOST`, else github.com. Write the host in front
for a repository on another GitHub (`ghe.corp.example/octo/repo`, issue-311) — the host is
part of the identity, so a github.com repository with the same `OWNER/REPO` is a
*different* repository and neither admits the other.

Each entry is kept **as you wrote it**. What reaches `gh --repo` is your own string, never
a normalisation; the comparison the ingresses do happens on a `host/owner/repo` key
derived from it.

An entry that is not `[HOST/]OWNER/REPO` is skipped with a debug line and nothing else —
never guessed at. The same is true of a section that is not a list. A fault can therefore
only **shrink** the declared set; it can never hand an ingress a repository you did not
declare.

#### Who reads it

| Reader | What the list does |
|---|---|
| the [`gh-webhook` receiver](/cli/receiver) | drops a delivery whose repository is not in it, and any work item it names in a repository that is not in it — `routing.dropped`, reason `undeclared-repository`, recorded before the actor is even read |
| the [poller](/config/cli/polling-options) | polls exactly these repositories; a source now says only *how* (provider, label, monitor, binary) |
| the `/the-loop` slash command | may only target a work item in one of them ([decision-116](/decisions/decision-116) D4) |
| a [Slack kickoff](/config/cli/channels-options#slack-kickoff-repo) | resolves its `<repo>:` prefix against them, and its fallback target must be one of them ([decision-120](/decisions/decision-120) D1) |

#### Empty bounds nothing

::: warning An empty or unset list is not a closed door
With nothing declared, the receiver accepts a delivery for **any** repository that reaches
it — exactly what it did before issue-348 — and says so at start:

```
no repositories declared — this receiver will accept a delivery for ANY
repository that reaches it. Set the top-level `repositories` in the CLI
config to bound it to the ones this instance works with
```

The poller, meanwhile, has nothing to poll and says so on its first cycle. Declare your
repositories; the empty default exists so that upgrading cannot silently stop an
instance, not because it is a sensible place to stay.
:::

This is the one direction in which the declaration is permissive. Everything else about it
fails closed.

#### What it is not

A repository bound is **not** authentication. It narrows what a forged or unsigned
delivery can address; it does not make one trustworthy. Two guards sit beside it and
neither is replaced:

- the `X-Hub-Signature-256` HMAC, which is only checked
  [when a secret is configured](/config/cli/webhook-options#secretenv);
- the authorized-actor guard on the event's actor
  ([`routing.authorizedUsers`](/config/cli/routing-options#authorizedusers),
  [decision-023](/decisions/decision-023)).

It is also not [`instance.scope`](/config/cli/instance-options#scope-mode), which answers
*which instance* takes a work item — a different question from *which repositories may
reach this machine*.

## Migrating from `polling.sources[].repos`

The key is gone, and a config that still declares it makes the runtime **refuse to
start**, naming the key, its replacement and the command. Run
[`the-loop migrate-config`](/cli/commands/migrate-config) (or let
`/the-loop:upgrade-the-loop` run it):

```yaml
# before — 0.7.0
polling:
  sources:
    - provider: github
      repos: [octo/app, octo/lib]
channels:
  slack:
    kickoff:
      repo: octo/app
```

```yaml
# after — 0.9.0
repositories: [octo/app, octo/lib]
polling:
  sources:
    - provider: github
channels:
  slack:
    kickoff:
      repo: octo/app        # still the channel's default target — it now POINTS AT
                            # a declared repository rather than declaring one
```

Every `github` source's list moves up, in declaration order, deduplicated;
`channels.slack.kickoff.repo` joins the list and stays where it is. A source under another
provider keeps its own keys untouched. The migration is idempotent, previewable with
`--dry-run`, and keeps a `.bak`.

**One thing does change behaviour on upgrade, on purpose:** your receiver is now bounded
by this list too. If you were relying on it accepting deliveries from a repository you
never listed, add that repository.
