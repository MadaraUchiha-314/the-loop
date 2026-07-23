# Decision 029: Register user instruction docs inline in config (guidance counterpart of externalTools)

- **Status:** accepted
- **Date:** 2026-07-23
- **Deciders:** MadaraUchiha-314 + harness
- **Work item:** issue-59

## Context

Teams carry conventions the structured config cannot model — coding/testing styles,
naming rules, house rules — usually already written down as a readme or markdown doc.
the-loop had no first-class way to be pointed at such docs: harness-native memory files
(`CLAUDE.md`, Cursor rules) are harness-specific and outside the-loop's contract, and
stuffing prose conventions into `.the-loop/config.yaml` keys does not scale. Issue #59
asks that a user, when initializing the-loop, can point to custom instruction file(s)
at configurable, per-installation paths — supplementary to the existing external-tools
registry.

## Decision

Add a **`customInstructions`** config section — an ordered inline list of
`{path, notes}` instruction docs plus an `onMissing` policy — mirroring how
`externalTools` registers tools inline (issue-37's one-YAML principle). The two are
complementary: externalTools registers *capabilities the harness may use*;
customInstructions registers *guidance the harness must follow*.

- **Read points:** every working command reads the docs in list order immediately
  after loading the config; re-read after a context clear and on demand per each
  entry's `notes` (progressive disclosure).
- **Onboarding:** a new `confirm`-level `instructions` group — init proposes detected
  candidates (`CONTRIBUTING.md`, docs style guides), never auto-registers.
- **Precedence (fail-closed):** hard gates (security, paper trail, phase/review gates,
  autonomy) can never be instructed away — such instructions are ignored and logged;
  the structured config wins for everything it models (mismatches surfaced, not
  silently overridden); the docs win everywhere else; later docs beat earlier ones.
- **Instruction-level, not code** — defined in a new skill reference
  (`reference/instructions.md`) and wired into the commands, like every other process
  rule.

## Consequences

- Each installation of the-loop can carry its own conventions — including per-machine
  absolute paths (org-wide docs outside the repo) — without forking the plugin.
- The loop's rigor floor is preserved by construction: custom instructions extend the
  config's reach into prose territory but cannot weaken gates or silently override
  config keys.
- One more thing read at session start; bounded by the docs the operator registers,
  and verbose docs can be sub-agented (`tokenEconomy.subAgentDelegation`).
- Nothing is enforced in code; a harness can ignore the instructions — identical to
  every other process rule and covered by the open hooks-vs-instructions question
  (`reference/workflow.md` § predictability).

## Alternatives considered

- **Reuse harness-native memory files (`CLAUDE.md`, Cursor rules)** — harness-specific,
  no configurable/per-machine paths, and outside the-loop's contract; kept as an
  independent, complementary channel.
- **A separate registry file (e.g. `.the-loop/instructions.yaml`)** — contradicts the
  one-YAML inline-registry direction taken for externalTools (issue-37 PR feedback).
- **Modeling conventions as more structured config keys** — the point of these docs is
  exactly the prose the schema cannot (and should not) model.
- **URL/remote instruction sources** — new moving parts and a supply-chain surface for
  what a checked-in or synced file already solves; fails the minimalism ladder.
