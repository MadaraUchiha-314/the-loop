---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#419"
---

# Documentation: one verbosity switch over the whole trace, defaulting to quiet

> The ready-to-ship gate's documentation item: the affected capability docs are updated in
> the same pull request as the change.

## Updated in this PR

**[`docs/capabilities/control-plane.md`](../../../capabilities/control-plane.md)** — the
organized view of the dashboard's behaviour, and the only capability doc that describes
the trace panel.

- The dashboard section gains the rule this work item establishes: the trace defaults to
  what a human can read or act on, behind one *Verbose* switch; what the switch hides, the
  full list of bookkeeping families, what it never hides (`level=error`, an unclassified
  family, prose, thinking, human replies, malformed lines, meta rows with text, the gate
  and question banners), that the trail's row budget is spent after the filter, and that a
  view the filter emptied names its hidden count.
- The three-column description's *Tool calls* switch is renamed *Verbose*, so the doc no
  longer names a control that does not exist.
- A history row for issue-419, above issue-395.

## Not affected

- `docs/capabilities/observability.md` and `skills/the-loop/reference/observability.md` —
  they describe the **event log** and `the-loop events`, neither of which changed. The
  filter is the dashboard's rendering choice, not a property of the log, and `the-loop
  events` still returns every record it always did.
- `ui/README.md` — it describes the workspace's layout and toolchain, not the trace's
  row-level behaviour; nothing in it names the switch.
- `docs/api-specs/openapi/the-loop.v1.yaml` — no route, parameter or response changed.
- No decision record: nothing here overturned a recorded decision or needed a human's
  opinion. The one judgement worth writing down — family-level classification, failing
  open — is argued in `design.md` § What it costs, where a reviewer of this change will
  look for it.
