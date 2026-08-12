"""The scenario runner for the PDLC end-to-end suite (issue-217).

One work item, walked ticket → complete through the REAL runtime — the shipped
``pdlc-work-item-loop``, the shipped hooks, real artifact gates over real files
in a throwaway checkout. The "agent" is a step interpreter playing back a
scenario's fixtures; the only fakes sit at the transport seams every existing
integration test already fakes:

* ``the_loop.graph.integrations.resolve`` → :class:`FakeIntegration`
  (labels/comments, with a fail knob for the gh-unreachable scenario);
* the event log, pointed at a per-scenario temp file;
* ``core_sessions``'s comment poster and ``TmuxRunner`` (the ask/reply seams,
  exactly as ``test_ask_reply_integration.py`` patches them).

The step vocabulary is a CLOSED enum (see README.md): a scenario can hand the
process an artifact, a comment, or a completion claim — never a command. An
unknown step kind refuses the scenario naming the file and field.

Spec: docs/specs/issue-217/design.md.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from the_loop import eventlog
from the_loop.authz import mark_self_authored
from the_loop.core import sessions as core_sessions
from the_loop.graph import hooks  # noqa: F401 — registers the shipped hooks
from the_loop.graph.frontmatter import read_front_matter, sections, split_front_matter
from the_loop.graph.integrations import IntegrationError
from the_loop.graph.model import PDLC_WORK_ITEM_LOOP, load_graph
from the_loop.graph.runtime import Runtime
from the_loop.graph.state import GraphState
from the_loop.runner import TmuxResult
from the_loop.sessions.registry import Session, SessionRegistry
from the_loop.state import layout_from_config
from the_loop.workitem import WorkItemRef

SCENARIOS_DIR = Path(__file__).parent / "scenarios"

#: The one authorized human of every scenario world.
OWNER = "owner"
#: Where every scenario's ticket lives; refs derive as ``github:e2e/e2e#<n>``.
ORIGIN_REPO = "e2e/e2e"

#: The spec-chain artifacts whose lock state is snapshotted the moment the
#: pointer reaches ``implementation`` (R1.3: locked before implementation).
SPEC_CHAIN = ("requirements.md", "design.md", "testing-plan.md", "tasks.md")

#: The closed step vocabulary (security consideration 1): playback, never code.
STEP_KINDS = frozenset(
    {
        "comment",
        "emit",
        "complete",
        "advance",
        "ask",
        "reply",
        "inner-loop",
        "fail-github",
        "restore-github",
        "expect",
    }
)

#: What the fake transport serves. Anything else raising is the hermeticity
#: tripwire (security consideration 3): a hook reaching for an operation the
#: e2e world does not model fails loudly instead of silently leaving the world.
FAKE_OPS = frozenset(
    {"add-comment", "set-labels", "get-labels", "list-comments", "post-message"}
)


class ScenarioFormatError(AssertionError):
    """A malformed scenario directory — named, never silently skipped (R2.2)."""


class ScenarioAssertionError(AssertionError):
    """A process-conformance divergence, reported at its first occurrence (R1.4)."""


def match_subsequence(
    actual: List[Dict[str, Any]], wanted: List[Dict[str, Any]]
) -> Optional[str]:
    """Ordered-subsequence match of expected events over the actual log (R1.3).

    Every expected matcher must find an event of its ``event`` name whose
    stated fields all match, at or after the previous match — unrelated events
    are permitted in between. Returns ``None`` on a full match, or one message
    naming the first expected event that could not be found (R1.4).
    """
    cursor = 0
    for position, raw in enumerate(wanted):
        matcher = dict(raw)
        name = str(matcher.pop("event", ""))
        found = None
        for i in range(cursor, len(actual)):
            candidate = actual[i]
            if candidate.get("event") != name:
                continue
            if all(str(candidate.get(k, "")) == str(v) for k, v in matcher.items()):
                found = i
                break
        if found is None:
            seen = [str(e.get("event")) for e in actual[cursor:]]
            return (
                f"expected event #{position} ({name} {matcher or ''}) not found "
                f"after log index {cursor}; remaining events: {seen}"
            )
        cursor = found + 1
    return None


def scenario_dirs() -> List[Path]:
    """Every committed scenario, sorted — the discovery the tests parametrize."""
    return sorted(p for p in SCENARIOS_DIR.iterdir() if p.is_dir())


@dataclass(frozen=True)
class Scenario:
    """One parsed and validated ``scenario.yaml`` plus its fixture directory."""

    name: str
    work_item: str
    steps: Tuple[Tuple[str, Dict[str, Any]], ...]
    expect: Dict[str, Any]
    directory: Path

    @classmethod
    def load(cls, directory: Path) -> "Scenario":
        manifest = directory / "scenario.yaml"
        if not manifest.is_file():
            raise ScenarioFormatError(f"{directory}: no scenario.yaml")
        data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ScenarioFormatError(f"{manifest}: the manifest is not a mapping")
        for required in ("name", "workItem", "steps"):
            if not data.get(required):
                raise ScenarioFormatError(f"{manifest}: missing field {required!r}")
        steps: List[Tuple[str, Dict[str, Any]]] = []
        for i, raw in enumerate(data["steps"], start=1):
            if not isinstance(raw, dict) or len(raw) != 1:
                raise ScenarioFormatError(
                    f"{manifest}: step {i} must be one `<kind>: {{…}}` mapping"
                )
            kind, params = next(iter(raw.items()))
            if kind not in STEP_KINDS:
                raise ScenarioFormatError(
                    f"{manifest}: step {i} has unknown kind {kind!r}; "
                    f"expected one of {sorted(STEP_KINDS)}"
                )
            params = dict(params or {})
            for fixture_field in ("fixture",):
                if fixture_field in params:
                    fixture = directory / "artifacts" / str(params[fixture_field])
                    if not fixture.is_file():
                        raise ScenarioFormatError(
                            f"{manifest}: step {i} names a missing fixture "
                            f"{params[fixture_field]!r} (looked at {fixture})"
                        )
            steps.append((kind, params))
        expect = data.get("expect") or {}
        if not isinstance(expect, dict):
            raise ScenarioFormatError(f"{manifest}: `expect` must be a mapping")
        return cls(
            name=str(data["name"]),
            work_item=str(data["workItem"]),
            steps=tuple(steps),
            expect=expect,
            directory=directory,
        )


class FakeIntegration:
    """The control-plane transport, faked (labels + comments + tick state).

    Posted comments are served back through ``list-comments`` — that round trip
    is how the phase-selection gate reads its own checklist's tick state, and
    how marked comments exist to be filtered. ``fail_ops`` makes named
    operations raise :class:`IntegrationError` (the gh-unreachable scenario);
    an operation outside :data:`FAKE_OPS` raises outright.
    """

    name = "e2e-fake"
    transport = "fake"
    operations = frozenset(FAKE_OPS)

    def __init__(self) -> None:
        self.calls: List[Tuple[str, Dict[str, Any]]] = []
        self.comments: List[str] = []
        self.labels: List[str] = []  # every successfully applied label, in order
        self.fail_ops: set = set()

    def call(self, op: str, **params: Any) -> Dict[str, Any]:
        if op not in FAKE_OPS:
            raise AssertionError(
                f"unexpected integration operation {op!r} — the e2e world does "
                "not model it, and a hermetic scenario must not need it"
            )
        if op in self.fail_ops:
            raise IntegrationError(f"e2e: {op} is unreachable (scenario knob)")
        self.calls.append((op, params))
        if op == "add-comment":
            self.comments.append(str(params.get("body") or ""))
            return {}
        if op == "set-labels":
            self.labels.extend(str(label) for label in params.get("labels") or [])
            return {}
        if op == "get-labels":
            return {"labels": self.labels[-1:] if self.labels else []}
        if op == "list-comments":
            return {"comments": [{"body": body} for body in self.comments]}
        return {}  # post-message (slack): accepted and dropped


class _ReplyRunner:
    """``TmuxRunner`` stand-in for the reply path (the ask-reply tests' shape)."""

    delivered: List[Tuple[str, str]] = []
    result: Optional[TmuxResult] = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def deliver(self, session: Any, prompt: str, timeout: Any = None) -> TmuxResult:
        _ReplyRunner.delivered.append((session.work_item.ref, prompt))
        return _ReplyRunner.result or TmuxResult(ok=True)


class ScenarioRun:
    """The hermetic world one scenario executes in, and its observable trace."""

    def __init__(self, scenario: Scenario, tmp_path: Path, monkeypatch: Any) -> None:
        self.scenario = scenario
        self.checkout = tmp_path / "checkout"
        number = scenario.work_item.rsplit("-", 1)[-1]
        self.ref = f"github:{ORIGIN_REPO}#{number}"
        self.spec_dir = self.checkout / "docs" / "specs" / scenario.work_item
        self.spec_dir.mkdir(parents=True)
        (self.checkout / ".the-loop").mkdir()
        (self.checkout / ".the-loop" / "harness-config.yaml").write_text(
            'version: "0.2.0"\nworkflow:\n  specDir: docs/specs\n'
            '  phaseLabelPrefix: "loop:"\n',
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "init", "-q", "-b", "main", str(self.checkout)],
            check=True,
            capture_output=True,
        )

        self.integration = FakeIntegration()
        monkeypatch.setattr(
            "the_loop.graph.integrations.resolve",
            lambda target, config: self.integration,
        )
        self.events_path = tmp_path / "events.jsonl"
        eventlog.configure("pdlc-e2e", path=self.events_path)

        self.runtime = Runtime(
            self.checkout,
            graph=load_graph(name=PDLC_WORK_ITEM_LOOP),
            config={
                "phaseLabelPrefix": "loop:",
                "authorizedUsers": [OWNER],
                "originRepo": ORIGIN_REPO,
            },
        )

        # The ask/reply seams (issue-208's own test shape): a registered session
        # for the work item, the comment poster routed through the fake
        # integration, and a tmux stand-in with a session-missing knob.
        self.cli_config = {"state": {"root": str(tmp_path / ".the-loop")}}
        layout = layout_from_config(self.cli_config)
        registry = SessionRegistry(layout.local_dir)
        registry.register(
            Session(
                work_item=WorkItemRef.parse(self.ref),
                harness="claude",
                harness_session_id="e2e-sess-1",
                cwd=str(self.checkout),
                tmux_target=f"loop-e2e-e2e-{number}",
            )
        )
        monkeypatch.setattr(
            core_sessions, "post_issue_comment_with_url", self._post_comment_with_url
        )
        monkeypatch.setattr(core_sessions, "post_issue_comment", self._post_comment)
        monkeypatch.setattr(core_sessions, "TmuxRunner", _ReplyRunner)
        _ReplyRunner.delivered = []
        _ReplyRunner.result = None

        #: Lock-state snapshot, taken the moment the pointer reaches
        #: `implementation` (R1.3) — None until then.
        self.locks_at_implementation: Optional[Dict[str, str]] = None

    # -- the gh layer the ask/reply verbs post through -------------------------

    def _post_comment_with_url(
        self, work_item: Any, body: str, gh_binary: str = "gh"
    ) -> Tuple[bool, str, str]:
        try:
            self.integration.call("add-comment", ref=work_item.ref, body=body)
        except IntegrationError as exc:
            return False, str(exc), ""
        return True, "", f"https://example.invalid/{work_item.ref}"

    def _post_comment(
        self, work_item: Any, body: str, gh_binary: str = "gh"
    ) -> Tuple[bool, str]:
        ok, error, _ = self._post_comment_with_url(work_item, body, gh_binary)
        return ok, error

    # -- execution --------------------------------------------------------------

    def execute(self) -> "ScenarioRun":
        report = self.runtime.start(self.scenario.work_item, ref=self.ref)
        if report is None or report.status != "pass":
            raise ScenarioAssertionError(
                f"{self.scenario.name}: the work item did not enter the graph: {report}"
            )
        self._after_step()
        for index, (kind, params) in enumerate(self.scenario.steps, start=1):
            handler = getattr(self, "_step_" + kind.replace("-", "_"))
            try:
                handler(params)
            except (ScenarioAssertionError, ScenarioFormatError):
                raise
            except AssertionError:
                raise
            except Exception as exc:
                raise ScenarioAssertionError(
                    f"{self.scenario.name}: step {index} ({kind}) raised "
                    f"{type(exc).__name__}: {exc}"
                ) from exc
            self._after_step()
        self.assert_expect(self.scenario.expect)
        return self

    def _after_step(self) -> None:
        if self.locks_at_implementation is None:
            if self.state().current_node == "implementation":
                snapshot: Dict[str, str] = {}
                for name in SPEC_CHAIN:
                    path = self.spec_dir / name
                    if path.is_file():
                        snapshot[name] = str(read_front_matter(path).get("status", ""))
                self.locks_at_implementation = snapshot

    # -- the step vocabulary (the mocked agent) ----------------------------------

    def _body(self, params: Dict[str, Any]) -> str:
        if params.get("fixture"):
            path = self.scenario.directory / "artifacts" / str(params["fixture"])
            return path.read_text(encoding="utf-8")
        return str(params.get("body") or "")

    def _step_comment(self, params: Dict[str, Any]) -> None:
        body = self._body(params)
        if params.get("marked"):
            body = mark_self_authored(body)  # the production marker, not a copy
        author = str(params.get("author") or OWNER)
        self.runtime.advance(
            self.scenario.work_item,
            ref=self.ref,
            event={"comments": [{"author": author, "body": body}]},
        )

    def _step_emit(self, params: Dict[str, Any]) -> None:
        artifact = str(params.get("artifact") or "")
        if not artifact:
            raise ScenarioFormatError(
                f"{self.scenario.name}: an emit step names no artifact"
            )
        source = self.scenario.directory / "artifacts" / str(params["fixture"])
        shutil.copyfile(source, self.spec_dir / artifact)

    def _step_complete(self, params: Dict[str, Any]) -> None:
        node = str(params.get("node") or "")
        envelope = self.runtime.complete(
            self.scenario.work_item, ref=self.ref, node=node, actor="e2e-agent"
        )
        expected = str(params.get("status") or "pass")
        if envelope["status"] != expected:
            raise ScenarioAssertionError(
                f"{self.scenario.name}: completing {node!r} returned status "
                f"{envelope['status']!r} (expected {expected!r}): "
                f"{envelope['messages']}"
            )

    def _step_advance(self, params: Dict[str, Any]) -> None:
        self.runtime.advance(self.scenario.work_item, ref=self.ref)

    def _step_ask(self, params: Dict[str, Any]) -> None:
        core_sessions.ask_session(
            self.ref, str(params.get("question") or ""), config=self.cli_config
        )

    def _step_reply(self, params: Dict[str, Any]) -> None:
        if params.get("sessionMissing"):
            sent_before = sum(
                1 for e in self.events() if e["event"] == "session.reply_sent"
            )
            _ReplyRunner.result = TmuxResult(ok=False, session_missing=True)
            try:
                core_sessions.reply_session(
                    self.ref,
                    str(params.get("text") or ""),
                    actor=str(params.get("actor") or ""),
                    config=self.cli_config,
                )
            except LookupError:
                # Fail-closed, as the contract says: never a respawn — and the
                # refusal must not have recorded a delivery that never happened.
                sent_after = sum(
                    1 for e in self.events() if e["event"] == "session.reply_sent"
                )
                if sent_after != sent_before:
                    raise ScenarioAssertionError(
                        f"{self.scenario.name}: a refused reply still emitted "
                        "session.reply_sent"
                    ) from None
                return
            finally:
                _ReplyRunner.result = None
            raise ScenarioAssertionError(
                f"{self.scenario.name}: a reply into a dead pane was accepted — "
                "the reply route must fail closed (404), never respawn"
            )
        result = core_sessions.reply_session(
            self.ref,
            str(params.get("text") or ""),
            actor=str(params.get("actor") or ""),
            config=self.cli_config,
        )
        if not result.get("delivered"):
            raise ScenarioAssertionError(
                f"{self.scenario.name}: the reply was not delivered: {result}"
            )

    def _step_inner_loop(self, params: Dict[str, Any]) -> None:
        pr = int(params.get("pr") or 0)
        repo = str(params.get("repo") or "")
        base = self.spec_dir / "pr-loops"
        if repo:
            base = base / repo.replace("/", "__")
        state_dir = base / f"pr-{pr}"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "graph-state.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "workItem": self.scenario.work_item,
                    "currentNode": str(params.get("node") or ""),
                    "loop": "pdlc-pr-loop",
                }
            ),
            encoding="utf-8",
        )

    def _step_fail_github(self, params: Dict[str, Any]) -> None:
        self.integration.fail_ops = set(params.get("ops") or FAKE_OPS)

    def _step_restore_github(self, params: Dict[str, Any]) -> None:
        self.integration.fail_ops = set()

    def _step_expect(self, params: Dict[str, Any]) -> None:
        self.assert_expect(params)

    # -- the observable trace ----------------------------------------------------

    def state(self) -> GraphState:
        return GraphState.load(self.spec_dir, self.scenario.work_item)

    def events(self) -> List[Dict[str, Any]]:
        if not self.events_path.is_file():
            return []
        return [
            json.loads(line)
            for line in self.events_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def node_trace(self) -> List[str]:
        """The walked sequence, derived from the event log alone.

        Entered nodes appear by id; nodes the pointer routed around appear with
        a ``~`` suffix — so a skip can never satisfy an expectation written for
        a pass, which is the "skips are reported as declarations, never passes"
        conformance in trace form.
        """
        trace: List[str] = []
        for event in self.events():
            if event["event"] == "graph.started":
                trace.append(str(event["node"]))
            elif event["event"] == "graph.node_skipped":
                trace.append(str(event["node"]) + "~")
            elif event["event"] == "graph.advanced":
                trace.append(str(event["to"]))
        return trace

    # -- assertions ----------------------------------------------------------------

    def assert_expect(self, expect: Dict[str, Any]) -> None:
        known = {
            "finalNode",
            "currentNode",
            "completed",
            "parked",
            "nodes",
            "labels",
            "events",
            "lockedBeforeImplementation",
            "executionLogSections",
        }
        unknown = set(expect) - known
        if unknown:
            raise ScenarioFormatError(
                f"{self.scenario.name}: unknown expect key(s) {sorted(unknown)}; "
                f"expected among {sorted(known)}"
            )
        state = self.state()
        for key in ("finalNode", "currentNode"):
            if key in expect and state.current_node != expect[key]:
                raise ScenarioAssertionError(
                    f"{self.scenario.name}: expected the pointer at "
                    f"{expect[key]!r}, found {state.current_node!r}"
                )
        if "parked" in expect:
            if bool(state.parked) != bool(expect["parked"]):
                raise ScenarioAssertionError(
                    f"{self.scenario.name}: expected parked={expect['parked']}, "
                    f"found {state.parked!r}"
                )
        if "completed" in expect:
            seen = any(e["event"] == "graph.completed" for e in self.events())
            if seen != bool(expect["completed"]):
                raise ScenarioAssertionError(
                    f"{self.scenario.name}: expected completed={expect['completed']}, "
                    f"and graph.completed {'was' if seen else 'was not'} emitted"
                )
        if "nodes" in expect:
            self._assert_nodes(list(expect["nodes"]))
        if "labels" in expect:
            actual = self.integration.labels
            wanted = [str(label) for label in expect["labels"]]
            if actual != wanted:
                divergence = next(
                    (i for i, (a, w) in enumerate(zip(actual, wanted)) if a != w),
                    min(len(actual), len(wanted)),
                )
                raise ScenarioAssertionError(
                    f"{self.scenario.name}: label trail diverges at index "
                    f"{divergence}: expected {wanted[divergence : divergence + 1]}, "
                    f"found {actual[divergence : divergence + 1]}\n"
                    f"  expected: {wanted}\n  actual:   {actual}"
                )
        if "events" in expect:
            self._assert_events(list(expect["events"]))
        if "lockedBeforeImplementation" in expect:
            snapshot = self.locks_at_implementation
            if snapshot is None:
                raise ScenarioAssertionError(
                    f"{self.scenario.name}: implementation was never entered, so "
                    "there is no lock snapshot to assert on"
                )
            for name in expect["lockedBeforeImplementation"]:
                status = snapshot.get(str(name), "(absent)")
                if status != "approved":
                    raise ScenarioAssertionError(
                        f"{self.scenario.name}: {name} was not locked when "
                        f"implementation was entered (status: {status})"
                    )
        if "executionLogSections" in expect:
            self._assert_log_sections(list(expect["executionLogSections"]))

    def _assert_nodes(self, wanted: List[str]) -> None:
        actual = self.node_trace()
        for index, (a, w) in enumerate(zip(actual, wanted)):
            if a != str(w):
                raise ScenarioAssertionError(
                    f"{self.scenario.name}: node trace diverges at index {index}: "
                    f"expected {w!r}, found {a!r}\n"
                    f"  expected: {wanted}\n  actual:   {actual}"
                )
        if len(actual) != len(wanted):
            raise ScenarioAssertionError(
                f"{self.scenario.name}: node trace length {len(actual)} != "
                f"expected {len(wanted)}\n"
                f"  expected: {wanted}\n  actual:   {actual}"
            )

    def _assert_events(self, wanted: List[Dict[str, Any]]) -> None:
        divergence = match_subsequence(self.events(), wanted)
        if divergence:
            raise ScenarioAssertionError(f"{self.scenario.name}: {divergence}")

    def _assert_log_sections(self, wanted: List[str]) -> None:
        path = self.spec_dir / "execution-log.md"
        if not path.is_file():
            raise ScenarioAssertionError(
                f"{self.scenario.name}: no execution-log.md to assert sections on"
            )
        _, body = split_front_matter(path.read_text(encoding="utf-8"))
        found = sections(body)
        for section in wanted:
            match = next((h for h in found if h.strip() == section.strip()), None)
            if match is None or not found[match].strip():
                raise ScenarioAssertionError(
                    f"{self.scenario.name}: execution-log.md section "
                    f"{section!r} is " + ("missing" if match is None else "empty")
                )
