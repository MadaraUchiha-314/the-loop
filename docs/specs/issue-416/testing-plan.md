---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#416"
status: in-review            # draft | in-review | approved
approvedBy: []
overrides: {}
riskTier: 3
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: multi-modal messages are forwarded to the session, never parsed by the loop

> Derived from [requirements.md](requirements.md) and [design.md](design.md), before
> `tasks.md`. Authored at `test-planning`, completed at `verification`.

## What is testable here, and what is not

Everything this work item adds is code on a path a test already drives: the Socket Mode
handler and the poll readers take a fake Slack client, the dispatcher takes a `FakeTmux`,
and the one new network call takes an injected opener. So the matrix is mostly automated.
What automation cannot reach is a **real** Slack workspace producing a **real**
transcript, and a **real** private-repository asset answering a bearer token. Neither
exists in this environment; both are the operator's to confirm on first use, and the
plan says so rather than pretending a fixture proves them.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `attachments.py` in isolation: `kind_of`, `safe_name`, `vtt_to_text`, `github_attachment_urls`, `render_section`, `record_lines`; `fetch_url` against a fake opener (auth header only on allowed hosts, manual redirects, the cap, timeouts); `slack_attachments` with a fake fetch and a fake `files.info` (the transcript wait); `attachment_findings` | `uv run --project cli python -m pytest -q cli/tests/test_attachments.py` |
| T2 | Integration (scenario) | yes | The two paths end to end with fakes at the edges: a Socket Mode message with an image → delivered text and ledger record; a voice note → Slack's transcript in both; a file-only message delivered; a poll-read reply with files; a `record-context` snapshot naming a file; a kickoff body with 📎 lines; a GitHub `issue_comment` with an asset URL → the pasted prompt; an asset with no token; a re-seen asset reused; the manifest and the probe finding | `uv run --project cli python -m pytest -q cli/tests/test_attachments_integration.py` |
| T3 | Contract (OpenAPI / GraphQL) | n/a — no API surface changes; `POST /api/v1/sessions/reply` keeps `text: str`. | | |
| T4 | End-to-end | n/a — a real Slack workspace, app install and phone are not available here; the first-use check is manual (T11) and named as the operator's. | | |
| T5 | UI / visual | n/a — no rendered surface. | | |
| T6 | Snapshot | n/a — the section and record formats are asserted line by line in T1, which is the snapshot with the reasons attached. | | |
| T7 | Performance / load | n/a — the cost is bounded by constants (ten files, 25 MiB, 30 s, three transcript re-reads) and asserted as such in T1; there is no throughput budget to measure. | | |
| T8 | Security / abuse case | yes | Each abuse case from `design.md` § Security design as a negative test: off-host URL not fetched and no token sent; redirect off-host refused with the credential unsent; over-cap not saved; hostile name stays inside the directory; the section frames everything untrusted; a stranger's file never fetched; the record carries the permalink, never `url_private` or a path | `uv run --project cli python -m pytest -q cli/tests/test_attachments.py cli/tests/test_attachments_integration.py -k "off_host or redirect or cap or hostile or untrusted or stranger or permalink"` |
| T9 | Accessibility | n/a — no rendered surface. | | |
| T10 | Migration / upgrade | yes | The new `StateLayout.attachments_dir` is classified in `GENERATED_PATHS` and on the state page; the manifest still satisfies every existing manifest assertion; a prompt with no attachment is byte-identical to before; an `InboundReply` built without `files` behaves as before (every existing channel test) | `uv run --project cli python -m pytest -q cli/tests/test_state_portability.py cli/tests/test_channels_mentions.py cli/tests/test_channels_dm.py cli/tests/test_doctor_slack.py cli/tests/test_interaction_integration.py cli/tests/test_channels.py` |
| T11 | Manual exploratory | yes — **operator's, on first use** | With a real app carrying `files:read`: post an image in a bound thread and see the session read it; record a voice clip and see Slack's transcript in the record; drop a screenshot in a private-repository comment and see the path in the pane | A Slack workspace with the re-installed app; not available in this environment |
| T12 | Documentation parity | yes | The docs site's parity assertions still hold; the state page classifies the new path; the guide's manifest copy carries `files:read` | `uv run --project cli python -m pytest -q cli/tests/test_docs_parity.py cli/tests/test_state_portability.py` and `make lint` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.2, R6.2 | `Scenario: a file's kind, safe name and saved path are derived from its metadata` |
| T1 | R2.1 | `Scenario: WebVTT captions become plain text with cues stripped` |
| T1 | R4.1 | `Scenario: every GitHub asset URL shape in a body is found once` |
| T1 | R1.2, R1.4, R1.5, R2.3 | `Scenario: the section names kind, path, link, reason and frames everything untrusted` |
| T1 | R3.1, R3.2 | `Scenario: the record lines carry the permalink and the transcript, never a path` |
| T1 | R2.2 | `Scenario: a processing transcript is re-read a bounded number of times` |
| T1 | R1.6 | `Scenario: files past the cap of ten are named, not fetched` |
| T1 | R5.2, R5.3 | `Scenario: a missing files:read is one finding; unreadable scopes are none` |
| T8 | abuse 1 | `Scenario: a file URL off Slack's host is not fetched and no token is sent` |
| T8 | abuse 2 | `Scenario: a redirect off the allowed hosts is refused with the credential unsent` |
| T8 | abuse 3 | `Scenario: a file over the cap is not saved` |
| T8 | abuse 4 | `Scenario: a hostile file name stays inside the work item's directory` |
| T8 | abuse 6 | `Scenario: a stranger's file is never fetched` |
| T2 | R1.1–R1.4, R3.1 | `Scenario: a Slack image reaches the session as a path and the ticket as a link` |
| T2 | R2.1, R3.1 | `Scenario: a voice note reaches the session and the ticket as Slack's transcript` |
| T2 | R1.3 | `Scenario: a message that is only an image is delivered` |
| T2 | R1.1 | `Scenario: a poll-read reply carries its files` |
| T2 | R1.7 | `Scenario: a gate answer with a file names it on the record` |
| T2 | R3.3 | `Scenario: a recorded thread names the files its messages carried` |
| T2 | R3.4 | `Scenario: a kickoff with a file links it from the issue body` |
| T2 | R4.1, R4.2, R4.5 | `Scenario: a GitHub comment's screenshot reaches the pane as a path after the excerpt` |
| T2 | R4.2, R4.3 | `Scenario: a private asset with no token is named, not fetched` |
| T2 | R4.4 | `Scenario: an asset seen again is reused from disk` |
| T2 | R5.1 | `Scenario: the manifest declares files:read` |
| T10 | R6.1 | `test_state_portability.py` — classified and documented |
| T11 | R1, R2, R4 | The operator's first-use check, three steps |

