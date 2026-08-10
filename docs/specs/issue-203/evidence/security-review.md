# Evidence — security review (issue-203)

Mechanism: the built-in **security-review skill**, which `security.review.mechanism: auto`
selects when it is available (it is, in this session). Scope: the lines this work item
changes — `.the-loop/cli-config.schema.json`, `cli/the_loop/graph/integrations/base.py`,
`cli/the_loop/graph/integrations/slack.py`. The skill's own diff command resolves against
`origin/HEAD`, which in this fresh checkout spans far more than this branch; the review
below is scoped to this work item's diff, which is what the gate is about.

## Findings

**None at HIGH or MEDIUM.** No new vulnerability of any reported category is introduced.

| Category examined | Verdict |
|---|---|
| Injection / code execution | The value reaches `urllib.request.Request(url, …)` and `slack_sdk`'s `WebhookClient(url=…)`. No shell, no path, no template, no eval, no deserialization. |
| Data exposure | The URL is never logged and never appears in an exception. `_url()`'s `IntegrationError` names the **config key and the env var**, not the value — pinned by `test_the_failure_names_both_remedies_and_not_the_url`, which asserts `hooks.slack` is absent from the message. |
| Input validation | `"type": "string"` under a `slack` object that keeps `additionalProperties: false`. A mapping, list or number is refused at validation. `str(section.get("url") or "")` collapses null/missing/blank to absent. |
| AuthN / AuthZ | Untouched. No gate, allowlist or credential check reads or is influenced by the new key. |
| Crypto / secrets | No algorithm, key or randomness involved. |

## The one question worth writing down: can an untrusted repository set it?

Asked because the answer is not obvious. `notify` reads `ctx.config["integrations"]`, which
`graph/bootstrap.py` populates from the **CLI config**, resolved by
`cli_config.default_cli_config_path()`:

```python
env = os.environ.get(CLI_CONFIG_ENV)          # 2. $THE_LOOP_CLI_CONFIG
if env: return Path(env)
cwd_candidate = Path(".the-loop") / CLI_CONFIG_FILENAME   # 3. ./.the-loop/cli-config.yaml
if cwd_candidate.is_file(): return cwd_candidate
return Path.home() / ".the-loop" / CLI_CONFIG_FILENAME    # 4. ~/.the-loop/…
```

Candidate 3 is **cwd-relative**, so a checkout can supply the file when a verb runs inside
it. That is a deliberate, documented property (the schema says so: "an operator may choose
to track it in a specific repo") and it long predates this work item — the CLI config is a
trusted input by construction, exactly as the harness config is a trusted input only in
the ⟶ direction (decision-044).

What matters for this gate is whether `url` **widens** that trust. It does not, by some
distance: the same file already carries `integrations.github.cli.binary` — a program name
the daemon executes — and `integrations.github.api.baseUrl`, the host a GitHub **token** is
sent to. Against an attacker who already controls the CLI config, the ability to redirect
one channel's notification text is not the marginal capability; arbitrary execution and
token exfiltration are, and both are pre-existing. Adding a webhook URL to a file that
already names an executable does not move the boundary.

The pre-change alternative is not a mitigation either: `urlEnv` under attacker control
lets them point resolution at a different variable, which is unset, so delivery stops.
That is availability, not confidentiality, and it is out of scope by the review's own
exclusions.

**Conclusion: no finding.** The genuine cost of this change is the one the requirements,
the decision record and the docs already state in the open — an operator who sets `url`
commits a bearer credential to a file, and git history keeps it. That is a documented
trade-off the operator elects, not a vulnerability the code imposes: nothing writes the key
on their behalf, `urlEnv` remains the default and the recommendation, and the carve-out
stops at Slack's webhook URL — `github.api.tokenEnv` and `webhooks.ghWebhook.secretEnv`
stay env-only.

## Human sign-off

Risk tier 4 meets `security.review.humanSignOffMinTier: 4`, so this review does **not**
close the gate on its own. A named sign-off from @MadaraUchiha-314 is requested in the PR
briefing and recorded in [`../execution-log.md`](../execution-log.md) § Security review.
