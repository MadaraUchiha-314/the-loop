---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#462"
---

# Security review: CI monitoring and self-healing (issue-462)

- **Mechanism:** the-loop checklist (`reference/security.md`), checked against the diff.
- **Outcome:** pass.
- **Findings:** none.
  - *New network path:* `GitHubClient.job_log_tail` makes two requests per log. The
    first is the API's `GET …/actions/jobs/{id}/logs`, authenticated, through PyGithub's
    `requestBlobAndCheck`, which does not follow the `302`. The second fetches the signed
    `Location` with the standard library. `_urlopen` builds its opener from exactly the
    HTTPS, proxy, redirect and error handlers, so an `http:`, `file:` or `ftp:` URL,
    whether given directly or reached by redirect, has no handler and fails. The request
    carries no `Authorization` header, so the token never leaves the API host. A test
    asserts a `file:` redirect is refused with no fetch.
  - *Bounded cost:* at most five logs per call. Each is streamed in 64 KiB chunks, only
    the last 256 KiB is held, and reading stops at 32 MiB (tested with lowered caps). The
    budget remembers at most 1,024 checks, least recently seen evicted first (tested).
  - *Input validation:* `job_id` must be a positive integer (`_number`), `owner`/`repo`
    pass `_coordinates`, and the ref's host passes `_trusted`. A bad job id, an untrusted
    host, a bare PR number without `--work-item`, and a negative `--log-lines` are all
    refused before any request (tested).
  - *Prompt injection:* job logs and check summaries are written by code the pull request
    controls. The log reaches the session only when it runs `pr checks`. The CI section
    the gate adds carries the check's name, conclusion, SHA, URL and PR, not its summary
    or log, and says the log is untrusted. The event excerpt below the section is the
    pre-existing allow-listed one (issue-243), already framed as UNTRUSTED. The skill
    (`SKILL.md`, `workflow.md` § Self-healing CI) repeats the rule.
  - *Suppression:* the gate can only withhold a delivery the session would otherwise have
    received; it creates none. Every withheld event is logged (`dispatch.dropped` with
    its reason and check). A check's count resets only on a passing run of the same check
    name on the same pull request, and a pass means the check passed.
  - *Authorization:* CI events are actor-less, so the gate sits behind the existing
    ingress guards and adds no way in. `pr checks` is read-only, so it is open like
    `pr status`. No write path changed.
  - *Secrets in logs:* GitHub Actions masks registered secrets before storing a log.
    `pr checks` returns what `gh run view --log` already returned to the same token.
- **Risk tier:** 3. It changes which events reach a session and adds a read verb. No
  sensitive path (auth, secrets, CI config, migrations) is touched. That is below the
  tier-4 threshold for a named human security sign-off; the PR approval is the human
  gate.
