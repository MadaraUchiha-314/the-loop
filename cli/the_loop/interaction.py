"""Where a spawned session takes its answers from — the CLI, or the work item (issue-134).

A session the daemon spawns or resumes was never told **where a human is**. The
rendered prompt said what happened and which rules apply, then left the most
consequential question to the model's guess — and both guesses fail. Guessing
"the terminal" in a ``process``-runner session asks a question into a pipe
nobody reads; guessing "the ticket" while the operator sits in an attached tmux
pane routes a live conversation through GitHub for no reason.

The operator knows which one they want, so they declare it:
``routing.interaction.mode`` is ``work-item`` (the default)
or ``cli``. This module owns two things and nothing else:

1. **Resolution.** :meth:`InteractionConfig.from_mapping` never raises and never
   returns an undeclared mode. The schema ``enum`` is the authoring-time gate;
   this is the runtime one, because the daemon does not validate its config
   against the schema at load. An unrecognised value falls back to
   ``work-item`` **with a warning** — never to ``cli``. The asymmetry is the
   point: a wrong ``work-item`` leaves a visible comment awaiting a reply, a
   wrong ``cli`` leaves a question in a void.
2. **The directive text.** A **constant per mode** — no interpolation at all,
   not even the work-item ref (the templates already carry that in their own
   ``$work_item`` slot). That is what keeps the security argument short: there
   is no path from untrusted payload data into this string, and the dispatcher
   renders it *above* the payload excerpt both templates already label as
   untrusted.

:func:`apply_directive` is the fail-safe. ``string.Template.safe_substitute``
silently ignores a placeholder the template never declared, which is exactly how
an operator's custom ``promptTemplate`` would drop the rule without anyone
noticing — so a template that does not declare ``$interaction_directive`` gets
the directive appended instead.

Spec: docs/specs/issue-134/design.md, docs/decisions/decision-051.md.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Tuple

logger = logging.getLogger("the-loop.interaction")

__all__ = [
    "DEFAULT_MODE",
    "MODES",
    "PLACEHOLDER",
    "InteractionConfig",
    "apply_directive",
    "directive_for",
]

#: The declared vocabulary, mirrored by the schema's ``enum``.
MODES: Tuple[str, ...] = ("work-item", "cli")

#: Fail-closed default: the only channel guaranteed to reach a human who was not
#: already watching a terminal.
DEFAULT_MODE = "work-item"

#: The placeholder the prompt templates declare to receive the directive.
PLACEHOLDER = "interaction_directive"

# Both modes close with the same paragraph. The artifact rule is an INVARIANT,
# not a third setting (decision-051): a checked-in file's review surface is the
# PR that carries it, in either mode. The skill carries the full rule — this is
# the one-line restatement for a session whose first (and sometimes only)
# instruction is this prompt.
_ARTIFACT_RULE = """\
Once an artifact of the chain exists (`brainstorm.md`, `requirements.md` /
`bugfix.md`, `design.md`, `tasks.md`), iterate on it ONLY through pull-request
review: commit and push it, open or update the PR that carries it, and take
feedback as review comments and replies on that PR. Do not re-paste artifact
contents into new ticket comments, and do not iterate on an artifact
interactively — the file, the discussion and the approval belong in one place."""

_WORK_ITEM_DIRECTIVE = f"""\
## Where your answers come from (the-loop interaction mode: `work-item`)

Do NOT assume a human is watching this session's terminal. Anything you need
from a person — a clarification, a decision, an approval, a review — MUST be
asked as a comment on the work item or on its pull request, never as an
interactive prompt here. Ask, mark the comment as your own (the loop-prevention
marker), then stop and wait: the reply reaches you as a new event in this same
conversation.

Never block on an interactive prompt, and never read silence as consent. If you
are genuinely blocked, log the conflict, escalate once, and move on to the next
available work — the-loop's normal rules.

{_ARTIFACT_RULE}"""

_CLI_DIRECTIVE = f"""\
## Where your answers come from (the-loop interaction mode: `cli`)

A human is attached to this session's terminal — that is where the operator
chose to iterate. Ask your questions, clarifications and decisions here,
interactively, rather than round-tripping through the work item.

This does not waive the paper trail: record the OUTCOME of every human decision
as a comment on the work item, marked as your own, so the reasoning survives
this terminal.

{_ARTIFACT_RULE}"""

_DIRECTIVES = {
    "work-item": _WORK_ITEM_DIRECTIVE,
    "cli": _CLI_DIRECTIVE,
}


def directive_for(mode: str) -> str:
    """The directive text for ``mode``; the default's text for anything else."""
    return _DIRECTIVES.get(mode, _DIRECTIVES[DEFAULT_MODE])


@dataclass(frozen=True)
class InteractionConfig:
    """Mirror of ``routing.interaction`` (see config schema)."""

    mode: str = DEFAULT_MODE

    @classmethod
    def from_mapping(cls, data: object, runner: str = "process") -> "InteractionConfig":
        """Resolve the declared mode, degrading to :data:`DEFAULT_MODE`.

        Silent when nothing was declared (a config that predates issue-134 is
        not a mistake); **warned** when something was declared and is not a mode
        — that is a typo the operator wants to hear about, and honouring it
        would mean choosing an interaction channel they never asked for.

        ``runner`` is taken only to warn about the one combination that
        reproduces the defect this feature exists to remove: ``cli`` under the
        headless ``process`` runner is a session told to ask a human who has no
        terminal to be asked in. It is a *warning*, not a refusal — the operator
        may be piping the harness somewhere the-loop cannot see, and a daemon
        that refuses to start over a prompt hint is worse than a loud one.
        """
        resolved = cls._resolve(data)
        if resolved.mode == "cli" and str(runner or "").strip().lower() == "process":
            logger.warning(
                "routing.interaction.mode is 'cli' but routing.runner is 'process': "
                "a headless one-shot session has no terminal for a human to answer "
                "in. Use runner 'tmux' to sit in the session, or interaction mode "
                "'work-item' to be asked on the ticket"
            )
        return resolved

    @classmethod
    def _resolve(cls, data: object) -> "InteractionConfig":
        if not isinstance(data, dict) or "mode" not in data:
            return cls()
        raw = data.get("mode")
        mode = str(raw).strip().lower() if isinstance(raw, str) else ""
        if mode in MODES:
            return cls(mode=mode)
        logger.warning(
            "routing.interaction.mode %r is not one of %s; using %r — a session "
            "must never be told to ask on a channel nobody is watching",
            raw,
            ", ".join(MODES),
            DEFAULT_MODE,
        )
        return cls()

    @property
    def directive(self) -> str:
        """The prompt block that tells the agent which channel to use."""
        return directive_for(self.mode)


def apply_directive(rendered: str, template_text: str, directive: str) -> str:
    """Guarantee the directive reached ``rendered`` (R2.4).

    ``safe_substitute`` is silent about a placeholder the template never
    declared, so a custom ``promptTemplate`` could strip the interaction rule
    with nobody the wiser. When the template does not declare the placeholder,
    the directive is appended instead of being lost.
    """
    if f"${PLACEHOLDER}" in template_text or f"${{{PLACEHOLDER}}}" in template_text:
        return rendered
    logger.debug(
        "prompt template does not declare $%s; appending the interaction directive",
        PLACEHOLDER,
    )
    return f"{rendered.rstrip()}\n\n{directive}\n"
