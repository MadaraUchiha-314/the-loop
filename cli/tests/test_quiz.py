"""The explainer's quiz gates (issue-488) — unit level.

The two hooks (`post-quiz-attestation`, `quiz-attested`), the GitHub edit
history they read (`comment_edits`), the `explainer` checklist row, the
runtime's `not-offered` skip, and the doorbell's three ends: the poller, the
webhook router and the dispatcher.
"""

from __future__ import annotations

import re

from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from ghfakes import FakeGitHubClient, not_found

from the_loop.authz import mark_self_authored
from the_loop.ghapi import GhComment, GhCommentEdits, GitHubClient
from the_loop.graph.contract import HookContext, WorkItem
from the_loop.graph.hooks import quiz, selection
from the_loop.graph.integrations.github import GitHubProvider
from the_loop.graph.model import load_graph
from the_loop.graph.runtime import NOT_OFFERED, Runtime
from the_loop.graph.state import WorkItemState
from the_loop.quizmarks import ATTESTATIONS, attestation_ticked, quiz_marker
from the_loop.sessions import WorkItemRef
from the_loop.webhook.router import QUIZ_ATTESTATION_EVENT, quiz_attestation_event

REF = "github:o/r#7"
OWNER = "owner"
SPEC_LINE = ATTESTATIONS["spec-quiz"]
CODE_LINE = ATTESTATIONS["code-quiz"]
RECORD = """# Spec explainer: x

## Spec explainer

| Field | Value |
|---|---|
| Depth | standard |
| Location | {location} |
| Published as | own artifact |
| Questions | 3 |
"""
DIGEST = ["requirements.md|bugfix.md", "design.md", "testing-plan.md"]


# -- fixtures ------------------------------------------------------------------


@pytest.fixture()
def spec_dir(tmp_path: Path) -> Path:
    path = tmp_path / "docs" / "specs" / "issue-7"
    (path / "evidence").mkdir(parents=True)
    (path / "requirements.md").write_text("# R\n", encoding="utf-8")
    (path / "design.md").write_text("# D\n", encoding="utf-8")
    (path / "testing-plan.md").write_text("# T\n", encoding="utf-8")
    _record(path, "https://claude.ai/code/artifact/abc")
    return path


@pytest.fixture()
def github(_hermetic_graph_integration) -> FakeGitHubClient:
    """The autouse provider's in-memory client — seeded per test."""
    return _hermetic_graph_integration.client


def _record(spec_dir: Path, location: str, name: str = "spec-explainer.md") -> None:
    (spec_dir / "evidence" / name).write_text(
        RECORD.format(location=location), encoding="utf-8"
    )


def _ctx(
    spec_dir: Path,
    node: str = "spec-quiz",
    boundary: str = "exit",
    params: Optional[Dict[str, Any]] = None,
    event: Optional[Dict[str, Any]] = None,
    authorized: Optional[List[str]] = None,
) -> HookContext:
    if params is None:
        params = (
            {"digest": DIGEST}
            if boundary == "exit" and node == "spec-quiz"
            else {
                "node": node,
                "record": "evidence/spec-explainer.md",
                "on": "ticket",
                "digest": DIGEST,
            }
        )
    return HookContext(
        work_item=WorkItem(ref=REF, id="issue-7", spec_dir=spec_dir),
        node={"id": node},
        boundary=boundary,
        repo=spec_dir.parents[2],
        event=event,
        config={"authorizedUsers": authorized if authorized is not None else [OWNER]},
        params=params,
    )


def _posted_body(spec_dir: Path, github: FakeGitHubClient, node="spec-quiz") -> str:
    result = quiz.post_quiz_attestation(_ctx(spec_dir, node=node, boundary="entry"))
    assert result.status == "pass", result.messages
    return github.posted[-1][3]


def _seed(
    github: FakeGitHubClient,
    body: str,
    *,
    ticked: bool,
    editors: List[str],
    cid: str = "IC_1",
    line: str = SPEC_LINE,
) -> None:
    """Put the-loop's comment on the thread, ticked or not, with an edit history."""
    if ticked:
        body = body.replace(f"- [ ] {line}", f"- [x] {line}")
    github.comments[("o", "r", 7)] = [
        # the-loop posts under the operator's own login (decision-023)
        GhComment(id=cid, body=body, author=OWNER, created_at="t0", url="u")
    ]
    github.edits[cid] = GhCommentEdits(
        body=body,
        url="https://github.com/o/r/issues/7#issuecomment-1",
        author=OWNER,
        edits=tuple((who, f"2026-10-15T00:00:0{i}Z") for i, who in enumerate(editors)),
    )


