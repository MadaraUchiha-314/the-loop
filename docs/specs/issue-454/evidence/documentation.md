---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#454"
---

# Documentation: the CLI suite reads the machine it runs on

> The ready-to-ship gate's documentation item: the affected capability docs and
> user-facing docs are updated in the same pull request as the change.

## Capability docs

**[`docs/capabilities/testing-and-contracts.md`](../../../capabilities/testing-and-contracts.md)**
owns the suite's hermeticity rules. issue-412 added "a test reads no ambient machine
state" there, and issue-422 added "the suite never writes into `.the-loop/`".

- A new requirement section, *A test controls the executables, paths and process metadata
  it asserts on (issue-454)*. It covers: executable lookups fixed by the test; canonical
  path containment with the escape check kept; `getsid`/`getpgid` and never `ps sess`; a
  preflight-only binary from an explicit fixture with a tripwire; and `make test` passing
  with or without tmux and harness CLIs.
- A history row for issue-454, above issue-422.

The index line in `capabilities.md` still describes the capability correctly, so it is
unchanged.

## Documentation

None changed, for these reasons:

- **`README.md`** states no host requirement for running the tests that this change
  makes wrong.
- **The documentation site and the skill's `reference/` docs** describe the loop's
  process. They do not describe this repository's own test suite.
- **`CONTRIBUTING`-style guidance** lives in the `Makefile` comments and the capability doc
  above. The `make test` command did not change; it now also passes on the hosts the
  ticket names.
