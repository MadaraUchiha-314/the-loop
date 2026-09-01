# Quickstart

This walks through taking a single GitHub issue through the whole loop.

## 1. Scaffold the-loop into your repo

```text
/the-loop:init
```

A guided, schema-driven onboarding writes `.the-loop/harness-config.yaml` with sensible
defaults. Idempotent — safe to re-run. Pass `--defaults` to skip the interactive
walkthrough.

The schema that validates it ships **with the plugin** and is never copied into your
repository, so what you get is your configuration and nothing of the-loop's internals. The
written file opens with a `# yaml-language-server: $schema=…` line, which is what gives
your editor completion and validation while you edit it.

## 2. Run the whole spec workflow on a ticket

```text
/the-loop:work-on <ticket>
```

`<ticket>` is a GitHub issue or Jira id. This is the superset command: it runs
requirements → design → tasks → execute, pausing for human review at each phase gate,
and is resumable per phase if you stop partway through.

## 3. Or drive phases one at a time

The granular commands run the same flow a step at a time — useful when you want to
pause and think between phases, or a fuzzy idea needs to be brainstormed before it's
worth writing requirements for:

```text
/the-loop:brainstorm <title>        # optional — free-form scratchpad for a fuzzy idea
/the-loop:new-requirement <title>   # draft requirements.md before a ticket exists
/the-loop:create-ticket <path>      # create the ticket from requirements.md
/the-loop:create-design <id>        # design.md from approved requirements
/the-loop:create-tasks-plan <id>    # tasks.md DAG from requirements + design
/the-loop:execute-tasks <id>        # implement, self-check, self/critic-review, evidence
/the-loop:finish-tasks <id>         # cleanup once all tasks are complete
/the-loop:work-status <id>          # read-only status from specs, tasks, execution log
```

See the full [command reference](/reference/commands) for what each one does.

## 4. Watch the artifacts land

Each phase writes to `docs/specs/<id>/` in your repo:

```text
docs/specs/<id>/
  brainstorm.md       # optional root artifact
  requirements.md      # or bugfix.md for bug work
  design.md             # + design/ for UI/UX artifacts, when user-facing
  tasks.md               # the DAG of small, verifiable tasks
  execution-log.md        # progress log written during execution
```

The ticket's phase label moves through `not-started → requirements-definition → design
→ test-planning → tasks-breakdown → implementation → verification → needs-review →
complete` as the loop advances —
`work-status` reads it back out for you at any point.

## 5. Or skip the process entirely — ad-hoc tasks {#ad-hoc-tasks}

Not every task deserves a spec chain. For a **tactical** one — bump a dependency, fix a
typo, add a log line — comment this on the issue:

```text
the-loop do
```

That is the whole trigger. The-loop walks the **ad-hoc loop** (`pdlc-adhoc-loop`) instead
of the outer loop: it reads the issue as its instruction, does the work, and reports back
on the thread. There is no `requirements.md`, no design, no phase-selection checklist and
no review chain.

The keyword can ride along with the instruction, so one comment is usually the whole
interaction:

```text
the-loop do — bump ruff to 0.16 and fix whatever it flags
```

Then it is a conversation. Reply on the ticket and the-loop picks it up:

| You comment | What happens |
|---|---|
| anything that is **not** a "we're done" | more work — it routes back and keeps going |
| `done` / `lgtm` / `that's all` / `ship it` | the item is complete |
| *(you close the issue)* | the session ends, same as any work item |

Three things to know before you use it:

- **You must be an authorized user.** `the-loop do` is a control keyword like
  `the-loop start`, so the same `routing.authorizedUsers` allowlist applies, and the-loop
  can never answer its own gate.
- **No review chain runs.** No self-review, no critic round, no security-review gate.
  That is the point, and it is recorded: the loop this item walked is frozen in its
  `graph-state.json`, and your arming comment stays on the thread — so a reviewer of the
  resulting change can see that no automated review ran and who decided that. Lint,
  type-check and tests still run.