# -- the vocabulary --------------------------------------------------------------


def test_only_a_ticked_attestation_line_counts():
    assert attestation_ticked(f"- [x] {SPEC_LINE}")
    assert attestation_ticked(f"* [X] {SPEC_LINE}", "spec-quiz")
    assert not attestation_ticked(f"- [ ] {SPEC_LINE}")
    assert not attestation_ticked(f"- [x] {SPEC_LINE}", "code-quiz")
    assert not attestation_ticked("- [x] I have read something else.")
    assert not attestation_ticked(f"> - [x] {SPEC_LINE}")  # a quote is not the box


def test_the_digest_is_stable_and_moves_with_one_byte(spec_dir):
    first = quiz.spec_digest(spec_dir, DIGEST)
    assert first == quiz.spec_digest(spec_dir, DIGEST) and len(first) == 12
    (spec_dir / "design.md").write_text("# D!\n", encoding="utf-8")
    assert quiz.spec_digest(spec_dir, DIGEST) != first
    assert quiz.spec_digest(spec_dir / "nowhere", DIGEST) == "-"


# -- A3: who edited a comment -------------------------------------------------------


class _GraphQL(GitHubClient):
    def __init__(self, answer):
        self.answer = answer

    def graphql(self, query, variables, host=""):
        return self.answer


def test_comment_edits_sorts_newest_first_and_keeps_unknown_editors_empty():
    client = _GraphQL(
        {
            "node": {
                "body": "b",
                "url": "u",
                "author": {"login": "the-loop"},
                "userContentEdits": {
                    "nodes": [
                        {"editedAt": "2026-10-15T00:00:01Z", "editor": {"login": "a"}},
                        {"editedAt": "2026-10-15T00:00:03Z", "editor": None},
                        {"editedAt": "2026-10-15T00:00:02Z", "editor": {"login": "b"}},
                    ]
                },
            }
        }
    )
    found = client.comment_edits("IC_1")
    assert [who for who, _ in found.edits] == ["", "b", "a"]
    assert found.author == "the-loop"


def test_comment_edits_refuses_a_missing_node():
    from the_loop.ghapi import GitHubApiError

    with pytest.raises(GitHubApiError):
        _GraphQL({"node": None}).comment_edits("IC_1")
    with pytest.raises(GitHubApiError):
        _GraphQL({}).comment_edits("")


def test_the_provider_maps_comment_edits():
    client = FakeGitHubClient()
    client.edits["IC_1"] = GhCommentEdits("b", "u", "the-loop", (("owner", "t"),))
    out = GitHubProvider(client=client).call("comment-edits", ref=REF, id="IC_1")
    assert out["edits"] == [{"editor": "owner", "editedAt": "t"}]


def test_jira_does_not_claim_to_know_who_edited():
    from the_loop.graph.integrations.base import OperationUnsupported
    from the_loop.graph.integrations.jira import JiraProvider
    from jirafakes import FakeJiraClient

    with pytest.raises(OperationUnsupported):
        JiraProvider(client=FakeJiraClient()).call(
            "comment-edits", ref="jira:x/A-1", id="1"
        )


# -- A4: post-quiz-attestation --------------------------------------------------------


def test_the_quiz_comment_links_the_page_and_carries_one_unticked_box(spec_dir, github):
    body = _posted_body(spec_dir, github)
    assert "https://claude.ai/code/artifact/abc" in body
    assert f"- [ ] {SPEC_LINE}" in body and body.count("- [ ]") == 1
    marker = quiz_marker(body)
    assert marker == {
        "node": "spec-quiz",
        "round": "1",
        "digest": quiz.spec_digest(spec_dir, DIGEST),
    }
    assert "no reply needed" in body


def test_posting_is_idempotent_per_round_and_digest(spec_dir, github):
    body = _posted_body(spec_dir, github)
    _seed(github, body, ticked=False, editors=[])
    quiz.post_quiz_attestation(_ctx(spec_dir, boundary="entry"))
    assert len(github.posted) == 1
    (spec_dir / "design.md").write_text("# D changed\n", encoding="utf-8")
    quiz.post_quiz_attestation(_ctx(spec_dir, boundary="entry"))
    assert len(github.posted) == 2  # a new digest is a new quiz


