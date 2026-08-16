# After: the same event, distilled

Testing-plan row **T8**, captured after the change, with the same script and the same
payload as [`baseline.md`](baseline.md).

## Command

```console
uv run python docs/specs/issue-243/evidence/measure_prompt.py
```

## Output

```text
the-loop version          : the_loop.webhook.dispatcher @ tree under test
raw webhook payload       :   6335 chars
payload excerpt delivered :    203 chars
  parses as JSON          : yes
  truncated               : False
whole rendered prompt     :   2865 chars
  the instruction itself  :     61 chars
  the-loop constant text  :   2290 chars
  graph context           :    372 chars

---- the excerpt as delivered ----
{
  "comment": {
    "body": "the-loop execute\n\nPlease keep the anchor for inline comments.",
    "html_url": "https://github.com/o/r/issues/243#issuecomment-9876543210",
    "author": "reviewer"
  }
}
```

## The delta

| | Before | After | Change |
|---|---:|---:|---:|
| Payload excerpt | 4,014 chars | 203 chars | **−94.9%** |
| Whole rendered prompt | 6,676 chars | 2,865 chars | **−57.1%** |
| Excerpt parses as JSON | no — cut mid-string at char 4,000 | **yes** | — |
| The instruction's share of the prompt | 0.9% | 2.1% | ×2.3 |

The instruction is still a small share of the prompt, and that is now the-loop's own
constant text (2,290 chars) rather than GitHub's metadata — which is exactly the ticket's
second question. It is answered in
[`design.md` § The constant text](../design.md#the-constant-text-the-tickets-second-question)
with four options and a recommendation, and left for the owner to decide.
