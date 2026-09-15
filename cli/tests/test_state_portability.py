"""The generated-state classification, pinned (issue-128, decision-046).

Issue #128 asked which of the-loop's state files may be carried to another
machine. The answer is one of the four — the portable work-item records — and the
reason is that the rest are handles to one machine rather than facts about the
world. That answer is written in three places — ``the_loop.state.GENERATED_PATHS``, ``docs/cli/state.md`` and the
repository's own ``.gitignore`` — so it needs a test, or the next generated file
will be added with the question unasked.

Five assertions:

======  ==========================================================  ==========================
S1      every ``StateLayout`` path property is claimed by an entry  a path added, unclassified
S2      every entry's ``attr``/``default`` resolves against it      a declaration gone stale
S3      every entry is documented with the same classification      docs disagreeing with code
S4      the documented ``.gitignore`` block is the one in use       the recipe undogfooded
S5      the block's patterns match the classification               a recipe that lies
======  ==========================================================  ==========================

S5 is the one that earns its keep: S4 only proves two files are identical, while S5
evaluates the patterns against the paths they are supposed to govern. It is checked
with the small matcher below rather than by shelling out to ``git check-ignore``, so
this stays a pure unit test.

Pure filesystem reads: no network, no subprocess, no fixtures. The documentation
assertions skip when ``docs/`` is absent (a source distribution), matching
``test_docs_parity.py``; S1 and S2 need no documentation and always run.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

import pytest

from the_loop.state import (
    ATTRIBUTE_KINDS,
    ATTRIBUTES,
    DEFAULT_STATE_ROOT,
    GENERATED_PATHS,
    MACHINE_FILE,
    OPERATOR_FILE,
    REPOSITORY_FILE,
    StateLayout,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_DOC = REPO_ROOT / "docs" / "cli" / "state.md"
GITIGNORE = REPO_ROOT / ".gitignore"

#: A sample work-item slug, for the paths documented with a ``<slug>`` placeholder.
SAMPLE_SLUG = "github-octo-repo-15"

needs_docs = pytest.mark.skipif(
    not (REPO_ROOT / "docs").is_dir(),
    reason="documentation site not present (source distribution)",
)


def _layout_path_attrs() -> List[str]:
    """Every public path property of :class:`StateLayout`.

    ``root_path`` is excluded: it is the root itself, not something generated under
    it. Everything else that resolves to a path is a file or directory the-loop
    writes, and therefore something an operator has to know whether to carry.
    """
    return sorted(
        name
        for name, value in vars(StateLayout).items()
        if isinstance(value, property) and name != "root_path"
    )


def _resolved(entry) -> str:
    """The entry's documented default with ``<root>`` filled in, posix-style."""
    return entry.default.replace("<root>", DEFAULT_STATE_ROOT)


# -- S1/S2: the declaration against the layout ---------------------------------------


def test_every_generated_path_is_classified() -> None:
    """S1 — a new path on StateLayout must say whether it travels."""
    declared = {entry.attr for entry in GENERATED_PATHS}
    missing = [attr for attr in _layout_path_attrs() if attr not in declared]
    assert not missing, (
        f"StateLayout.{missing[0]} generates a path that GENERATED_PATHS does not "
        "classify — add an entry saying whether it means anything on another machine "
        "(the-loop/state.py), and document it in docs/cli/state.md"
    )


def test_declared_attrs_resolve_to_their_documented_default() -> None:
    """S2 — the declaration cannot drift from the paths the code actually derives."""
    layout = StateLayout()
    for entry in GENERATED_PATHS:
        assert hasattr(layout, entry.attr), (
            f"GENERATED_PATHS entry {entry.name!r} names StateLayout.{entry.attr}, "
            "which does not exist"
        )
        resolved = Path(getattr(layout, entry.attr)).as_posix()
        documented = _resolved(entry)
        assert documented == resolved or documented.startswith(resolved + "/"), (
            f"{entry.name}: declared default {entry.default!r} does not sit under "
            f"StateLayout.{entry.attr} ({resolved!r})"
        )


def test_exactly_the_world_facts_are_portable() -> None:
    """The split itself, stated once so a flipped boolean is a red build."""
    portable = sorted(e.name for e in GENERATED_PATHS if e.portable)
    # The records, and the index that describes them (issue-130) — which travels
    # for exactly that reason: left behind, it would describe a directory that is
    # not there.
    assert portable == ["work-item index", "work-item record"]
    assert all(entry.why.strip() for entry in GENERATED_PATHS)


