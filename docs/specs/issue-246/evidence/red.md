# Red run — the reported symptom, as failing tests

Captured on the fix branch with the three source files reverted (`git stash push cli/the_loop/poller/*`),
so the tests are the new ones and the code is `10.2.1` as shipped. Command:

```console
$ uv run pytest cli/tests/test_poller.py cli/tests/test_poller_integration.py -q
E       AssertionError: assert ['IC_1'] == ['IC_1', 'PRRC_1', 'PRR_1']
E         
E         Right contains 2 more items, first extra item: 'PRRC_1'
E         Use -v to get more diff
E       ValueError: not enough values to unpack (expected 1, got 0)
E       ValueError: not enough values to unpack (expected 1, got 0)
E       Failed: DID NOT RAISE ProviderError
E       TypeError: Comment.__init__() got an unexpected keyword argument 'raw'
E       TypeError: Comment.__init__() got an unexpected keyword argument 'raw'
E       ValueError: not enough values to unpack (expected 1, got 0)
E       ValueError: not enough values to unpack (expected 1, got 0)
E       AssertionError: assert {'IC_200', 'I...'IC_205', ...} == {'IC_0', 'IC_...'IC_102', ...}
E         
E         Extra items in the right set:
E         'IC_8'
E         'IC_95'
E         'IC_47'
E         'IC_75'
E         'IC_97'...
E         
E         ...Full output truncated (196 lines hidden), use '-vv' to show
E       assert False
E        +  where False = wait_until(<function test_a_pr_review_and_an_inline_comment_reach_the_session_once_each.<locals>.<lambda> at 0x7fa2fada37e0>)
FAILED cli/tests/test_poller.py::test_gh_list_comments_on_a_pr_reads_all_three_surfaces
FAILED cli/tests/test_poller.py::test_gh_review_comment_on_an_outdated_line_keeps_its_original_anchor
FAILED cli/tests/test_poller.py::test_gh_review_from_a_deleted_account_has_no_author
FAILED cli/tests/test_poller.py::test_gh_review_fetch_failure_is_not_swallowed_into_no_comments
FAILED cli/tests/test_poller.py::test_provider_review_event_is_shaped_like_the_webhook_one
FAILED cli/tests/test_poller.py::test_provider_review_comment_event_carries_its_file_and_line
FAILED cli/tests/test_poller.py::test_provider_passes_the_review_kind_through_to_the_event
FAILED cli/tests/test_poller.py::test_a_self_authored_review_never_leaves_the_poller
FAILED cli/tests/test_poller.py::test_the_id_ledger_holds_a_whole_merged_thread
FAILED cli/tests/test_poller_integration.py::test_a_pr_review_and_an_inline_comment_reach_the_session_once_each
10 failed, 139 passed in 6.97s
```
