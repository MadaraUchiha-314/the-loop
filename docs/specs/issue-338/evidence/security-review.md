# Security review — issue-338

> Mechanism: the-loop checklist (`security.review.mechanism: auto`; no security-review
> skill is invocable from this session's plugin set). Tier 3: below
> `security.review.humanSignOffMinTier: 4`, so no named human sign-off is required; the
> owner's PR approval is the gate.

## Threat model recap

The change is a rendering step inside the Slack channel: `digest.fit` sits between the
event the bus handed the renderer and the `chat.postMessage` call the channel already
makes. It reads the event's text and URL and nothing else; it writes nothing; it makes
no call. The text it reads is **untrusted** in every case (a collaborator's comment
mirrored as `comment.human`, any agent comment, an artifact excerpt). There is **no new
trust boundary**: the ledger is still the record every gate and control path reads
(decision-103 D1), and the digest is a view of it. No new grant, scope, token, config
surface beyond one enum key, or state. The mitigations, in the order they apply: every
pattern linear by construction; HTML comments removed and Slack broadcast sequences
neutralised before anything is drawn; the closing link taken from the event, never the
text; nothing outside the renderer imports the module.

## Abuse cases — disposition

| # | Abuse case | Closed by | Evidence |
|---|------------|-----------|----------|
| A1 | A comment crafted with thousands of unclosed `**`, `<!--`, `[`, fence openers, list markers and pipes makes the parser super-linear | every regex excludes its own delimiter or is line-anchored (`[^*\n]`, `[^\[\]\n]`, `[^()\s]`, `[^_\n]`, `[^~\n]`, and the backtick class for code spans); `strip_comments` is a forward scan; the abbreviation check reads a 12-character window, not the prefix; lazy continuation joins without re-scanning | `test_channels_digest.py::test_a_pathological_comment_digests_in_linear_time` (a 64 KB crafted comment, three digests plus the drawing plus the cut, under a 5-second wall clock; observed well under one second) |
| A2 | A mirrored comment carries `<!channel>` / `<!here>` / `<!everyone>` / `<!subteam^…>` and pages the workspace | `_neutralise` rewrites `<!` (not `<!--`) to `&lt;!` after the comment scan, on every path — short, digested and truncated alike, inside code fences too | `test_a_slack_broadcast_in_a_comment_is_neutralised` |
| A3 | A link in the text labelled as the full text is taken for the pointer | the footer is built from the event's `url` alone; the text's link is drawn as any link (`<url\|text>`), never promoted | `test_the_footer_links_the_event_never_the_text` |
| A4 | A misleading first question hides the decision; someone acts on the digest | the footer always links the record; no module but `slack.py` imports the digest — the pipeline, the bus, the ledger and the gates never see it | `test_nothing_but_the_renderer_reads_the_digest` (import lines of every `channels/*.py`) |
| A5 | An HTML comment that is not the-loop's survives into Slack | `strip_comments` is not marker-aware: every `<!-- … -->` goes | `test_a_foreign_html_comment_is_removed_too`, `test_html_comments_never_reach_slack` |

## Checklist

- [x] AuthN/AuthZ: unchanged — the digest runs after the bus decided what to post and to whom; who may speak on the channel and what a message may become are the pipeline's, untouched (`test_channels.py`, `test_channels_buttons.py`, `test_channels_integration.py` green).
- [x] Through the ledger, never around it: the digest adds no call and no path; a `comment.agent` mirror still writes nothing to the ledger (`test_a_long_agent_comment_reaches_slack_as_a_digest` asserts `records == []`).
- [x] Input validation: the text is untrusted and treated as text; every pattern is linear (A1); the drawn text is re-measured against the cap so the one rule that grows a text (`<!` → `&lt;!`) can never post a section over Slack's limit (`test_a_text_that_grows_past_the_cap_when_drawn_is_digested`).
- [x] Secrets: the digest reads no token and no environment; the fallback text carries what the section carries; no event is emitted with text (no new event type).
- [x] Fail closed, restated: an unknown `longMessages` resolves to the default with a warning and the schema refuses it at load (`test_an_unknown_long_messages_value_resolves_to_digest`, `test_configschema.py`); empty, whitespace, unterminated-fence and unterminated-comment inputs return a string, never raise (`test_empty_and_odd_inputs_never_raise`).
- [x] Faithfulness: every non-pointer line of a digest is the author's text after the drawing (`test_every_digest_line_is_the_authors`); code fences and spans are drawn as written (`test_code_is_drawn_as_written`).
- [x] Scope: no new bot scope, no manifest change, no new state file; both schema copies identical (`test_config_schema_parity.py`).
- [x] Evidence redaction: every URL, path and comment in the tests is a fixture; nothing here is real.

## Outcome

**Pass** on the autonomous checklist. No human sign-off required at tier 3; the pull
request's review is the human gate.
