# Unit and integration runs

Testing-plan rows **T1–T7**, after the change.

## T1, T2, T3, T6 — the excerpt's own units

```console
$ uv run pytest cli/tests/test_excerpt.py -q
............................                                             [100%]
28 passed in 0.06s
```

## T6 — the abuse cases alone

```console
$ uv run pytest cli/tests/test_excerpt.py -k abuse -q
........                                                                 [100%]
8 passed, 20 deselected in 0.03s
```

## T4, T5 — the two ingresses, and the gates

```console
$ uv run pytest cli/tests/test_excerpt_integration.py -q
....                                                                     [100%]
4 passed in 0.05s
```

## T7 — the whole suite

```console
$ uv run pytest cli -q
.....................................................................    [100%]
2156 passed, 1 skipped in 110.54s (0:01:50)

```

## The integration tests, red first

T4/T5 were written after the wiring, so their red was captured by restoring the
pre-change `excerpt.py` (commit `08b7bd6`) under the already-wired dispatcher — the
wiring alone changes nothing while the distiller is the old one:

```console
$ git show 08b7bd6:cli/the_loop/webhook/excerpt.py > cli/the_loop/webhook/excerpt.py
$ uv run pytest cli/tests/test_excerpt_integration.py -q
FAILED cli/tests/test_excerpt_integration.py::test_the_poller_and_the_webhook_render_the_same_comment_identically
FAILED cli/tests/test_excerpt_integration.py::test_a_polled_review_and_inline_comment_distil_like_their_webhook_twins
FAILED cli/tests/test_excerpt_integration.py::test_the_gates_read_the_payload_not_the_excerpt
FAILED cli/tests/test_excerpt_integration.py::test_a_delivered_prompt_carries_the_instruction_and_not_the_metadata
4 failed in 0.09s
```
