# `pr`

Open, inspect and merge a work item's pull request, without `gh`.

```bash
the-loop pr create --work-item github:OWNER/REPO#N --title "feat: …" --body-file briefing.md
the-loop pr status  github:OWNER/REPO#16            # or its URL, or: 16 --work-item …
the-loop pr threads github:OWNER/REPO#16 [--all]
the-loop pr merge   github:OWNER/REPO#16 [--method squash]
```

A `PR` argument is a ref (`github:[HOST/]OWNER/REPO#16`), the pull request's URL, or
its bare number together with `--work-item` (resolved against the work item's
repository, as [`sessions link-pr`](/cli/commands/sessions) does).

## `pr create`

Opens the pull request **and records it against the work item in the same act**,
exactly as `sessions link-pr` would. There is no second step to forget, and the
plugin's `PostToolUse` hook does not need to catch it.

| Flag | Default | Meaning |
|------|---------|---------|
| `--work-item` | required | The work item the PR delivers. |
| `--title` | required | The PR title. |
| `--body` / `--body-file` | required (one) | The PR body; `--body-file -` reads stdin. |
| `--head` | the checkout's branch | The branch to merge from; `OWNER:BRANCH` for a fork. Read in the working directory, on the CLI side. A detached HEAD needs the flag. |
| `--base` | the repository's default branch | The branch to merge into. |
| `--repository` | the work item's | `[HOST/]OWNER/REPO` for a PR in a contributing repository. |
| `--draft` | off | Open it as a draft. |

If the PR opens but cannot be linked (no session is recorded for the work item on
this machine), the verb still exits 0. It prints the PR and says on stderr why it
is not linked. The PR exists, and a failure would invite a second one.

## `pr status`

Prints as JSON the PR's `state`, `merged`, `mergeable`, `mergeableState`, `draft`,
`headSha`, `url`, and one `checks` verdict over both check runs and commit statuses:

| `checks.conclusion` | When |
|---------------------|------|
| `failure` | A check run concluded `failure`, `cancelled`, `timed_out` or `action_required`, or a status is `failure` or `error`. |
| `pending` | Nothing failed, and something is still running. |
| `success` | Everything finished and nothing failed. |
| `none` | The head commit carries no check at all. |

`checks.failing` and `checks.pending` name the checks. The verb makes three GitHub
requests: the PR, its check runs, and its combined status.

## `pr threads`

Prints as JSON the PR's **unresolved** review threads: `id`, `path`, `line`,
`isOutdated`, and each comment's `author`, `body`, `createdAt` and `url`. `--all`
includes resolved threads.

## `pr merge`

Merges with `--method merge|squash|rebase` (default `merge`), **only if** the
operator's `routing.mergeOnApproval` is `true`, which is the default. When it is
`false`, the verb exits 1, merges nothing, and names the key: a person merges this
repository's PRs. The knob is read from the config of the process that runs the
merge, which is the daemon's when a service is running. No flag overrides it.
GitHub still enforces branch protection and required reviews (exit 1, with
GitHub's message).

## Notes

- Routed through the control-plane service when one runs, and otherwise run
  in-process on `GH_TOKEN`, with a note on stderr. See
  [`comment`](/cli/commands/comment#where-it-runs-and-whose-token).
- Exit 1 is a GitHub refusal (a duplicate PR, a PR that is not mergeable), a
  missing token, or the merge policy. Exit 2 is a malformed argument, sent nowhere.
