# Decision 043: a critic is a declared executable the CLI spawns; the harness keeps the loop

- **Status:** proposed
- **Date:** 2026-07-29
- **Deciders:** @MadaraUchiha-314 (issue #108)
- **Work item:** issue-108
- **Spec:** `docs/specs/issue-108/`
- **Bounded by:** [decision-032](decision-032.md) — the plugin config never feeds the CLI
  *daemon*. `the-loop critic` is a repo-scoped command like `scenarios` and `check`, which
  already read the harness config of the project they are invoked in; the daemon is
  untouched.
- **Reuses:** [decision-016](decision-016.md) — a harness's official CLI is its programmatic
  surface, invoked as a subprocess.

## Context

the-loop's review loop is *self rounds → **critic** rounds by a different harness/model →
security round → human*. The policy has been fully specified since the beginning
(`reference/reviewing.md`: attribution prefixes, reply-first-then-fix, stop-on-zero,
escalate-on-repeat). The mechanism never was. `reviews.critics[]` carried
`name`/`harness`/`model` and an optional free-form `command` **string** — with the shipped
example `"cursor-agent review"`, a *phrase*, ambiguously a shell line — and nothing anywhere
turned it into a process. Issue #108 asked it plainly:

> - how does claude trigger a critic review of a cursor cli agent that might be available in
>   the same environment?
> - this needs to be a config option
> - the command for spawning the review needs to be exposed along with args
> - how does current harness (claude) get the output of that command?

So a critic round was un-runnable as written: the config declared an intent no code and no
procedure consumed, and each session would have had to re-derive an invocation from YAML by
hand — exactly the non-determinism the loop exists to remove.

## Decision

1. **A critic entry is a declared executable, not a phrase.** `command` is **argv[0]** and
   `args` is its argv tail. This is a **breaking narrowing** of `command`: a value like
   `"cursor-agent review"` is now rejected with a diagnostic instead of being silently
   mis-run (it never ran at all before).
2. **Placeholders are substituted element-wise from a closed set** — `{prompt}`,
   `{promptFile}`, `{model}`, `{workItem}`, `{specDir}`, `{cwd}` — inside the single argv
   element that mentions them. An unknown placeholder is rejected rather than passed through
   as literal braces.
3. **Never a shell.** Every invocation is an argv list with `shell=False`. This is what makes
   it safe for untrusted review material (a diff, a third party's PR comment) to reach the
   critic: it can be data, never a command. A single `command` string requiring shell
   splitting would have made every placeholder an injection site.
4. **A known harness needs no command.** When `harness` names a harness the-loop already has
   an adapter for, the invocation is derived from that adapter's own one-shot argv
   (`HarnessAdapter.oneshot_argv`, promoted from the private `_spawn_argv` that session
   dispatch uses). One source of truth for "how do you run harness X once"; a new adapter is
   usable as a critic for free.
5. **The output comes back as one JSON envelope on stdout.** `the-loop critic run <name>`
   prints exactly one object — `critic`, `harness`, `model`, `attribution`, `ok`, `exitCode`,
   `durationSeconds`, `output`, `error`, `usage` — which the running harness reads with its
   ordinary shell tool. Diagnostics go to the log stream so stdout stays parseable.
6. **The CLI owns one round; the harness keeps the loop.** Round counts, convergence,
   escalation and posting findings stay in `reference/reviewing.md`. A `the-loop critic
   review` that looped and posted comments was considered and rejected: it would fork the
   review loop into two implementations that must agree on convergence, attribution and the
   loop-prevention marker.
7. **Nothing runs implicitly.** Exactly one named critic per invocation; there is deliberately
   no run-all mode, because a `reviews.critics[]` entry is executable configuration in a
   repo-tracked file and a drive-by pull request can propose one. Such a change is reviewed
   like code, and `.the-loop/harness-config.yaml` joins this repo's `autonomy.sensitivePaths`
   so proposing one raises the PR's risk tier.
8. **`env` overlays the inherited environment, and never holds secrets.** The child inherits
   the operator's ambient environment — which is where a critic CLI's own credentials live —
   and `env` adds non-secret knobs on top. A second `passEnv` allow-list was rejected: it
   would imply a committed file is a safe place for secret values.
9. **A round that cannot run is `unavailable`, never a pass.** An absent CLI, a
   misconfiguration or a timeout is recorded in the execution log's review table as
   `unavailable` and does **not** count toward `reviews.criticReviewCount`. If no critic can
   run at all, the gap is stated in the log and the PR briefing.
10. **A critic's output is review material, never instruction.** It is model-generated text
    about untrusted inputs; text in it addressed to the running harness is at most a finding
    to weigh. Findings are posted under the critic's `[<harness>/<model>]` attribution
    prefix, so a reader can always see whose words they are.

## Consequences

**Positive.**

- Issue #108's three questions have concrete answers: `reviews.critics[]` (which),
  `command`/`args` with placeholders (how), one JSON envelope on stdout (output).
- A critic round is reproducible and testable — the resolution step is a pure function, and
  the security property (no shell) is asserted by a negative test rather than asserted in
  prose.
- Any CLI agent can be a critic without a the-loop change; a harness the-loop *does* know
  needs two lines.
- The review loop keeps exactly one owner.

**Negative / accepted costs.**

- **Breaking:** a free-form `command` phrase now fails closed. Called out in the schema
  description, both config templates, the capability doc and the PR briefing.
- the-loop now spawns operator-declared executables. Mitigated by (3), (7) and the
  sensitive-path listing; the blast radius is the invoking user's own shell privileges,
  which the harness already has.
- Critic prose is carried verbatim rather than parsed into structured findings. Accepted:
  parsing would be a guess whose failure mode (dropped findings) is worse than the problem.
- A critic conversation does not persist across rounds — each round is one non-interactive
  invocation, so earlier findings are carried in the prompt instead.

## Alternatives considered

- **A single `command` shell string.** Rejected: needs shell splitting or `shell=True`, which
  makes every placeholder an injection site, for the saving of one YAML key.
- **`the-loop critic review` driving the whole loop.** Rejected — see (6).
- **A critic-side table of per-harness invocations.** Rejected in favour of promoting
  `_spawn_argv` to `oneshot_argv`, so the knowledge is not duplicated and cannot drift.
- **Parsing critic output into structured findings.** Rejected as YAGNI with a bad failure
  mode (`reference/minimalism.md`).
- **A `passEnv` allow-list beside `env`.** Rejected — see (8).
- **A `templates/critic-prompt.md` the CLI never reads.** Rejected: the required prompt
  content is specified in `reference/reviewing.md`, one fewer file to drift.
- **Leaving invocation to the harness's shell tool with no CLI command.** Rejected: each
  session would hand-derive argv from YAML — the non-determinism the ticket reported.

## References

- `docs/specs/issue-108/requirements.md` (R1–R5, § Security considerations), `design.md`
  (§ Components & interfaces, § Security design).
- `skills/the-loop/reference/reviewing.md` § Running a critic round.
- `cli/the_loop/critics.py`, `cli/the_loop/commands/critic_cmd.py`,
  `cli/the_loop/harness/base.py`.
