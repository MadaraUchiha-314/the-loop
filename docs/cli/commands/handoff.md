# `handoff`

Post, show, import or re-point a conversation **handoff record**
([issue-517](https://github.com/MadaraUchiha-314/the-loop/issues/517)). The record
lets an idea talked through with Claude start the loop at the stage the developer
reached instead of at the first phase.

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
| `import` | Writes the carried files into `docs/specs/<id>/`. They come from the checked-out spec branch, from the ticket's record and part comments, or from `--from-dir`, where the session extracted the spec-chain artifact's embedded files. The artifact carrier requires `--from-dir`. Each file is checked against the record's `sha256`, and only verified files are written. The verb prints `written`, `verified` and `refused` (`{name, reason}`) as JSON. A refusal still exits 0, because the graph's `import-handoff` hook does the demotion. |
| `note` | Points the record at the committed files and the PR: `carried-by: branch <branch> · PR #<n>`. If the-loop posted the record, the comment is edited in place. Otherwise it posts one comment that supersedes the record. The PR comes from state unless `--pull-request` is given. |

`show`, `import` and `note` take the work item as a spec id or a ref, plus `--repo`
and `--spec-dir`, which work as they do for [`graph`](/cli/commands/graph).

## Exit codes

| Code | When |
|------|------|
| 0 | Done. For `import`, this includes files that were refused. |
| 1 | GitHub refused a post. |
| 2 | Usage error: a malformed ref or record, missing `--files` or `--from-dir`, no record in state, or a branch outside `the-loop/`. Nothing is sent or written. |
