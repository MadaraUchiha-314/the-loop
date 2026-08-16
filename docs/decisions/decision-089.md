# Decision 089: the harness's own markdown passes the project's linter; a human's words are never rewritten to

- **Status:** proposed
- **Date:** 2026-08-16
- **Work item:** [issue-247](https://github.com/MadaraUchiha-314/the-loop/issues/247)
- **Deciders:** maintainer (via ticket); harness (proposal)

## Context

the-loop writes markdown into files it then asks a project to lint. `record-feedback` is
the only hook that does it today — it appends an approving reviewer's comment to the
artifact's `## Review comments` section — and it wrote the attribution as
`**@handle**` alone on a line. That is the exact shape markdownlint's **MD036
(no-emphasis-as-heading)** exists to reject, so the first approval-with-comments on any
work item left the approved artifact failing the lint the same project is configured with.

Observed on [issue-239](https://github.com/MadaraUchiha-314/the-loop/issues/239): the
`design-approval` gate recorded into `design.md` and `testing-plan.md`, and `make lint`
failed on both. The session unblocked itself by hand-editing the recorded blocks — which
means the harness put a session in the position of editing a paper trail to satisfy a
linter, and that is the part worth writing a decision about rather than just a patch.

The second half of the problem has no patch. A reviewer's comment body is a human's text,
written into a linted file verbatim, and it can fail on its own merits: an `#` heading in
it trips MD025, a `+` bullet trips MD004, a hard tab trips MD010. Blockquoting the body
does not help — measured, not assumed: those rules fire identically through a blockquote
and the quoting adds MD027 of its own
([evidence](../specs/issue-247/evidence/shapes.md) §3).

## Decision

Two rules, and the second is why the first is not simply "make the file lint".

1. **Every line the harness authors into a checked-in artifact passes the project's
   configured linter.** The harness's own output is the harness's responsibility, and a
   gate that hands back an unlintable document has not finished its job.
2. **The harness never rewrites a human's words to satisfy a linter.** A reviewer's comment
   body is recorded verbatim (`.strip()` on the ends, nothing else). If a body makes an
   artifact fail lint, that is a fact about the body, and the answer is a human's edit or a
   deliberate lint-disable region — never a silent reflow by the recorder.

Applied here, that made the attribution `**@handle** wrote:` — emphasis plus trailing text,
so MD036's premise fails outright — and gave a comment with an empty body a single line of
its own (`**@handle** left no comment text.`) instead of the `\n\n\n` that tripped MD012.

**Not** the ticket's other suggestion, a blockquoted attribution. `> **@handle**` does pass,
but only because MD036 does not descend into blockquotes. That is an implementation detail
of the linter rather than a documented promise, and a fix that rests on where a rule chooses
to look regresses silently when it starts looking there.

## Consequences

- A recorded approval no longer costs a manual lint fix, and no session is asked to edit a
  paper trail again.
- The next hook that writes into an artifact inherits rule 1 as a review criterion. There is
  no shared "emit safe markdown" helper yet, on purpose: one call site, one shape
  (`reference/minimalism.md` — inline before abstraction). A second call site is when the
  helper becomes the right answer.
- Rule 2 is a standing limitation, not an oversight: a hostile or merely sloppy comment body
  can still fail an artifact's lint, and the-loop will not fix it by rewriting the comment.
  Whether the recorded region should instead be fenced in
  `<!-- markdownlint-disable -->` is a live question — it trades away lint coverage of the
  artifact, so it is a separate work item and a separate decision.
- Nothing here changes what the harness *accepts*: authorization, the self-authored marker
  and the `authorizedUsers` allowlist are upstream of the recorder and untouched
  ([decision-042](decision-042.md)).
