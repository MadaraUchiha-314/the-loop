---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#398"
---

# Documentation: a logo for the-loop (issue-398)

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| none affected | This work item produces design artifacts under its own spec folder and changes no capability's behaviour. It *uses* the `design-artifacts` capability (a self-contained gallery, iterated on the rendering with the designer — round 1 → round 2 on the owner's review — screenshot evidence) exactly as that doc describes; nothing in `docs/capabilities/design-artifacts.md` becomes wrong or incomplete. | none |

## Documentation

| Document | What changed |
|----------|--------------|
| `README.md`, the docs site, the plugin manifests | **Not changed, on purpose.** Nothing is adopted until the owner picks an option; wiring the chosen mark into the README, the site's hero and favicon, and the two plugin manifests is the follow-up work item this one's `requirements.md` § Out of scope names. Until then the user-facing surface has no logo, as before, and describes nothing this PR makes wrong. |
| `docs/specs/issue-398/design/logo-options.html` | New (round 2 supersedes round 1 in place) — the reviewable presentation of the five options; it says what changed since round 1 and carries its own instructions (the source file, how to regenerate and check), so a reader who lands on it needs nothing else. |
