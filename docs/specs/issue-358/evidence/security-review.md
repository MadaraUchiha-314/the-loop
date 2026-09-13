# Security review: issue-358

Mechanism: the-loop's own checklist (`reference/security.md`), run against
[`requirements.md`](../requirements.md) § Security considerations and
[`design.md`](../design.md) § Security design.

**Risk tier 4** — the change touches `**/*schema*` and assembles the argv of an unattended
agent from an authorized human's reply. A named human sign-off is required and is the owner's
approval of PR #359.

## The one new trust boundary

Comment text → an argv. It is **designed out rather than mitigated**: a reply yields a token
that is a key into the operator's declared list, and the argv is built from
`cli-config.yaml` plus the harness adapter's own flag. There is no data path from a comment to
a command line, so command injection here is absent rather than defended against.

Two guards hold that up, and both are tested:

1. **The token grammar.** `_CHECK_LINE` admits no whitespace, quote or metacharacter, and a
   model name additionally matches `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`. That grammar is what
   makes it safe to pass a provider's own spelling verbatim into an argv.
2. **The lookup.** What survives the grammar is matched against what the operator declared
   *now*. Anything else is no choice.

## Abuse cases → mechanism → negative test

| Case | Mechanism | Test | Result |
|---|---|---|---|
| A1 an unauthorized user ticks and executes | `_authorized_comments`, upstream of any parse | `test_abuse_an_unauthorized_reply_freezes_nothing` | closed |
| A2 a reply naming a flag, a path, a metacharacter | token grammar + lookup into the declared set | `test_abuse_a_reply_naming_a_flag_or_a_path_resolves_to_nothing`, `test_abuse_a_shell_fragment_after_a_real_name_is_not_smuggled_through` | closed |
| A3 a declared entry widens permissions | applied as declared, and only from the declaration | `test_abuse_the_argv_contains_only_what_config_and_the_adapter_produced` | closed |
| A4 a hand-edited portable record | re-validated on read, three ways: declared set, operator narrowing, availability | `test_abuse_a_forged_frozen_choice_is_ignored`, `test_abuse_a_declaration_withdrawn_stops_reaching_the_argv`, `test_abuse_a_model_narrowed_to_another_harness_cannot_be_forced_onto_this_one` | closed |
| A5 a label named after a model | no label is read anywhere in this path | `test_abuse_a_label_named_after_a_model_selects_nothing` | closed |
| A6 the checklist cannot be read | the existing empty-body path resolves to no choice | `test_abuse_an_unreadable_checklist_keeps_the_operators_arguments` | closed |
| A7 a forged availability verdict | the cache may withhold, never introduce | `test_abuse_a_forged_verdict_cannot_introduce_a_choice` | closed |

**One finding, found by writing these tests rather than by the design.** A4's third form:
`harnesses:` on a model is the operator's narrowing, and it was enforced only where the
checklist is rendered. A frozen record is a state file an agent can write, so a hand-edited one
could have put a cursor-only model onto claude. Now enforced where the argv is built as well —
the gate decides what may be *picked*, resolution decides what may be *run*, and both consult
the same declaration.

## The new egress

`modelprobe` is the one component that starts a process and reaches a vendor. Bounded:

- it sends a **fixed the-loop constant** as its prompt (`PROBE_PROMPT`) and the resolved
  arguments — never any text from a work item, a comment or a repository;
- it runs **off the delivery path** — `models check`, daemon start, and one stale-verdict
  re-probe;
- it inherits the daemon's environment exactly as a critic run does, adding no variable;
- its cache lives in the **machine-local** state tree, so it is not agent-writable and never
  travels in a repository.

It does spend tokens. That is stated in the command's own documentation and in the design's
cost section, because an operator should not discover it from a bill.

## Fail-closed audit

Every ambiguity resolves to **the operator's stated configuration** — not to the narrowest or
cheapest model, which would be a different and wrong reading of "closed": it would let a
malformed reply silently downgrade a tier-5 work item.

| Situation | Resolves to |
|---|---|
| no tick, several ticks, an unknown token | no choice |
| an unreadable checklist comment | no choice |
| an unreadable or absent frozen record | the harness's own arguments |
| a model no longer declared, or narrowed away from this harness | the harness's own arguments |
| a `refused` verdict | the harness's own arguments, **plus one comment saying so** |
| an unreadable verdict cache | offerable — a cache fault must not withhold a declared capability |
| a harness with no model flag | no model section offered at all |

## Least privilege

A choice contributes only the arguments its declaration carries. the-loop adds no permission
flag of its own, and there is deliberately **no operator-written `args` on a model** — a harness
that cannot be handed a model is offered no model section rather than given a hand-written flag
nothing validates.

## Secrets

None involved. This work item reads and writes no secret, token or environment variable. A
model name is not a credential.

## Outcome

**Pass**, with the one finding above fixed in the same PR. Human sign-off: pending the owner's
approval of [PR #359](https://github.com/MadaraUchiha-314/the-loop/pull/359).
