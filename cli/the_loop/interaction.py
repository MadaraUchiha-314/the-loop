"""Where a spawned session takes its answers from — the CLI, or the work item (issue-134).

A session the daemon spawns or resumes was never told **where a human is**. The
rendered prompt said what happened and which rules apply, then left the most
consequential question to the model's guess — and both guesses fail. Guessing
"the terminal" when nobody ever attaches to the tmux session asks a question
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

from . import prompts

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
# instruction is this prompt. The prose lives in the_loop/prompts/interaction/
# (issue-540); this module only composes it.
_ARTIFACT_RULE = prompts.load("interaction/artifact-rule", inline=True)

_WORK_ITEM_DIRECTIVE = (
    prompts.load("interaction/work-item", inline=True) + "\n\n" + _ARTIFACT_RULE
)

_CLI_DIRECTIVE = prompts.load("interaction/cli", inline=True) + "\n\n" + _ARTIFACT_RULE

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
    def from_mapping(cls, data: object) -> "InteractionConfig":
        """Resolve the declared mode, degrading to :data:`DEFAULT_MODE`.

        Silent when nothing was declared (a config that predates issue-134 is
        not a mistake); **warned** when something was declared and is not a mode
        — that is a typo the operator wants to hear about, and honouring it
        would mean choosing an interaction channel they never asked for.
        """
        return cls._resolve(data)

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

    @property
    def unattended(self) -> bool:
        """Whether nobody answers the session's pane — every mode but ``cli``.

        What the directive *says*, made true in the argv (issue-426): a harness
        launched unattended is denied its interactive question tool, so a
        question ends the turn instead of freezing a pane nobody watches.
        """
        return self.mode != "cli"


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
