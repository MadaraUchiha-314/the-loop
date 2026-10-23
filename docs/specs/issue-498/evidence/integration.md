# Integration evidence — T2 / T8 (issue-498)

Commit `08dbf02a`.

| Command | Outcome |
|---------|---------|
| `uv run pytest cli/tests/test_routing.py cli/tests/test_reactions.py cli/tests/test_reactions_integration.py cli/tests/test_control_integration.py` | **291 passed** |

| Scenario | Requirement | Result |
|----------|-------------|--------|
| `test_an_ambiguous_comment_reaches_the_live_session_and_executes_nothing` | R2.1–R2.3 | PASSED — neither paused nor stopped; one delivery |
| `test_a_comment_discussing_two_commands_in_prose_reaches_the_session` | R1.2 (the #496 comment) | PASSED — no command, delivered |
| `test_an_ambiguous_comment_on_a_paused_session_is_still_suppressed` | Security: forwarding bypasses no gate | PASSED — stays paused, settled `session-paused`, nothing delivered |
| `test_an_ambiguous_comment_does_nothing_at_all` (updated) | AC1.4 of issue-106 + R2 | PASSED — no command recorded, delivered once |
| `test_conflicting_keywords_are_delivered_as_conversation` (reactions) | R2 | PASSED — no `confused` reaction, delivered |

Slack surface (R1.5): `test_bus*.py`, `test_channels*.py`, `test_selection_control.py` —
**153+ passed** after the relay record was changed to put the person's words first
(design §1).
