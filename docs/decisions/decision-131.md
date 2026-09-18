<!-- Authored per the the-loop:writing skill. -->

# Decision 131: a work item is armed by a set of labels, every one of which must be present; the single label is migrated, not aliased

- **Status:** proposed
- **Date:** 2026-09-18
- **Deciders:** the-loop (architect, engineer), asked for by @MadaraUchiha-314
- **Work item:** [issue-381](https://github.com/MadaraUchiha-314/the-loop/issues/381)
- **Builds on:** [decision-040](decision-040.md) (the label arms; an authorized command
  starts), [decision-110](decision-110.md) (an instance is a named, scoped config) and
  the migration doctrine of `cli/the_loop/migrations.py` (issue-109 onward).

## Context

[Issue #381](https://github.com/MadaraUchiha-314/the-loop/issues/381): several people
run the-loop against one repository, every install ships `autoExecuteLabel:
"the-loop: auto-execute"`, and so every instance arms every labelled item. The instance
scope of issue-322 decides *which instance takes a work item that already names one*; it
does not decide *which items an instance looks at*. Renaming the one label per operator
would, but it breaks the convention `/the-loop:work-on` and the Slack kickoff apply.

Two questions had more than one defensible answer.

## Decision

**1. The gate is a list, and every entry must be present.** `routing.autoExecuteLabels`
(default `["the-loop: auto-execute"]`) replaces the string; an item is armed only when it
carries all of them, on both ingresses. An operator keeps the shared label and adds one
of their own, and adding a label can only *narrow* what an instance arms. The poll source
mirrors it (`labels`, empty = reuse the routing list), passes one `--label` per entry to
`gh`, and re-checks the returned label set before tracking, so the two ingresses agree
whatever a CLI's filter returns. An empty list arms nothing: `all([])` is the one answer
the predicate must never give.

**2. The old keys are refused and migrated, not read as a one-entry list.** Reading
`autoExecuteLabel: x` as `[x]` is lossless, and the migration does exactly that — but
the *runtime* refuses the old key, because the doctrine is "version the schema, don't
sniff for keys" and because an operator whose custom label were ever read under the wrong
key would fall back to the shared default, which arms *more* than they set. Config
version `0.9.0` → `0.10.0`; `the-loop migrate-config` wraps the string, drops an empty
source label, keeps a list already declared beside the old key, and flags an empty routing
label (`[]`, which the schema refuses) for the operator to decide.

## Consequences

- An operator who never set the key sees no change: a one-entry list arms what the string
  did.
- Every operator with a config pays one `the-loop migrate-config`, as for every breaking
  change since issue-109.
- The agent's own commands apply the whole list when they arm an issue or a pull request,
  and a Slack kickoff's `labels` must name every entry to arm what it files.
- A self-diagnosed issue's label must be none of the list, as it had to differ from the
  one label.
- An item already carrying the shared label is not armed for an instance that added a
  second one until that label is applied by hand — the point of the change.

## Alternatives considered

- **Any-of semantics** — the ticket asks for all-of, and any-of would let the shared
  label alone arm everything again. Rejected.
- **Deriving a per-instance label from `instance.name`** — couples two declarations and
  arms nothing for an unnamed instance; the operator can write the same label in one
  line. Rejected.
- **Reading the old key as a one-entry list with a warning** — a warning nobody reads is
  how a config comes to lie about what it arms; the migration doctrine refuses removed
  keys, and this one is no exception. Rejected.
- **A per-label policy (required / optional)** — nobody has asked for it, and it is a
  branch nobody would test. Deferred.
