---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#511"
---

# UI / visual evidence (T5, R7): de-cluttering the control plane UI

> Headless Chromium stills of the **built** app on the demo fixture, both themes, at
> 1440×900 and 390×844, captured at `verification` on 2026-10-20 by
> `node ui/scripts/screenshots.mjs` against `bun run preview --port 4173` over `dist/`.
> 32 captures under [`ui/`](ui/); [`ui/capture.log`](ui/capture.log) lists them and
> recorded no `pageerror` and no `console.error`. Recaptured after the self-review and
> critic rounds, so the stills are of the reviewed code. The web fonts loaded, so the stills
> render in the design's faces; the prototype stills render in system faces (design D10).

## Each state beside its prototype still

| Capture (dark · light) | State | Prototype counterpart under `design/screenshots/` |
|---|---|---|
| `01-home-dark.png` · `01-home-light.png` | Work, nothing selected (the newest item) | `c-01-item-*` |
| `02-item-214-dark.png` · `02-item-214-light.png` | #214 selected: question banner, one-line rows, two groups, PRs under the selected item, the meta line, verbs + Session details control | `c-01-item-*` |
| `03-full-graph-dark.png` · `03-full-graph-light.png` | Full graph on: the node row beneath the header | `c-02-full-graph-*` |
| `04-verbose-expanded-dark.png` · `04-verbose-expanded-light.png` | Verbose on, a tool group and a call open | `(trace, unchanged)` |
| `05-verbose-off-dark.png` · `05-verbose-off-light.png` | Verbose off | `(trace, unchanged)` |
| `06-pr-session-dark.png` · `06-pr-session-light.png` | PR #216's session: the `work item` kicker before the verbs, the PR tab current | `c-05-pr-session-*` |
| `07-gate-dark.png` · `07-gate-light.png` | #205: `Human gate · waiting <age>`, the parked note beside the phase chip | `c-04-gate-*` |
| `08-fallback-dark.png` · `08-fallback-light.png` | #187: no transcript served, the event-trail fallback, the blocked composer's reason, `start` | `c-06-fallback-*` |
| `09-standing-dark.png` · `09-standing-light.png` | Standing surface, listing the standing sessions | `(unchanged pane, same header)` |
| `10-settings-dark.png` · `10-settings-light.png` | Settings pane | `(unchanged pane, same header)` |
| `11-sidebar-collapsed-dark.png` · `11-sidebar-collapsed-light.png` | the sidebar collapsed; Open sidebar in the header | `—` |
| `13-details-open-dark.png` · `13-details-open-light.png` | Session details open: Harness · tmux · Ticket, values in full, the attach command, Open on GitHub | `c-03-disclosures-open-*` |
| `14-search-open-dark.png` · `14-search-open-light.png` | the finder open behind the search toggle | `—` |
| `12-mobile-dark.png` · `12-mobile-light.png` | 390 px: the sidebar closed, the header wrapped | `c-07-narrow-*` |
| `12b-mobile-sidebar-dark.png` · `12b-mobile-sidebar-light.png` | 390 px with the sidebar open over the column | `—` |
| `12c-mobile-details-dark.png` · `12c-mobile-details-light.png` | 390 px with Session details open, bounded to the viewport | `c-08-narrow-details-dark` |

## Elements drawn by default on the Work surface (R7.2)

Counted with the inventory of `design.md` § Element inventory, #214 selected, a worker,
the sidebar open, nothing expanded.

| | Count | Source |
|---|---|---|
| Before (20.5.1) | 56 | the inventory's tally of `design/screenshots/current-01-item-dark.png` |
| After (this branch) | 27 | recounted on `ui/02-item-214-dark.png` |

The 27 after, by inventory row: 1 brand row · 2 surface nav · 3 the search icon · 5 dot ·
6 `#n` · 7 title · 11 the urgent flag · 13 the selected item's PR rows · 15 the Needs you
count · 16 Everything else · 19 Settings · 20 service line · 21 health word · 22 title ·
23 ref chip · 25 phase chip · 27 `updated` · 28 copy · GitHub · theme · 35 Full graph ·
37 the tabs (#214 has two PR sessions) · 39 `Harness trace` · 41 Verbose · 45 the question
banner · 46 the composer · 64 the verbs · 66 the demo banner · the Session details control.

## Checked against the design

- the phase chip is the one statement of the current node; the strip's counts and
  `at <node>` are gone; the gate banner says `Human gate` (07);
- the repository appears once, inside the ref chip; the tmux target once, inside the
  attach command (13); the age once, as `updated` (02);
- the sidebar rows are one line with the flag at the right; PRs nest under #214 only
  (02 vs 07, where #205's PR nests instead); the Standing group is gone (02); the finder
  is behind the icon (14);
- the tab bar renders for #214 and #205 (two sessions each) and not for #187 (08);
- the popover is bounded and scrolls at 390 px (12c); the header wraps and the title keeps
  its line (12);
- the demo banner, the `degraded` health word and the blocked composer's reason are drawn
  in every still that has them (02, 08).
