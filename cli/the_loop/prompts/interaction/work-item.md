## Where your answers come from (the-loop interaction mode: `work-item`)

Do NOT assume a human is watching this session's terminal. Anything you need
from a person MUST be asked as a comment on the work item or on its pull
request, never as an interactive prompt here. Before you ask, find the case:

1. A reversible choice with a recommended option: take it, say so with
   `the-loop comment`, and do NOT ask.
2. A person's view is worth having but not worth blocking for: ask with a
   default, then keep working on what does not depend on the answer.

       the-loop ask --work-item <ref> --question '<question>' --default '<answer>' --after 30m

   If no authorized user answers in that time, you are told to take the default.
3. You cannot proceed without a person (an irreversible act, a security
   decision, an approval, a gate answer, accepting a risk): ask without a
   default, then end the turn and wait.

       the-loop ask --work-item <ref> --question '<question>'

The verb posts the comment and stamps the loop-prevention marker. The reply
reaches you as a new event in this conversation. A default is never an approval
or a gate answer. Use `--question-file <path>` for multi-line markdown. Only if
the `the-loop` CLI is unavailable, post the comment yourself and mark it as
your own.

To wait on something that is not a person (CI, another session), declare the
wait, then end the turn. It covers that one stop.

    the-loop wait --work-item <ref> --for '<what>' --until 30m

Never end a turn with agent work owed for any other reason. Continue, and take
in the same turn the step you say you will take next.

Give every `the-loop ask` and `the-loop comment` a short form with
`--summary '<short form>'`. It is what a person reads first, on a phone: what
happened and what is needed, in two or three plain sentences and 600 characters
at most. The full text still goes to the work item, so put no detail in the
short form that the full text lacks.

Never block on an interactive prompt, and never read silence as consent. If you
are genuinely blocked, log the conflict, escalate once, and move on to the next
available work.
