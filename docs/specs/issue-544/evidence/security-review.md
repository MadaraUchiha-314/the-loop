---
type: evidence
workItem: "issue-544"
---

<!-- Written per the `the-loop:writing` skill. -->

# Security review: make what the-loop writes easy to read and review

## The short version

The built-in security review found no vulnerability in the new code. The new values can
come only from an authorized reply, are limited to a fixed set of names everywhere they
are read, and are rendered as text on the explainer page. The risk tier is below 4, so no
human sign-off is needed.

## Security review (gate)

- **Mechanism:** the security-review skill, run over `git diff origin/main...HEAD` (code
  files; docs and tests out of scope), on 2026-11-18.
- **Outcome:** pass.
- **Findings:** none at confidence 8 or above. What was checked:
  - **Authorization (abuse case 1):** experiment rows are read only from the reply the
    existing gate already filters to `routing.authorizedUsers`; an unauthorized reply
    freezes nothing (T2 scenario).
  - **Persisted state:** every read of `explainerExperiments` passes the closed-set
    filter, so a hand-edited state file cannot carry text into the prompt, archive or
    terminal.
  - **Prompt line:** the names are re-filtered before rendering; no payload text enters.
  - **`focus` parameter:** comes from the shipped graph and is only a catalog key; an
    unknown key adds nothing.
  - **Explainer page (abuse case 2):** every agent-supplied string is set with
    `textContent`; no `innerHTML`, `insertAdjacentHTML`, `document.write` or `eval`; the
    URL fragment only selects an existing tab. The `<` rule for data blocks is
    unchanged and covers the new blocks (T5: the `<img onerror>` title rendered as text).
  - **archify (abuse case 4):** guidance only; nothing installs or fetches it.
- **Human sign-off:** n/a (risk tier below 4).
