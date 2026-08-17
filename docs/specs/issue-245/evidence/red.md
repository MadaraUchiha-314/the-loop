# Red run — the tests fail before the implementation exists

TDD evidence (`tdd.mode: standard`): the two new test modules were written and run before any implementation code. Both fail at import — nothing they guard exists yet.

```
$ uv run --project cli python -m pytest cli/tests/test_channels.py cli/tests/test_channels_integration.py -q
E   ModuleNotFoundError: No module named 'the_loop.channels'
=========================== short test summary info ============================
ERROR cli/tests/test_channels.py
ERROR cli/tests/test_channels_integration.py
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!!
2 errors in 0.14s
```
