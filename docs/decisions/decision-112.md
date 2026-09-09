# Decision 112: the dashboard's presentational layer is rebuilt on the prototype's own utility layer, over unchanged connectors, and ships nothing the service cannot back

- **Status:** proposed
- **Date:** 2026-09-09
- **Work item:** [issue-327](https://github.com/MadaraUchiha-314/the-loop/issues/327)
- **Deciders:** MadaraUchiha-314 (the prototype and the directive), the-loop (design); MadaraUchiha-314 (owner, at the PR)
- **Refines:** the issue-298 rule that a UI overhaul is presentation-only over untouched connectors

## Context

The owner replaced the dashboard's design with a prototype built in Lovable: React 19,
Tailwind v4, lucide icons, tokens in oklch, a `.dark` class for the theme. The
instruction was to remove the presentational components and replace them with it,
inventing nothing. Three questions had to be settled: **how** the design system is
expressed in this repository, **which** of the prototype's controls ship when the
service backs none of the ones it fakes, and **how** the theme is chosen and kept.

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **Tailwind v4 is added to the dashboard's build** (`tailwindcss`, `@tailwindcss/vite`), with the prototype's tokens declared in `@theme`; the JSX carries the prototype's utility classes. | The prototype *is* a Tailwind build. Reproducing it in hand-written CSS would mean re-deriving every spacing and colour and then arguing equivalence; copying its classes lets a reviewer diff the implementation against the prototype's rendered DOM. Build-time only: the browser receives generated CSS, no library. The minimalism ladder allows a dependency when the alternative is a large hand-maintained layer that exists to imitate that dependency's output. |
| D2 | **Icons are inline SVG paths**, one file, not `lucide-react`. | About twenty-five icons. Inline sits above a new dependency on the ladder, and the file is smaller than the package's type definitions. |
| D3 | **Controls with no backing route are not rendered**: New work item, Checks, cleanup, `/` commands. **Controls the loaded data backs are rendered and do exactly that**: search filters the rows already on screen; copy writes a ref or a tmux command to the clipboard. | A button that does nothing teaches the operator that the dashboard lies. Filtering and copying invent no capability — they act on what the connectors already deliver — and the prototype draws both. The line is *does the service back it*, not *is it small*. |
| D4 | **Two themes, browser preference as the default, choice persisted beside the base URL**, applied before first paint by a four-line inline script. | The prototype's toggle is two-state and unpersisted, and its first paint is the wrong theme. Persisting in the existing settings store is what every other per-browser choice does; the pre-paint script is the only way to avoid a flash on a static page. A third "system" state is a control nobody asked for — following the preference until the operator chooses is the same outcome with one fewer control. |
| D5 | **Fonts from Google Fonts**, as the current stylesheet already does. | Self-hosting three families adds three packages and roughly 400 KB to a bundle whose usual origin is loopback. The fallback stacks keep the page readable offline. |

## Consequences

**Good.** The implementation is checkable against the prototype element by element; the
theme survives a reload; the operator sees no control that cannot act; connectors, join
and tests of behaviour are untouched, so the regression surface is the markup alone.

**Costs, accepted.** One build dependency the Pages workflow now resolves (`bun install
--frozen-lockfile` already pins it); utility classes in JSX are longer to read than
semantic class names, which is the price of a diffable contract; the inline theme script
is a small piece of code outside React that has to be reviewed once.

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| Hand-written CSS on the tokens, as issue-298 did | Would restate a Tailwind build by hand, with no way to check equivalence except by eye |
| Vendor the prototype's compiled CSS | A purged build; every class the prototype did not use is absent, and it is unreadable as a source |
| `lucide-react` | A runtime dependency for twenty-five paths |
| Render New work item disabled with a tooltip | The service has no create route to promise; a disabled control is still a lie about the roadmap |
| Three-state theme control | An extra control for an outcome the default already gives |
| `@fontsource` packages | Bundle size for a loopback dashboard; the current app already loads from Google Fonts |
