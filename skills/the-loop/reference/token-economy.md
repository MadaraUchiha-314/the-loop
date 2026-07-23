# Token economy reference — spend fewer tokens, never less rigor

the-loop iterates, is verbose by design, and (in the default `process` runner) re-primes
the harness on every webhook event — so it is inherently token-hungry (issue-37). This
reference is the loop's **opinion on token economy**: a set of config-driven levers
(`tokenEconomy` in `.the-loop/config.yaml`) plus the guidance that makes them real.

## The one guardrail (absolute)

Every lever here is **advisory** — it informs how the loop works, it **never gates a
merge**, and it may **never** trade away:

> input validation · error handling · security · accessibility · test-first discipline ·
> the paper trail · review depth.

Cheaper never means sloppier. When a lever and correctness/safety conflict,
correctness/safety wins, every time. This is the same stance as `minimalism.md`.

## The levers

### 1. Progressive disclosure (`tokenEconomy.progressiveDisclosure`)

`SKILL.md` is a **thin index**; the heavy detail lives in `reference/*.md` and is pulled
in **just-in-time**. Deepen it: a step loads only the reference file(s) its phase needs —
do not read the whole corpus up front. The phase → reference loading map:

| Phase / step | Load only |
|--------------|-----------|
| brainstorm | (SKILL.md index) + `token-economy.md` if optimizing |
| requirements-definition | `workflow.md` |
| design | `workflow.md`, `design-artifacts.md` (user-facing only), `minimalism.md` |
| tasks-breakdown | `workflow.md` |
| implementation | `tooling.md`, `testing.md`, `minimalism.md`, `observability.md` |
| self/critic review | `reviewing.md` |
| reviewer briefing / evidence | `collaboration.md` |
| any autonomous/webhook run | `automation.md`, `token-economy.md` |

### 2. Tighten what we control (corpus density)

The `SKILL.md` + `reference/*.md` + templates are context **rent** paid every turn that
pulls them in. Keep them dense: no filler, no duplication between `SKILL.md` and a
reference file, detail pushed **down** the disclosure tree. This is caveman applied to our
own prompts — unambiguously safe because we own the text and the structural rules stay
intact.

### 3. Tool-output & MCP hygiene

- Prefer the dedicated file/search tools over shell dumps; return **summaries, not raw
  logs**. Verbose tool results are resent every turn.
- Keep the MCP/tool surface **scoped to the task** — every connected server loads its full
  tool schemas into context whether used or not.

### 4. Generation minimalism (see `minimalism.md`)

The YAGNI → stdlib → native → existing-dep → inline → new-abstraction ladder is **also** a
token lever: code never generated is tokens never spent (and never reviewed). This is
ponytail's "lazy senior developer" ladder expressed natively; ponytail itself is registered
in `config.externalTools` for operators who want the packaged skill.

### 5. Output-verbosity compression (`tokenEconomy.outputVerbosity`)

`mode: concise` → drop conversational filler, prefer fragments, in the agent's **narration
only**. NEVER compress anything in `outputVerbosity.preserve`: code, commands, diffs,
errors, paper-trail comments, the **reviewer briefing**, specs, decisions, capability docs.
Because the reviewer briefing and ticket/PR comments are exempt, the *educate-the-reviewer*
mandate (`userInteraction.prSummary`) is fully preserved. This is caveman's preservation
rule; caveman is registered in `config.externalTools`.

### 6. Model routing (`tokenEconomy.modelRouting`)

Different stages need different horsepower — mechanical stages (evidence, capability-doc
fold-in, reviewer briefing, status reads, checkmark/lint updates, learnings) do **not** need
a frontier model. Route by an abstract **tier** (`economy | standard | frontier`) that the
operator binds to concrete per-harness model ids (`tiers.<tier>.claude` / `.cursor`); an
empty binding means "use the harness default for that tier." The default **stage → tier**
map (overridable):

| Tier | Stages |
|------|--------|
| `frontier` | brainstorm, requirements, design, critic-review |
| `standard` | tasks, implementation, self-review |
| `economy` | evidence, capability-docs, reviewer-briefing, status, learnings |

`riskTierFloor` lifts high-risk work (tier 4/5) to a minimum tier regardless of stage, so an
auth/schema change never runs on the economy model. Routing is **advisory**: where a harness
can't switch models programmatically, treat the tier as the model the human should select.

### 7. Thinking-effort control (`tokenEconomy.thinkingEffort`)

Extended thinking bills as **output** tokens. Cap effort by stage: `high` for
design/critic-review, `medium` for implementation, `none`/`low` for status/evidence/
formatting. Advisory where a harness can't set effort.

### 8. Sub-agent delegation (`tokenEconomy.subAgentDelegation`)

Run verbose work — the test suite, doc fetches, scanning large files/logs — in a **fresh-
context sub-agent** so the raw output stays in *its* window and only a short summary returns
to the controller. This keeps the controller's window lean across a long autonomous run
(the classic 6k-tokens-read → 400-token-summary trade). Guidance where a harness lacks
sub-agents.

### 9. Compaction & filesystem-as-memory (`tokenEconomy.compaction`)

the-loop already persists durable state to disk (specs, `execution-log.md`, capability
docs) — that is *why* resumability works, and it is a **token** strategy: offload state to
disk, keep the window lean. For long runs: checkpoint state to the execution log, then
compact/reset the window with a "preserve the spec + open threads" instruction rather than
letting the window grow unbounded ("context rot").

### 10. Prefer resident sessions over cold re-priming

In the **`tmux` runner (issue-32)** the harness TUI stays resident and each webhook event is
**forwarded into the existing session** — no re-spawn, no cold re-prime. That makes
`runner: tmux` a token lever over long chains of `process`-runner `-p --resume` spawns.
Where `process` runner is used, prefer **fresh context per work item** over one giant
mega-session (which re-sends the whole growing conversation every turn).

### 11. Measure it (`tokenEconomy.telemetry`) — the prerequisite

You cannot reduce what you do not measure. Usage (input/output/cache tokens + cost) is
parsed best-effort from each harness's JSON output (`DispatchResult.usage`) and surfaced per
work item in `execution-log.md`. Every other lever is judged against this **real baseline**,
not vendor claims — so the loop sets **no headline reduction target** until it has measured
one.

## Best-practices checklist (adoption status)

| # | Practice | Lever |
|---|----------|-------|
| 1 | Progressive disclosure (thin index, JIT bodies) | §1 |
| 2 | Dense, de-duplicated prompt corpus | §2 |
| 3 | Tool-output trimming / MCP hygiene | §3 |
| 4 | Generation minimalism (YAGNI ladder ≈ ponytail) | §4 |
| 5 | Output-verbosity compression (≈ caveman) | §5 |
| 6 | Model routing by stage + risk tier | §6 |
| 7 | Thinking-effort control | §7 |
| 8 | Sub-agents w/ fresh context for verbose work | §8 |
| 9 | Compaction + structured note-taking | §9 |
| 10 | Resident sessions / fresh-context-per-item | §10 |
| 11 | Per-work-item token/cost telemetry | §11 |

## References

- Root artifact & research digest: `docs/specs/issue-37/brainstorm.md`.
- Anthropic — *Effective context engineering for AI agents*; *Agent Skills*.
- Claude Code docs — *Manage costs effectively*.
- External plugins (registered, not vendored): caveman (output compression),
  ponytail (generation minimalism) — see `config.externalTools` in `.the-loop/config.yaml`.
