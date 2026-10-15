# T11: live attribution and the redaction grep

Executed at the `verification` node, 2026-10-15, on PR #489.

## Live attribution

**The question.** Does GitHub's GraphQL edit history (`IssueComment.userContentEdits`)
name the user who ticked a box in a comment the-loop posted? `quiz-attested` relies on it,
and a fake cannot prove it.

**The procedure.**

1. the-loop posted a sandbox quiz comment on PR #489 with `the-loop ask`. It carried an
   unticked attestation line and the marker `<!-- the-loop:quiz spec-quiz round=99
   digest=- -->`. Round 99 matches no real round, so no gate could read it.
   [The comment](https://github.com/MadaraUchiha-314/the-loop/pull/489#issuecomment-6199247862).
2. @MadaraUchiha-314 ticked the box.
3. @MadaraUchiha-314 replied that this session may run one read-only query with the
   session token
   ([reply](https://github.com/MadaraUchiha-314/the-loop/pull/489#issuecomment-6201342841)).
   The token is the `THE_LOOP_GH_TOKEN` flagged in
   [the security finding](https://github.com/MadaraUchiha-314/the-loop/pull/489#issuecomment-6199110164).
   It was used for this one call only, and was never printed.
4. The query was the shipped client method. Only the login, the timestamps and a boolean
   were printed:

   ```sh
   cd cli && env -u GH_TOKEN -u GITHUB_TOKEN uv run python -c "
   from the_loop.ghapi import GitHubClient, GitHubApiConfig
   c = GitHubClient(GitHubApiConfig(token_envs=('THE_LOOP_GH_TOKEN',)))
   r = c.comment_edits('IC_kwDOTGeGic8AAAABcYED9g')
   ..."
   ```

**Output** (complete):

```text
author: MadaraUchiha-314
ticked-line-present: True
edit: MadaraUchiha-314 2026-10-15T20:04:55Z
edit: MadaraUchiha-314 2026-10-15T18:23:18Z
```

**Outcome: pass.**

- The newest edit, at 20:04:55Z (the tick), names `MadaraUchiha-314` as its editor.
- The older entry is the comment's creation, at 18:23:18Z.
- The body now carries the ticked line.

So `comment_edits` returns the ticking user as `edits[0]`, which `quiz-attested` reads as
the editor.

**What this does not prove.** the-loop posts under the operator's own account, so here the
comment's author and its editor are the same login. The edit history tells a person apart
from another GitHub account. It cannot tell the operator apart from a session holding the
operator's token. That is the open security finding, carried into the security review.

**Departure from the plan.** The plan named a sandbox *issue*. A comment on PR #489 was
used instead. Both are `IssueComment` nodes on the same API, and no extra issue was opened
or left to tear down.

## Redaction grep

**Scope:** every committed explainer HTML file. This work item's own explainer is published
as a Claude artifact, not committed, so it is outside the grep.

```sh
grep -nEi 'gh[pousr]_[A-Za-z0-9]{20,}|token|cookie|@[a-z0-9.-]+\.(internal|corp|local)' \
  docs/specs/issue-488/design/explainer.html skills/the-loop/templates/explainer.html
```

| File | Matches | Verdict |
|---|---|---|
| `skills/the-loop/templates/explainer.html` | none | clean |
| `docs/specs/issue-488/design/explainer.html` | 1. Line 173, in a quiz option: "Four declared skips under the token explainer…" | false positive. The match is the word "token", meaning the phase-selection token. It is not a credential |

**Outcome: pass.** The match was reviewed by hand. The credential-shaped part of the
pattern (`gh[pousr]_…`), cookies and internal hostnames match nothing.
