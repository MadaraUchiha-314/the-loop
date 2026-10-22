"""The handoff record: format, parser, renderer and reader (issue-517, design §C2).

The record is a machine-read comment the poller trusts, so most of this file is
the negative space: every way a record is refused (T8), beside the round trips
(T1), the R6 starting-step table, part splitting at GitHub's 65,536-character
limit and the rendered-record snapshots (T6).

Golden files under ``tests/fixtures/handoff/`` hold the rendered record for each
carrier (``.txt``, so markdownlint leaves them alone). They are rendered from the
real code at test time; a change to the wire format fails here until the golden
file is regenerated and reviewed (``THE_LOOP_REGEN_HANDOFF_GOLDEN=1``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Dict, List, Optional

import pytest

from the_loop.core import handoff
from the_loop.core.handoff import (
    ALLOWED_ENTRY,
    CHAIN,
    COMMENT_LIMIT,
    MARKER,
    HandoffArtifact,
    HandoffRecord,
    collect_parts,
    extract_files,
    find_record,
    is_valid_branch,
    parse,
    parse_with_reason,
    render,
    sha256_text,
    stage_entry,
)

FIXTURES = Path(__file__).parent / "fixtures" / "handoff"
REGEN = os.environ.get("THE_LOOP_REGEN_HANDOFF_GOLDEN") == "1"

BRAINSTORM = "# Brainstorm\n\nOptions considered: A, B. Rejected: C.\n"
REQUIREMENTS = (
    "# Requirements\n\n```python\nprint('a fenced block inside a carried file')\n```\n"
)
SHA_B = sha256_text(BRAINSTORM)
SHA_R = sha256_text(REQUIREMENTS)


@dataclass
class FakeComment:
    """The four fields of :class:`the_loop.poller.base.Comment` the reader uses."""

    body: str
    author: str
    url: str
    created_at: str
    id: str = ""
    raw: Dict = field(default_factory=dict)


def _record(**overrides) -> HandoffRecord:
    base = HandoffRecord(
        version=1,
        stage="requirements-settled",
        enter="requirements-approval",
        artifacts=(
            HandoffArtifact("brainstorm.md", SHA_B),
            HandoffArtifact("requirements.md", SHA_R),
        ),
        carried_by="branch",
        branch="the-loop/issue-42-x",
        pull_request=43,
        source="Claude chat · 2026-10-21",
        approved_in_chat=("brainstorm.md",),
        mirror="jira:acme/PROJ-123",
        confirmation="> yes, file it",
    )
    return replace(base, **overrides)


def _body(**overrides) -> str:
    return render(_record(**overrides))[0]


def _golden(name: str, text: str) -> None:
    path = FIXTURES / name
    text += "\n"  # the golden file ends in a newline; the comment need not
    if REGEN:
        path.write_text(text, encoding="utf-8")
    assert path.is_file(), f"missing golden file {path}; regenerate with REGEN"
    assert text == path.read_text(encoding="utf-8")


def _swap(body: str, key: str, value: Optional[str]) -> str:
    """``body`` with the ``key:`` line's value replaced (or the line dropped)."""
    out: List[str] = []
    for line in body.split("\n"):
        if line.startswith(f"{key}:"):
            if value is None:
                continue
            line = f"{key}: {value}"
        out.append(line)
    return "\n".join(out)


# -- round trips per carrier (T1 R5.1, T6) -----------------------------------


def test_branch_record_round_trips():
    """
    Feature: the handoff record
      Scenario: a branch-carried record renders and parses back unchanged
        Given a requirements-settled record carried by a spec branch and PR
        When it is rendered and the comment is parsed
        Then the parsed record equals the original

    Requirement: docs/specs/issue-517/requirements.md R5.1
    """
    record = _record()
    comments = render(record)
    assert len(comments) == 1
    assert comments[0].startswith(MARKER)
    assert parse(comments[0]) == record


def test_ticket_record_round_trips_with_its_files():
    """
    Feature: the handoff record
      Scenario: a ticket-carried record carries each file in a details block
        Given a record carried by the ticket, with both files
        When it is rendered, parsed and its files extracted
        Then the record round-trips and each file comes back byte-equal

    Requirement: docs/specs/issue-517/requirements.md R5.1, R5.2
    """
    record = _record(carried_by="ticket", branch="", pull_request=0)
    files = {"brainstorm.md": BRAINSTORM, "requirements.md": REQUIREMENTS}
    comments = render(record, files)
    assert len(comments) == 1
    assert "<details><summary>requirements.md</summary>" in comments[0]
    assert parse(comments[0]) == record
    assert extract_files(comments) == files


