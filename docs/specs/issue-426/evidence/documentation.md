---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#426"
---

# Documentation: work-item mode launches Claude Code without its question menu

> The ready-to-ship gate's documentation item: the affected capability docs are updated in
> the same pull request as the change.

## Capability docs

- **[`docs/capabilities/webhook-triggers.md`](../../../capabilities/webhook-triggers.md)**
  owns the interaction mode. Its requirement *Every rendered prompt states where the
  session takes its answers from* gains a sub-requirement: the mode also reaches the
  argv, with the `=` spelling, the `cli` opt-out, the reload behaviour, the unchanged
  `harness_args`, and the unaffected standing and critic runs. A history row for
  issue-426 sits above issue-416.
- **[`docs/capabilities/interactive-sessions.md`](../../../capabilities/interactive-sessions.md)**
  owns the tmux-hosted argv. A new requirement states the work-item-mode argv shape,
  and a history row sits above issue-410.

## Documentation

- [`docs/config/cli/routing-options.md`](../../../config/cli/routing-options.md)
  § `interaction.mode`: the mode is enforced as well as stated, `cli` is the opt-out,
  and a reload applies from the next launch.
- [`docs/config/cli/harnesses-options.md`](../../../config/cli/harnesses-options.md)
  § `harnesses[].args`: the token is added for you, and a variadic flag at the end of
  the list swallows the prompt unless written with `=`. This is the ticket's workaround,
  and until now nothing warned about it.
- [`skills/the-loop/reference/collaboration.md`](../../../../skills/the-loop/reference/collaboration.md)
  and [`automation.md`](../../../../skills/the-loop/reference/automation.md): one
  sentence each saying the daemon enforces the no-interactive-prompt rule for Claude
  Code in `work-item` mode.

## Not affected

- `README.md`: it does not describe the spawn argv or the interaction mode's mechanics.
- The config schema: no key was added (the mode is the switch; see `design.md`
  § Trade-offs).
- `docs/capabilities/distribution.md`, `docs/capabilities/control-plane.md`: no route,
  hook or packaging change.
