# `diagnose`

One [self-diagnosis](/config/cli/self-diagnosis-options) scan, on demand: read the-loop's
own [event log](/cli/state) for harness-level failures — error-level events, terminal
give-ups — debug each **new** one in an isolated agent one-shot, and file the findings as
an issue on the-loop's own repository, labeled `the-loop: self-diagnosed`
([issue-242](https://github.com/MadaraUchiha-314/the-loop/issues/242)).

```bash
the-loop diagnose [--dry-run]
```

The automatic form of the same capability is the background watcher the poller and
gh-webhook daemons host when `selfDiagnosis.enabled` is true; this command is for
deployments running neither daemon, and for previewing.

| Flag | Default | Meaning |
|------|---------|---------|
| `--dry-run` | off | Build and print the redacted report(s) without posting. Works while the feature is **disabled** — this is how you see exactly what would leave the machine before opting in. |

Without `--dry-run`, the command refuses unless `selfDiagnosis.enabled: true` is set in
the [CLI config](/config/cli/self-diagnosis-options) — self-diagnosis posts publicly with
your own `gh` credentials, so nothing short of that explicit opt-in posts anything.

## What a run does

For each new failure fingerprint in the log: build the redacted dossier (field
allow-list, free text scrubbed), run the configured harness (`claude` | `cursor`) as a
one-shot subprocess in a private temporary directory, compose the issue (summary, root
cause hypothesis, suggested fix, trigger evidence, environment), and create it via your
`gh` CLI with the `the-loop: self-diagnosed` label requested. Every outcome is printed
and recorded — in the event log (`diagnosis.*` events) and in the
[self-diagnosis ledger](/cli/state#self-diagnosis-ledger-rootself-diagnosisjson), which
maps each fingerprint to the issue it produced.

A self-filed issue is **never armed**: no auto-execute label, no control-keyword
comment, control keywords in the body visibly defanged, and the self-authored marker so
the-loop's own ingress drops it.

Failures are bounded: an agent that keeps failing abandons the fingerprint after
`maxRetries` attempts, and at most `maxIssuesPerDay` issues post per rolling day — the
excess is deferred to a later scan, never dropped.