def test_artifact_record_round_trips():
    """
    Feature: the handoff record
      Scenario: an artifact-carried record pins the spec-chain artifact's hash
        Given a design-settled record whose files live only in the artifact
        When it is rendered and parsed
        Then the URL and its sha256 survive the round trip

    Requirement: docs/specs/issue-517/requirements.md R5.1
    """
    record = _record(
        stage="design-settled",
        enter="test-planning",
        artifacts=(
            HandoffArtifact("requirements.md", SHA_R),
            HandoffArtifact("design.md", "c" * 64),
        ),
        carried_by="artifact",
        branch="",
        pull_request=0,
        spec_artifact="https://claude.ai/artifact/abc123",
        spec_artifact_sha256="d" * 64,
        approved_in_chat=("requirements.md",),
        mirror="",
    )
    assert parse(render(record)[0]) == record


@pytest.mark.parametrize(
    "name, record, files",
    [
        ("record_branch.txt", _record(), None),
        (
            "record_ticket.txt",
            _record(carried_by="ticket", branch="", pull_request=0),
            {"brainstorm.md": BRAINSTORM, "requirements.md": REQUIREMENTS},
        ),
        (
            "record_artifact.txt",
            _record(
                carried_by="artifact",
                branch="",
                pull_request=0,
                spec_artifact="https://claude.ai/artifact/abc123",
                spec_artifact_sha256="d" * 64,
                mirror="",
            ),
            None,
        ),
    ],
)
def test_rendered_record_snapshot(name, record, files):
    """
    Feature: the handoff record
      Scenario: the rendered record is byte-stable for each carrier
        Given a record for the branch, ticket or artifact carrier
        When it is rendered
        Then the comment equals the reviewed golden file

    Requirement: docs/specs/issue-517/testing-plan.md T6 (R5.1)
    """
    comments = render(record, files)
    _golden(name, "\n\n---- next comment ----\n\n".join(comments))


def test_golden_records_parse():
    """The checked-in fixtures are themselves valid records (they are the
    hand-reviewable form of the wire format)."""
    for name in ("record_branch.txt", "record_ticket.txt", "record_artifact.txt"):
        text = (FIXTURES / name).read_text(encoding="utf-8")
        assert parse(text) is not None, name


def test_as_dict_round_trips_with_camel_case_keys():
    record = replace(_record(), author="dev", comment_url="https://x/c/1")
    data = record.as_dict()
    assert data["carriedBy"] == "branch"
    assert data["pullRequest"] == 43
    assert data["approvedInChat"] == ["brainstorm.md"]
    assert data["artifacts"][0] == {"name": "brainstorm.md", "sha256": SHA_B}
    assert data["commentUrl"] == "https://x/c/1"
    # A state blob carries runtime keys beside the record (recordedAt).
    assert HandoffRecord.from_dict({**data, "recordedAt": "t"}) == record


def test_record_tolerates_unaligned_keys_and_unfenced_block():
    body = "\n".join(
        [
            MARKER,
            "stage: brainstorm-settled",
            "enter: brainstorm-approval",
            f"artifacts: brainstorm.md sha256:{SHA_B}",
            "carried-by: ticket",
        ]
    )
    record = parse(body)
    assert record is not None
    assert record.stage == "brainstorm-settled"
    assert record.carried_by == "ticket"


def test_multi_line_confirmation_round_trips():
    record = _record(confirmation="> yes, file it\n> and run it now")
    assert parse(render(record)[0]) == record


# -- STAGE_ENTRY (T1, R6 table) ----------------------------------------------


@pytest.mark.parametrize(
    "stage, names, node",
    [
        ("exploring", (), "brainstorming"),
        ("exploring", ("brainstorm.md",), "brainstorming"),
        ("brainstorm-settled", ("brainstorm.md",), "brainstorm-approval"),
        ("requirements-settled", ("requirements.md",), "requirements-approval"),
        (
            "requirements-settled",
            ("brainstorm.md", "requirements.md"),
            "requirements-approval",
        ),
        (
            "design-settled",
            ("requirements.md", "design.md", "testing-plan.md"),
            "design-approval",
        ),
        ("design-settled", ("requirements.md", "design.md"), "test-planning"),
        ("design-settled", ("bugfix.md", "design.md"), "test-planning"),
    ],
)
def test_stage_entry_rows(stage, names, node):
    """
    Feature: the poller starts at the right step
      Scenario: each stage enters its row's starting step
        Given a stage and the artifacts it carries
        When the starting step is computed
        Then it is the R6 table's starting step, and an allowed entry node

    Requirement: docs/specs/issue-517/requirements.md R6 table
    """
    assert stage_entry(stage, names) == node
    assert node in ALLOWED_ENTRY


