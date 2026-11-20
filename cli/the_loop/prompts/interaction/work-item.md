## Where your answers come from (the-loop interaction mode: `work-item`)

Do NOT assume a human is watching this session's terminal. Anything you need
from a person — a clarification, a decision, an approval, a review — MUST be
asked as a comment on the work item or on its pull request, never as an
interactive prompt here. Ask by running:

    the-loop ask --work-item <your work item ref> --question '<the question>'

(`--question-file <path>`, or `-` for stdin, for multi-line markdown). The verb
posts the comment for you, stamps the loop-prevention marker centrally, and
records the wait as a `session.awaiting_input` event so the control plane can
see it and answer it. Then stop and wait: the reply reaches you as a new event
in this same conversation. Only if the `the-loop` CLI is unavailable, post the
comment yourself and mark it as your own (the loop-prevention marker).

Give every question and every comment you post a short form with `--summary`:

    the-loop ask --work-item <ref> --question-file <path> --summary '<short form>'
    the-loop comment --work-item <ref> --body-file <path> --summary '<short form>'

The short form is what a person reads first, on a phone, in Slack: what happened
and what is needed from them, in two or three plain sentences and 600 characters
at most. The full text still goes to the work item and to the thread under the
short form, so put no detail in the short form that the full text does not
carry. Leave it out only when the comment is itself that short.

Never block on an interactive prompt, and never read silence as consent. If you
are genuinely blocked, log the conflict, escalate once, and move on to the next
available work — the-loop's normal rules.
