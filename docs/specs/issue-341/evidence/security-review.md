# Security review — issue-341

> Mechanism: the-loop checklist (`security.review.mechanism: auto`; no security-review
> skill is invocable from this session's plugin set). Tier 3: below
> `security.review.humanSignOffMinTier: 4`, so no named human sign-off is required; the
> owner's PR approval is the gate.

## Threat model recap

The change lets a Slack kickoff message choose **which repository** its issue is opened
in, by a `<repo>:` prefix on its first line. The prefix is untrusted text; everything
else about the pipeline is unchanged. There is **no new trust boundary** and no new
grant, scope, config key, event type or state file.

The boundary that *moves* is the set of repositories a kickoff may write to: from one
config value (`kickoff.repo`) to a set of config values (`kickoff.repo` plus every
`repos` entry of every `github` source in `polling.sources`). Both halves of that set
are the operator's own, and the value handed to the issue writer is always a **declared
string** — `DeclaredRepo.declared` — never the member's text. The grammar the prefix
must satisfy (one to three `/`-separated segments, each starting alphanumeric) cannot
express a shell, path or argv metacharacter, and every declared entry is validated
through `is_github_host` / `is_github_name` before it can be a candidate.

One new disclosure exists: a refusal names the declared repositories so the member can
retype. It is bounded by placing the whole resolve-and-refuse step **below** the
allow-list — an unlisted member's kickoff is dropped in silence, as it was, and is told
nothing at all.

Mitigations, in the order they apply: the `work-item.create` grant; the allow-list; the
prefix grammar; resolution against the declared set only; refusal rather than a guess;
a reply composed from fixed words, the quoted prefix and declared names.

## Abuse cases — disposition

| # | Abuse case | Closed by | Evidence |
|---|------------|-----------|----------|
| A1 | An unlisted member posts `owner/repo: …` and is answered, or learns the repository list | the allow-list runs before the reaction, the resolve and the reply; the drop is silent (`unauthorized-actor`) | `test_channels_integration.py::test_an_unlisted_members_kickoff_is_told_nothing` (nothing created, no reaction, no reply in its thread) |
| A2 | An undeclared repository is named and the fallback silently absorbs it | a **qualified** prefix that matches no declared key returns `unknown-repo`, which is not `ok`, so nothing is published | `test_channels_kickoff.py::test_an_undeclared_qualified_prefix_is_refused`, `::test_an_undeclared_qualified_prefix_never_falls_back` |
| A3 | Shell, path or argv metacharacters in the prefix reach a command | `PREFIX_RE` cannot match them, so they are never read as a prefix; and what reaches `comments.create_issue` is always a config string | `::test_metacharacters_never_parse_as_a_prefix` (`../etc/passwd`, `$(id)`, `a;b`, `o/r --repo evil/x`, `-flag`), `::test_only_a_declared_slug_reaches_the_writer` |
| A4 | A foreign host (`evil.example/o/r:`) selects something | the prefix's key is built with `parse_repo_path` against this instance's host and compared to declared keys only, so it matches nothing and is refused | `::test_a_foreign_host_matches_nothing` |
| A5 | The refusal reply leaks a token, a member id, a channel id or the member's prose | `refusal_text` composes fixed sentences, the quoted prefix and declared repository names — nothing else | `::test_the_refusal_carries_no_token_or_other_config` (`xoxb`, the message text, `UHUMAN`, `C123` all absent) |
| A6 | A malformed or unreadable `polling` section widens the set | every read is guarded and contributes nothing on failure; entries that fail `parse_repo_path` are skipped | `::test_a_malformed_polling_section_widens_nothing`, `::test_a_malformed_declared_entry_is_skipped`, `::test_a_non_github_source_is_ignored` |
| A7 | The grant is absent and a prefixed message is still read or answered | `kickoff_enabled` still requires `work-item.create`; without it nothing is fetched and a socket message is not treated as a kickoff | `::test_without_the_grant_nothing_is_read_or_answered`, `test_bus.py::test_kickoff_needs_the_grant_not_a_repo` |

## Fail-closed check

| Configuration | Outcome |
|---------------|---------|
| no `channels` section / `enabled: false` / no `channel` | `kickoff_enabled` false — nothing read |
| no `work-item.create` grant | `kickoff_enabled` false — nothing read, whatever the prefix |
| empty allow-list | every kickoff dropped, silently |
| declared set empty **and** no `kickoff.repo` | every kickoff refused (`no-target`), nothing created |
| `polling` unreadable | the set is whatever could be read — smaller, never larger |

## Residual risk (accepted, recorded in decision-120)

A **bare** prefix that is a typo (`slim-gim:`) is not refused: it matches nothing, is
judged not to be a prefix, and the message lands in `kickoff.repo` with the typo in its
title. This is deliberate — refusing it would start rejecting ordinary first lines such
as `fix: …` on every install that works today — and is bounded by the confirmation
reply naming the created ref (`Opened owner/repo#N`) and by qualified prefixes being
strict. The failure mode is the pre-existing one (an issue in the fallback repository),
never a write to an undeclared repository.
