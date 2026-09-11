# Decision 118: long text reaches Slack as a structural digest the channel computes — never a model's summary — above `maxChars`, under one enum key

- **Status:** proposed
- **Date:** 2026-09-11
- **Work item:** [issue-338](https://github.com/MadaraUchiha-314/the-loop/issues/338)
- **Deciders:** jc1993 (the ask), the-loop (design); MadaraUchiha-314 (owner, at the PR)
- **Refines:** [decision-103](decision-103.md) (rendering is the channel's; the ledger
  is the record and nothing acts on a channel's rendering), [decision-005](decision-005.md)
  (the CLI bundles no runtime), [decision-094](decision-094.md) (the Slack provider's
  verbosity and cap)

## Context

Issue-338 asks for a transformation layer between the agent's output and Slack: above
some length, *summarize* instead of truncating — never mid-sentence, the full comment
behind a link — lead with the ask, render a choice as a numbered list, strip what
Slack cannot use (code fences, absolute paths, stack traces), and leave short messages
untouched. At 13.10.0 the channel cuts every text section at `maxChars` mid-sentence,
and GitHub markdown (the-loop's own `<!-- … -->` markers included) reaches Slack as
written.

Three questions had to be settled: **what does the summarizing** — a model or the
channel; **how it is configured** — a new block, or the cap the operator already has;
and **what "untouched" means** for a short message when the channel also has to draw
markdown as mrkdwn.

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **The channel computes a structural digest, deterministically: the first question (or the "reply `…`" instruction) first, lists as numbered lines, fences / tables / stack traces replaced by a pointer, absolute paths shortened, the rest in the author's order, cut at a sentence, one closing link to the full text. No model reads the text.** | The Slack message is the one place a member reads before pressing Execute or Approve; the ledger is the record the gate acts on (decision-103 D1). A generated summary can paraphrase or invent an option, and there is no way to prove it did not — a digest made only of the author's sentences can be pinned by a test (every line is a substring of the source). It also costs no runtime (decision-005), no secret in the post path, no latency in a hook that posts synchronously, and it reads the structure the-loop already writes (the checklist's boxes, the writing skill's conclusion-first spine, the ask's question mark). The name is *digest*, not *summary*, on purpose. |
| D2 | **One enum key, `channels.slack.longMessages: digest \| truncate` (default `digest`); the threshold is `maxChars`.** | `maxChars` already means "how much text one message carries" and is the lever a phone reader will turn; a second threshold would be a second number to keep consistent with it. An enum rather than a boolean names the alternative — `truncate`, 13.10.0's cut — and leaves room for a `summarize` value routed through a `reviews.critics`-style executable entry, if a model summary is ever wanted, without a second key. |
| D3 | **Markdown is rendered as mrkdwn on every message; the digest runs only above the cap.** "Untouched" means the words, their order and their number — not the characters that draw them. | `**bold**`, `## headings`, `[text](url)`, task boxes and HTML comments are all *drawn wrong* on Slack whatever the length, and the issue-337 log already noted the markers showing literally. Converting them removes no word; the digest — which does remove words — is what the length gate protects short messages from. The same pass neutralises Slack's broadcast sequences (`<!channel>`), which is the one thing in a comment's text that *acts* on Slack. |

## Consequences

**Good.** A long comment on a phone opens with the question, offers the choice as a
list, and ends with the link; a two-line message is exactly what was written. The
notification preview leads with the ask too. Every sentence a member reads is the
author's. No new call, grant, scope, token or state; a 13.10.0 configuration parses
unchanged and gains the digest.

**Costs, accepted.** The digest is only as good as the text's structure: a comment with
no question mark and no list leads with its first sentence, and a rhetorical question
early in the text leads over the real one later — the closing link is the remedy, and
the writing skill's conclusion-first rule is the prevention. A code block a member
wanted to see inline is a pointer; `longMessages: truncate` or a larger `maxChars`
brings it back. Markdown that mrkdwn cannot draw (nested emphasis) is left as it was.

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| A model call in the channel (an API key, a prompt, a summary) | D1: a paraphrase in the seat where a member decides, unverifiable; a runtime and a secret in the post path; latency in a synchronous hook |
| Asking the agent to write a Slack-sized "TL;DR" block the channel prefers | Every producer would have to learn it — hooks, the ledger's mirror of human comments never would — and the digest reads the structure the writing skill already asks for |
| A `digest:` block with its own `threshold`, `maxLines`, per-event switches | D2: knobs before a reader asked for them; `maxChars` is the lever |
| Digest short messages too (always) | R4: a two-line message must arrive as written; the digest removes words and has no business on a message that fits |
| Leave markdown unconverted on short messages | D3: the drawing is the channel's job at every length; the markers were already an open observation |
