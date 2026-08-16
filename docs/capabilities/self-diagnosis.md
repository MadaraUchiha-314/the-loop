# Capability: self-diagnosis

> the-loop notices that **it** broke — an error in its own machinery, not in the work
> item it was running — debugs the failure in an isolated agent one-shot, and files the
> findings as a redacted issue on the-loop's own repository. Opt-in, default off.

## What it is

A scanner over the [event log](observability.md) that turns harness-level failures
(error-level records, terminal give-ups such as
[#240](https://github.com/MadaraUchiha-314/the-loop/issues/240)'s
`poll.comment_failed`) into well-formed bug reports on the-loop's tracker, labeled
`the-loop: self-diagnosed` — so the-loop improves itself from its own failures instead
of depending on a human replaying a JSONL file. It runs as a background watcher inside
the two ingress daemons (the poller and the gh-webhook receiver) and as the manual
[`the-loop diagnose`](../cli/commands/diagnose.md) verb; `--dry-run` previews exactly
what would leave the machine, and works while the feature is disabled.

## Current behaviour

- Detection SHALL be a policy over event-log records — `level: error`, or
  `will_retry: false` — never an exception hook; `diagnosis.*` events SHALL never be
  candidates (no recursion). One normalized fingerprint per defect: retries and
  volatile tokens (digits, hex, paths) SHALL NOT split it, and a fingerprint already
  reported or abandoned SHALL NOT be diagnosed again.
- The feature SHALL be **opt-in and off by default** (`selfDiagnosis.enabled` in the
  CLI config): absent, `false`, or malformed all mean no scan, no watcher thread, no
  agent run, no post — a malformed section resolves to disabled with a logged error.
- The diagnosis SHALL run in an **isolated agent one-shot** (claude | cursor, via the
  critic invocation mechanics of decision-043): argv list, never a shell, under a
  timeout, in a private temporary directory; its prompt SHALL contain only the
  redacted dossier, the-loop's version and package location, and the reporting
  instructions.
- Everything that leaves the machine SHALL be **redacted**: the dossier is a field
  allow-list (event types, levels, enums, counters — never `work_item`, `cwd`,
  `delivery_id`, `tmux_target` or unknown fields), free text passes the scrubber
  (home, username, hostname, paths, e-mails, tokens, sensitive env values), and an
  unbuildable report SHALL post nothing (fail closed).
- The created issue SHALL carry the requested label (`the-loop: self-diagnosed` by
  default; GitHub drops it silently without triage rights, and the body names it
  either way), the loop-prevention marker plus visible attribution, and SHALL be
  traceable: URL in the local ledger and a `diagnosis.posted` event.
- A self-filed issue SHALL **never arm itself**: no auto-execute label, no
  control-keyword comment, control keywords in the body defanged so `parse_command`
  finds nothing, and the self-authored marker drops the text at ingress (issue-104).
- Storms SHALL be bounded: `maxIssuesPerDay` (rolling; excess **deferred**, never
  dropped), `maxRetries` failed attempts before a fingerprint is abandoned, and a
  per-scan lock so concurrent scanners never double-post.

## Design

[`docs/specs/issue-242/design.md`](../specs/issue-242/design.md) ·
config: [self-diagnosis options](../config/cli/self-diagnosis-options.md) ·
state: [`<root>/self-diagnosis.json`](../cli/state.md)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-242 | The capability: detection over the event log, the isolated diagnosis one-shot, allow-list redaction, never-armed issue creation, the watcher in both daemons and `the-loop diagnose` | [spec](../specs/issue-242/), [decision-090](../decisions/decision-090.md) |