- **It is not a smaller `work-on`, and not `the-loop contribute`.** `contribute` joins
  somebody else's in-progress work and refuses to start without a stated goal and
  success criteria. Ad-hoc has neither: the ticket is the instruction and you decide when
  it is done.

Driving it from your editor instead of the ticket: `/the-loop:do-task <id>`. Configuring
or disabling the word: [`control.keywords.do`](/config/cli/routing-options#controlkeywordsdo).

## 6. Or ask for a review — PR reviews {#pr-reviews}

the-loop can also sit on the **other side** of a pull request: the reviewer's. Comment
this on the PR you want reviewed:

```text
the-loop review
```

the-loop walks the **review loop** (`pdlc-review-loop`) — bound to the pull request
itself, even when it links a ticket — and replies with a fill-in template asking what
the review should look at. Answer it (or put the block in the arming comment to skip the
round trip):

```text
the-loop review
Questions:
- does this change the public client API?
Angles:
- concurrency around the session registry
Validations:
- run the poller integration suite against this branch
```

At least one section with one bullet is enough; drop the rest. The brief is frozen with
your name on it, and each review round answers it in one comment: every question
answered, every angle examined, every validation run (or a stated reason it could not
be). Then it is a conversation, exactly like an ad-hoc task: any reply that is not a
"done" / "lgtm" is another round; say it is done — or merge/close the PR — and the
review ends.

It works on a **work item** too: comment `the-loop review` on the issue and one review
conversation spans every pull request delivering it. The template gains a
`Pull requests:` section, pre-filled with the PRs the-loop could detect (its own
tracking, plus the issue's linked pull requests) — edit the list, or fill it in when
nothing was detected.

Two things to know before you use it:

- **The reviewer is authorized, and the-loop changes no code.** The same
  `routing.authorizedUsers` allowlist arms the review and states the brief — and the
  review session commits nothing, pushes nothing and opens no PR. A finding worth
  fixing becomes a new work item (`the-loop start`, `contribute` or `do` — your call).
- **It installs nothing.** A review is a guest: it never writes the-loop's config into
  the reviewed repository, so you can invite it into any repo the daemon can reach.

Driving it from your editor instead of the thread: `/the-loop:review-pr <id>`.
Configuring or disabling the word:
[`control.keywords.review`](/config/cli/routing-options#controlkeywordsreview).

## Bring one more person onto one work item

`routing.authorizedUsers` is all-or-nothing: a login directs every work item your daemon
watches, or none. So when the-loop asks a question that only your colleague can answer,
their reply is dropped before anything reads it — unless you hand them the whole
deployment.

Instead, invite them onto that one work item:

```text
the-loop add-collaborator @dana
```

From then on Dana's comments **on this work item** (and on the pull requests delivering
it) reach the session, exactly like yours. That is all they can do: Dana cannot start,
stop, pause or clean up anything, cannot invite anyone else, and cannot approve a phase —
those still need a login on `routing.authorizedUsers`. The grant covers this work item
only, and it is cleared when the item closes; `the-loop remove-collaborator @dana` takes
it back sooner.

From a terminal it is the same two words:

```bash
the-loop add-collaborator @dana --work-item github:OWNER/REPO#307
```

Either way the keyword lands on the thread, so the ticket records who invited whom.
Details: [`add-collaborator`](/cli/commands/add-collaborator) ·
[`control.keywords.add-collaborator`](/config/cli/routing-options#controlkeywordsadd-collaborator).

## Next

- [How it works](/guide/how-it-works) — configuration, templates, and where knowledge
  lives.
- [Command reference](/reference/commands) — every command in one table.
- [the-loop CLI](/cli/) — the optional companion CLI: webhook and poll ingress,
  sessions, observability. Start at its
  [getting started](/cli/getting-started) page.
- [Configuration](/config/) — the harness config and the CLI config, option by option.
