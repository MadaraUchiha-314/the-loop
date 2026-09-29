---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#433"
---

# Self-review: two bugs in the `hooks[]` declaration loader (issue-433)

> `the-loop critic policy` on this machine: `selfReviewCount: 3`,
> `stopOnNoNewFindings: true`; no critic CLI is configured in this cloud checkout, so the
> critic rounds are **unavailable** and do not count toward `criticReviewCount`
> (`reference/reviewing.md` § Running a critic round). The self-review read the change
> adversarially in three passes; round 3 found nothing new, which is the stop rule.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | self (scope read) | new findings | (a) the first draft of `_normalise_keys` was a bare dict comprehension, which would have **silently kept the last value** when an entry carried both `on:` and `"on":`. Two values for one key is a malformed entry, and the loader's rule is that a malformed entry is refused naming it, never read as something else — added the refusal and a test. (b) The ticket's fix for bug 2 sorted with `key=str`; `str(1) == "1"` and `str("1") == "1"` collide and the rendering would not distinguish them. Sorted and rendered with `repr`, which is what the message shows | `declaration.py` `_normalise_keys`; T2, T3 |
| 2 | self (mechanism read) | new findings | (c) considered mapping the other YAML 1.1 booleans too (`False → "off"`, as the graph loader does). Rejected: `off` is not a hooks key, so mapping it would only change which unknown key the refusal names; kept the normalisation to the one key that exists. (d) considered normalising in `read_declaration` for every entry rather than in `_read_entry`; rejected because the `name` check has to run first so the refusal can name the entry, and `_read_entry` owns that ordering. (e) checked that the existing `test_an_unknown_key_is_refused` still holds under the new quoting (`'bogus'` contains `bogus`); it does, and the new tests assert the quoted form so the wording is pinned | `bugfix.md` § The fix, § Out of scope |
| 3 | self (adversarial read) | zero (converged) | — | — |
| — | critic | unavailable | no critic CLI configured on this machine | — |

## Questions asked of the diff, and their answers

- **Does the test prove the fix or a stub?** The fix. T1 runs `yaml.safe_load` for real
  on the options page's first entry and asserts the boolean key arrived before asserting
  the loader read it back; T4 goes through a file on disk, `load_cli_config` and the
  `hooks` command. Nothing is monkeypatched on the path under test.
- **Can the normalisation ever widen the declaration?** No. It maps one key name; the
  value still passes `_read_on`, which is unchanged and still refuses a non-catalog
  point (the existing abuse-case test). No other key is touched.
- **Is the both-spellings refusal reachable from YAML?** Yes: `on: [...]` and
  `"on": [...]` in one mapping produce the keys `True` and `"on"` under PyYAML, which
  does not reject them as duplicates because they are different keys to it. That is
  exactly the case the refusal is for.
- **Is the ordering right?** `_normalise_keys` runs after the `name` check, so a
  nameless entry is still refused as `hooks[i]`, and before the unknown-key, foreign-key
  and `_read_on` rules, so all of them see `on`. Verified by T1 (the `required: true`
  in the documented entry is read after normalisation) and T2.
- **Does the negative control show the bug?** Yes: with `declaration.py` stashed, the
  seven new tests fail with the ticket's two `TypeError` texts, and the command test
  records the exact `could not read …: TypeError: sequence item 0` line the ticket
  quotes. See `verification.md` § T5.
- **Was the wider option worth taking?** The graph loader's `_normalise_edge_keys` and
  this function could share a helper. Two call sites with different key sets (`on`/`off`
  vs `on`) is below the rule of three; the shared helper is a refactor for a third
  occurrence, noted in `documentation.md`.

## What a reviewer should push on

The one judgement is **normalise rather than rename or quote** (`bugfix.md` § The fix).
The alternatives cost more than they buy: a rename one release after the key shipped, or
teaching every operator a YAML trap and editing the schema description to do it. If the
reviewer would rather the docs quoted the key as well, belt and braces, that is a
one-line follow-up to the two pages and the shipped example, and does not change the
loader.
