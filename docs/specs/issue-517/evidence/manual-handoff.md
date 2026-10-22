# Manual handoff: issue-517 T11

**Partial.** The network half of the handoff ran against real GitHub. The interview and
the live poller pick-up did not run, for the two reasons under *Not executed*.

## What ran

Scratch issue [#520](https://github.com/MadaraUchiha-314/the-loop/issues/520), opened
with `the-loop ticket create`, never armed, and closed afterwards.

1. Two carried files: a 89,078-character `brainstorm.md` (backtick fences, `<tags>`,
   `&` and non-ASCII text, sized to need a part comment) and this item's
   `requirements.md` (16,992 characters). The record is *requirements settled*, carried
   by `ticket`, with `approved-in-chat: brainstorm.md`.
2. `uv run the-loop handoff post --work-item github:MadaraUchiha-314/the-loop#520 --record record.json --files files/`:

   ```json
   {
     "workItem": "github:MadaraUchiha-314/the-loop#520",
     "posted": [
       "https://github.com/MadaraUchiha-314/the-loop/issues/520#issuecomment-6334743682",
       "https://github.com/MadaraUchiha-314/the-loop/issues/520#issuecomment-6334744112"
     ],
     "complete": true
   }
   ```

3. The comments were read back with `gh api repos/MadaraUchiha-314/the-loop/issues/520/comments`
   and run through the branch's own `find_record`, `collect_parts` and `extract_files`:

   ```text
   comments: 2 sizes: [65451, 41752]
   record: ('requirements-settled', 'requirements-approval', 'ticket', 1, 'MadaraUchiha-314', 'https://github.com/MadaraUchiha-314/the-loop/issues/520#issuecomment-6334743682') reasons: []
   brainstorm.md present hash-ok byte-equal
   requirements.md present hash-ok byte-equal
   ```

   With the dispatcher's exact authorization check (a self-marked record must also have
   an authorized author):

   ```text
   authorized=[MadaraUchiha-314] -> honoured []
   authorized=[someone-else] -> ignored ["ment-6334743682: author 'MadaraUchiha-314' is not authorized"]
   ```

**Result:** both comments fit under 65,536 characters (65,451 and 41,752). GitHub
stored them without changing a byte the parser depends on. Both files came back
byte-equal and hash-verified. The record is honoured for an authorized author and
ignored otherwise.

## Not executed

- **The interview (steps 1–2 of the T11 procedure).** This session is daemon-spawned in
  `work-item` interaction mode, which launches Claude Code without `AskUserQuestion`
  (issue-426). The skill itself refuses to interview here (R2.10). The interview needs a
  developer at a terminal.
- **The live poller pick-up (steps 4–6).** The running daemon on this machine is the
  released 20.8.0, not this branch. Arming a scratch issue would exercise the old code
  and prove nothing about `import-handoff`. The pick-up is covered in-process by the
  five R6-table walk scenarios and the dispatcher scenarios (`tests.md`).

Both need a developer to run `/the-loop:handoff` against a daemon built from this
branch. That is escalated on PR #518 for the human-approval gate.