# -- S3: the declaration against the documentation ------------------------------------


def _doc_classifications() -> dict:
    """``{path: "portable" | "local"}`` from the state page's classification table."""
    rows = {}
    row_re = re.compile(r"^\|\s*`([^`]+)`\s*\|(.+)\|\s*$")
    for line in STATE_DOC.read_text().splitlines():
        match = row_re.match(line)
        if not match:
            continue
        verdicts = [word for word in ("portable", "local") if word in match.group(2)]
        if len(verdicts) == 1:
            rows[match.group(1)] = verdicts[0]
    return rows


@needs_docs
def test_every_generated_path_is_documented() -> None:
    """S3 — the page classifies every declared path, the same way the code does."""
    documented = _doc_classifications()
    for entry in GENERATED_PATHS:
        assert entry.default in documented, (
            f"{entry.name} ({entry.default}) is missing from the classification table "
            f"in {STATE_DOC.relative_to(REPO_ROOT)}"
        )
        expected = "portable" if entry.portable else "local"
        assert documented[entry.default] == expected, (
            f"{entry.name} is {expected} in the-loop/state.py but "
            f"{documented[entry.default]} in {STATE_DOC.relative_to(REPO_ROOT)}"
        )


# -- S4/S5: the recipe ----------------------------------------------------------------


def _documented_block() -> str:
    """The ```gitignore fenced block on the state page."""
    text = STATE_DOC.read_text()
    match = re.search(r"```gitignore\n(.*?)```", text, re.DOTALL)
    assert match, f"no gitignore block in {STATE_DOC.relative_to(REPO_ROOT)}"
    return match.group(1)


@needs_docs
def test_repository_uses_the_documented_block() -> None:
    """S4 — the-loop tracks its own portable state, with the block it publishes."""
    assert _documented_block() in GITIGNORE.read_text(), (
        "the .gitignore block documented in docs/cli/state.md is not the one this "
        "repository uses — the recipe and the dogfood have drifted apart"
    )


def _compile(pattern: str) -> Tuple[re.Pattern, bool, bool]:
    """One gitignore pattern → (regex, negated, directory-only).

    Only the syntax the block uses: leading ``!``, a trailing ``/`` for
    directory-only, and ``*`` as "anything but a separator". Every pattern here
    contains a ``/``, so all of them are anchored at the root, which is why no
    unanchored-basename case is modelled.
    """
    negated = pattern.startswith("!")
    body = pattern[1:] if negated else pattern
    dir_only = body.endswith("/")
    body = body.rstrip("/")
    regex = "".join("[^/]*" if ch == "*" else re.escape(ch) for ch in body)
    return re.compile(rf"^{regex}$"), negated, dir_only


