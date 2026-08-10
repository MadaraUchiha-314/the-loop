# Evidence — unit tests (T1) and abuse cases (T9)

Work item: issue-194 · captured 2026-08-10 · no network, no credentials.

## T1 — `uv run --project cli python -m pytest -q cli/tests/test_graph_refs.py`

```text
.................................                                        [100%]
33 passed in 0.07s
```

### The 33 cases, by name

```text
tests/test_graph_refs.py::test_derive_ref_builds_the_ref_the_integration_expects
tests/test_graph_refs.py::test_derive_ref_round_trips_with_the_ingress_translation
tests/test_graph_refs.py::test_derive_ref_output_parses_as_a_ref_and_as_a_split
tests/test_graph_refs.py::test_derive_ref_ignores_leading_and_trailing_whitespace
tests/test_graph_refs.py::test_derive_ref_refuses_non_issue_ids[draft-some-slug]
tests/test_graph_refs.py::test_derive_ref_refuses_non_issue_ids[194]
tests/test_graph_refs.py::test_derive_ref_refuses_non_issue_ids[issue-]
tests/test_graph_refs.py::test_derive_ref_refuses_non_issue_ids[issue-1x]
tests/test_graph_refs.py::test_derive_ref_refuses_non_issue_ids[issue-1/../issue-2]
tests/test_graph_refs.py::test_derive_ref_refuses_non_issue_ids[ISSUE-1]
tests/test_graph_refs.py::test_derive_ref_refuses_non_issue_ids[]
tests/test_graph_refs.py::test_derive_ref_refuses_malformed_origin_repo[]
tests/test_graph_refs.py::test_derive_ref_refuses_malformed_origin_repo[octo]
tests/test_graph_refs.py::test_derive_ref_refuses_malformed_origin_repo[/repo]
tests/test_graph_refs.py::test_derive_ref_refuses_malformed_origin_repo[octo/]
tests/test_graph_refs.py::test_derive_ref_refuses_malformed_origin_repo[octo/repo/sub]
tests/test_graph_refs.py::test_derive_ref_refuses_malformed_origin_repo[ghe.example.com/octo/repo]
tests/test_graph_refs.py::test_derive_ref_refuses_malformed_origin_repo[octo/re po]
tests/test_graph_refs.py::test_derive_ref_refuses_malformed_origin_repo[octo/repo#1]
tests/test_graph_refs.py::test_derive_ref_refuses_malformed_origin_repo[../../etc]
tests/test_graph_refs.py::test_derive_ref_is_total
tests/test_graph_refs.py::test_ref_for_builds_a_pull_requests_ref
tests/test_graph_refs.py::test_ref_for_refuses_a_number_github_cannot_have[0]
tests/test_graph_refs.py::test_ref_for_refuses_a_number_github_cannot_have[-1]
tests/test_graph_refs.py::test_ref_for_shares_derive_refs_validation
tests/test_graph_refs.py::test_split_ref_names_both_remedies
tests/test_graph_refs.py::test_split_ref_still_accepts_every_shape_it_did_before
tests/test_graph_refs.py::test_degradations_reports_a_pass_that_recorded_an_error
tests/test_graph_refs.py::test_degradations_stays_quiet_about_a_legitimate_no_op
tests/test_graph_refs.py::test_degradations_stays_quiet_about_an_ordinary_pass
tests/test_graph_refs.py::test_degradations_reports_every_failing_hook_in_order
tests/test_graph_refs.py::test_degradations_ignores_an_empty_error_field
tests/test_graph_refs.py::test_degradation_message_is_the_loops_own_text
```

## T9 — the abuse cases on their own

The three abuse cases from `design.md` § Security design: a hostile `ticketing.github`
redirecting comments (A1), a crafted work-item id escaping into another ref (A2), and a
degradation message carrying anything but the-loop's own text (A3).

```text
$ uv run --project cli python -m pytest -q cli/tests/test_graph_refs.py -k "refuses or leak"
..................                                                       [100%]
18 passed, 15 deselected in 0.05s
```
