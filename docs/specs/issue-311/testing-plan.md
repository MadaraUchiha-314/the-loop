---
type: testing-plan
phase: test-planning
workItem: "issue-311"
status: locked
approvedBy: []
overrides: {}
---

# Testing plan: every link and every `gh` call names the GitHub it is on

> Derived from the locked `bugfix.md` and `design.md`, **before** `tasks.md`.
> Authored at `test-planning`, completed at `verification`.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit — the resolver | yes | the five tiers in order; an invalid candidate at any tier is skipped with a warning and the walk continues; `api_base_for`, `host_of_api_base`, `host_from_remote` over every remote shape; the remote is read only with a `repo_root` | `uv run pytest cli/tests/test_ghhost.py` |
| T2 | Unit — minting | yes | `ref_for`/`derive_ref` with a host write `github:host/o/r#n`, write nothing for `github.com`, refuse an invalid host, and keep every existing refusal | `uv run pytest cli/tests/test_graph_refs.py` |
| T3 | Unit — the `gh` spellings | yes | `gh_host_args` for a hosted and a default ref; `comment_argv`, `issue_argv` and `create_issue` (a `host/o/r` kickoff slug → `--hostname` + hosted ref); `reactions._argv`/`target_from_event`; `existence_argv` unchanged | `uv run pytest cli/tests/test_comments.py cli/tests/test_reactions.py cli/tests/test_linkage.py` |
| T4 | Unit — the poller | yes | `RepoSpec.parse("ghe.corp/o/r")`, `gh_repo`, `full_name` unchanged; every `GhClient` argv carries `--repo ghe.corp/o/r` or `--hostname`; `owns` compares hosts; `closure` asks the ref's host | `uv run pytest cli/tests/test_poller.py` |
| T5 | Unit — the graph integrations | yes | `_ref_parts` on a hosted ref; `GitHubCli` argv for every operation; `GitHubApi` base derivation (default → `https://host/api/v3`; explicit stays); `_linked_pull_refs` carries the host | `uv run pytest cli/tests/test_graph_integrations.py` |
| T6 | Unit — the review brief | yes | a GHE pull URL freezes as a hosted ref; slugs and bare numbers take the work item's host; `_state_pulls` carries it; the github.com brief freezes the same strings as today | `uv run pytest cli/tests/test_graph_review.py` |
| T7 | Integration — the ticket's symptom | yes | a CLI config naming `integrations.github.host` → `build_runtime` → the derived ref, its URL and the `notify` event's link all name the host; the same with `GH_HOST` and with a remote; and a config saying nothing yields the github.com ref byte-for-byte | `uv run pytest cli/tests/test_ghhost_integration.py` |
| T8 | Config / schema / docs | yes | both schema copies accept `integrations.github.host` (parity test), the template and this repo's config validate, the docs↔schema parity test sees the new option documented | `uv run pytest cli/tests/test_config_schema_parity.py cli/tests/test_configschema.py cli/tests/test_docs_parity.py`; `make validate` |
| T9 | Security / abuse case | yes | A1 (every invalid host shape refused at every entry point), A4 (the remote is last and only with a root), A5 (github.com strings unchanged) | T1, T2, T3, T4, T7 |
| T10 | Lint / typecheck / tests | yes | the commands CI runs | `make check` |
| T11 | Contract (OpenAPI) | n/a — no route, request or response shape changes | | |
| T12 | UI / visual | n/a — no dashboard surface changes | | |
| T13 | Performance | n/a — one `git config` read per graph command, only in-session | | |
| T14 | Manual | n/a — no GHE instance is available to this session; the argv and URL assertions are the proof, and `gh`'s `--hostname`/`--repo HOST/OWNER/REPO` grammar is its documented one | | |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.2, R6.1, A1, A4 | precedence, skipping, logging, the remote gated on a root |
| T2 | R2.1–R2.3 | hosted, default and invalid hosts through both minting functions |
| T3 | R4.1, R4.2, R4.4, R4.5 | one helper, every writer |
| T4 | R4.1, R4.2, R5.1–R5.3 | enterprise poll source end to end at the argv |
| T5 | R4.1–R4.4 | both transports |
| T6 | R3.1–R3.3 | the brief |
| T7 | R2.1, R1.1, A5 | the symptom, fixed, and github.com unchanged |
| T8 | R1.3, R1.4 | the key exists, validates, is documented, needs no migration |

## Verification results

Recorded at `verification` in [`evidence/verification.md`](evidence/verification.md):
every applicable row (T1–T10) **pass**; `make check` clean — ruff, format, pyright,
config validation, markdownlint, 2925 tests passed / 1 skipped.
