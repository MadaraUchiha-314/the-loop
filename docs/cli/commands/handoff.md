# `handoff`

Post, show, import or re-point a conversation **handoff record**
([issue-517](https://github.com/MadaraUchiha-314/the-loop/issues/517)). The record
lets an idea talked through with Claude start the loop at the stage the developer
reached instead of at the first phase. The `/the-loop:handoff` command
(`skills/handoff-to-the-loop/SKILL.md`) calls `post`. The `import-handoff` node's
session calls `import` and `note`.

```bash
the-loop handoff post --work-item github:OWNER/REPO#N --record record.json [--files DIR]
the-loop handoff show issue-N
the-loop handoff import issue-N [--from-dir DIR]
the-loop handoff note issue-N [--branch the-loop/…] [--pull-request M]
```

## Actions

| Action | What it does |
|--------|--------------|
| `post` | Renders the record from its JSON (the shape `show` prints). For `carried-by: ticket` it also renders the files from `--files` and any part comments, then posts each comment in order the way [`comment`](/cli/commands/comment) does, so each one carries the self-authored marker. Prints the posted URLs as JSON. |
| `show` | Prints the record stored in `work-item-state.json` as JSON (`{}` when there is none). Read-only. |
| `import` | Writes the carried files into `docs/specs/<id>/`. They come from the checked-out spec branch, from the ticket's record and part comments, or from `--from-dir`, where the session extracted the spec-chain artifact's embedded files. The artifact carrier requires `--from-dir`. Each file is checked against the record's `sha256`, and only verified files are written. The verb prints `written`, `verified` and `refused` (`{name, reason}`) as JSON, and records `handoff.imported`. A refusal still exits 0, because the graph's `import-handoff` hook does the demotion. |
| `note` | Points the record at the committed files and the PR: `carried-by: branch <branch> · PR #<n>`. The record comment is edited in place only when the-loop posted it **and** the verb runs outside a daemon-spawned session. The control plane has no comment-edit route, so in a daemon session `note` always posts one comment that supersedes the record. The output's `edited` says which happened. The PR comes from state unless `--pull-request` is given. |

`show`, `import` and `note` take the work item as a spec id or a ref, plus `--repo`
and `--spec-dir`, which work as they do for [`graph`](/cli/commands/graph).

## The record

One comment on the GitHub issue: the marker `<!-- the-loop:handoff v1 -->`, then a
`text`-fenced block of `key: value` lines. With `carried-by: ticket` the files follow,
one `<details>` block each.

```text
stage:            requirements-settled
enter:            requirements-approval
artifacts:        brainstorm.md sha256:<64 hex>, requirements.md sha256:<64 hex>
carried-by:       branch the-loop/issue-42-x · PR #43
from:             Claude chat · 2026-10-21
approved-in-chat: brainstorm.md
confirmation:     > yes, file it
```

- **Keys** are `stage`, `enter`, `artifacts`, `carried-by` (all required),
  `spec-artifact` (`<https URL> sha256:<hex>`, stored as `specArtifact` and
  `specArtifactSha256`), `from`, `approved-in-chat`, `mirror` (`jira:<site>/<KEY-N>`),
  `confirmation` and `parts`. An unknown key or version rejects the record.
- **`parts`** is the **number** of part comments. A file body past GitHub's
  65,536-character limit continues in comments that open with
  `<!-- the-loop:handoff-part v1 n/N -->`. A part counts only when the record's author
  wrote it after the record.
- **`enter`** must be the starting step for the stage and the carried artifacts:
  `brainstorming`, `brainstorm-approval`, `requirements-approval`, `test-planning` or
  `design-approval`, never later.
- **Artifact names** are a closed set (`brainstorm.md`, `requirements.md`, `bugfix.md`,
  `design.md`, `testing-plan.md`). No path comes from the record.
- **`approved-in-chat`** may name only carried artifacts, and never the furthest one.
- **Who may post one.** The poller admits a record only from a login in
  `routing.authorizedUsers`, and never from a comment with no author. The self-marker
  that `post` stamps grants nothing by itself: the-loop's own records count because on
  GitHub it posts as the operator, an authorized login.

## Exit codes

| Code | When |
|------|------|
| 0 | Done. For `import`, this includes files that were refused. |
| 1 | GitHub refused a post. |
| 2 | Usage error: a malformed ref or record, missing `--files` or `--from-dir`, no record in state, or a branch outside `the-loop/`. Nothing is sent or written. |
