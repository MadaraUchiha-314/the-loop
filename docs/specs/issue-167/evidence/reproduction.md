# Evidence: the defect, reproduced and gone (issue-167)

## The ticket's script, and why its output alone is not the proof

The reproduction script on the issue looks for a node that declares `sections:` and no
`produces:`. It was written before `validates:` existed, so **it still prints all six
nodes after the fix** — it is asking about the old vocabulary, not about the behaviour:

```console
$ uv run --directory cli python - <<'PY'   # the ticket's script, verbatim, AFTER the fix
self-review required= False gates on ['Review cycles'] -> skips
critic-review required= False gates on ['Review cycles'] -> skips
security-review required= True gates on ['Security review (gate)'] -> skips
evidence required= False gates on ['Final validation evidence'] -> skips
capability-docs required= False gates on ['Capability docs'] -> skips
reviewer-briefing required= False gates on ['Pull requests'] -> skips
```

Stated plainly rather than quietly replaced: the script's `-> skips` conclusion is now
wrong, because the six nodes resolve their artifact through `validates:` instead. The two
checks below are the ones that answer the question the script was standing in for.

## 1. The corrected structural check — is any gate inert?

The same question, asked of the vocabulary as it now stands: a `validate-artifacts` entry
that declares a content check and resolves neither `produces` nor `validates`. This is
the assertion `test_p5a_every_content_gate_resolves_an_artifact_to_read` runs in CI.

```console
$ uv run --directory cli python - <<'PY'
… for spec in n.exit:
…     w = spec.get("with") or {}
…     if any(w.get(c) for c in ("locked","frontMatter","sections","checkmarks")) \
…        and not n.produces and not w.get("validates"):
…         inert.append(n.id)
PY
(nothing — every content gate resolves an artifact)
```

Against the pre-fix graph the same script prints all six node ids.

## 2. The behavioural check — what the chain actually returns

The definitive one: drive each node's real exit chain, from the shipped graph, against a
work item whose spec folder has no execution log. Before this change every line read
`skip` and the chain passed straight through. After it:

```console
$ uv run --directory cli python -  # Runtime.evaluate over the shipped graph, empty spec dir
self-review          -> block  required artifact is missing (docs/specs/issue-1/execution-log.md)
critic-review        -> block  required artifact is missing (docs/specs/issue-1/execution-log.md)
security-review      -> block  required artifact is missing (docs/specs/issue-1/execution-log.md)
evidence             -> block  required artifact is missing (docs/specs/issue-1/execution-log.md)
capability-docs      -> block  required artifact is missing (docs/specs/issue-1/execution-log.md)
reviewer-briefing    -> block  required artifact is missing (docs/specs/issue-1/execution-log.md)
```

`security-review` — `required: true`, annotated "never skippable, at any risk tier" — is
no longer skippable. The same six nodes pass once each section carries a record, which is
what `test_graph_review_chain_integration.py` pins in both directions.
