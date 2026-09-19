---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#389"
---

<!-- Authored per the the-loop:writing skill. -->

# Security review: the mention is the address, and three acts each end in the session

> The `security-review` node's record, against `requirements.md` § Security
> considerations and `design.md` § Security design. See
> `skills/the-loop/reference/security.md`.

## Security review (gate)

- **Mechanism:** the-loop checklist (`reference/security.md` § The checklist), run over
  the diff by the session, with the round-1 self-review as the adversarial read.
- **Outcome:** findings fixed — two security-relevant findings of the self-review
  (rows 6 and 7 below), both closed with tests; no residual finding.
- **Findings:** the table below.
- **Human sign-off:** **required — risk tier 4** (`riskTier: 4` in `requirements.md`;
  the change touches the two schema copies and `.the-loop/`, and widens who may speak
  on a work item). Pending: a named approval of this review by @MadaraUchiha-314 on
  [PR #390](https://github.com/MadaraUchiha-314/the-loop/pull/390), distinct from the
  PR approval. The work item does not complete before it.

## The boundaries this work item touches

1. **A new address**: Slack's `app_mention` event. What was every message in a declared
   room is now only the message that addresses the-loop — the boundary *narrows* for
   rooms; a DM with the bot and a room an authorized user declared `--listen all` keep
   hearing plain messages.
2. **A new grammar**: a fixed verb list after the mention, composed into the configured
   keyword exactly as the slash command does; no model reads the text.
3. **Two new records** on the ticket, quoting other people's words — a thread snapshot
   and a decision — marked, scrubbed, defanged, neutralised, enveloped; delivered into the
   session under a preset frame that names the text untrusted.
4. **A second speaker tier**: a work-item collaborator known by Slack member id, input
   only; the binding acts stay the allow-list's.
5. **Two interactive payloads**: `message_action` and `view_submission`, authorized by
   their own `user.id`, their coordinates validated by shape.
6. **A read verb** over the ledger's comments, trusting only what the ledger credential
   itself posted.

## The checklist

| # | Item | Held? | Where |
|---|---|---|---|
| 1 | Every trust boundary in design § Security design is enforced where the design says | yes | `input_decision` before anything else; `speaker_for` before `_classify`; `Speaker.may` per act; `_shortcut_reply` validates coordinates by shape; `records_from_comments(author=login)` |
| 2 | Untrusted inputs validated at their ingress; named injection classes closed | yes | `_CHANNEL_ID_RE` / `_TS_RE` on every shortcut and modal coordinate; `strip_html_comments`, `neutralise_broadcasts`, `defang_control_keywords`, `scrub` on every quoted text; the `once` ring per trigger and view |
| 3 | Untrusted content cannot steer privileged behaviour | yes | the frames name the text untrusted and are composed from fixed words and ids (`core/sessions.py`); a marked record is never a gate answer (`test_a_decision_is_never_a_gate_answer`); a keyword inside a snapshot is defanged |
| 4 | No secrets in code, config, logs or fixtures | yes | the fixtures under `cli/tests/fixtures/slack/` carry placeholder ids and a `redacted-verification-token`; `status` prints token presence only; no new secret |
| 5 | AuthZ fails closed | yes | an empty allow-list and an empty roster deny everyone; a roster entry with a bad or missing id grants nobody; an unknown `listen` reads as `mentions`; an unreadable login makes `channels records` say so |
| 6 | Least privilege | yes | one new bot scope, `app_mentions:read`, measured by the probe; no new token; the read verb needs the `gh` login it already has |
| 7 | Every abuse case has a passing negative test | yes | A1–A12 in `test_channels_mentions_security.py` ([`security.md`](security.md)) |
| 8 | New dependencies justified | n/a | none added |

## Findings

| # | Finding | Severity | Disposition |
|---|---|---|---|
| 6 | `channels records` trusted the marker alone: a ticket commenter could paste an authorized user's "decision" | medium | fixed in `5f8479e` — only the ledger login's comments are records; the author is printed on every row; tests |
| 7 | A shortcut on an unbound channel told a stranger "Nothing recorded (unmapped)"; the decision modal opened without the grant | low | fixed in `6f71041` — silence for `unmapped`, the grant checked before the form; tests |

No residual finding. Nothing was accepted as a risk, no guard weakened, no allow-list
entry added.

## Verdict

Pass, pending the tier-4 human sign-off named above.
