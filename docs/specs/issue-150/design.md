---
type: design
phase: design
workItem: "issue-150"
status: approved
approvedBy: [MadaraUchiha-314]
overrides: {}
---

# Design: Replace the README workflow mermaid diagram with an Excalidraw diagram

> Phase 2 of 3, derived from [requirements.md](requirements.md). Compact by tier.

## Architecture

Two checked-in artifacts under a new `docs/assets/` home (repo-level README images
had none; per-spec images live under `docs/specs/<id>/design/`):

- `docs/assets/the-loop-workflow.excalidraw` — the scene source, generated
  programmatically so geometry stays consistent across regenerations.
- `docs/assets/the-loop-workflow.svg` — the embed the README references, produced by
  Excalidraw's own `exportToSvg` (headless Chromium, scratchpad-only tooling; nothing
  enters the repo): Virgil font embedded as a data URI, `exportEmbedScene` on so the
  SVG itself reopens in excalidraw.com.

GitHub cannot render `.excalidraw` files, hence the SVG indirection. The diagram
mirrors the mermaid original 1:1: ticket → (brainstorm) → requirements → design →
tasks inside a "specified and reviewed" zone; implement/self-check → self/critic
review → evidence inside an "executed autonomously" zone; complete → learn; phase
labels rendered as gray captions under each node.

`userInteraction.diagramFormat: mermaid` is untouched: it governs diagrams the
harness produces (specs, PR briefings). This is an explicit operator request scoped
to the README hero diagram.

## Security design

The requirements name no trust boundary and no abuse case; this design keeps it that
way. The one considered vector — SVG script execution — is closed by construction:
the file comes from Excalidraw's exporter (shapes, paths, an embedded font and the
scene payload; no `<script>`, no event handlers), and GitHub additionally serves
README images through its sanitizing image proxy. Fail-closed check: the exported
SVG was grepped for scripting before commit.

## Testing strategy

Docs-only change, no code paths: verification is `markdownlint` on the changed
markdown (same hook locally and in CI), a JSON validity check of the scene, a
headless-Chromium screenshot of the SVG reviewed visually against the mermaid
original, and a round-trip of both files through excalidraw.com.
