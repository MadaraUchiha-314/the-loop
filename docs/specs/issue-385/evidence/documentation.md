---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#385"
---

<!-- Authored per the the-loop:writing skill. -->

# Documentation: the repository carries its own knowledge graph

> The `capability-docs` node's record: the capability docs and the user-facing docs this
> change makes wrong, updated in the same pull request.

## Capability docs

| Doc | What changed |
|---|---|
| [`docs/capabilities/knowledge-graph.md`](../../../capabilities/knowledge-graph.md) (new) | the capability: what is committed, the two jobs, the incremental rule, where the key lives, the cost table, the local refresh, the history row |
| [`docs/capabilities/capabilities.md`](../../../capabilities/capabilities.md) | one index row |
| `docs/.vitepress/config.mts` | one sidebar entry under Capabilities |

No existing capability doc describes CI workflows as a group; `release-publishing` is
about the release and is unchanged (its `bump:` commit and this work item's graph commit
share a token and an identity, and nothing about the release changed).

## Documentation

| Doc | What changed |
|---|---|
| [`docs/contributing.md`](../../../contributing.md) | a new **The knowledge graph** section: what `graphify-out/` is, that it is generated on `main` and never committed from a branch, `make graph` for the no-model refresh |
| [`README.md`](../../../../README.md) | one paragraph under *Working on the-loop* pointing at the graph, `graphify query` and `make graph` |
| [`docs/decisions/decision-133.md`](../../../decisions/decision-133.md) (new) + `decisions.md` | the durable record: headless in CI, the key on an environment, the asset on `main` through the script, the tracked set, the pinned model, the rehearsal — and the Claude Code-in-CI recipe (install, `claude -p`, `ANTHROPIC_API_KEY` / `CLAUDE_CODE_OAUTH_TOKEN`, `anthropics/claude-code-action@v1`) as the alternative the ticket literally asked about |
| `Makefile` | `graph` target and the `help` line |

**Not changed, and why:** the skill and its `reference/` docs describe the PDLC, which
this does not touch. No CLI command, config key or schema changed, so no `docs/cli/`,
`docs/config/` or schema page is affected — `test_docs_parity.py` covers that claim
mechanically. `docs/architecture/architecture.md` describes the-loop's own components;
the graph is a repository asset, not a component, and the capability doc is where it is
described.