def test_stage_entry_rejects_an_unknown_stage():
    with pytest.raises(ValueError):
        stage_entry("implemented", ())


def test_chain_is_the_closed_set():
    assert set(CHAIN) == {
        "brainstorm.md",
        "requirements.md",
        "bugfix.md",
        "design.md",
        "testing-plan.md",
    }


# -- every rejection reason (T1 R5.5, T8) ------------------------------------


def test_missing_marker_is_not_a_record():
    record, reason = parse_with_reason("stage: exploring\nenter: brainstorming\n")
    assert record is None
    assert "marker" in reason


def test_unknown_version_is_ignored():
    """
    Feature: the handoff record
      Scenario: a record of a version the reader does not know is ignored
        Given a record opening with the v2 marker
        When it is parsed
        Then no record is returned and the reason names the version

    Requirement: docs/specs/issue-517/requirements.md R5.5
    """
    body = _body().replace(MARKER, "<!-- the-loop:handoff v2 -->")
    record, reason = parse_with_reason(body)
    assert record is None
    assert "version" in reason


def test_unknown_key_is_rejected():
    """
    Feature: the handoff record
      Scenario: a record with a key the reader does not know is rejected
        Given a valid record plus a "run-now: yes" line
        When it is parsed
        Then no record is returned

    Requirement: docs/specs/issue-517/requirements.md R5.5
    """
    body = _body().replace("stage:", "run-now: yes\nstage:", 1)
    record, reason = parse_with_reason(body)
    assert record is None
    assert "run-now" in reason


def test_enter_implementation_is_rejected():
    """
    Feature: handoff abuse cases
      Scenario: a handoff record entering implementation is rejected
        Given a record whose enter line names implementation
        When it is parsed
        Then no record is returned (abuse case 2)

    Requirement: docs/specs/issue-517/requirements.md §Security, abuse case 2
    """
    record, reason = parse_with_reason(_swap(_body(), "enter", "implementation"))
    assert record is None
    assert "implementation" in reason


def test_enter_that_disagrees_with_the_stage_is_rejected():
    # An allowed node, but not the one the stage enters.
    record, reason = parse_with_reason(_swap(_body(), "enter", "design-approval"))
    assert record is None
    assert "enter" in reason


@pytest.mark.parametrize(
    "artifacts",
    [
        f"../../etc/passwd sha256:{SHA_B}",
        f"docs/specs/x/requirements.md sha256:{SHA_R}",
        f"notes.md sha256:{SHA_B}, requirements.md sha256:{SHA_R}",
    ],
)
def test_artifact_name_outside_the_closed_set_is_rejected(artifacts):
    """
    Feature: handoff abuse cases
      Scenario: an artifact name outside the closed set is refused
        Given a record listing a path or an unknown file name
        When it is parsed
        Then no record is returned, so no path ever comes from the record

    Requirement: docs/specs/issue-517/design.md §Security design
    """
    record, reason = parse_with_reason(_swap(_body(), "artifacts", artifacts))
    assert record is None
    assert "artifact" in reason


def test_requirements_and_bugfix_together_are_rejected():
    value = f"requirements.md sha256:{SHA_R}, bugfix.md sha256:{SHA_R}"
    record, reason = parse_with_reason(_swap(_body(), "artifacts", value))
    assert record is None
    assert "bugfix" in reason


def test_duplicate_artifact_is_rejected():
    value = f"requirements.md sha256:{SHA_R}, requirements.md sha256:{SHA_R}"
    assert parse(_swap(_body(), "artifacts", value)) is None


@pytest.mark.parametrize(
    "value",
    [
        "requirements.md",
        "requirements.md sha256:abc",
        f"requirements.md sha256:{SHA_R.upper()}",
        f"requirements.md md5:{SHA_R}",
    ],
)
def test_bad_sha_is_rejected(value):
    record, reason = parse_with_reason(_swap(_body(), "artifacts", value))
    assert record is None
    assert "sha256" in reason


