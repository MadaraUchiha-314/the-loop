# `the-loop ui`

Serve or build the **control-plane UI** — the statically-hostable frontend under
`ui/` (issue-161). All frontend code is TypeScript; the toolchain is Vite, scoped
entirely to `ui/` (the Python package's dependency footprint is unchanged).

Both verbs delegate to the frontend's own scripts — `npm --prefix ui run <verb>` as
an argv list, never a shell — and report a clear error when `npm` is not on `PATH`
or the current directory has no `ui/` (run them from a the-loop checkout).

## `ui dev`

Runs the Vite dev server against a local API service. Start the service first
(`the-loop service start`); the dev origin (`http://localhost:5173`) is allowed by
the service's CORS defaults ([`service.ui.origins`](/config/cli/service-options#ui-origins)).
The service carries no in-app auth, so there is nothing to enter — the UI just talks
to the configured API base.

## `ui build`

Builds the static bundle (`ui/dist/`) — plain assets, hostable anywhere (GitHub
Pages included). The API base URL is configurable at build time (`VITE_API_BASE`)
and overridable at runtime (`?api=` query parameter, remembered in localStorage), so
one bundle serves any deployment. A UI hosted publicly reaches the data plane only
where the service is actually exposed
([`service.exposed`](/config/cli/service-options#exposed)) and its gateway routes to
it; against a loopback-only service it simply shows nothing.