## Verification environment

- **Repositories:** this repo only.
- **Services / containers:** none. No Slack workspace is contacted; no network call is
  made — every fetch in every test goes through an injected fake, and the unit tests
  assert that the real opener is never constructed.
- **Fixtures & data:** hand-built Slack file objects (an image, an audio clip with a
  `transcription` block and a `vtt` URL) and GitHub comment payloads, in the test
  modules; the existing `FakeSlackClient` and `FakeTmux` doubles.
- **Credentials:** **none are required, and none are used.** Tests set the bot token
  variable to a dummy value where the code reads it for presence; referenced by name
  only: `THE_LOOP_SLACK_BOT_TOKEN`, `GH_TOKEN`.
- **Bring-up:** `uv sync` · **Tear-down:** none (`tmp_path`).
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate on the ticket.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T8 | the two new modules' output, red first then green, with the Gherkin scenario titles | `verification.md` |
| T10, T12 | portability, parity, manifest and prompt-identity suites' output | `verification.md` |
| All | the full `make check` run | `verification.md` |
| T11 | the operator's procedure, written down; marked **not executed here** | `verification.md` |
| security | the security review against the abuse cases | `security-review.md` |
| — | self-review against the requirements | `self-review.md` |
| — | capability-doc and guide updates | `documentation.md` |
| — | the pull request opened for this work item | `pull-requests.md` |

**Redaction.** No credential exists in this environment; the dummy values the tests set
are literals in the test source. Any absolute path naming the container's home directory
in captured output is elided.

## Verification activities

- [ ] T1 — `uv run --project cli python -m pytest -q cli/tests/test_attachments.py`
- [ ] T2 — `uv run --project cli python -m pytest -q cli/tests/test_attachments_integration.py`
- [ ] T8 — the abuse-case selection: `uv run --project cli python -m pytest -q cli/tests/test_attachments.py cli/tests/test_attachments_integration.py -k "off_host or redirect or cap or hostile or untrusted or stranger or permalink"`
- [ ] T10 — `uv run --project cli python -m pytest -q cli/tests/test_state_portability.py cli/tests/test_channels_mentions.py cli/tests/test_channels_dm.py cli/tests/test_doctor_slack.py cli/tests/test_interaction_integration.py cli/tests/test_channels.py`
- [ ] T12 — `uv run --project cli python -m pytest -q cli/tests/test_docs_parity.py` and `make lint`
- [ ] All — `make check`
- [ ] T11 — the operator's first-use check (not executable here; procedure recorded)

## Verification results

Not yet executed.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with comments.
