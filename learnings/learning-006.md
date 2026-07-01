# Learning 006: Separate the published artifact from internal project meta

- **Date:** 2026-07-01
- **Source:** user-feedback
- **Work item:** issue-1

## What happened

Because the-loop's repo is both the plugin *and* a reference project that dogfoods the-loop,
its founding-issue and roadmap detail bled into the **skill** — the artifact shipped to
every user. A reference file documented "issue #1 realization", deferred work, `decision-NNN`
links, open TODOs, and "the-loop uses the-loop to develop itself". PR #2 review flagged that
this internal roadmap should not be published in the skill.

## Learning

When one repo is both a product and its own development project, draw a hard line between
the **published artifact** (commands/skills/hooks — what the user gets) and **internal
project meta** (the founding issue, decision log, roadmap, deferred status, self-development
notes). The published artifact describes capabilities that exist, in user-facing terms;
internal roadmap and provenance live in `docs/` and never leak into what ships. State
capability *boundaries* factually, but never as "roadmap/deferred/issue #N".

## Action

- Moved the internal roadmap to `docs/roadmap.md`; rewrote the skill reference as
  capability docs; scrubbed issue/decision provenance from all skill files (`decision-010`).
- Going forward, before shipping any skill/command change, check it for references to the-
  loop's own issues, decisions, roadmap, or build status — those belong in `docs/`, not in
  the published artifact.