def test_a_record_with_no_location_blocks_the_gate(spec_dir, github):
    _record(spec_dir, "<the Claude artifact URL, or …>")  # the template, unfilled
    result = quiz.post_quiz_attestation(_ctx(spec_dir, boundary="entry"))
    assert result.status == "block" and not github.posted
    (spec_dir / "evidence" / "spec-explainer.md").unlink()
    assert (
        quiz.post_quiz_attestation(_ctx(spec_dir, boundary="entry")).status == "block"
    )


def test_a_committed_page_gets_view_commands_built_only_from_safe_parts(
    spec_dir, github
):
    _record(
        spec_dir,
        "https://github.com/o/r/blob/feat/x/docs/specs/issue-7/explainer/explainer.html",
    )
    body = _posted_body(spec_dir, github)
    assert (
        "gh api -H 'Accept: application/vnd.github.raw' "
        "'repos/o/r/contents/docs/specs/issue-7/explainer/explainer.html?ref=feat/x'"
    ) in body
    assert "https://raw.githubusercontent.com/o/r/feat/x/docs/specs/" in body
    assert "python3 -m webbrowser" in body


def test_a_hostile_location_gets_no_shell_command(spec_dir, github):
    _record(spec_dir, "https://github.com/o/r/blob/x/a$(rm -rf ~).html")
    body = _posted_body(spec_dir, github)
    assert "gh api" not in body and "curl" not in body


def test_the_code_quiz_goes_to_every_open_pull_request(spec_dir, github):
    state = WorkItemState.load(spec_dir, "issue-7")
    from the_loop.graph.state import PullRequest

    state.pull_requests = [
        PullRequest(ref="github:o/r#20", repository="o/r", number=20),
        PullRequest(ref="github:o/r#21", repository="o/r", number=21),
    ]
    state.save(spec_dir)
    _record(spec_dir, "https://claude.ai/code/artifact/abc", "explainer.md")
    ctx = _ctx(
        spec_dir,
        node="code-quiz",
        boundary="entry",
        params={
            "node": "code-quiz",
            "record": "evidence/explainer.md",
            "on": "pull-requests",
        },
    )
    quiz.post_quiz_attestation(ctx)
    assert sorted(p[2] for p in github.posted) == [20, 21]
    assert all(f"- [ ] {CODE_LINE}" in p[3] for p in github.posted)


def test_the_code_quiz_falls_back_to_the_ticket_with_no_pull_request(spec_dir, github):
    _record(spec_dir, "https://claude.ai/code/artifact/abc", "explainer.md")
    ctx = _ctx(
        spec_dir,
        node="code-quiz",
        boundary="entry",
        params={
            "node": "code-quiz",
            "record": "evidence/explainer.md",
            "on": "pull-requests",
        },
    )
    quiz.post_quiz_attestation(ctx)
    assert [p[2] for p in github.posted] == [7]


# -- A4: quiz-attested ----------------------------------------------------------------


def test_a_tick_by_an_authorized_user_passes_and_names_them(spec_dir, github):
    _seed(github, _posted_body(spec_dir, github), ticked=True, editors=[OWNER])
    result = quiz.quiz_attested(_ctx(spec_dir, event={"comments": []}))
    assert result.status == "pass"
    assert result.data["decision"] == "spec-quiz"
    assert result.data["attestedBy"] == OWNER and result.data["via"] == "tick"


def test_an_unticked_box_keeps_the_gate_waiting(spec_dir, github):
    _seed(github, _posted_body(spec_dir, github), ticked=False, editors=[OWNER])
    assert quiz.quiz_attested(_ctx(spec_dir, event={"comments": []})).status == "wait"


def test_no_event_means_no_github_call(spec_dir, github):
    _seed(github, _posted_body(spec_dir, github), ticked=True, editors=[OWNER])
    calls = len(github.calls)
    assert quiz.quiz_attested(_ctx(spec_dir, event=None)).status == "wait"
    assert len(github.calls) == calls


def test_quiz_attested_refuses_unauthorized_editor(spec_dir, github, caplog):
    """Abuse case 1: someone not on the allow-list ticks the box."""
    _seed(github, _posted_body(spec_dir, github), ticked=True, editors=["mallory"])
    result = quiz.quiz_attested(_ctx(spec_dir, event={"comments": []}))
    assert result.status == "wait"
    assert result.data["refused"] == ["mallory"]
    assert "mallory" in caplog.text


