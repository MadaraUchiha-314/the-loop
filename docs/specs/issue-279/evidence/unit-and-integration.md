# Evidence: the review-loop suite (T1, T2, T8)

Captured 2026-08-24, on the work item's branch, from `cli/`.

## The whole suite (T1 — unit + hooks + keyword + loop selection)

```console
$ uv run pytest tests/test_graph_review.py -q
........................................................                 [100%]
56 passed in 0.26s
```

(55 at first verification; +1 after the security review's marker-spoofing fix added
`test_a_spoofed_marker_cannot_suppress_the_template`.)

## The walk and the targeting scenarios (T2 — integration)

```console
$ uv run pytest tests/test_graph_review.py -k "Walk or target" -q
.....                                                                    [100%]
5 passed, 50 deselected in 0.32s
```

Scenario names (Gherkin docstrings in `cli/tests/test_graph_review.py`):

- `Scenario: brief, review, follow-up rounds, done` — the full walk
  `review-brief → review → follow-up → review → follow-up → complete`.
- `Scenario: no brief, no review` — the template is posted, the gate waits, an
  authorized brief releases it.
- `Scenario: the-loop review on a pull request binds to the pull request itself` —
  through the real dispatcher, with a linked work item present.
- `Scenario: PR-first targeting is review's alone` — `the-loop start` on the same
  payload still binds to the linked work item.
- `Scenario: an unauthorized "the-loop review" arms nothing`.

## The abuse cases (T8 — security)

```console
$ uv run pytest tests/test_graph_review.py \
    -k "unauthorized or refused or invented or self_authored or cannot or empty_allowlist or prose" -q
.........                                                                [100%]
9 passed, 46 deselected in 0.06s
```

One negative test per abuse case in `requirements.md` §Security considerations:
unauthorized arming (1), two-command refusal (2), unauthorized brief (3),
self-authored brief and the harness ending its own review (4 — `classify-adhoc-reply`'s
own suite carries the self-authored "done"), invented loop name (5), unauthorized
follow-up (6 — carried by the reused hook's suite, `test_graph_adhoc.py`), plus the
prose-boundary tests on the keyword and the empty-allowlist fail-closed read.