@pytest.mark.parametrize(
    "carried",
    [
        "branch main · PR #43",
        "branch spec/issue-42 · PR #43",
        "branch the-loop/../main · PR #43",
        "branch the-loop/x.lock · PR #43",
        "branch the-loop/a@{1} · PR #43",
        "branch the-loop/a~1 · PR #43",
        "branch the-loop/ · PR #43",
        "branch the-loop/a b · PR #43",
        "branch the-loop/a · PR #x",
        "carrier-pigeon",
    ],
)
def test_bad_branch_or_carrier_is_rejected(carried):
    """
    Feature: handoff abuse cases
      Scenario: a branch outside the-loop/ or failing check-ref-format is refused
        Given a record whose carried-by names such a branch
        When it is parsed
        Then no record is returned

    Requirement: docs/specs/issue-517/design.md §Security design
    """
    record, reason = parse_with_reason(_swap(_body(), "carried-by", carried))
    assert record is None
    assert reason


@pytest.mark.parametrize(
    "name, ok",
    [
        ("the-loop/issue-42-x", True),
        ("the-loop/a/b_c.d", True),
        ("the-loop/a..b", False),
        ("the-loop/.hidden", False),
        ("the-loop/a.", False),
        ("the-loop//a", False),
        ("the-loop/a/", False),
        ("the-loop/a?b", False),
        ("the-loop/a*b", False),
        ("the-loop/a[b", False),
        ("the-loop/a\\b", False),
        ("the-loop/a:b", False),
        ("the-loop/a^b", False),
        ("the-loop/a\tb", False),
        ("the-loop/a\x7fb", False),
        ("feature/x", False),
        ("the-loop", False),
    ],
)
def test_is_valid_branch(name, ok):
    assert is_valid_branch(name) is ok


def test_approving_the_furthest_artifact_in_chat_is_rejected():
    """The furthest artifact is approved only by its gate on the ticket (R8.3)."""
    record, reason = parse_with_reason(
        _swap(_body(), "approved-in-chat", "brainstorm.md, requirements.md")
    )
    assert record is None
    assert "furthest" in reason


def test_approving_an_artifact_not_carried_is_rejected():
    body = _swap(_body(), "approved-in-chat", "design.md")
    assert parse(body) is None


def test_missing_required_key_is_rejected():
    record, reason = parse_with_reason(_swap(_body(), "stage", None))
    assert record is None
    assert "stage" in reason


def test_duplicate_key_is_rejected():
    body = _body().replace("stage:", "stage: exploring\nstage:", 1)
    assert parse(body) is None


def test_stage_whose_artifacts_do_not_fit_is_rejected():
    # brainstorm-settled carrying requirements.md: the stage undersells the chain.
    body = _swap(_body(), "stage", "brainstorm-settled")
    body = _swap(body, "enter", "brainstorm-approval")
    assert parse(body) is None


def test_artifact_carrier_without_a_spec_artifact_is_rejected():
    assert parse(_swap(_body(), "carried-by", "artifact")) is None


def test_bad_spec_artifact_is_rejected():
    body = _body(
        carried_by="artifact",
        branch="",
        pull_request=0,
        spec_artifact="https://claude.ai/artifact/abc123",
        spec_artifact_sha256="d" * 64,
    )
    assert parse(body) is not None
    assert parse(_swap(body, "spec-artifact", "https://claude.ai/a")) is None
    assert parse(_swap(body, "spec-artifact", f"javascript:x sha256:{SHA_B}")) is None


def test_bad_mirror_is_rejected():
    assert parse(_swap(_body(), "mirror", "PROJ-123")) is None


def test_parts_on_a_non_ticket_carrier_is_rejected():
    body = _body().replace("confirmation:", "parts: 2\nconfirmation:", 1)
    assert parse(body) is None


def test_two_records_in_one_comment_are_rejected():
    assert parse(_body() + "\n\n" + _body()) is None


def test_quoted_record_is_not_a_record():
    quoted = "\n".join(f"> {line}" for line in _body().split("\n"))
    assert parse(quoted) is None


# -- parts (T1 R5.2) ---------------------------------------------------------


