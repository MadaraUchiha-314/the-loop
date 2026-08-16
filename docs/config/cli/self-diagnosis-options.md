---
configBase: selfDiagnosis
---

# Self-diagnosis options

Options under `selfDiagnosis` — the-loop noticing that **it** broke, and filing the bug
itself ([issue-242](https://github.com/MadaraUchiha-314/the-loop/issues/242)). When the
daemons hit a harness-level failure — an error-level event, or a terminal give-up like
[#240](https://github.com/MadaraUchiha-314/the-loop/issues/240)'s
`poll.comment_failed` — the evidence is already in the
[event log](/config/cli/observability-options). Self-diagnosis scans that log, debugs
each **new** failure in an isolated agent one-shot, and posts the findings as an issue
on the-loop's own repository, labeled `the-loop: self-diagnosed`.

**Strictly opt-in, off by default.** Enabling it means this machine may post redacted
failure reports publicly, with your own `gh` credentials. Before opting in, run
[`the-loop diagnose --dry-run`](/cli/commands/diagnose) — it prints exactly what would
leave the machine, and works while the feature is disabled.

Three properties hold regardless of configuration:

- **Everything posted is redacted.** Reports are built from a field *allow-list*
  (event types, levels, enums, counters); free text is scrubbed of paths, usernames,
  hostnames, e-mails, tokens and sensitive environment values. Work-item refs and
  repository names never appear.
- **A self-filed issue is never armed.** No auto-execute label, no control-keyword
  comment; keywords inside the body are visibly defanged, and the body carries the
  self-authored marker so the-loop's own ingress drops it.
- **Storms are bounded.** One issue per failure fingerprint ever; a rolling daily cap
  defers (never drops) the excess; repeated agent failures abandon the fingerprint.

The watcher runs inside the daemons that already exist (the poller and the gh-webhook
receiver) — there is no fourth service. Deployments running neither daemon use
[`the-loop diagnose`](/cli/commands/diagnose).

```yaml
selfDiagnosis:
  enabled: false
  repo: MadaraUchiha-314/the-loop
  label: "the-loop: self-diagnosed"
  harness: claude
  model: ""
  timeoutSeconds: 900
  intervalSeconds: 3600
  maxIssuesPerDay: 3
  maxRetries: 3
```

## Options

### `enabled`

- **Type:** `boolean`
- **Default:** `false`

The opt-in. Only a literal `true` enables anything; an absent section, `false`, or a
malformed section all mean no scan, no watcher thread, no agent run, no post — fail
closed.

### `repo`

- **Type:** `string`
- **Default:** `MadaraUchiha-314/the-loop`

`owner/repo` the issues are filed on. Defaults to the-loop's own repository — the point
of the feature is fixing the-loop, not your project. Point it at a fork if you triage
there first.

### `label`

- **Type:** `string`
- **Default:** `the-loop: self-diagnosed`

Label requested on each created issue. GitHub silently drops the request for callers
without triage rights on the target repository; the body names the intended label either
way, so the marker survives the permission gap. Must never equal
[`routing.autoExecuteLabel`](/config/cli/routing-options) or any
`polling.sources[].label` — the label must mark, never arm.

### `harness`

- **Type:** `string` — `claude` | `cursor`
- **Default:** `claude`

Which agent harness runs the isolated diagnosis one-shot (the same adapter set as
[`routing.defaultHarness`](/config/cli/routing-options)). The run is a subprocess with
an argv list — never a shell — under `timeoutSeconds`, in a private temporary directory.

### `model`

- **Type:** `string`
- **Default:** `""` (the harness's own default)

Model passed to the harness's one-shot invocation.

### `timeoutSeconds`

- **Type:** `number`
- **Default:** `900`

Wall-clock budget for one diagnosis agent run.

### `intervalSeconds`

- **Type:** `number`
- **Default:** `3600`

How often the background watcher scans the event log for new failures. A manual
[`the-loop diagnose`](/cli/commands/diagnose) scans regardless.

### `maxIssuesPerDay`

- **Type:** `integer`
- **Default:** `3`

Rolling 24-hour cap on created issues (storm control). Candidates over the cap are
**deferred** to a later scan, never dropped — a real bug is late, not lost.

### `maxRetries`

- **Type:** `integer`
- **Default:** `3`

Failed diagnosis attempts (agent run or post) per failure fingerprint before it is
abandoned and never retried. The ledger of reported, retrying and abandoned
fingerprints is the [self-diagnosis state file](/cli/state).
