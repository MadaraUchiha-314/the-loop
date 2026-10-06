---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#464"
---

# Self-review: a Slack app from one click (issue-464)

> `the-loop critic list` reports no critics configured in this cloud checkout, so the
> critic rounds are unavailable. Round 3 found nothing new, which meets the stop rule
> (`the-loop critic policy`: 3 self, 3 critic, stop on no new findings).

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition |
|-------|----------|---------|------------------------|
| 1 | self (scope read) | new findings | (a) The issue says the user "pastes the bot token back". That conflicts with the credential preflight's rule that a token never enters the conversation. The walkthrough sends tokens to the environment or `env.file`, and the requirements name the reading for the reviewer. (b) Clicking the link a second time creates a second app. The init, upgrade and guide text all say to paste the kept file over the existing app's *App Manifest* instead. |
| 2 | self (diff read) | new findings | (c) The guide's 1b section told operators to edit the two name lines by hand to keep their name. It now says to regenerate with `--write`, since pasting the packaged manifest resets the name. (d) The renamed YAML loses the packaged file's comments. Kept the no-option path verbatim so `the-loop channels manifest` prints exactly what it did before, and documented the trade-off in the design. |
| 3 | self (adversarial read) | zero (converged) | — |
| — | critic | unavailable | — |

## Questions asked of the diff, and their answers

- **Can a tampered kept file keep a widened scope through an upgrade?** No. `write`
  reads only `display_information.name` back, and the test adds `admin` to the old file
  and checks the result equals the packaged manifest, reporting `- admin`.
- **What does `--write` do to a file it did not write?** It reads it as JSON. Without a
  name in it, it refuses with exit 2 and leaves the file byte-for-byte as it was (tested
  for four shapes). `--name` is the explicit override.
- **Does a crash leave half a manifest?** No. The text goes to a temporary sibling and
  `os.replace` swaps it in.
- **Does `--write` with an unreadable old file and `--name` report a sensible delta?**
  It reports every scope as added and asks for a reinstall. With no readable baseline,
  that is the safe direction. Accepted as is.
- **Is the slash command renamed with the app?** No. Every reply and help text names
  `/the-loop`, and Slack lets two apps share a command. Recorded as a design decision.
