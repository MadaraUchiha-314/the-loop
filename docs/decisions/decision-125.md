# Decision 125: an adapter's flags are the spelling the harness's own `--help` lists, declared once and never derived at runtime

- **Status:** proposed
- **Date:** 2026-09-14
- **Deciders:** the-loop (engineer), reported by @jc1993
- **Work item:** [issue-360](https://github.com/MadaraUchiha-314/the-loop/issues/360)

## Context

`CursorAgentAdapter.model_flag` was `-m`. `cursor-agent` has no such option, so every
critic declared `harness: cursor` **with** a `model:` exited on
`error: unknown option '-m'` before the prompt was read, and `the-loop models check`
recorded the resulting non-zero exit as the *harness refusing the model* — which then
withheld that model from the phase-selection checklist. Neither surface said "the-loop
sent a flag this CLI does not have"; one reported a missing review round, the other
reported a refusal.

The flag was never wrong in a way the repository could see. `-m` is a plausible short form,
and the tests asserted the adapter's own constant back to itself — `("-m", name)` on both
sides of the assertion — so the suite agreed with the defect. The only assertion that ran
the full critic argv had the same `-m` written into it.

Two questions fall out, and they have different answers:

1. Where does a flag spelling come from?
2. Should the-loop verify it against the binary at runtime?

## Decision

**A `model_flag` (and any future adapter flag) is a spelling the harness's own `--help`
lists, taken in the long form when a CLI offers both, declared in the adapter and stated in
the `review-loop` capability doc — and never derived from the binary at runtime.**

Concretely:

- `CursorAgentAdapter.model_flag = "--model"`, with the reason and the failure it caused in
  a comment beside it.
- The rule is written into `docs/capabilities/review-loop.md` §Current behaviour, next to
  the statement that a built-in critic's invocation derives from the adapter's argv, so the
  next adapter is read into existence rather than guessed.
- A regression test asserts the **argv**, not the constant: `oneshot_argv(prompt, model)`
  for cursor, and the full `resolve_invocation` for a cursor critic. An assertion that
  compares an adapter's attribute to itself proves nothing about the process it spawns.

The long form is the operative half of the rule. A CLI that offers both accepts the long
one; a CLI that offers one nearly always offers the long one. Choosing it costs nothing and
removes the class of defect entirely.

## Consequences

- **A cursor critic with a model runs**, and the review round it was configured for happens
  — with the attribution prefix naming the model, which the `args` workaround could not do.
- **`models check` stops mislabelling a parse error as a refusal** on cursor, so a declared
  model is offerable again at the gate.
- **No migration for the cached verdicts.** A verdict records the digest of the argv it was
  taken against and `VerdictCache.get` drops one whose digest no longer matches, so the
  `-m` era's `refused` answers stop applying the moment the flag changes. Asserted by a
  test rather than assumed.
- **The next adapter costs a `--help` read.** That is the intended price: the rule makes
  the check explicit and cheap instead of implicit and unperformed.
- **Nothing detects the *next* wrong flag automatically.** `models check` probes whether a
  *model* runs, not whether the-loop's own flags parse; on a machine with the binary a
  wrong flag still shows up as a blanket `refused`, which is a symptom, not a diagnosis.
  Making the probe distinguish the two is a follow-up, not this fix.

## Alternatives considered

- **Parse `cursor-agent --help` and pick a spelling it lists.** Rejected: it makes the argv
  depend on the machine, spends a second process on a path that runs per critic round and
  per probe, and replaces a wrong declared fact with a derived one that is harder to review.
  It also buys compatibility only with a `cursor-agent` nobody has seen.
- **Accept both spellings (try `--model`, fall back to `-m`).** Rejected: an adapter carries
  one flag, and a fallback would have to observe a failure to trigger — which is exactly the
  signal this defect corrupted.
- **Fix the constant with no doc and no rule.** Rejected: the value was already a one-line
  constant and still stayed wrong through a release, because nothing said where the value is
  supposed to come from. The rule is the part that does not recur.
- **Edit `docs/specs/issue-358/design.md`**, which answers the owner's question with
  "`model_flag` is … `-m` for Cursor". Rejected: a locked spec is the record of what was
  decided and believed at the time, and that belief is now part of how this defect is
  explained. Current behaviour belongs in the capability doc, which is where a reader is
  pointed for what is true now.
