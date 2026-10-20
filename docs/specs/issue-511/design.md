---
type: design
phase: design
workItem: "github:MadaraUchiha-314/the-loop#511"
status: draft
approvedBy: []
overrides: {}
---

<!-- Written per the `the-loop:writing` skill. -->

# Design: de-cluttering the control plane UI — three levels, one pick

> Phase 2 of 3 (requirements → design → tasks). Derives from the approved
> [requirements](requirements.md). Reviewed with [`testing-plan.md`](testing-plan.md)
> at the `design-approval` gate, where the owner **names the option** to build.

## Overview

Three prototypes, strictly nested, generated from one template so they cannot drift:
**Option A — Trim** removes the duplicates and the bookkeeping and keeps every column,
band and section; **Option B — Focus** also collapses the sidebar rows to one line and
folds the session panel's facts behind disclosures; **Option C — Minimal** also drops the
session panel as a column, folds the graph strip into the header, and reduces the sidebar
to two groups. The owner opens the three files under [`design/`](design/) (or the
screenshots beside them), and names one at the gate. Nothing is added: every change is a
removal, a relocation behind an existing idiom (`<details>`, a copy control, a popover),
or a condensation drawn with the existing primitives.

| | Today | A — Trim | B — Focus | C — Minimal |
|---|---|---|---|---|
| Inventory elements drawn by default on the Work surface (#214 selected, a worker, both panels open, nothing expanded) | 56 | 42 | 31 | 27 |
| Times the current node is written as a statement | up to 5 | 1 | 1 | 1 |
| Times the tmux target is written | 3 | 1 | 1 (behind a disclosure) | 1 (behind a disclosure) |
| Times the repository is written | 4 | 1 | 1 | 1 |
| Columns · bands in the main column | 3 · 5 | 3 · 5 | 3 · 5 | 2 · 3 (+1 on *Full graph*) |

The counts are the inventory's tallies (§ Element inventory); the implementation
briefing restates them from the built app (R7.2).

![Today](design/screenshots/current-01-item-dark.png)
![Option A](design/screenshots/a-01-item-dark.png)
![Option B](design/screenshots/b-01-item-dark.png)
![Option C](design/screenshots/c-01-item-dark.png)

## Architecture

The Work surface keeps its shape — sidebar, main column, session panel — and the change
is in what each band renders. The three options are one rendering with three levels of
omission, so the implementation is one code path per component with the chosen level
baked in, not a runtime setting (R5.5: no new setting).

```mermaid
flowchart TB
  subgraph W["Work surface (ui/src/views/Work.tsx)"]
    direction LR
    S["Sidebar<br/>brand · surfaces · finder<br/>groups · rows · footer"]
    subgraph M["main column (WorkItemDetail)"]
      direction TB
      H["HeaderBar<br/>title · meta · actions"]
      G["GraphStrip<br/>position · node row"]
      T["SessionTabs"]
      R["trace head · Transcript · banners · ChatBar"]
    end
    P["SessionAside<br/>controls · facts"]
  end
  S -. "C: Standing group out,<br/>finder behind an icon,<br/>two groups" .-> S
  G -. "C: line merged into the header meta;<br/>node row only on Full graph" .-> H
  P -. "C: column removed;<br/>controls → header actions,<br/>facts → one header disclosure" .-> H
```

What every level does to the data flow: **nothing**. `api/`, `state/` and `demo/` are
untouched (R5.1); the views read the same `WorkItemView` and call the same `TheLoopApi`
methods from the same user actions. The one view-model change is `railNote`, which stops
naming the node it is drawn beside.

## Components & interfaces

One row per component, one column per level. A cell inherits the column to its left: B
does everything A does, C everything B does (R1.2).

| Component | A — Trim | B — Focus (in addition) | C — Minimal (in addition) |
|---|---|---|---|
| `Sidebar` | Row = dot · `#n` · title (two lines) · instance chip, plus a second line **only** for an urgent flag (`needs input`, `human gate`, `blocked`). Repo, node, age and non-urgent flags leave the row. Group counts render only on **Needs you**. The Standing group renders only when a standing session exists. | Row is one line: title truncated, the urgent flag inline at the right. PR rows nest under the **selected** item only, and drop their age. Standing rows drop the description. | Two groups: **Needs you** and **Everything else** (sorted by last activity). No Standing group (the Standing surface keeps it). Search and the instance filter sit behind one icon button in the brand row (`aria-expanded`), closed by default. |
| `HeaderBar` meta (from `WorkItemDetail`) | ref chip · instance chip (fleet) · phase chip · `updated <age>`. The repository line leaves (it is in the ref chip). | ref chip · phase chip · `updated <age>`. The instance chip stays on the sidebar row only. The ref chip stays at every level: it is the one default-visible copy of the repository (R2.1; critic finding C2). | ref chip · phase chip · the parked/blocked note · `updated <age>` · **Full graph** control. |
| `HeaderBar` actions | copy ref · GitHub · theme · *Open session panel* (when closed) | same | pause/resume/stop/start as `ControlButton`s, preceded by a visible `work item` kicker when a PR session is selected (the verbs act on the work item's session, as today's section title said; critic C3) · copy ref · GitHub · theme · **Session details** (a `<details>` whose summary is an `IconButton` and whose body is the facts popover, bounded to the viewport and scrolling inside; critic C4). The *Open session panel* button is gone with the panel. |
| `GraphStrip` | Line = loop name · the parked/blocked note (no `n of m`, no `skipped`, no `at <node>`), *Full graph* at the right; compact node row beneath, the current node highlighted. | same | The band renders only while *Full graph* is on: the loop name and the full node row. The line's content moved into the header meta. |
| `SessionTabs` | Renders only when the item has more than one session (R2.6); the `n sessions · …` tally leaves. | same | same |
| Trace head | `Harness trace · <harness>` · **Verbose** | `Harness trace` · **Verbose** (the harness name is in the Harness facts) | same |
| `GateBanner` | `Human gate · waiting <age>` · reason · **Approve — advance graph** · *Request changes on the ticket*. The node name leaves (it is the phase chip). | same | same |
| `QuestionBanner` | unchanged | unchanged | unchanged |
| `ChatBar` | Input · send. The hint line renders **only** the blocked reason; `delivers to tmux · <target> · bracketed paste · ⌘⏎` leaves (⌘⏎ stays in the send button's title). | same | same |
| `SessionAside` | Head · **Harness** (harness, status, started, session id *abbreviated + copy*, transcript *file name + copy*) · **tmux** (cwd *last segment + copy*, the attach command button) · **Ticket** / **Pull request** (inner loop for a PR, *Open on GitHub*) · **Controls**. Leaves: the note banner (now the strip's), instance, current node, the tmux `target` row (the attach command carries it), repo and number (the header's). | **Controls** first; Harness, tmux and Ticket become `<details>` sections closed by default (`Section` gains a `collapsible` prop). Inside a disclosure the session id, transcript path and cwd render **in full**, as today's `KV` rows, with no copy control (R2.3 is met by the disclosure; R5.5 forbids a new control — critic C5). Only the attach-command copy stays. | Not rendered on Work. Its facts render as `SessionFacts` inside the header's **Session details** popover; its verbs render in the header actions. `Panels.asideOpen` is unused on Work and the header's open-panel button is not rendered. |
| `railNote` (`WorkItemDetail.tsx`) | `parked — awaiting a human` (no `at <node>` suffix); the attention detail otherwise, as today. | same | same |
| `HealthDot`, `DemoBanner`, `ConnectionBanner` | unchanged | unchanged | unchanged |
| Standing · Settings · Instances panes | inherit the header's changes; nothing else | same | same |

No new helper for the chosen option: the facts inside the Session details disclosure
render from the same typed fields through the same `KV` rows as today. (Option A alone
would have needed `abbreviateId` / `lastSegment` formatters; it is not built.)

### Element inventory — one verdict per element per option (R1.3)

`keep` · `relocate → where` · `remove`. The reason is the one that applies to the first
level that acts; a later level inherits it.

| # | Band · element | A — Trim | B — Focus | C — Minimal | Reason |
|---|---|---|---|---|---|
| 1 | Sidebar · brand row (logo, wordmark, collapse) | keep | keep | keep | orientation |
| 2 | Sidebar · surface nav (Work · Standing · Instances) | keep | keep | keep | the only way between surfaces |
| 3 | Sidebar · search box | keep | keep | relocate → behind a search icon in the brand row | used rarely; the rows are the list |
| 4 | Sidebar · instance filter (fleet only) | keep | keep | relocate → same icon | as 3; never on a worker (R2.6) |
| 5 | Row · dot | keep | keep | keep | urgency (R2.2) |
| 6 | Row · `#n` | keep | keep | keep | identity (R2.2) |
| 7 | Row · title, two lines | keep | condense → one line | one line | B: one line scans; the header has the full title |
| 8 | Row · instance chip (fleet only) | keep | keep | keep | on a fleet it is identity (one ref on two instances is two rows) |
| 9 | Row · second line · repository | remove | — | — | not a reason to choose (R2.2); drawn once in the ref chip / Ticket |
| 10 | Row · second line · current node | remove | — | — | drawn once, as the phase chip (R2.1) |
| 11 | Row · second line · flag | keep only when urgent (`needs input`, `human gate`, `blocked`) | condense → inline on the one line | inline | R2.2: a flag only when the item needs a human; `paused`, `merged`, `closed` are the group's job |
| 12 | Row · second line · age | remove | — | — | drawn once, as the header's `updated` (R2.1) |
| 13 | Nested PR rows (dot, icon, label) | keep | condense → under the selected item only | under the selected item only | B: they double the row count for items not being looked at; the tab bar lists them once selected |
| 14 | Nested PR row · age | keep | remove | — | one-line rule; the tab and the Harness facts carry the session's state |
| 15 | Group header counts | keep **Needs you** only | same | same | R2.4: the one count that changes what you do |
| 16 | Groups In flight · Shipped · Idle | keep | keep | condense → **Everything else**, sorted by activity | C: three groups to scan for things that need nothing |
| 17 | Standing rows (dot, name, description) | keep; the group hides when empty (R2.6) | condense → name only | remove (the Standing surface keeps them) | a session with no work item among the work items |
| 18 | *Manage standing sessions →* | keep | keep | remove | the surface nav already says Standing |
| 19 | Footer · Settings icon + word | keep | keep | keep | the only way to Settings besides the hash |
| 20 | Footer · service line | keep | keep | keep | where the data comes from — a trust signal |
| 21 | Footer · health word + popover | keep | keep | keep | fail-closed: `degraded` must stay visible |
| 22 | Header · title | keep | keep | keep | identity |
| 23 | Header · ref chip | keep | keep | keep | the one default-visible copy of the repository and the ref (R2.1) |
| 24 | Header · instance chip (fleet) | keep | remove (the row keeps it) | — | drawn once |
| 25 | Header · phase chip | keep | keep | keep | **the one statement of the current node** |
| 26 | Header · repository | remove | — | — | it is inside the ref chip (R2.1) |
| 27 | Header · `updated <age>` | keep | keep | keep | the one age (R2.1) |
| 28 | Header · copy ref · GitHub · theme | keep | keep | keep | R5.2 actions |
| 29 | Header · *Open session panel* (when closed) | keep | keep | remove (no panel) | with the column |
| 30 | Strip · loop name | keep | keep | relocate → the revealed node row's label | C: the line is gone |
| 31 | Strip · `n of m nodes passed` | remove | — | — | bookkeeping (R2.4) |
| 32 | Strip · `n skipped` | remove | — | — | bookkeeping; the node row strikes them through |
| 33 | Strip · `at <node>` / `blocked at <node>` | remove | — | — | second statement of the position (R2.5); the chip and the highlighted node say it |
| 34 | Strip · parked/blocked note | keep (the one qualifier) | keep | relocate → header meta | R2.5: the position's qualifier, once |
| 35 | Strip · *Full graph* | keep | keep | relocate → header meta; reveals the band | R3.3 |
| 36 | Strip · compact node row | keep | keep | relocate → behind *Full graph* | C: one line |
| 37 | Tabs · one tab per session | keep when >1 session | same | same | R2.6 |
| 38 | Tabs · `n sessions · 1 work item loop · …` | remove | — | — | bookkeeping (R2.4) |
| 39 | Trace head · `Harness trace` | keep | keep | keep | names the column and anchors the switch |
| 40 | Trace head · harness name | keep | remove | — | R3.2; the Harness facts carry it |
| 41 | Trace head · **Verbose** | keep | keep | keep | R5.2 |
| 42 | Gate banner · `Human gate — <node>` | condense → `Human gate` | same | same | the node is the phase chip (R2.1) |
| 43 | Gate banner · `waiting <age>` | keep | keep | keep | a distinct fact: how long a human has been needed |
| 44 | Gate banner · reason · Approve · Request changes | keep | keep | keep | R3.4 |
| 45 | Question banner (all of it) | keep | keep | keep | R3.4 |
| 46 | Composer · input · send | keep | keep | keep | R3.4 |
| 47 | Composer · `delivers to tmux · <target>` | remove | — | — | third copy of the target; nobody acts on it (R2.4) |
| 48 | Composer · `bracketed paste + enter` · `⌘⏎ to send` | remove (⌘⏎ stays in the send title) | — | — | hints, not facts |
| 49 | Composer · blocked reason | keep | keep | keep | fail-closed |
| 50 | Panel · note banner | relocate → the strip's qualifier (34) | — | — | second copy of the note |
| 51 | Panel · Harness · instance | remove (header + row) | — | — | drawn twice already |
| 52 | Panel · Harness · harness | keep | relocate → Harness disclosure | relocate → Session details | |
| 53 | Panel · Harness · session id | condense → abbreviated + copy | disclosure, in full, no copy control | Session details, in full | R2.3: on demand; R5.5: no new control |
| 54 | Panel · Harness · status | keep | disclosure | Session details | |
| 55 | Panel · Harness · current node | remove | — | — | fifth copy |
| 56 | Panel · Harness · started | keep | disclosure | Session details | |
| 57 | Panel · Harness · transcript path | condense → file name + copy | disclosure, in full | Session details, in full | R2.3; R5.5 |
| 58 | Panel · tmux · target | remove (the attach command carries it) | — | — | R2.1: the target once |
| 59 | Panel · tmux · cwd | condense → last segment + copy | disclosure, in full | Session details, in full | R2.3; R5.5 |
| 60 | Panel · tmux · attach command (copy) | keep | disclosure | Session details | the one copy of the target, and the action on it |
| 61 | Panel · Ticket · repo · number | remove (the ref chip is the one copy) | — | — | drawn once (R2.1); never restored (R1.2, critic C6) |
| 62 | Panel · Ticket · inner loop (PR tab) | keep | disclosure | Session details | a PR's own position; not drawn elsewhere |
| 63 | Panel · Ticket · Open on GitHub | keep | disclosure | Session details | the header's icon is the primary |
| 64 | Panel · Controls grid | keep | keep, moved to the top | relocate → header actions, with a visible `work item` kicker on a PR selection | R3.4: one interaction; the target stays visible (R5.2) |
| 65 | Panel · head (`Session`, close) | keep | keep | remove | with the column |
| 66 | Demo banner · connection banner | keep | keep | keep | fail-closed (Security considerations) |

Tally: the inventory rows drawn by default with #214 selected on a worker, both panels
open, nothing expanded — so the fleet-only rows (4, 8, 24, 51), the gate rows (42–44),
the PR-tab row (62) and the closed-panel and blocked-composer rows (29, 49) are out of
every column, and a `relocate` counts only where its new home is drawn by default (the
search icon, the header's note and *Full graph*, the header's verbs and the Session
details control in C). Today 56 · A 42 · B 31 · C 27. The search icon and the Session
details control in C are disclosure toggles in the *Full graph* idiom, not new
capabilities (R5.5).

### Where the current node is drawn — the rule the inventory follows

The **phase chip is the statement**; the **node row is the map**. A node's name inside
the row is a member of a list, highlighted when current, not a second sentence saying
where the loop is. The strip's text therefore says only the qualifier (`parked — awaiting
a human`, or the attention detail), never `at <node>`; the gate banner says `Human gate`,
never `— <node>`; the panel's `current node` row is gone. One statement, one map.

## UI/UX design

| Artifact | Type | Location / link | Covers (screen · requirement) | Status |
|----------|------|-----------------|-------------------------------|--------|
| Option A — Trim | html-prototype | [`design/option-a-trim.html`](design/option-a-trim.html) | Work · R2, R3.1, R4, R6 | offered, not chosen — kept as the record (R1.5) |
| Option B — Focus | html-prototype | [`design/option-b-focus.html`](design/option-b-focus.html) | Work · R2, R3.2, R4, R6 | offered, not chosen — kept as the record (R1.5) |
| **Option C — Minimal** | html-prototype | [`design/option-c-minimal.html`](design/option-c-minimal.html) | Work · R2, R3.3, R4, R6 | **selected** — chosen by @MadaraUchiha-314 on PR #513, 2026-10-20 ([comment](https://github.com/MadaraUchiha-314/the-loop/pull/513#issuecomment-6295462213)); [decision-148](../../decisions/decision-148.md). The visual contract the implementation matches. |
| `design/screenshots/current-*.png` | rendered stills of the **built 20.5.1 app** on the demo fixture | [`design/screenshots/`](design/screenshots/) | the baseline, #214 and the #205 gate, both themes | reference |
| `design/screenshots/{a,b,c}-01…08-*.png` | rendered stills of the three prototypes | same | item · full graph · disclosures open · gate · PR session · no-transcript fallback · 390 px, both themes | draft |

The owner named **Option C** on PR #513 on 2026-10-20 ("I prefer the "minimal" option,
option-c"), before the gate asked: the row above is marked selected and
[decision-148](../../decisions/decision-148.md) records the pick. The two other
prototypes stay checked in as the record of what was offered (R1.5). The
`design-approval` gate still posts its one review request covering this document and
the testing plan; the component table's **C** column and the inventory's **C** column
are what the tasks derive from.

- **How to look at them:** open a prototype in a browser; it needs no server. The
  sidebar rows and the PR rows navigate (`#item/<ref>`), the header's theme button
  switches theme, *Full graph*, **Verbose**, the panel's disclosures and the sidebar's
  collapse all work. **Approve** and the control verbs are inert. Select **#205** for the
  gate banner, **#178** for a blocked item, **#187** for an item with no session (the
  no-transcript fallback and a blocked composer), **#216** for a PR session.
- **Flows & states covered:** select item → the main column (and the panel, A/B) swap;
  select a PR tab or row → the trace and the facts swap; *Full graph* ↔ *Collapse graph*;
  **Verbose** on/off; collapse/open each panel; theme; the gate banner with Approve; the
  question banner above the composer; the blocked composer with its reason; the
  no-transcript fallback; the demo banner. States not drawn by the prototypes but kept
  by the implementation unchanged: loading, empty board, connection error, missing deep
  link, truncated tail, stream reconnecting/fallen back, daemon stopped, degraded fleet
  (R5.3) — none of their components change.
- **Design system / tokens:** the issue-327 token set from `ui/src/styles/app.css`,
  copied verbatim into each prototype's `:root` / `.dark`; the same five state colours,
  the same radius, the same `ref-chip`, `pulse-dot` and `scroll-thin` utilities; no new
  token, shadow or gradient (R4.1). Every class in the prototypes is a hand-written
  equivalent of a Tailwind utility the app already uses. The prototypes fetch no web
  font (`selfContained`), so they render in the system faces; the built app keeps its
  Google Fonts link.
- **Accessibility & responsiveness:** the Session details popover (C) is bounded to the
  viewport (`max-height: calc(100vh - 9rem)`, width at most the viewport less the gutter)
  and scrolls inside, so a long transcript path or working directory never pushes the
  Ticket section and *Open on GitHub* off a short screen; every disclosure is a native `<details>` (the
  panel sections in B, the health popover, the Session details popover in C) or a button
  with `aria-expanded` (*Full graph*, the search icon in C); a row's `aria-label` carries
  `#n — title — flag`; `aria-current` marks the selected row, tab and node; the trace
  keeps `role="log"`, its name and `tabindex`; below 1280 px the panel starts closed (in
  C the popover always starts closed), below 768 px the sidebar starts closed and the
  header wraps so the title keeps its width (R6).
- **Evidence:** `design/screenshots/` holds the stills above, captured headlessly at
  1440×900 and 390×844; the console and the network were watched during capture — no
  page error, no request left the file. Verification recaptures the **built** app.

### Side by side

| State | Today | A — Trim | B — Focus | C — Minimal |
|---|---|---|---|---|
| #214, dark | ![current 01 item dark](design/screenshots/current-01-item-dark.png) | ![a 01 item dark](design/screenshots/a-01-item-dark.png) | ![b 01 item dark](design/screenshots/b-01-item-dark.png) | ![c 01 item dark](design/screenshots/c-01-item-dark.png) |
| #214, light | ![current 01 item light](design/screenshots/current-01-item-light.png) | ![a 01 item light](design/screenshots/a-01-item-light.png) | ![b 01 item light](design/screenshots/b-01-item-light.png) | ![c 01 item light](design/screenshots/c-01-item-light.png) |
| #205 gate, dark | ![current 04 gate dark](design/screenshots/current-04-gate-dark.png) | ![a 04 gate dark](design/screenshots/a-04-gate-dark.png) | ![b 04 gate dark](design/screenshots/b-04-gate-dark.png) | ![c 04 gate dark](design/screenshots/c-04-gate-dark.png) |
| Full graph, dark | — | ![a 02 full graph dark](design/screenshots/a-02-full-graph-dark.png) | ![b 02 full graph dark](design/screenshots/b-02-full-graph-dark.png) | ![c 02 full graph dark](design/screenshots/c-02-full-graph-dark.png) |
| Disclosures open, dark | — | — | ![b 03 disclosures open dark](design/screenshots/b-03-disclosures-open-dark.png) | ![c 03 disclosures open dark](design/screenshots/c-03-disclosures-open-dark.png) |
| PR #216 session, light | — | ![a 05 pr session light](design/screenshots/a-05-pr-session-light.png) | ![b 05 pr session light](design/screenshots/b-05-pr-session-light.png) | ![c 05 pr session light](design/screenshots/c-05-pr-session-light.png) |
| No transcript, light | — | ![a 06 fallback light](design/screenshots/a-06-fallback-light.png) | ![b 06 fallback light](design/screenshots/b-06-fallback-light.png) | ![c 06 fallback light](design/screenshots/c-06-fallback-light.png) |
| 390 px, dark | — | ![a 07 narrow dark](design/screenshots/a-07-narrow-dark.png) | ![b 07 narrow dark](design/screenshots/b-07-narrow-dark.png) | ![c 07 narrow dark](design/screenshots/c-07-narrow-dark.png) |
| 390 px, Session details open, dark | — | — | — | ![c 08 narrow details dark](design/screenshots/c-08-narrow-details-dark.png) |

## Data models

None change. `WorkItemView`, `PullRequestView`, `RailNode`, `SessionRecord` and the
hash route are read as today (R5.1, R5.4). The view-side additions are two string
formatters (`abbreviateId`, `lastSegment`) and, in Option C, a second group table for
the sidebar:

```ts
// views/grouping.ts — Option C only
export const SIDEBAR_GROUPS_MINIMAL = [
  { key: "needs-you", title: "Needs you" },
  { key: "everything", title: "Everything else" }, // in-flight | shipped | idle, by lastActivity desc
] as const;
```

`sidebarGroup(view)` keeps returning the four-way answer (the Standing and Instances
panes, `itemStatus` and the tests read it); the sidebar maps it to the two-way table.

## Error handling

Every failure surface is unchanged in wording and placement (R5.3): the connection
banner above the columns, the health word in the footer (`degraded` when a daemon stops,
the stream falls back or a member is down), the muted *No transcript served* notice with
the server's reason, the `tail — the last n of m entries` line, the composer's blocked
reason in the hint slot, the gate banner's and the controls' `role="alert"` error lines.
De-cluttering removes nothing a failure says. The copy controls fall back silently, as
today, when the clipboard is unavailable.

**Scope of "visible by default" for the health word** (critic C1): the health word's
home is the sidebar footer at 20.5.1 and at every option, and the stream's fallen-back
state is the word itself (`degraded`), not only the popover's sentence. A collapsed
sidebar hides the footer today exactly as it will after this change, by default below
768 px; this work item neither introduces nor widens that gap and, under R5.5, adds no
second home for the word. Giving the header a health signal while the sidebar is closed
is a follow-up outside this ticket (§ Open questions).

## Security design

- **AuthN/AuthZ:** unchanged — the browser talks to the service over the base URL the
  settings hold; no new request, route or credential (R5.5). The prototypes are static
  files that perform no request.
- **Input validation & injection surfaces:** untrusted text (ticket titles, node names,
  transcript lines, event fields, paths, the tmux target) reaches the DOM only through
  React children, in the relocated positions too: the one-line row's truncated title, the
  disclosure summaries and the popover's rows. `renderInline` is the only transformer
  and it still emits text nodes inside `<strong>` / `<code>`. No `dangerouslySetInnerHTML`, no `eval`, no inline handler on served
  content. The prototypes escape every data string through one `esc()` before
  interpolation, so a title such as `<img onerror>` renders as text there as well.
- **Secrets handling:** none stored, moved or displayed; the attach command is built from
  the tmux target the service already serves.
- **Least privilege:** the two clipboard writes are today's (`copy ref`, `copy attach
  command`), `navigator.clipboard.writeText` on a user gesture; nothing reads the
  clipboard, and no copy control is added (critic C5).
- **Fail-closed behaviour:** the demo banner, the connection banner, the health word, the
  stream's fallen-back state and the composer's blocked reason are inventory rows 21, 49
  and 66 — `keep` in every column. A check that cannot be made (no checkout → Approve
  disabled with its reason; no session → composer disabled with its reason) renders as
  today.
- **Abuse-case coverage:** the table below.

| Abuse case (requirements) | Mechanism | Negative test |
|---|---|---|
| 1 — markup / `**` / backtick in a title, line, path or node name | React escaping in every relocated element; `renderInline` emits text nodes | component tests render a fixture title `<b>x</b>` and a node `**n**` through the one-line row, the disclosure summary, the popover and the abbreviated id, and assert `textContent` equals the input and no element was created |
| 2 — content moved behind a disclosure | the `<details>` bodies render from the same `SessionRecord` / `PullRequestView` fields as today's `KV` rows, never from a string assembled in the DOM | the same tests assert the disclosure body's text derives from the typed record |

- **No new attack surface,** justified: this change adds no route, no request, no HTML
  rendering, no dependency and no setting; it removes and relocates markup the app
  already renders, and the two helpers it adds are pure string functions.

## Testing strategy

The requirements map to three kinds of proof. **Component tests** (vitest + Testing
Library, the existing suites) assert each inventory verdict for the chosen option: what a
band renders by default, what a disclosure reveals, the accessible names and
`aria-current`, the fail-closed rows, the abuse cases above, and the one-session tab rule
(`Sidebar.test.tsx`, `GraphStrip.test.tsx`, `WorkItemDetail.test.tsx`, a new
`SessionAside.test.tsx`, `primitives.test.tsx`, `grouping.test.ts`). **Screenshot
evidence** (`ui/scripts/screenshots.mjs`, extended with the disclosure states) proves the
built app against the locked prototype in both themes and at 390 px, and gives R7.2 its
before/after count. **The CI commands** (`bun run lint`, `bun run test`, `bun run
build`) and a bundle-size comparison prove the non-functional requirements. The
executable detail — the matrix, the environment, the evidence list — is
[`testing-plan.md`](testing-plan.md).

## Trade-offs & decisions

- **D1 — One template, three files.** The prototypes are generated from one HTML template
  with an `OPTION` constant, so nesting is structural: a rule is written once as `L ≥ 2`
  or `L ≥ 3`. Three hand-edited files would drift. The generator is a throwaway; the
  three files are the artifacts.
- **D2 — The phase chip is the one statement of the current node.** R2.1 (node once) and
  R3.2 (B keeps the phase chip) only reconcile if the strip's `at <node>` goes, the gate
  banner drops `— <node>` and the panel's `current node` row goes — so they do, from A.
  The node row stays as the map (§ above).
- **D3 — The panel's note folds into the strip at A.** R3.2 reads "controls and the
  note", but R2.1 allows the parked/blocked note once and R2.5 puts it in the strip. The
  floor wins, from A. The owner can overturn this at the gate; it is one `Notice` either
  way.
- **D4 — A one-session tab bar hides at every level.** R2.6 is the floor; R3.3 lists the
  rule for C again. Applied from A, so the owner's screenshot (one session) gains a band
  back at no level.
- **D5 — The gate's `waiting <age>` stays beside the header's `updated <age>`.** They are
  different facts (how long a human has been needed; when anything last happened). R2.1's
  "age" is the latter.
- **D6 — Identifiers: a disclosure, not a copy control (B, C).** R2.3 allows "a
  disclosure or a copy control"; R5.5 forbids a new control. Behind a disclosure the
  values can be drawn in full, as today's `KV` rows draw them, so B and C add no copy
  button (critic C5). Option A alone, keeping the rows in the open, would have used the
  copy-control reading with abbreviated values; it is not built.
- **D7 — One-line rows truncate the title (B, C).** A 19 rem column holds about twenty-two
  characters beside a flag such as `needs input`. The header carries the full title and
  the row's `aria-label` carries it for screen readers. Widening the sidebar would be a
  layout change the ticket did not ask for.
- **D8 — C folds the strip into the header meta rather than keeping a one-line band.** A
  band whose only content would be the loop name and *Full graph* is a line for its own
  sake. The qualifier and the control sit beside the phase chip, and the node row appears
  beneath the header while *Full graph* is on.
- **D9 — C's controls become header actions.** Pause/stop next to the icon buttons
  crowds the header (two mono buttons plus five icons); that is the honest cost of
  removing the column, drawn so the owner sees it before choosing. On a PR selection a
  `work item` kicker precedes the verbs, so the target the panel's section title used to
  name stays visible (critic C3).
- **D11 — R2.1 outranks R3.2's literal list.** "Reduce the header meta to the phase chip
  and the age" would leave the repository drawn zero times by default in B and C, against
  the floor. The ref chip stays at every level as the one copy of the repository and the
  ref; what R3.2 removes is the instance chip and the repository line (critic C2, C6).
- **D10 — The prototypes render in system fonts.** `selfContained: true` forbids the
  Google Fonts request; the built app keeps it. The screenshots therefore differ from the
  app in face, never in colour, size or spacing.

Durable decision: `docs/decisions/decision-148.md` — *the owner's chosen level* — is
written when the pick is made (R1.5).

## Open questions

- **Which option?** Asked by the `design-approval` gate's review request, answered by a
  review comment on the PR naming **A**, **B** or **C**. Not asked separately here.
- Carried from the requirements, still open to overturning at the gate: "main bar"
  read as the main column's top band plus the composer's hint; Option C's two sidebar
  groups.
- **Follow-up, not this ticket:** a health signal in the header while the sidebar is
  collapsed (critic C1) — the gap exists at 20.5.1 and R5.5 forbids adding an element
  here.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed: an approval never silently
> discards a reviewer's suggestions, and the feedback travels with the document
> it concerns rather than living in a side-channel tracker.
