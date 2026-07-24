---
type: bugfix
phase: requirements-definition
workItem: issue-78
status: approved
approvedBy: ["@MadaraUchiha-314"]
severity: low
collaborators: [engineer]
overrides: {}
---

# Bugfix spec: `the-loop --version` reports stale hardcoded 0.1.0

> Phase 1 of 3 for a bug (bugfix → design → tasks).

## Summary

`the-loop --version` prints `the-loop 0.1.0` regardless of the installed package
version. The package installed via `uv tool install the-loopy-one` is 0.14.0, but the CLI
still reports 0.1.0 because the version string is hardcoded in `cli/the_loop/__init__.py`
(`__version__ = "0.1.0"`) rather than derived from package metadata. Tracked as
[issue #78](https://github.com/MadaraUchiha-314/the-loop/issues/78).

## Steps to reproduce

1. `uv tool install the-loopy-one` (installs the current release, e.g. 0.14.0).
2. Run `the-loop --version`.
3. Observe the output: `the-loop 0.1.0`.

## Expected vs actual

- **Expected:** `the-loop --version` reports the actually-installed package version
  (`the-loop 0.14.0`).
- **Actual:** it always prints `the-loop 0.1.0`.

## Root cause (confirmed)

`__version__` was a literal `"0.1.0"` in `cli/the_loop/__init__.py`. Commitizen owns the
canonical version in `.cz.toml` and rewrites every artifact listed in `version_files` on a
bump — but `cli/the_loop/__init__.py` is **not** one of those targets (only
`cli/pyproject.toml` and the plugin/marketplace manifests are). So the hardcoded
`__version__` was never touched by a release and silently froze at 0.1.0 while the
published `[project] version` advanced to 0.14.0. This is the same failure mode as
issue #46 (manifests frozen at 0.1.0), applied to the CLI's own `__version__`.

The webhook receiver carried the same latent hardcoded string
(`server_version = "the-loop-gh-webhook/0.1.0"` in `cli/the_loop/webhook/server.py`).

## Acceptance criteria (EARS)

1. WHEN `the-loop --version` runs against an installed package THEN the system SHALL report
   the installed distribution's version (derived from package metadata), not a hardcoded
   string.
2. `the_loop.__version__` SHALL equal `importlib.metadata.version("the-loopy-one")` for an
   installed package, and SHALL NOT be `"0.1.0"`.
3. WHEN the package is imported from an uninstalled source tree (no metadata) THEN
   `__version__` SHALL fall back to a clearly non-release sentinel rather than raising.
4. The webhook receiver's `Server` header SHALL carry the derived version rather than a
   second hardcoded `0.1.0`.

## Out of scope

- Adding `cli/the_loop/__init__.py` to `.cz.toml` `version_files`. Deriving from metadata
  removes the drifting duplicate entirely, so no new lockstep target is needed.
- Changing the release/bump machinery or the canonical version source.

## Security considerations

None. The change reads local package metadata (`importlib.metadata`) — no new input,
network, or trust boundary. The `Server` header already advertised a version string; it
now advertises the accurate one, which does not increase exposure.

## Open questions

None.
