---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#240"
status: approved             # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Testing plan: a read-only tmux observer blocks every comment the poller forwards

> Derived from [`bugfix.md`](bugfix.md) and [`design.md`](design.md), **before**
> [`tasks.md`](tasks.md) — each task's `_Test:_` names a row of the matrix below. Authored
> at the `test-planning` node and **completed at the `verification` node**.
>
> **This file is executable content.** It names commands an agent will run, so review it
> like code. Credentials appear **by reference only**; this plan needs none.

## What has to be proved, and the one thing that is hard about it

The bug reproduces only on tmux ≥ 3.7, and this repository's CI (and the machine this work
item was executed on) runs tmux 3.4. So the plan is split deliberately:

- **T1 proves the mechanism** on a live tmux, with a genuine read-only client attached —
  that an unbracketed `paste-buffer` of a carriage return submits, and that it is accepted
  while `send-keys` would be resolved against the observer. This is real, and it runs
  wherever tmux exists.
- **T2 pins the contract that makes the mechanism reachable** — the exact argv sequence.
  This is what protects the fix on machines where the failing tmux is not installed, and it
  is the reason R4.2 asks for the whole list rather than "no `send-keys`".
- **T11 records the version evidence** — that `send-keys` acquired the guard after 3.6 — so
  the claim in `bugfix.md` is checkable rather than asserted.

What cannot be proved here is stated once, in Verification results, rather than implied: no
tmux ≥ 3.7 is available in this environment, so the end-to-end refusal is demonstrated from
tmux's own source and version history, not from a failing command.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Integration (live tmux) | yes | An unbracketed CR paste submits a bracketed-pasted prompt, with **and** without a read-only client attached; a real `#{client_readonly}` client is present for the second half | manual procedure, output committed as evidence |
| T2 | Unit | yes | `TmuxRunner.deliver` issues exactly `load-buffer`, `paste-buffer -p`, `load-buffer`, `paste-buffer` — no `send-keys`, both buffers `-d`, both tempfiles unlinked | `uv run --project cli python -m pytest -q cli/tests/test_tmux_runner.py` |
| T3 | Unit | yes | `giveup_notice` builds a body carrying the marker, the attempts and the recovery, and takes no parameter that could carry a comment body | `uv run --project cli python -m pytest -q cli/tests/test_poller.py` |
| T4 | Integration (scenario) | yes | Gherkin-documented: a poller that exhausts the budget posts one notice; the ledger is written first; a failing post changes nothing | `uv run --project cli python -m pytest -q cli/tests/test_poller_integration.py` |
| T5 | Integration (scenario) | yes | The webhook→tmux pipeline's recorded argv no longer contains `send-keys` | `uv run --project cli python -m pytest -q cli/tests/test_tmux_runner_integration.py` |
| T6 | Security / abuse case | yes | No payload-derived text reaches an argv or the notice body; the notice carries the self-comment marker so it cannot resume the session | `uv run --project cli python -m pytest -q cli/tests/test_poller.py -k notice` |
| T7 | Contract (OpenAPI / GraphQL SDL) | n/a — no API surface changes. `deliver` is internal; the poller exposes no route. | | |
| T8 | End-to-end | n/a — an end-to-end run needs a live harness TUI, a GitHub repository and the daemon; T1 covers the tmux half against a real server and T4 covers the poller half against a real ledger. | | |
| T9 | UI / visual | n/a — no UI is touched. | | |
| T10 | Snapshot | n/a — no snapshot artifacts in this repository. | | |
| T11 | Manual exploratory | yes | tmux version archaeology: `send-keys` carries no read-only guard at 3.4/3.5a/3.6 and does at master; a read-only client is genuinely attached during T1 | manual procedure, output committed as evidence |
| T12 | Performance / load | n/a — one extra tmux round trip per delivered event, on a path that already writes a tempfile and probes liveness. Not measurable against the harness's own latency. | | |
| T13 | Accessibility | n/a — no user interface. | | |
| T14 | Migration / upgrade | n/a — no persisted shape changes. The poll ledger's `gaveUp` record is written exactly as before; the notice adds no field. | | |
| T15 | Regression suite | yes | The whole Python suite, to prove nothing else depended on `send-keys` or on the poller's give-up branch being silent | `uv run --project cli python -m pytest -q cli` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.3, R1.4 | A prompt pasted bracketed is submitted by an unbracketed CR paste, while `tmux list-clients` reports `client_readonly=1` |
| T2 | R1.2, R1.5, R3.3, R3.4, R4.1, R4.2 | The argv sequence; `-d` on both pastes; both tempfiles gone; unchanged `session_missing` behaviour |
| T3 | R2.1, R2.2, R2.3, R2.6 | `giveup_notice` content and signature |
| T4 | R2.1, R2.4, R2.5, R4.3 | `Scenario: A comment abandoned after the retry budget is reported on the ticket` · `Scenario: A give-up is recorded even when the ticket cannot be told` |
| T5 | R1.2, R3.1, R3.2 | `Scenario: An event is delivered into a live tmux session without send-keys` |
| T6 | R2.6, R2.2 | Negative: the notice for a comment whose body is `<script>`/marker-forgery text contains none of it, and carries `<!-- the-loop:agent-comment -->` |
| T11 | R1.1 (root cause) | Version archaeology + a real read-only client |
| T15 | R3.1, R3.2 | No regression anywhere else in the CLI |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none. T1 and T11 need a running `tmux` on the machine
  (`tmux 3.4` here) and a pty for the read-only attach, obtained with
  `script -q -c "tmux attach-session -r -t <session>" /dev/null`.
- **Fixtures & data:** none. The poller tests use the existing in-repo fakes (an injected
  `runner` in place of `gh`, a `WorkItemStore` under `tmp_path`).
- **Credentials:** none. No test invokes a real `gh`; `post_issue_comment` takes an
  injectable runner and every test supplies one.
- **Bring-up:** `uv sync` · **Tear-down:** `tmux kill-server` after T1/T11.
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T2, T3, T4, T5, T6, T15 | test summaries (counts, duration) and the red run that preceded the fix | `unit-and-integration.md`, `red.md` |
| T1, T11 | the live tmux transcript: session set-up, the read-only client's `#{client_readonly}`, the two pastes, the pane's own output, and the per-version `cmd-send-keys.c` counts | `manual.md` |

Nothing captured here contains a token, a hostname or personal data: the transcripts are
local tmux session names and pytest counts.

## Verification activities

- [x] T1 — live tmux: bracketed paste + CR paste submits, with a read-only client attached
- [x] T2 — `uv run --project cli python -m pytest -q cli/tests/test_tmux_runner.py`
- [x] T3 — `uv run --project cli python -m pytest -q cli/tests/test_poller.py`
- [x] T4 — `uv run --project cli python -m pytest -q cli/tests/test_poller_integration.py`
- [x] T5 — `uv run --project cli python -m pytest -q cli/tests/test_tmux_runner_integration.py`
- [x] T6 — `uv run --project cli python -m pytest -q cli/tests/test_poller.py -k notice`
- [x] T11 — tmux version archaeology, recorded with the commands that produced it
- [x] T15 — `uv run --project cli python -m pytest -q cli`
- [x] Red run — every new assertion, failing against unfixed code, committed before the fix

## Verification results

_Not yet executed._

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| | | | |

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed.
