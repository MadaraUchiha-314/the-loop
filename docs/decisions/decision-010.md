# Decision 010: Keep the-loop's internal roadmap out of the published skill

- **Status:** accepted
- **Date:** 2026-07-01
- **Deciders:** @MadaraUchiha-314 (PR #2 review)
- **Work item:** issue-1

## Context

The skill (`skills/the-loop/`) is the **published artifact** loaded by every harness that
installs the-loop. Its reference files had drifted into documenting the-loop's *own*
development: a file literally titled "Automation, distribution & roadmap" that "captures
the realization details of issue #1", plus "deferred", "open TODOs carried from issue #1",
`decision-<nnn>` links, and "the-loop uses the-loop to develop itself". PR #2 review: "The
GitHub issue and the roadmap for the-loop is internal to it. Why are we publishing and
referencing that in our skills that's going to be our published artifact?"

## Decision

- The published skill documents **only capabilities that exist**, in user-facing terms. It
  must not reference the-loop's founding issue (#1), its decision log, its deferred/roadmap
  status, or its self-development meta.
- the-loop's **internal roadmap** (deferred automation, the dream, open questions carried
  from issue #1, self-development meta) moves to `docs/roadmap.md` — a project doc, not
  shipped in the skill.
- Renamed `reference/automation-and-roadmap.md` → `reference/automation.md`, rewritten as
  capability docs. Scrubbed "(issue #1)" / "deferred (see decision-NNN)" provenance tags
  from the other reference files (`tooling`, `observability`, `workflow`, `collaboration`).

## Consequences

- The published plugin reads as a product, not as the-loop's issue tracker; users are not
  confused by internal build status.
- The distinction is now explicit: **skill = what it does (product); `docs/` = how we build
  it (internal)**. Recorded as `learning-006`.
- Capability *boundaries* that users must know (e.g. the webhook receiver verifies events
  but does not yet route them) are stated factually in the skill, without roadmap framing.

## Alternatives considered

- **Leave it and just soften wording** — rejected: the issue/decision references are
  inherently internal regardless of tone.
- **Drop the forward-looking content entirely** — rejected: it is valuable to the-loop's
  own development; it belongs in `docs/roadmap.md`, just not in the shipped skill.
