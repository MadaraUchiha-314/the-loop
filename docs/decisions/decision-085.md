# Decision 085: ship the SDK as a router + lifespan seam, not a second application

- **Status:** proposed
- **Date:** 2026-08-15
- **Work item:** [issue-212](https://github.com/MadaraUchiha-314/the-loop/issues/212)
- **Deciders:** maintainer (via ticket); harness (proposal)

## Context

the-loop's control plane is reachable one way: `the-loop start`, a whole process, its own
port. The ticket asks for the deployment that is not that — a team with an existing Python
service that wants the-loop **inside** it: their FastAPI app, their auth middleware, their
transaction-id logging, one process.

The capability is already there and already correctly layered (decision-058: one
transport-free `core`, transports on top). What is missing is a supported seam. Today an
embedder can only call `create_app()` and get an *application* — its own title, its own
`/api/docs`, its own lifespan, `/mcp` mounted at its root — or mount that application as a
sub-app, where Starlette runs no lifespan so the MCP session manager never starts, or reach
into `the_loop.core` directly, which is undocumented and unversioned.

## Decision

1. **`the_loop.sdk` is the public surface; everything else stays internal.** `TheLoop`, its
   eight capability namespaces, its HTTP-seam methods and the environment contract change
   under semantic versioning. `the_loop.core`, `the_loop.api` and the rest may change in
   any release.
2. **The `/api/v1` surface becomes one `APIRouter`** (`api/routes.py`) with two consumers:
   `create_app` and the SDK. A parity test asserts router == served app == authored OpenAPI
   contract, so the embedded and standalone surfaces cannot drift — they are the same
   object.
3. **Per-request behaviour rides on the router's route class, not on an application.** The
   config refresh (issue-222), the `ValueError`/`LookupError`/`SpliceError` translation and
   the `api.request` audit event move off middleware and app-level handlers, because a
   route class is the only extension point that travels with `include_router` into an
   application the-loop does not own. `create_app` loses its middleware and its three
   handlers and behaves identically.
4. **The SDK touches a host application in at most two ways:** `include_router` and — unless
   `lifespan=False` — its lifespan. No middleware, no exception handlers, no CORS. CORS in
   particular is refused on principle: `service.cors` is an application-wide policy, and
   applying one the-loop config key to every route of somebody else's app is not a library's
   decision.
5. **`mount()` wraps the host lifespan by default.** Not composing it is silent at import,
   silent at startup, and surfaces as a session-manager error on the first MCP call, from a
   client, in production. The host's lifespan still runs, inside the-loop's; `lifespan=False`
   hands composition back, and an MCP request arriving with the lifespan not running is
   answered `503` naming the omission.
6. **The MCP app mounts at the prefix, and the prefix may not be empty.** Mounting at the
   prefix (after the router) is what makes `<prefix>/mcp` answer with no trailing-slash
   redirect — the same arrangement `create_app` uses at the root, for the same reason. At the
   root inside a host app it would shadow every route declared after the mount, so that
   combination is refused rather than produced. `mcp_allowed_hosts` lets an embedded
   deployment declare its real hostnames; the default derivation describes the standalone
   service's bind.
7. **Authorization stays the deployment's** (decision-059 unchanged). The SDK's obligation is
   to make attaching it a parameter: `dependencies=` on `router()`/`mount()`, applied to
   every operation before any handler executes, documented at the top of the embedding page
   rather than in an appendix. No in-app auth layer is added — a second, weaker one would be
   worse than none.
8. **Construction reads the CLI config strictly.** `TheLoop(config_path=…)` is the ticket's
   shape; a missing or unparseable file raises rather than degrading to `{}`. The CLI's
   leniency is right for a short-lived command and wrong for a long-lived service, where an
   empty `routing.authorizedUsers` fails closed *invisibly* and looks like a healthy start.
9. **Lifecycle writes are not on the SDK.** `status()` reads; `start`/`stop`/`restart` manage
   the-loop's own processes, and `--with-upgrade` reaches the installer. The REST router
   still carries `POST /api/v1/restart` and the daemon controls — dropping them would break
   §2 — and the docs name both as operations whose meaning changes when embedded.
10. **The environment contract is a table in code** (`sdk/environment.py`): per binary, the
    config key that renames it, the capability it serves, and the predicate deciding whether
    *this* configuration needs it. `check_environment()` resolves with `shutil.which` and
    never executes what it finds; it is a report, never a gate. A parity test binds the table
    to `docs/sdk/environment.md` in both directions.
11. **No new runtime dependency**, and the no-extras rule (PR #162) holds: one
    `pip install the-loopy-one` yields the SDK.
12. **The vendor SDKs stay out of this work item.** The Claude Agent SDK, Cursor's
    programmatic surface and PyGithub are analysed in
    [`docs/reports/vendor-sdk-analysis.md`](../reports/vendor-sdk-analysis.md) and raised as
    their own tickets. decision-016's reasoning still holds for what ships today, and
    swapping a harness adapter is a behaviour change that deserves its own spec chain rather
    than a rider on a packaging work item.

## Consequences

- Additive to the package: nothing is removed, renamed or moved in the CLI config, the CLI
  surface, the on-disk state or `create_app`'s signature. No migration.
- A second public contract now exists, and it is versioned. A rename in `core` is free; a
  rename on `the_loop.sdk` is a breaking change.
- **The security boundary moves for embedded deployments.** The exposure guard and the CORS
  allowlist are the standalone service's; an embedder who mounts on a public app with no
  dependency has published a session-spawning API. That residual risk is closed by
  documentation and by `dependencies=` being a first-class argument, not by a guard the SDK
  could enforce on somebody else's application.
- `create_app` no longer has middleware or app-level exception handlers. Anything that
  depended on those objects (nothing does today) would need the route class instead.

Spec: [docs/specs/issue-212/](../specs/issue-212/requirements.md)
