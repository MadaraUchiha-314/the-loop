---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#389"
---

<!-- Authored per the the-loop:writing skill. -->

# Final validation: the mention is the address, and three acts each end in the session

> The `evidence` node's proof, summarised from the executed verification —
> [`testing-plan.md`](../testing-plan.md) § Verification results — and mapped onto the
> requirements of [`requirements.md`](../requirements.md). Raw output sits beside this
> file.

## Final validation evidence

| Acceptance criterion | How it was proved | Where |
|----------------------|-------------------|-------|
| R1 — a conversation reaches the-loop only when addressed (R1.1–R1.9) | the §1 input table as a pure decision and end to end: a plain message in a room is `not-addressed` with no trace; a mention is input in a room, under the-loop's own question, and as a kickoff; a DM hears plain messages; a redelivery acts once; poll mode reads no mention-gated conversation; the probe names the missing scope | [`integration.md`](integration.md) scenarios 1–3, 5–7, 9; [`security.md`](security.md) A7, A8, A10; [`upgrade.md`](upgrade.md) |
| R2 — a room can be switched to hear everything, by an authorized user only (R2.1–R2.4) | `--listen all` on the CLI and the keyword; an `all` room hears a plain message; a collaborator's switch is refused; `status` counts the rooms and `threads` prints the mode | [`integration.md`](integration.md) scenario 8; [`security.md`](security.md) A2, A12; [`unit.md`](unit.md) (`test_channels_mentions.py`) |
| R3 — the grammar after the mention (R3.1–R3.7) | verbs, keyword composition, `help` ephemeral, the fallthrough reply, a member mention as the roster token, the grammar read only after an address, the reply in the thread with the record's link | [`unit.md`](unit.md) (`test_channels_verbs.py`); [`integration.md`](integration.md) scenarios 4, 10, 11; self-review findings 1 and 3 |
| R4 — `record-context` (R4.1–R4.7) | the snapshot with names, links and the cap; scrubbed, defanged, neutralised, marked, enveloped; idempotent per thread; delivered under the context frame; `channels records` lists it | [`integration.md`](integration.md) scenarios 11–13, 22; [`security.md`](security.md) A4, A5, A9; [`snapshot.md`](snapshot.md) |
| R5 — `record-decision` (R5.1–R5.6) | the marked record with kind and rationale, never a gate answer, delivered under the decision frame; the empty text refused; `channels records` lists it | [`integration.md`](integration.md) scenarios 14, 22; [`security.md`](security.md) A6 |
| R6 — the shortcuts and the modal (R6.1–R6.6) | the manifest's two shortcuts; the context shortcut byte-equal to the typed mention; the modal opened on the trigger and its submission the typed decision; once per trigger; Slack's own payload shapes; the listener's routing | [`integration.md`](integration.md) scenarios 17–21; [`snapshot.md`](snapshot.md); [`security.md`](security.md) A3 |
| R7 — who may address the-loop, per act (R7.1–R7.5) | the roster's Slack id (CLI and keyword), the two tiers per act, a stranger's silence, a collaborator's reply as input at any gate, a roster on one item widening nothing on another | [`integration.md`](integration.md) scenarios 15–16; [`security.md`](security.md) A1, A2, A11; [`upgrade.md`](upgrade.md) |
| R8 — the change ships with its documentation (R8.1–R8.4) | the catalog rows, both schema copies, the options page, the guide, the capability docs, the command pages, the operating model; the docs pins pass | [`documentation.md`](documentation.md); [`upgrade.md`](upgrade.md) (`test_docs_parity.py`, `test_config_schema_parity.py`, `test_graph_parity.py`) |
| Non-functional — no new call per message, the cap, an upgrade that reads as before | the mention gate adds no call; one paged read per snapshot bounded by the cap; a pre-change declaration, roster and state file read unchanged | [`upgrade.md`](upgrade.md); [`checks.md`](checks.md) |
| T11 — the real-workspace walk-through | **not executed** in this environment (no workspace, no credentials); the procedure is written for the owner | [`manual.md`](manual.md) |