def _is_ignored(block: str, path: str, *, is_dir: bool = False) -> bool:
    """Whether ``path`` (repo-relative, posix) is ignored by ``block``.

    Models the two rules the block depends on: **last match wins**, and git does
    not descend into an excluded directory — so a ``!`` cannot rescue a file whose
    parent is excluded. Comments and blank lines are skipped.
    """
    patterns = [
        _compile(line.strip())
        for line in block.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    def matches(candidate: str, candidate_is_dir: bool) -> bool:
        verdict = False
        for regex, negated, dir_only in patterns:
            if dir_only and not candidate_is_dir:
                continue
            if regex.match(candidate):
                verdict = not negated
        return verdict

    parts = path.split("/")
    for depth in range(1, len(parts)):
        if matches("/".join(parts[:depth]), True):
            return True  # an excluded ancestor: nothing below it is reachable
    return matches(path, is_dir)


@needs_docs
def test_block_ignores_exactly_the_local_paths() -> None:
    """S5 — the patterns agree with the classification they claim to implement."""
    block = _documented_block()
    for entry in GENERATED_PATHS:
        path = _resolved(entry).replace("<slug>", SAMPLE_SLUG)
        ignored = _is_ignored(block, path)
        assert ignored is not entry.portable, (
            f"{entry.name} ({path}) is declared "
            f"{'portable' if entry.portable else 'local'} but the documented "
            f".gitignore block {'ignores' if ignored else 'tracks'} it"
        )


@needs_docs
def test_block_ignores_the_atomic_writers_temporaries() -> None:
    """A crash between mkstemp and os.replace must not leave a tracked stray."""
    block = _documented_block()
    assert _is_ignored(block, ".the-loop/portable/tmp9k2f.tmp")
    # ...while the record it was about to become stays tracked.
    assert not _is_ignored(block, ".the-loop/portable/github-octo-repo-15.json")


# -- the attribute classification (issue-368) ----------------------------------
#
# `GENERATED_PATHS` above answers "does this FILE travel?". These answer the
# question that had no answer at all until issue-368 — "where does this
# ATTRIBUTE go?" — which is why a pull request came to be recorded only in a
# file that never travels, a Slack thread only in a machine-wide one, and a
# harness session id in a repository. The rule is data (`ATTRIBUTES`), so the
# next attribute cannot be added without answering "whose is this?".


def _state_keys() -> set:
    """Every top-level key the work item's own checked-in file is written with."""
    from the_loop.graph.state import WorkItemState

    return set(WorkItemState(work_item="issue-1").as_dict())


def _portable_keys() -> set:
    """Every section the operator's record may carry, plus its identity keys."""
    from the_loop.workitem import SEALED, SECTIONS

    return set(SECTIONS) | {"ref", "url", SEALED}


def _registry_keys() -> set:
    """Every top-level key a machine-local session record is written with."""
    from the_loop.sessions import Session, WorkItemRef

    session = Session(
        work_item=WorkItemRef.parse("github:octo/repo#15"),
        harness="claude",
        harness_session_id="s-1",
        cwd=".",
    )
    session.channels = {"slack": {"cursors": {}}}
    return set(session.record_dict())


def test_every_attribute_is_classified() -> None:
    """S6 — a file cannot grow a key the rule does not name."""
    declared = {(a.file, a.key) for a in ATTRIBUTES}
    for file_id, keys in (
        (REPOSITORY_FILE, _state_keys()),
        (OPERATOR_FILE, _portable_keys()),
        (MACHINE_FILE, _registry_keys()),
    ):
        for key in keys:
            assert (file_id, key) in declared, (
                f"{file_id} writes {key!r}, which no ATTRIBUTES entry claims — "
                "say which kind of thing it is, and the rule will say which "
                "file it belongs in"
            )


def test_no_attribute_is_declared_for_a_key_that_is_not_written() -> None:
    """S7 — a declaration that outlived its key is a rule about nothing."""
    written = {
        REPOSITORY_FILE: _state_keys(),
        OPERATOR_FILE: _portable_keys(),
        MACHINE_FILE: _registry_keys(),
    }
    for attribute in ATTRIBUTES:
        assert attribute.key in written[attribute.file], (
            f"ATTRIBUTES claims {attribute.key!r} in {attribute.file}, which "
            "does not write it"
        )


def test_every_kind_sits_in_the_file_its_rule_allows() -> None:
    """S8 — the rule, enforced: a machine handle can never be in a tracked file.

    This is the assertion the whole table exists for. `session` was in the
    repository's file for two releases because nothing could state that a
    harness conversation id is a machine handle and that a machine handle is
    never checked in.
    """
    for attribute in ATTRIBUTES:
        allowed, why = ATTRIBUTE_KINDS[attribute.kind]
        if not allowed:
            continue  # `derived` lives wherever its reader is
        assert attribute.file == allowed, (
            f"{attribute.key!r} is a {attribute.kind}, which belongs in "
            f"{allowed} — {why} — but it is declared in {attribute.file}"
        )


def test_no_machine_handle_is_in_a_tracked_file() -> None:
    """S9 — the same rule from the other side, stated as the property it buys."""
    tracked = {REPOSITORY_FILE, OPERATOR_FILE}
    handles = [a for a in ATTRIBUTES if a.kind == "machine-handle"]
    assert handles, "the machine's file must hold something"
    for attribute in handles:
        assert attribute.file not in tracked, (
            f"{attribute.key!r} is a machine handle in {attribute.file}, which "
            "is tracked in git — a conversation id, a tmux name or an absolute "
            "path must never reach a repository"
        )


@needs_docs
def test_the_attribute_table_is_documented() -> None:
    """S10 — `docs/cli/state.md` names every attribute the code declares."""
    page = (REPO_ROOT / "docs" / "cli" / "state.md").read_text(encoding="utf-8")
    for attribute in ATTRIBUTES:
        assert f"`{attribute.key}`" in page, (
            f"{attribute.key!r} ({attribute.file}) is declared in ATTRIBUTES but "
            "docs/cli/state.md does not mention it"
        )
