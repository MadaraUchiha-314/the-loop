# Decision 081: the config editor splices the file, and validates with a schema it ships

- **Status:** proposed
- **Date:** 2026-08-14
- **Deciders:** @MadaraUchiha-314 (owner), the-loop (engineer)
- **Work item:** [issue-222](https://github.com/MadaraUchiha-314/the-loop/issues/222)

## Context

[Issue-222](https://github.com/MadaraUchiha-314/the-loop/issues/222) asks for an endpoint
that updates the CLI config, the Settings tab driving it, and the existing hot reload
verified through that path. The routing and the form are ordinary work. Two questions
underneath them are not, and both had an obvious answer that was wrong.

**How does a save write the file?** The obvious answer is `yaml.safe_load` →
`yaml.safe_dump`. The shipped `cli-config.yaml` is ~270 lines, of which about half are
comments explaining what each knob protects and why its default fails closed. A
round-trip deletes every one of them, silently, the first time somebody ticks a checkbox
in a browser. That is the kind of loss an operator discovers weeks later in a diff.

**What validates a write?** The obvious answer is `jsonschema`, which this repository
already uses in CI (`scripts/validate_config.py`). As a *runtime* dependency it would pull
`attrs`, `referencing` and the compiled `rpds-py` into a CLI whose lightness is one of its
stated properties — imported by every `the-loop poll` process, to validate nothing.

A third question came with them: the service serves a schema and validates against it, and
must do both from `pip install the-loopy-one`, where no plugin checkout exists.

## Decision

**Edit the operator's text; ship what is needed to check it; keep the dependency set.**

1. **A save is a splice, not a re-serialization.** `the_loop.yamlpatch` locates a value's
   own bytes through PyYAML's composer marks and rewrites exactly those. Comments, key
   order, blank lines, quoting and indentation are never parsed and so never lost. Style
   is preserved on the way out: a block list stays a block list, a flow list stays inline.
2. **A splice must prove itself.** `apply()` re-parses the text it produced and compares
   it to the document it was asked to produce; a mismatch raises and the caller writes
   nothing. This is what makes a hand-written text editor an acceptable thing to point at
   somebody's config — every edge case nobody thought of fails closed instead of
   corrupting the file. It is also why the write is atomic and why every rejection path is
   tested by asserting the file is byte-identical afterwards.
3. **The patch is sparse, and `null` removes.** Only changed keys travel, so the file
   keeps every key the form did not render and two people editing two sections do not
   overwrite each other. A leaf of `null` removes the key — free of ambiguity, because no
   key in the-loop's schemas is typed to accept `null`.
4. **The validator is ours, and two tests keep it honest.** `the_loop.configschema`
   implements the ten constraining keywords the-loop's schemas actually use. A **keyword
   guard** fails when a schema grows a construct it does not implement, and a
   **differential test** requires it to agree with real `jsonschema` over a corpus of valid
   and invalid documents. `scripts/validate_config.py` keeps using `jsonschema` for CI.
   The runtime dependency set is unchanged: PyYAML and the standard library.
5. **The schemas ship as package data too.** `cli/the_loop/schemas/` carries
   `cli-config.schema.json` and `collaborators.schema.json`, resolved relative to the
   module — the argument `graph/model.py::shipped_graph_path` already makes for the process
   graphs: a wheel with no plugin checkout must still work. This does not reopen
   [decision-080](decision-080.md), whose rule is about **projects**: `.the-loop/` remains
   the single authored home, and a byte-parity test holds the packaged copy to it.
6. **The service reloads its own config.** It gains the `Reloader` its daemons have had
   since issue-63, refreshed once per request, so a save through the API — or a hand-edit —
   is live on the next request. What genuinely cannot reload (the bind, the CORS
   middleware) is **reported** as `restartRequired` rather than pretended away.
7. **The form is derived from the schema, not written out.** Sections, prose, types,
   enums, ranges and defaults all come from `GET /api/v1/config/schema`. A hand-written
   TSX form over ~100 keys would be a second copy of the schema, and the copy is the one
   that rots. Subtrees with no typed control (a list of poll sources, the collaborator
   records) get a JSON field rather than a gap.
8. **A default is shown, never adopted.** An unset field displays the schema default as a
   placeholder and contributes nothing to the patch. Pre-filling would freeze today's
   defaults into the operator's file the first time they saved anything unrelated.
9. **Config is not an MCP tool.** Reading and writing the daemon's config stays an
   operator's act, alongside the existing exclusions (`sessions reset`, `graph force`): an
   agent that could rewrite `routing.authorizedUsers` or
   `integrations.github.cli.binary` would be editing the rules it is judged by.

## Consequences

- **The file an operator gets back is the file they wrote**, minus the values they
  changed. That is the property the whole splice mechanism exists for, and it is asserted
  against the real template rather than a fixture.
- **A new write path exists into executable daemon configuration**, reachable by anything
  that can reach the plane — which is already anything that can start a harness session
  (decision-059). The delta is durability and reach, not privilege, so the answer is
  visibility rather than a new gate: every save emits `config.updated` with the changed
  key paths (never the values), and `docs/capabilities/control-plane.md` states the
  route's authority beside the exposure guard. An operator who wants this route
  unreachable removes the browser origin from `service.cors.allowOrigins`; the network
  posture is otherwise unchanged.
- **Two copies of two schemas exist in the repository.** Byte parity is enforced by a
  test, and the authored file is the one under `.the-loop/` — but the copy is a real cost
  and a real thing to remember when editing a schema.
- **A validator we maintain can lag the spec.** It is scoped to the-loop's own schemas and
  guarded two ways, but a keyword added to a schema now has to be added to the validator
  (the guard test says so, in those words). If the schemas ever need `oneOf`/`allOf`, the
  trade should be revisited rather than extended indefinitely.
- **`restartRequired` is a promise about which keys are boot-time.** It is a literal list
  in `core.config`; a future value read at boot must be added to it, or the UI will say
  "live now" about something that is not.

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| `ruamel.yaml` round-trip mode | The standard answer to comment preservation, and a new runtime dependency for one write path. PyYAML's composer already exposes the marks, and the verification step covers the risk that buys. |
| `jsonschema` as a runtime dependency | A compiled transitive dependency (`rpds-py`) in every install, imported by processes that validate nothing. Kept as the dev/CI validator, where it is the right tool. |
| Full-document `PUT` | Makes comment loss inevitable and turns two people editing two sections into a lost update. |
| Dump the whole file and accept comment loss | The loss is silent and irreversible, and the comments are the documentation an operator reads while editing. |
| A hand-written form per config key | ~100 keys of schema, copied into TSX, guaranteed to drift. |
| Gate the write behind a new `service.configWrite` opt-in | Defensible, but it would leave the ticket's ask off by default and imply a boundary the plane does not have — the same caller can already spawn sessions. Visibility and the existing network posture are the honest answer. |
| Resolve the schema from `${CLAUDE_PLUGIN_ROOT}` at runtime | Breaks the case the service is for: a `pip install` with no plugin checkout. |
