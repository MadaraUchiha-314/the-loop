---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#549"
---

# Security review: the Slack collaboration experience

## The short version

One real vulnerability was found and fixed. A heading pattern took cubic time, so
crafted text could stall Slack delivery for hours. Two hardening notes were also acted
on. Every trust boundary in `design.md` § Security design held against about 40 crafted
inputs. The risk tier is **4**: the change adds a Slack path that answers human
approval gates, new authorization logic for button presses, a wider gateway method
allow-list, and new ref matching across repositories. A named human must sign off.

## Security review (gate)

- **Mechanism:** a security review in the shape of the built-in skill, run by a fresh
  agent over `git diff origin/main...HEAD -- cli/the_loop` on 2026-11-20, against the
  requirements' Security considerations and design abuse cases 1–9. Crafted inputs were
  run through the real code.
- **Outcome:** 1 finding at confidence 8 or above, fixed. 2 hardening notes, acted on.

### Finding

**S1: the heading pattern was cubic (abuse case 3). Confidence 9, medium. Fixed.**

- **Where:** `render.py` `HEADING_LINE_RE` and `mrkdwn.py` `_HEADING` were both
  `^#{1,6}\s+(.+?)\s*#*\s*$`.
- **Impact:** a line `# a` followed by thousands of spaces and `b` took 99 s at 4,000
  spaces. A 64 KB comment would take hours, and the outbox retried it after a restart.
- **Fix:** the patterns take the heading text whole (`^#{1,6}[ \t]+(\S.*)$`), and the
  closing `#` run is stripped in Python. A 64 KB crafted heading now renders in under
  2 s. Test: `test_abuse_a_heading_of_spaces_renders_in_linear_time`.

### Hardening, acted on

- **The stale-press check now compares the channel as well as the ts.** A press whose
  message is in another conversation than the open gate's is refused.
- **Identity keys use `lower()`, not `casefold()`.** `casefold` merged non-ASCII names
  (`straße` with `strasse`). GitHub names are ASCII.

### Checked, one line per boundary

1. **Broadcasts and mentions:** inert everywhere: the short form, its `text` fallback,
   the long form and the gate-closed edit. Inputs included nested links, `&gt;` inside
   links, tables, headings, `<details>` and code. Button values are constants.
2. **Links:** only `http`, `https` and `mailto` stay links. Every `javascript:` form
   renders as text (self-review R1-3).
3. **Approve presses:**
   - the allow-list is checked first;
   - a stale, forged or wrong-gate press is refused;
   - a press with no binding, or in an ambiguous room, is refused;
   - `gate.answered` is published only by the runtime.
4. **Denial of service:**
   - every pattern is now linear;
   - parts per message are bounded: 64 KB of `<` gives 24 parts, each within the 11,000
     budget;
   - delivery memory is capped.
5. **Credentials:** no token is logged. `reactions.remove` was added to the gateway
   allow-list, and a bot can only remove its own reactions.
6. **Identity:** only a GitHub ref's owner and repo are folded. The host, the number and
   Jira refs stay exact.

**Not verified:** whether Slack's `markdown` block acts on a bare `@here` typed as text.
The live check (T4) showed `<!here>` arriving inert. A bare `@here` is plain text in
Slack's API.

- **Human sign-off:** required (risk tier 4). Pending.
