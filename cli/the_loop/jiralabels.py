"""Jira-safe label names (issue-475, design §C5, R4.4).

A Jira label cannot contain whitespace, and the-loop's default arming label is
``the-loop: auto-execute``. :func:`jira_label` is the one mapping from a
configured name to the form written to Jira:

1. strip the ends;
2. a ``:`` followed by whitespace becomes ``:`` (``the-loop: rr`` → ``the-loop:rr``);
3. any other run of whitespace becomes ``-``;
4. an empty result, or one longer than 255 characters, has no safe form:
   :class:`JiraLabelError`, naming it.

=========================  ======================
configured                 on Jira
=========================  ======================
``the-loop: auto-execute``  ``the-loop:auto-execute``
``the-loop: rr``            ``the-loop:rr``
``loop:design``             ``loop:design``
=========================  ======================

The mapping is pure and deterministic, and is applied **only at the Jira
boundary**: the configuration, the work-item state and every GitHub label keep
the configured spelling. It is idempotent, so a label read back from Jira maps to
itself.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Mapping, Optional

__all__ = ["JIRA_LABEL_MAX", "JiraLabelError", "check_config_labels", "jira_label"]

#: Jira's own limit on a label's length.
JIRA_LABEL_MAX = 255

_COLON_SPACE = re.compile(r":\s+")
_WHITESPACE = re.compile(r"\s+")


class JiraLabelError(ValueError):
    """A configured label has no Jira-safe form. The message names the label."""


def jira_label(name: str) -> str:
    """``name`` as Jira can carry it, or raise :class:`JiraLabelError`."""
    text = str(name if name is not None else "")
    safe = _WHITESPACE.sub("-", _COLON_SPACE.sub(":", text.strip()))
    if not safe:
        raise JiraLabelError(f"label {text!r} has no Jira-safe form: it is empty")
    if len(safe) > JIRA_LABEL_MAX:
        raise JiraLabelError(
            f"label {text!r} has no Jira-safe form: Jira labels are at most "
            f"{JIRA_LABEL_MAX} characters"
        )
    return safe


def check_config_labels(config: Optional[Mapping[str, Any]]) -> Dict[str, str]:
    """``{configured: on Jira}`` for every label the-loop writes to Jira.

    Checked only when ``integrations.jira`` is configured — a GitHub-only
    deployment writes no Jira label, and GitHub takes the configured spelling.
    The labels are ``routing.autoExecuteLabels`` (the arming labels, default
    ``the-loop: auto-execute``); the ``loop:<phase>`` labels are node ids under
    a fixed prefix and always safe. Raises :class:`JiraLabelError` naming the
    key and the label.
    """
    document = dict(config or {})
    integrations = document.get("integrations")
    if not isinstance(integrations, Mapping) or not isinstance(
        integrations.get("jira"), Mapping
    ):
        return {}
    from .core.github_ops import auto_execute_labels

    mapping: Dict[str, str] = {}
    for label in auto_execute_labels(document):
        try:
            mapping[label] = jira_label(label)
        except JiraLabelError as exc:
            raise JiraLabelError(f"routing.autoExecuteLabels: {exc}") from None
    return mapping