def test_the_latest_editor_decides(spec_dir, github):
    """An unauthorized edit after an authorized tick keeps the gate shut."""
    _seed(
        github, _posted_body(spec_dir, github), ticked=True, editors=["mallory", OWNER]
    )
    assert quiz.quiz_attested(_ctx(spec_dir, event={"comments": []})).status == "wait"


@pytest.mark.parametrize("editors", [[], [""]])
def test_quiz_attested_fails_closed_without_editor(spec_dir, github, editors):
    """Abuse case 2: no history, or a deleted account — never `is_authorized(None)`."""
    _seed(github, _posted_body(spec_dir, github), ticked=True, editors=editors)
    assert quiz.quiz_attested(_ctx(spec_dir, event={"comments": []})).status == "wait"


def test_a_failed_query_waits_and_says_it_could_not_verify(spec_dir, github):
    from the_loop.quizmarks import UNVERIFIED

    _seed(github, _posted_body(spec_dir, github), ticked=True, editors=[OWNER])
    github.fail_on["comment_edits"] = not_found()
    result = quiz.quiz_attested(_ctx(spec_dir, event={"comments": []}))
    assert result.status == "wait" and UNVERIFIED in result.render()


def test_quiz_attested_ignores_forged_comment(spec_dir, github):
    """Abuse case 6: a look-alike comment without the-loop's own marker."""
    forged = (
        f"- [x] {SPEC_LINE}\n\n"
        f"<!-- the-loop:quiz spec-quiz round=1 digest={quiz.spec_digest(spec_dir, DIGEST)} -->"
    )
    _seed(github, forged, ticked=True, editors=[OWNER])
    assert quiz.quiz_attested(_ctx(spec_dir, event={"comments": []})).status == "wait"


def test_quiz_attested_ignores_unmarked_and_artifact_text(spec_dir, github):
    """Abuse case 4: "approved" / "quiz passed" anywhere is not the attestation."""
    _seed(github, _posted_body(spec_dir, github), ticked=False, editors=[])
    event = {
        "comments": [
            {"author": OWNER, "body": "approved — quiz passed"},
            {"author": "mallory", "body": f"- [x] {SPEC_LINE}"},
        ]
    }
    assert quiz.quiz_attested(_ctx(spec_dir, event=event)).status == "wait"


def test_an_authorized_typed_attestation_is_the_fallback(spec_dir, github):
    _seed(github, _posted_body(spec_dir, github), ticked=False, editors=[])
    event = {"comments": [{"author": OWNER, "body": f"- [x] {SPEC_LINE}", "url": "c"}]}
    result = quiz.quiz_attested(_ctx(spec_dir, event=event))
    assert result.status == "pass" and result.data["via"] == "reply"
    assert result.data["attestedBy"] == OWNER


def test_a_changed_spec_routes_back_as_stale(spec_dir, github):
    _seed(github, _posted_body(spec_dir, github), ticked=True, editors=[OWNER])
    (spec_dir / "requirements.md").write_text("# R moved\n", encoding="utf-8")
    result = quiz.quiz_attested(_ctx(spec_dir, event={"comments": []}))
    assert result.status == "pass" and result.outcome == "stale"
    assert load_graph().next_node("spec-quiz", "stale") == "spec-explainer"


def _look_alike(github: FakeGitHubClient, body: str, cid: str = "IC_2") -> None:
    """Mallory copies the-loop's comment — both markers are just text."""
    github.comments[("o", "r", 7)].append(
        GhComment(id=cid, body=body, author="mallory", created_at="t1", url="m")
    )


def test_a_look_alike_with_a_wrong_digest_cannot_send_the_quiz_back(spec_dir, github):
    """Abuse case 6: a copied marker from an unauthorized author is no quiz comment."""
    body = _posted_body(spec_dir, github)
    _seed(github, body, ticked=False, editors=[OWNER])
    forged = re.sub(r"digest=[0-9a-f]{12}", "digest=000000000000", body)
    _look_alike(github, forged)
    result = quiz.quiz_attested(_ctx(spec_dir, event={"comments": []}))
    assert result.status == "wait" and result.outcome != "stale"


def test_an_unticked_look_alike_cannot_hide_the_real_tick(spec_dir, github):
    body = _posted_body(spec_dir, github)
    _seed(github, body, ticked=True, editors=[OWNER])
    _look_alike(github, body)
    result = quiz.quiz_attested(_ctx(spec_dir, event={"comments": []}))
    assert result.status == "pass" and result.data["attestedBy"] == OWNER


