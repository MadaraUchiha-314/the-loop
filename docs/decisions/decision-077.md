# Decision 077: The published dashboard's origin is allowed to read the service by default

- **Status:** proposed
- **Date:** 2026-08-12
- **Deciders:** @MadaraUchiha-314 (owner), the-loop (engineer)
- **Work item:** [issue-211](https://github.com/MadaraUchiha-314/the-loop/issues/211)

## Context

[issue-207](https://github.com/MadaraUchiha-314/the-loop/issues/207) shipped the control-plane
dashboard as a static page on GitHub Pages, pointed at whichever machine runs
`the-loop service start`. Every call it makes is cross-origin, and the service sent no
`Access-Control-Allow-Origin` header at all — so the browser discarded each response
after it had already arrived. The page was unusable against a real service from the day
it was published, and both artifacts are ours.

The documented remedy was "run a gateway in front that adds the header". That asks an
operator to stand up an HTTP proxy in order to talk to a service already listening on
their own loopback interface — a cost with no security return, because the gateway in
[decision-059](decision-059.md) exists to terminate *auth* for an **exposed** deployment,
not to decorate a loopback one.

The ticket asked the question directly: make the allowed origins configurable, "and make
this one as a default in the config".

## Decision

**`service.cors.allowOrigins` is configuration, and it ships containing
`https://madarauchiha-314.github.io`** — the origin the-loop publishes its own dashboard
to. Four sibling keys (`allowMethods`, `allowHeaders`, `allowCredentials`,
`allowPrivateNetwork`) pass through to Starlette's `CORSMiddleware`, which FastAPI
already brings; nothing new is vendored.

Three boundaries the decision does **not** move:

1. **CORS is not a network setting.** `host`/`exposed` decide who may *connect*; this
   decides which page may *read* what came back. No value here widens the bind, and the
   exposure guard is untouched.
2. **Exact-string origins only.** No regex, no suffix match, no wildcard subdomains —
   the three ways an origin allowlist is usually subverted are not expressible.
3. **`"*"` with `allowCredentials: true` refuses to start**, before the bind and before
   the run lock. Browsers reject that pair anyway; a deployment that honoured it would
   hand every site on the internet an authenticated read of a service that spawns harness
   sessions.

`allowOrigins: []` is the opt-out, and it is the same switch the code branches on: with
an empty list no middleware is installed and the service behaves exactly as it did before
this work item.

## Consequences

**Easier.** The hosted dashboard works against a local service with nothing in between —
install the-loop, start the service, open the page. The posture is now *stated* rather
than emergent: an operator can read one block and know which pages may read their control
plane, instead of inferring it from the absence of a header.

**Harder — and this is the real cost.** An origin is host-granular, and
`madarauchiha-314.github.io` serves **every** GitHub Pages site under that account. A
script on any of them can, from a browser the operator has open, read and drive a
loopback service that has no in-app authentication. We cannot narrow that: the browser's
own model has no notion of "this path on this host". So it is written down — in the
schema description, in the config reference's warning block, in this record, and in the
capability doc — with `allowOrigins: []` named as the answer for anyone who does not use
the hosted page.

The exposure is also bounded in a way worth stating plainly: it applies only to a machine
where the service is *running*, only from a browser the operator has open, and only to
what the API already exposes to anything that can reach the port. It does not create
network reach, and it cannot.

## Alternatives considered

- **Default off; make the operator add the origin.** The safest default, and the one that
  leaves the published dashboard broken for everyone who has not read this page — which is
  where issue-207 already left it. Rejected as shipping a feature and its workaround at
  the same time. Anyone who wants this posture has one line.
- **Keep "put a gateway in front" as the only answer.** Rejected: it is a real deployment
  for an exposed service and pure overhead for a loopback one, and decision-059 never
  claimed the gateway's job included CORS for a page we publish ourselves.
- **Serve the dashboard from the service itself**, making it same-origin and the whole
  question moot. Genuinely attractive and genuinely a different product: the dashboard is
  deliberately a static artifact that any workstation points anywhere, and bundling it
  into the Python package puts a build step and a version skew between the two. Left open
  as a follow-up rather than decided here.
- **Allow an origin regex** (e.g. `^https://[a-z0-9-]+\.github\.io$`), so a fork's own
  Pages copy works untouched. Rejected: it widens the default from one account's sites to
  every GitHub Pages site in existence, for the convenience of a case that is one config
  line to fix by hand.
- **Wildcard `"*"` by default.** Rejected outright — that is every page on the internet.
