<!-- Written per the `the-loop:writing` skill. -->

# Decision 148: the control plane's Work surface is de-cluttered to Option C — Minimal

- **Status:** accepted (the owner named the option on the design PR, 2026-10-20)
- **Date:** 2026-10-20
- **Deciders:** MadaraUchiha-314 (the pick), the-loop (the three options)
- **Work item:** [issue-511](https://github.com/MadaraUchiha-314/the-loop/issues/511)
- **Spec:** [`docs/specs/issue-511/design.md`](../specs/issue-511/design.md) § Element inventory, § UI/UX design
- **Refines:** [decision-112](decision-112.md) (the issue-327 Control Plane UI 3.0 layout and design system — the tokens, type and primitives are kept verbatim)

## Context

The issue-327 dashboard drew one fact several times: with a work item selected, the
current node up to five times, the repository four, the tmux target three, the age
three. The owner asked for less information and a better information architecture
without a redesign, and for three candidate levels to choose from. The requirements
fixed a floor every level meets (each fact once, the sidebar row as identity and urgency
only, no bookkeeping counts, one statement of the loop's position) and a ladder of what
each level removes beyond it. The design phase built the three as self-contained
prototypes from one template, so they are strictly nested, and showed them beside the
current screen in both themes.

## Decision

**Option C — Minimal** is built. Beyond the floor, and beyond Option B's one-line sidebar
rows, selected-item-only PR rows, header meta of phase chip and age, and session facts
behind closed disclosures, it:

- removes the session panel as a standing column — the pause / resume / stop / start
  verbs become header actions, and the Harness, tmux and Ticket facts sit in one
  **Session details** disclosure in the header, closed by default;
- folds the graph strip into the header's meta line — the phase chip is the one
  statement of the position, the parked / blocked note its qualifier, and **Full graph**
  reveals the node row beneath the header;
- renders the session tab bar only when the item has more than one session;
- takes the Standing group out of the sidebar (the Standing surface keeps it);
- puts search and the instance filter behind one icon in the sidebar's brand row;
- reduces the sidebar to two groups, **Needs you** and **Everything else**, the latter
  sorted by last activity.

Options A and B stay checked in under `docs/specs/issue-511/design/` as the record of
what was offered; nothing of them is built.

## Consequences

- The Work surface goes from three columns and five main-column bands to two columns and
  three bands (a fourth while *Full graph* is on). The inventory's default-drawn element
  count goes from 56 to 27.
- Every fact the panel showed stays reachable within one interaction, from the header.
  The transcript path, the working directory and the session id are abbreviated with a
  copy control inside the disclosure; nobody reads a 150-character path on a dashboard.
- A one-line sidebar row truncates long titles beside a flag; the header carries the
  full title and the row's accessible name carries it for screen readers.
- The header carries more: two mono verbs and five icon controls. That is the cost of
  removing the column, shown in the prototype before the pick.
- The Standing, Settings and Instances panes inherit the header's changes and nothing
  else. `api/`, `state/` and `demo/` are untouched; no route, request, setting or
  dependency is added.

## Alternatives considered

- **Option A — Trim.** The floor only: duplicates and bookkeeping gone, every column,
  band and section kept. Rejected by the owner as not far enough.
- **Option B — Focus.** A plus one-line rows, nested PR rows under the selected item
  only, a header meta of phase chip and age, and a session panel reduced to its controls
  with the facts behind disclosures. Rejected by the owner in favour of removing the
  column.
- **A runtime density setting.** Would keep all three levels switchable. Rejected: the
  ticket asked for a pick, and a setting is a new control the requirements forbid (R5.5).