def test_a_tick_from_an_earlier_round_does_not_answer_this_one(spec_dir, github):
    body = _posted_body(spec_dir, github)
    _seed(github, body, ticked=True, editors=[OWNER])
    state = WorkItemState.load(spec_dir, "issue-7")
    state.enter("spec-quiz")
    state.enter("spec-quiz")  # round 2
    state.save(spec_dir)
    assert quiz.quiz_attested(_ctx(spec_dir, event={"comments": []})).status == "wait"


# -- A2: the checklist row ----------------------------------------------------------


def _selection_ctx():
    return HookContext(
        work_item=WorkItem(ref=REF, id="issue-7", spec_dir=Path(".")),
        node={"id": "phase-selection"},
        boundary="exit",
        repo=Path("."),
        config={"authorizedUsers": [OWNER]},
        graph=load_graph(),
    )


def test_the_row_is_ticked_and_absent_means_on():
    assert selection._parse_explainer("the-loop execute") is True
    assert selection._parse_explainer("- [x] `explainer`") is True
    assert selection._parse_explainer("- [ ] `explainer` — x") is False
    assert selection._is_non_phase(selection.EXPLAINER_TOKEN)


def test_the_row_stands_for_the_four_nodes():
    assert selection._explainer_nodes(_selection_ctx()) == (
        "spec-explainer",
        "spec-quiz",
        "code-explainer",
        "code-quiz",
    )
    skippable, _, _ = selection._phase_rows(_selection_ctx())
    assert not {"spec-explainer", "spec-quiz", "code-explainer", "code-quiz"} & set(
        skippable
    )


def test_a_loop_without_the_skip_set_has_no_row():
    from the_loop.graph.model import PDLC_CONTRIBUTION_LOOP

    ctx = _selection_ctx()
    ctx.graph = load_graph(name=PDLC_CONTRIBUTION_LOOP)
    assert selection._explainer_nodes(ctx) == ()
    assert f"`{selection.EXPLAINER_TOKEN}`" not in selection._checklist_body(ctx)


def _classify(body: str, github: FakeGitHubClient):
    ctx = _selection_ctx()
    ctx.event = {"comments": [{"author": OWNER, "body": body}]}
    return selection.classify_phase_selection(ctx)


def test_unticking_the_row_declares_four_skips_under_its_token(github):
    result = _classify("the-loop execute\n\n- [ ] `explainer`", github)
    skips = result.data["declaredSkips"]
    assert set(skips) == {"spec-explainer", "spec-quiz", "code-explainer", "code-quiz"}
    assert all(
        s["token"] == "explainer" and s["by"] == "@owner" for s in skips.values()
    )
    frozen = {n["id"]: n["skipped"] for n in result.data["frozenGraph"]["nodes"]}
    assert frozen["spec-quiz"] and frozen["code-quiz"]
    assert "Explainer and quizzes: **off**" in github.posted[-1][3]


def test_leaving_the_row_alone_keeps_all_four_and_says_so(github):
    result = _classify("the-loop execute", github)
    assert not set(result.data["declaredSkips"]) & {"spec-quiz", "code-quiz"}
    assert "Explainer and quizzes: **on**" in github.posted[-1][3]


def test_the_slack_mirror_keeps_the_row_as_a_setting():
    from the_loop.channels.slack import EXPLAINER_TOKEN, selection_rows

    assert EXPLAINER_TOKEN == selection.EXPLAINER_TOKEN
    rows = selection_rows(selection._checklist_body(_selection_ctx()))
    assert rows is not None
    assert selection.EXPLAINER_TOKEN in [r.token for r in rows.others]
    assert "spec-quiz" not in [r.token for r in rows.phases]


# -- T10: a work item frozen before these nodes existed -------------------------------


def test_frozen_graph_without_quiz_nodes_keeps_walking(tmp_path):
    graph = load_graph()
    runtime = Runtime(tmp_path, graph=graph)
    state = WorkItemState(work_item="issue-7")
    state.decisions["phase-selection"] = {
        "graph": {
            "nodes": [
                {"id": n.id}
                for n in graph.ordered()
                if n.id
                not in {"spec-explainer", "spec-quiz", "code-explainer", "code-quiz"}
            ]
        }
    }
    skips = runtime.declared_skips(state)
    for node in ("spec-explainer", "spec-quiz", "code-explainer", "code-quiz"):
        assert skips[node] == {"via": NOT_OFFERED}
    assert "design" not in skips


