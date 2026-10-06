---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#472"
---

# The phase-selection comment, before

> The comment before issue-472, as `main` rendered it at 26e4104: `_checklist_body` for the shipped outer loop, with two
> harnesses, two models and three effort levels declared so that every section renders.
> Generated, not hand-written; only the trailing HTML markers are removed. Compare with
> [`checklist-after.md`](checklist-after.md).

---

🤖 _the-loop_ — **which phases does this work item need?**

Before the loop starts, tell it what this item actually needs. **Untick anything this work item does not need, tick anything optional it does want, then reply `the-loop execute`.** The tick state at that moment is frozen and becomes the graph this item walks.

- [x] brainstorming
- [x] requirements-definition
- [x] requirements-approval
- [x] design
- [x] test-planning
- [x] design-approval
- [x] tasks-breakdown
- [x] implementation
- [x] verification
- [x] self-review
- [x] critic-review
- [x] security-review
- [x] evidence
- [x] capability-docs
- [x] reviewer-briefing
- [x] human-approval

**Optional phases — these do NOT run unless you tick them.** They are offered, not planned:

- [ ] design-critic-review — a different model/harness reviews the completed design.md against the requirements, before the testing plan and the task DAG are derived from it (the design is locked later, at design-approval — issue-281)

**Every phase of this loop is selectable — including the reviews, the security review and the approval gate.** Nothing but this question is mandatory. The phases this item skips are recorded as its own declared choice — in its work-item state, in a confirmation comment here, and in every `the-loop check` from now on — so a lighter run is always a visible one.

**Where should the outer loop happen?** This is not a phase — it is where the requirements, design, testing plan and task list are iterated with you:

- [ ] `outer-loop-on-pull-request` — on a pull request in this repository.

Leave it unticked (the default) and they happen **on this work item**, here. Tick it and they happen on a pull request instead. Either way the artifacts are committed files linked from here, and each repository this work item contributes code to gets its own pull request for the inner loop.

**Publish the spec chain as a Claude artifact too?** Not a phase, and off unless you tick it — the requirements, design, testing plan and task list become one page with a tab per file, which you can read and comment on in Claude:

- [ ] `claude-artifact` — one Claude artifact for this work item (`claude` harness only).

**Only the `claude` harness can publish one.** On any other harness the-loop ignores this box. The markdown files stay the source of truth either way, and every gate still reads them.

**How many sessions should this work item's pull requests get?** Also not a phase — it is how many harness conversations run for this item. **Tick exactly one**; this deployment's default is already ticked:

- [ ] `pr-sessions-never` — every pull request's events land in **this** work item's one session.
- [x] `pr-sessions-cross-repository` — only a pull request in **another** repository gets its own session; one in this repository is this work item's own delivery.
- [ ] `pr-sessions-always` — **every** pull request delivering this work item gets its own session, this repository's included.

Leave them alone and `cross-repository` stands — the operator's `routing.tmux.sessionPerPr`. Ticking none, or more than one, means the same thing. A pull request only ever gets a session when it can get a **working tree of its own**, in every mode: where it cannot, the event is delivered into this work item's session and recorded as `session.pr_session_declined`.

**Is this work item worked in a channel of its own?** Also not a phase — it is where the-loop posts this item's updates, and where messages from authorized users reach it:

None declared — this item's updates go to the operator's central channel. Reply `the-loop add-channel slack@C0123ABCD` (its conversation id, not `#name`) to give it a room of its own.

Declare it in a comment of its own, before or after this gate — the order does not matter, and a comment may carry only one keyword.

**Which harness should this work item run on?** Not a phase — it is the agent CLI its session is. **Tick at most one:**

- [ ] `harness-claude`
- [ ] `harness-codex`

Leave them alone and this work item runs on `claude`, this deployment's default. A model or effort ticked below is kept only if the harness it ends up on can run it. Ticking more than one means the same thing — two ticks are not a choice, and guessing which one you meant is how a work item ends up somewhere nobody asked for.

**Which model should this work item run on?** Not a phase — it is what the session is. **Tick at most one:**

- [ ] `model-claude-opus-5-5` — deepest reasoning, slowest
- [ ] `model-claude-sonnet-5-5` — the everyday default

Leave them alone and this work item runs on `claude-sonnet-5-5`, the `claude` harness's default model. Ticking more than one means the same thing — two ticks are not a choice, and guessing which one you meant is how a work item ends up somewhere nobody asked for.

**How hard should it think?** Also not a phase, and independent of the model above. **Tick at most one:**

- [ ] `effort-low`
- [ ] `effort-medium`
- [ ] `effort-high`

Leave them alone and the harness's own default effort stands. Ticking more than one means the same thing — two ticks are not a choice, and guessing which one you meant is how a work item ends up somewhere nobody asked for.

A doc fix usually needs little more than implementation and verification; a feature usually needs every phase. Reply `the-loop execute` with the boxes untouched to run the full process — every phase above that is already ticked, and none of the optional ones.

You can also put the list in the reply itself — a checklist in the `the-loop execute` comment wins over the boxes above. Either way the **authorization is your reply**: the tick state is a proposal, and saying the keyword is what makes it yours.

🤖 _the-loop, autonomous comment_