def _big(n: int) -> str:
    # Lines of mixed content, including backtick runs, so fences must adapt.
    line = "lorem ipsum ``` dolor — ünïcode ✓ sit amet\n"
    return (line * (n // len(line) + 1))[:n]


def test_body_over_the_limit_splits_into_parts_rejoined_byte_equal():
    """
    Feature: the handoff record
      Scenario: a body over 65,536 characters continues in part comments
        Given a ticket-carried record whose files total well over the limit
        When it is rendered
        Then every comment is at most 65,536 characters
        And the record lists the parts
        And the files extracted from all comments are byte-equal, none truncated

    Requirement: docs/specs/issue-517/requirements.md R5.2
    """
    files = {
        "brainstorm.md": _big(30_000),
        "requirements.md": _big(150_000),
        "design.md": _big(70_000) + "no trailing newline",
    }
    record = HandoffRecord(
        version=1,
        stage="design-settled",
        enter="test-planning",
        artifacts=tuple(HandoffArtifact(n, sha256_text(t)) for n, t in files.items()),
        carried_by="ticket",
    )
    comments = render(record, files)
    assert len(comments) >= 4
    assert all(len(c) <= COMMENT_LIMIT for c in comments)
    parsed = parse(comments[0])
    assert parsed is not None
    assert parsed.parts == len(comments) - 1
    for n, body in enumerate(comments[1:], start=1):
        assert body.startswith(f"<!-- the-loop:handoff-part v1 {n}/{parsed.parts} -->")
    assert extract_files(comments) == files
    for name, text in extract_files(comments).items():
        assert (
            sha256_text(text)
            == dict((a.name, a.sha256) for a in parsed.artifacts)[name]
        )


def test_render_rejects_files_outside_the_record():
    record = _record(carried_by="ticket", branch="", pull_request=0)
    with pytest.raises(ValueError):
        render(record, {"design.md": "x"})


def test_render_rejects_files_on_a_branch_carrier():
    with pytest.raises(ValueError):
        render(_record(), {"brainstorm.md": BRAINSTORM})


def test_extract_files_ignores_names_outside_the_chain():
    body = (
        _body(carried_by="ticket", branch="", pull_request=0)
        + "\n<details><summary>../evil.sh</summary>\n\n````\nrm -rf /\n````\n\n</details>\n"
    )
    assert "../evil.sh" not in extract_files([body])


def test_sha256_text_normalizes_line_endings():
    assert sha256_text("a\r\nb\n") == sha256_text("a\nb\n")


@pytest.mark.parametrize("text", ["", "\n", "a\r", "x\r\n\n", "`", "tail`"])
def test_edge_bodies_extract_to_their_hashed_bytes(text):
    """Empty files, trailing CR/LF and trailing backticks survive the fence."""
    record = HandoffRecord(
        version=1,
        stage="brainstorm-settled",
        enter="brainstorm-approval",
        artifacts=(HandoffArtifact("brainstorm.md", sha256_text(text)),),
        carried_by="ticket",
    )
    extracted = extract_files(render(record, {"brainstorm.md": text}))
    assert sha256_text(extracted["brainstorm.md"]) == sha256_text(text)


# -- find_record and collect_parts (T8 abuse 1, security design) ------------


def _authorized(login: str) -> bool:
    return login in {"dev", "owner"}


def test_unauthorized_record_is_ignored():
    """
    Feature: handoff abuse cases
      Scenario: a handoff record from an unauthorized user is ignored
        Given a well-formed record posted by a login not in authorizedUsers
        When the reader looks for the record
        Then no record is returned and the reason names the author (abuse case 1)

    Requirement: docs/specs/issue-517/requirements.md §Security, abuse case 1
    """
    comments = [
        FakeComment(_body(), "mallory", "https://x/c/1", "2026-10-21T10:00:00Z")
    ]
    record, reasons = find_record(comments, _authorized)
    assert record is None
    assert len(reasons) == 1
    assert "mallory" in reasons[0]


def test_newest_authorized_record_wins_and_metadata_comes_from_the_api():
    older = FakeComment(_body(), "dev", "https://x/c/1", "2026-10-21T10:00:00Z")
    newer = FakeComment(
        _body(confirmation="> newer"), "owner", "https://x/c/2", "2026-10-21T11:00:00Z"
    )
    noise = FakeComment(
        "just a comment", "dev", "https://x/c/3", "2026-10-21T12:00:00Z"
    )
    bad = FakeComment(
        _swap(_body(), "enter", "implementation"),
        "dev",
        "https://x/c/4",
        "2026-10-21T13:00:00Z",
    )
    record, reasons = find_record([older, newer, noise, bad], _authorized)
    assert record is not None
    assert record.confirmation == "> newer"
    assert record.author == "owner"
    assert record.comment_url == "https://x/c/2"
    assert len(reasons) == 1 and "https://x/c/4" in reasons[0]


def test_record_text_cannot_set_its_own_author():
    body = _body().replace("confirmation:", "author: owner\nconfirmation:", 1)
    comments = [FakeComment(body, "mallory", "https://x/c/1", "t1")]
    record, _ = find_record(comments, _authorized)
    assert record is None


def test_a_pasted_self_marker_from_an_unauthorized_author_is_ignored():
    """Requirement: docs/specs/issue-517/requirements.md abuse case 1 (self-review
    round 1): the self-marker is never evidence on its own."""
    body = _body() + "\n<!-- the-loop:agent-comment -->"
    comments = [FakeComment(body, "mallory", "https://x/c/1", "t1")]
    record, reasons = find_record(comments, _authorized)
    assert record is None
    assert "not authorized" in reasons[0]


def test_a_record_with_no_author_is_ignored():
    """Requirement: docs/specs/issue-517/requirements.md abuse case 1 (self-review
    round 1): a deleted account's comment has author "", which an actor-less
    authorization check would admit."""
    comments = [FakeComment(_body(), "", "https://x/c/1", "t1")]
    record, reasons = find_record(comments, lambda login: True)
    assert record is None
    assert "no author" in reasons[0]


def _split_comments(author_of_part: str = "dev") -> List[FakeComment]:
    files = {"requirements.md": _big(100_000)}
    record = HandoffRecord(
        version=1,
        stage="requirements-settled",
        enter="requirements-approval",
        artifacts=(
            HandoffArtifact("requirements.md", sha256_text(files["requirements.md"])),
        ),
        carried_by="ticket",
    )
    bodies = render(record, files)
    assert len(bodies) == 2
    return [
        FakeComment(bodies[0], "dev", "https://x/c/1", "t1"),
        FakeComment(bodies[1], author_of_part, "https://x/c/2", "t2"),
    ]


def test_parts_by_the_record_author_are_collected():
    comments = _split_comments()
    record, _ = find_record(comments, _authorized)
    assert record is not None
    bodies = collect_parts(comments, record)
    assert bodies is not None and len(bodies) == 2
    assert extract_files(bodies)["requirements.md"] == _big(100_000)


def test_part_by_another_author_is_ignored():
    """
    Feature: handoff abuse cases
      Scenario: a part comment by another author is ignored
        Given a record by an authorized user and its part posted by someone else
        When the parts are collected
        Then the forged part does not count and the set is incomplete

    Requirement: docs/specs/issue-517/design.md §Security design
    """
    comments = _split_comments(author_of_part="owner")
    record, _ = find_record(comments, _authorized)
    assert record is not None
    assert collect_parts(comments, record) is None


def test_genuine_part_wins_over_a_forged_one():
    comments = _split_comments()
    forged = FakeComment(
        comments[1].body.replace("lorem", "LOREM"), "mallory", "u", "t1.5"
    )
    comments.insert(1, forged)
    record, _ = find_record(comments, _authorized)
    assert record is not None
    bodies = collect_parts(comments, record)
    assert bodies is not None
    assert "LOREM" not in extract_files(bodies)["requirements.md"]


def test_record_without_parts_collects_itself():
    comments = [FakeComment(_body(), "dev", "https://x/c/1", "t1")]
    record, _ = find_record(comments, _authorized)
    assert record is not None
    assert collect_parts(comments, record) == [comments[0].body]


def test_module_exports():
    assert set(handoff.__all__) >= {
        "HandoffArtifact",
        "HandoffRecord",
        "parse",
        "parse_with_reason",
        "render",
        "find_record",
        "collect_parts",
        "extract_files",
        "stage_entry",
        "sha256_text",
    }


def test_a_carried_file_that_contains_the_marker_line_round_trips():
    """
    Feature: the handoff record
      Scenario: a carried brainstorm quotes the record marker
        Given a ticket-carried brainstorm.md with the marker line at column 0
        When the record is rendered and read back
        Then it posts, parses, and the file comes back byte-equal

    Requirement: R5.1, R5.2 (self-review round 1, finding 5)
    """
    text = "# Brainstorm\n\n" + MARKER + "\n\nThe record starts with that line.\n"
    record = HandoffRecord(
        version=1,
        stage="brainstorm-settled",
        enter="brainstorm-approval",
        artifacts=(HandoffArtifact("brainstorm.md", sha256_text(text)),),
        carried_by="ticket",
    )
    bodies = render(record, {"brainstorm.md": text})
    assert parse(bodies[0]) is not None
    assert extract_files(bodies)["brainstorm.md"] == text
