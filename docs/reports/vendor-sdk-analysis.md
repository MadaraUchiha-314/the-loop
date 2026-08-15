# Vendor SDKs vs. binaries: Claude, Cursor, GitHub

> Produced for [issue-212](https://github.com/MadaraUchiha-314/the-loop/issues/212), which
> asks: now that the-loop ships an SDK of its own, should it stop shelling out to `claude`,
> `cursor-agent` and `gh` and use the vendors' SDKs instead?
>
> **Conclusion: not in this work item, and not as one decision.** Each of the three is a
> different trade with a different risk profile, and one of them is much better value than
> the other two. Each is raised as its own ticket. The binary adapters ship unchanged.

## Where the-loop stands today

[decision-016](../decisions/decision-016.md) settled this once, in July: both harness
vendors' programmatic surface reachable from a dependency-light Python process is their CLI,
invoked as a subprocess. `the_loop.harness` is the seam — `HarnessAdapter` owns the argv, the
environment preparation and the JSON parsing, and its docstring already reserves the
possibility ("SDK-based implementations remain possible behind this same contract").
GitHub access is the same shape: `gh` as a subprocess, behind `GhClient`,
`reactions`, `announce`, `control` and the graph's GitHub integration.

Three properties of that arrangement are worth naming, because any replacement has to keep
them:

1. **One runtime dependency per capability, and it is not a Python package.** `the-loopy-one`
   has five runtime dependencies today; the harness and GitHub paths add none.
2. **The operator's own credentials, already configured.** `gh auth login` and the harness
   CLI's own login are what the-loop rides on. It mints no token, stores no secret, and every
   comment it writes carries the `<!-- the-loop:agent-comment -->` marker precisely because it
   is posting *as the operator*.
3. **Version skew is the operator's, not ours.** A `gh` that predates a field is handled by
   latching (`GhClient._no_link_field`); a harness that gains a flag needs no release of
   the-loop.

## Claude: the Agent SDK

**What it is.** `claude-agent-sdk` on PyPI (0.2.139 at the time of writing), Python ≥3.10 —
the same floor the-loop has. Runtime dependencies: `anyio`, `mcp` (which the-loop already
depends on), `sniffio`, and `typing-extensions` below 3.11. It offers a `query()` call and a
persistent client, with structured message streaming, hooks and permission callbacks.

**The fact that changes the argument.** The package bundles the Claude Code CLI ("no separate
installation required"), with an option to point at a separately installed one. So adopting
it does **not** remove a binary from the deployment — it moves the binary from "the operator
installs it" to "pip installs it", and it moves version control of that binary from the
operator to the-loop's dependency pin.

**What it would buy.** Structured, typed messages instead of parsing a JSON blob out of
stdout; a persistent conversation object instead of `--resume`; first-class permission and
hook callbacks; token accounting that does not need `usage_from_output`'s alias table. For
the critic-review path (`oneshot_argv`) that is a straightforward improvement. For the
*interactive* path it is not a substitute at all: the-loop hosts a **TUI in tmux** so a human
can attach and steer, and an SDK session is headless by construction.

**What it would cost.**

- Four new runtime dependencies for every install, including installs that never spawn a
  harness. The no-extras rule (PR #162) means everyone pays.
- A bundled CLI whose version the-loop now pins, on a package that moves fast.
- Two spawn paths to maintain — tmux-hosted TUI for interactive work, SDK for one-shot —
  where there is one adapter contract today.

**Verdict.** Worth doing **for the one-shot/critic path only**, behind the existing
`HarnessAdapter` contract, with the interactive path unchanged and the dependency question
answered explicitly. That is a spec chain of its own.

## Cursor: no SDK to adopt

`the_loop.harness.cursor_agent` records the position in its own docstring: the CLI is the
programmatic surface, and the adapter runs `cursor-agent -p … --output-format json` for
one-shot work and cannot host an interactive session at all
(`UnsupportedRunnerError`). Nothing in this analysis found an official Python SDK to replace
it with.

That makes the Cursor ticket a **watching brief plus a concrete gap**: re-check whether a
programmatic surface beyond the CLI exists, and — independently of any SDK — close the
asymmetry that Cursor sessions cannot be hosted interactively while Claude's can, which today
means `routing.defaultHarness: cursor` gets critic runs and nothing else. The second half is
useful whether or not an SDK ever appears.

## GitHub: PyGithub

**What it is.** PyGithub 2.9.1, Python ≥3.9. Runtime dependencies: `requests`, `pynacl`,
`pyjwt[crypto]`, `urllib3`, `typing-extensions` — five, none of which the-loop has, and two of
which (`pynacl`, `pyjwt[crypto]`) pull cryptography.

**What it would buy.** Typed objects instead of parsed JSON; real pagination instead of
`gh`'s flags; App/JWT authentication, which `gh` does not do; and no per-call process spawn —
the poller currently forks `gh` on every cycle.

**What it would cost, and this is the decisive one.** **Credentials.** Today the-loop needs no
token of its own: `gh` is already authenticated as the operator. PyGithub needs a token in the
process, which means the-loop acquires a secret to source, scope, store, rotate and redact —
a materially larger security surface, and one that reaches straight into
[`reference/security.md`](../operating-model/reference/security)'s fail-closed rules and the
paper-trail identity story. `gh auth token` can bridge it, but a bridge that shells out to
`gh` to feed a library that exists to avoid shelling out to `gh` is not the win it looks like.
The graph's GitHub integration already does exactly this in one place, which is the honest
precedent to reason from.

**Verdict.** The most valuable of the three *technically* and the most expensive *in policy*.
Worth a ticket that answers the credential question first — where the token comes from, what
scopes it needs, how it is redacted, and whether `gh` remains the default — and treats the
library swap as the consequence rather than the goal.

## Summary

| | Claude Agent SDK | Cursor | PyGithub |
|---|---|---|---|
| Official Python SDK exists | yes | no | yes (community-maintained, mature) |
| New runtime dependencies | 3–4 | — | 5 |
| Removes a binary from the image | **no** (bundles the CLI) | — | yes |
| Replaces the interactive (tmux TUI) path | no | no | n/a |
| Introduces a credential the-loop must hold | no | no | **yes** |
| Recommendation | adopt for one-shot/critic runs only | watching brief + close the interactive gap | answer the credential question first |

The common thread: `HarnessAdapter` and `GhClient` are already the seams, and every option
above lands behind them. Nothing in this analysis argues for changing the seam — which is why
none of it belongs in issue-212, whose subject is a different seam entirely.

## Tickets raised

- [#232](https://github.com/MadaraUchiha-314/the-loop/issues/232) — Claude Agent SDK for the
  one-shot/critic path.
- [#233](https://github.com/MadaraUchiha-314/the-loop/issues/233) — Cursor: programmatic
  surface re-check and the interactive-hosting gap.
- [#234](https://github.com/MadaraUchiha-314/the-loop/issues/234) — PyGithub, and the
  credential question it forces.
