"""Unit tests for what a machine that lost its memory may conclude (issue-363).

The vocabulary three call sites share — the poller deciding whether to replay a
thread, the graph link deciding whether a start would be a rewind, and the
dispatcher deciding whether a spawn needs to say the conversation is gone — plus
the two pieces of state that make the conclusion possible: the graph position on
the portable record, and the grace window a booting session gets.

Spec: docs/specs/issue-363/design.md; testing plan rows T1, T2, T3, T9, T12.
"""

from __future__ import annotations

import pytest

from the_loop import recovery
from the_loop.authz import is_self_authored
from the_loop.control import ControlStore
from the_loop.graph.hooks.sideeffects import PHASE_LABEL_PREFIX
from the_loop.workitem import GRAPH, POSITION, WorkItemStore

REF = "github:octo/repo#363"


class TestPhaseLabels:
    def test_the_prefix_is_the_one_the_hook_writes(self):
        """A second spelling of `loop:` would read every ticket as unlabelled."""
        assert recovery.PHASE_LABEL_PREFIX == PHASE_LABEL_PREFIX

    def test_only_loop_labels_are_phases(self):
        labels = ["the-loop: auto-execute", "loop:design", "bug", "P1"]
        assert recovery.phase_labels(labels) == ["design"]

    def test_labels_are_read_the_way_people_type_them(self):
        assert recovery.phase_labels(["  LOOP:Implementation "]) == ["implementation"]

    def test_a_phase_label_past_the_start_node_is_evidence_of_work(self):
        assert recovery.advanced_phase(["loop:implementation"]) == "implementation"
        assert recovery.advanced_phase(["loop:complete"]) == "complete"

    def test_an_unlabelled_item_and_a_start_phase_label_are_not_evidence(self):
        """Nothing to rewind: the pointer never left the node it starts on."""
        assert recovery.advanced_phase([]) == ""
        assert recovery.advanced_phase(["loop:not-started"]) == ""
        assert recovery.advanced_phase(["loop:phase-selection"]) == ""

    def test_a_graphs_own_start_phase_is_never_evidence_for_that_graph(self):
        """pdlc-adhoc-loop starts at a node whose phase is `implementation`.

        Asked without the graph (the poller's question) the label is evidence;
        asked about that graph it is the start node, and re-entering the node
        you are on is not a rewind.
        """
        assert recovery.advanced_phase(["loop:implementation"]) == "implementation"
        assert recovery.advanced_phase(["loop:implementation"], "implementation") == ""


class TestContextLost:
    def test_a_phase_label_alone_is_enough(self):
        assert recovery.context_lost(["loop:verification"], False) is True

    def test_the_loops_own_comment_is_evidence_even_without_a_label(self):
        """A contribution writes no label into a consuming repository at all."""
        assert recovery.context_lost([], True) is True

    def test_a_thread_with_neither_is_a_genuinely_new_work_item(self):
        """issue-119's case: an untouched ticket, whatever is on its thread."""
        assert recovery.context_lost(["bug", "loop:not-started"], False) is False


class TestTheNotice:
    def test_the_notice_carries_only_minted_values(self):
        """Abuse case: no parameter through which a commenter's body could reach
        a comment the-loop posts with the operator's own credentials."""
        body = recovery.context_lost_notice(ref=REF, cutoff="2026-09-14T09:00:00Z")
        assert REF in body and "2026-09-14T09:00:00Z" in body
        # The whole callable surface is two strings, both the-loop's own.
        assert set(recovery.context_lost_notice.__code__.co_varnames[:2]) == {
            "ref",
            "cutoff",
        }

    def test_the_notice_is_marked_as_the_loops_own(self):
        """Unmarked, the poller would read it back as a human comment and
        forward it into the very session it is about."""
        assert is_self_authored(
            recovery.context_lost_notice(ref=REF, cutoff="2026-09-14T09:00:00Z")
        )

    def test_the_notice_names_the_operators_remedy_and_claims_no_rewind(self):
        body = recovery.context_lost_notice(ref=REF, cutoff="then")
        assert "the-loop graph force" in body
        assert "not been moved" in body


class TestTheRecoveryPromptNotice:
    def test_a_recovery_spawn_prompt_says_the_conversation_is_gone(self):
        notice = recovery.recovery_prompt_notice(advanced=True, has_pointer=False)
        assert "NEW conversation replacing one that was lost" in notice
        assert "docs/specs/<id>/" in notice

    def test_an_ordinary_spawn_gets_nothing(self):
        """Every other prompt stays what the-loop has always sent."""
        assert recovery.recovery_prompt_notice(advanced=False, has_pointer=False) == ""
        assert recovery.recovery_prompt_notice(advanced=True, has_pointer=True) == ""
        assert recovery.recovery_prompt_notice(advanced=False, has_pointer=True) == ""


class TestThePortablePosition:
    @pytest.fixture()
    def store(self, tmp_path):
        return ControlStore(tmp_path / "portable")

    def test_a_record_without_a_position_reads_as_nothing_to_restore(self, store):
        """Every record written before issue-363, and every item that never
        advanced on a publishing machine."""
        assert store.graph_position(REF) is None
        store.record_frozen_graph(REF, {"loop": "pdlc-work-item-loop", "nodes": []})
        assert store.graph_position(REF) is None

    def test_recording_a_position_keeps_the_frozen_selection(self, store):
        store.record_frozen_graph(REF, {"loop": "pdlc-work-item-loop", "nodes": ["a"]})
        store.record_graph_position(
            REF, {"at": "t", "state": {"currentNode": "design"}}
        )
        assert store.graph_position(REF) == {
            "at": "t",
            "state": {"currentNode": "design"},
        }
        frozen = store.frozen_graph(REF) or {}
        assert frozen["loop"] == "pdlc-work-item-loop" and frozen["nodes"] == ["a"]

    def test_recording_a_selection_keeps_the_position(self, store):
        """The two writers of one section, in the other order: re-freezing a
        selection must not drop where the work item stands."""
        store.record_graph_position(
            REF, {"at": "t", "state": {"currentNode": "design"}}
        )
        store.record_frozen_graph(REF, {"loop": "pdlc-work-item-loop", "nodes": ["b"]})
        assert (store.graph_position(REF) or {}).get("state") == {
            "currentNode": "design"
        }
        assert (store.frozen_graph(REF) or {})["nodes"] == ["b"]

    def test_the_position_lives_inside_the_graph_section(self, tmp_path):
        """Where a reader of the tracked record finds it, in a PR diff."""
        store = ControlStore(tmp_path / "portable")
        store.record_graph_position(REF, {"at": "t", "state": {"currentNode": "x"}})
        record = WorkItemStore(tmp_path / "portable").read(REF)
        assert record[GRAPH][POSITION]["state"]["currentNode"] == "x"
