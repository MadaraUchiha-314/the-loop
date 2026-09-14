# Evidence — the red run (task 1)

The two assertions written before the fix, run against the unfixed adapter. Both fail on
the same fact from two different heights: the argv a critic would spawn, and the argv
fragment the model resolves to.

<!-- markdownlint-disable MD010 -->

```console
$ uv run --project cli python -m pytest -q \
    cli/tests/test_critics.py::test_cursor_oneshot_argv_uses_the_long_model_flag \
    cli/tests/test_modelchoice.py::test_a_model_resolves_through_the_adapters_flag

_______________ test_cursor_oneshot_argv_uses_the_long_model_flag ______________

        argv = CursorAgentAdapter().oneshot_argv("review this", model="gpt-5.6-sol")
>       assert argv == [
            "-p",
            "review this",
            "--output-format",
            "json",
            "--model",
            "gpt-5.6-sol",
        ]
E       AssertionError: assert ['-p', 'revie...'gpt-5.6-sol'] == ['-p', 'revie...'gpt-5.6-sol']
E
E         At index 4 diff: '-m' != '--model'
E         Use -v to get more diff

cli/tests/test_critics.py:89: AssertionError
_______________ test_a_model_resolves_through_the_adapters_flag ________________

    def test_a_model_resolves_through_the_adapters_flag():
        assert model_args("fable-5.1", ClaudeCodeAdapter()) == ("--model", "fable-5.1")
>       assert model_args("gpt-5.6-sol", CursorAgentAdapter()) == (
            "--model",
            "gpt-5.6-sol",
        )
E       AssertionError: assert ('-m', 'gpt-5.6-sol') == ('--model', 'gpt-5.6-sol')
E
E         At index 0 diff: '-m' != '--model'
E         Use -v to get more diff

cli/tests/test_modelchoice.py:128: AssertionError
=========================== short test summary info ============================
FAILED cli/tests/test_critics.py::test_cursor_oneshot_argv_uses_the_long_model_flag
FAILED cli/tests/test_modelchoice.py::test_a_model_resolves_through_the_adapters_flag
2 failed in 0.09s
```

<!-- markdownlint-enable MD010 -->

Two further reds followed from the same one-line change and are recorded here rather than
re-run in isolation, because each is a **pre-existing assertion that agreed with the bug**:

- `cli/tests/test_critics.py::test_builtin_harness_derives_argv_from_the_adapter` — the
  end-to-end critic argv, pinned to `-m` (task 3). It failed on the first full-suite run
  after the fix, which is exactly the signal task 3 exists to record: the one test that
  exercised the whole seam had encoded the defect as the contract.
- `cli/tests/test_modelprobe.py::test_a_verdict_probed_with_the_old_cursor_flag_no_longer_withholds`
  (task 4) fails before the fix on its first assertion — `resolved_args` returns
  `("-m", "gpt-5.6-sol")`, not `("--model", …)`.