def test_a_state_with_no_frozen_graph_infers_nothing(tmp_path):
    runtime = Runtime(tmp_path, graph=load_graph())
    assert "spec-quiz" not in runtime.declared_skips(WorkItemState(work_item="issue-7"))


# -- A5: the doorbell ---------------------------------------------------------------


def test_the_doorbell_is_keyed_by_comment_and_body():
    refs = [WorkItemRef.parse(REF)]
    a = quiz_attestation_event(refs, "IC_1", "x")
    assert a.event == QUIZ_ATTESTATION_EVENT and not a.labeled
    assert a.delivery_id == quiz_attestation_event(refs, "IC_1", "x").delivery_id
    assert a.delivery_id != quiz_attestation_event(refs, "IC_1", "y").delivery_id
    assert "comment" not in a.payload  # no body, no actor to trust


def _router():
    from the_loop.webhook.router import Router

    return Router(events=["issue_comment"], authorized_users=[OWNER])


def _edited(body: str) -> Dict[str, Any]:
    return {
        "action": "edited",
        "issue": {"number": 7, "html_url": "https://github.com/o/r/issues/7"},
        "repository": {"full_name": "o/r", "html_url": "https://github.com/o/r"},
        "comment": {
            "id": 9,
            "node_id": "IC_9",
            "body": body,
            "user": {"login": "the-loop"},
        },
        "sender": {"login": "mallory"},
    }


def test_an_edited_own_quiz_comment_becomes_the_doorbell():
    body = mark_self_authored(
        f"- [x] {SPEC_LINE}\n<!-- the-loop:quiz spec-quiz round=1 digest=- -->"
    )
    routed = _router().route("issue_comment", _edited(body), "d1")
    assert routed is not None and routed.event == QUIZ_ATTESTATION_EVENT
    assert routed.payload == {"attestation": {"comment_id": "IC_9"}}


def test_other_edits_of_own_comments_are_still_dropped():
    body = mark_self_authored(
        f"- [ ] {SPEC_LINE}\n<!-- the-loop:quiz spec-quiz round=1 digest=- -->"
    )
    assert _router().route("issue_comment", _edited(body), "d2") is None
    assert (
        _router().route("issue_comment", _edited(mark_self_authored("hi")), "d3")
        is None
    )


def test_a_human_comment_that_looks_like_a_quiz_is_not_the_doorbell():
    body = f"- [x] {SPEC_LINE}\n<!-- the-loop:quiz spec-quiz round=1 digest=- -->"
    routed = _router().route("issue_comment", _edited(body), "d4")
    assert routed is None or routed.event != QUIZ_ATTESTATION_EVENT


# -- B1: the page template --------------------------------------------------------


TEMPLATE = (
    Path(__file__).resolve().parents[2] / "skills/the-loop/templates/explainer.html"
)


def test_explainer_template_renders_text_not_markup():
    """Abuse case 3: the engine never turns quiz data into markup.

    Static half — runs in CI. The DOM half (a `<script>` string in an option
    renders as text) runs headless at verification (testing-plan T5).
    """

    html = TEMPLATE.read_text(encoding="utf-8")
    engine = html[html.index("<!-- ENGINE") :]
    for sink in (
        "innerHTML",
        "outerHTML",
        "insertAdjacentHTML",
        "document.write",
        "eval(",
    ):
        assert sink not in engine, sink
    assert "textContent" in engine


def test_the_template_is_self_contained_and_its_quiz_blocks_parse():
    import json
    import re

    html = TEMPLATE.read_text(encoding="utf-8")
    assert not re.search(r"""(src|href)\s*=\s*["']?(https?:)?//""", html)
    assert "@import" not in html and "fetch(" not in html
    for block in re.findall(
        r'<script type="application/json" id="quiz-\w+">(.*?)</script>', html, re.S
    ):
        assert isinstance(json.loads(block)["questions"], list)


def test_every_shipped_node_command_names_a_slash_command_file():
    """B2: `command: explain` resolves to commands/explain.md, like every other."""
    commands = Path(__file__).resolve().parents[2] / "commands"
    for node in load_graph().ordered():
        if node.command:
            assert (commands / f"{node.command}.md").is_file(), node.command
    assert load_graph().nodes["code-explainer"].command == "explain"
