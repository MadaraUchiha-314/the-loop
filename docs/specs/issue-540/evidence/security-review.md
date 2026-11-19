---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#540"
---

# Security review: prompts in Markdown files, application strings in one JSON catalog (issue-540)

## Security review (gate)

- **Mechanisms:** (1) the-loop checklist (`reference/security.md`), checked against
  `git diff origin/main -- cli/`. (2) The harness's built-in `/security-review`, run as a
  separate pass. A sub-agent reviewed the full diff against the vulnerability categories
  and false-positive exclusions; only findings at confidence 8 or above would be kept.
- **Risk tier:** 3. No sensitive path is touched: no schema, `.the-loop/**`, workflow,
  auth, secret or credential path. The `promptTemplate` schema descriptions were left
  unchanged on purpose. No named human security sign-off is required.
- **Checklist outcome:** pass, with no findings.

| # | Item | Result | Evidence |
|---|------|--------|----------|
| 1 | Design boundaries enforced | pass | The boundary that matters is untrusted payload text vs prompt instructions. Prompt order and labelling are unchanged: 66,174 old-vs-new renders are byte-identical (`verification.md` V2), and the directive still renders above the labelled payload excerpt. |
| 2 | Untrusted input constrained at ingress | pass | Prompt names and catalog keys are code literals, or built from fixed tuples (`prnotice/decline/<code>` over five literal codes; `sessions/frame-<kind>` over two). Untrusted codes (`item.error`, `event.event_type`, a refusal reason) are only dict keys looked up with `.get`/`in`, as on `main`. `_NAME` rejects `..`, absolute and empty-segment names (`test_names_outside_the_directory_are_refused`). |
| 3 | Untrusted content cannot steer privileged behaviour | pass | Every format string is packaged text (a prompt file or `en.json`). Untrusted values (Slack/ticket fields, CI check names and URLs, gate messages, MCP arguments, the dossier) are keyword *values*. `str.format` and `string.Template.safe_substitute` are single-pass, and no rendered output is used as a format string again; the sub-agent traced every composition. No packaged text uses attribute or index fields (`{x.y}`, `{x[0]}`). Tests: `test_untrusted_placeholders_in_a_payload_stay_literal`, `test_values_are_inserted_literally`. |
| 4 | No secrets | pass | Prompt and catalog files are maintainer-authored prose. No credential is read or rendered by the new modules. The dossier's allow-list and `scrub` are unchanged. |
| 5 | Fails closed | pass | A missing prompt raises `FileNotFoundError` naming the file. Most prompts load at import, so a broken install fails at daemon start. A missing `en` key raises `KeyError`, and an invalid `en.json` raises. Only a non-`en` locale degrades, to `en` with a warning, and the locale is trusted configuration. |
| 6 | Least privilege | pass | No new permission, network call, subprocess or argv construction. `mcp_call` builds the same prompt and argv as before. |
| 7 | Abuse cases have negative tests | pass | Abuse 1 (`$x`/`{x}` in a payload): `test_untrusted_placeholders_in_a_payload_stay_literal`, and the render grid fed `{x}`/`$x` values. Abuse 2 (keys from code): `test_every_key_the_code_looks_up_exists_with_matching_placeholders` (literal keys only). Abuse 3 (`$interaction_directive` omitted): the existing `apply_directive` tests in `test_interaction.py`, unchanged and green. Traversal: `test_names_outside_the_directory_are_refused`, `test_a_locale_name_cannot_leave_the_directory`. |
| 8 | New dependencies | pass (n/a) | None. `importlib.resources`, `json`, `functools`, `re` and `string` are stdlib; `cli/pyproject.toml` is unchanged. |

## Built-in `/security-review`

**Outcome:** no findings. The sub-agent checked:

- whether untrusted data can become a format string: no, every format string is packaged
  text;
- whether any output is formatted twice: no, the composed pieces in `framed_record`,
  `render_graph_context`, `render_assignment`, `prnotice`, `attachments`, `cimonitor` and
  the dossier are all passed as values or joined;
- whether input can pick a prompt name or catalog key: no;
- whether anything fails open: no. The trust checks (`defang_control_keywords`,
  `scrub`, `_is_https_url`, `_identifier`) all still run before rendering.

No candidate reached confidence 8, so the false-positive filtering stage had nothing to
filter.
