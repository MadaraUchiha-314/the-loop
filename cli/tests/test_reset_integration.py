"""End-to-end: `the-loop sessions reset` (issue-137).

These drive the registered action through ``the_loop.cli.main`` — argv in,
rendered report on stdout, process exit code out — against real stores on tmp
paths. That is what the unit tests cannot prove: that the action is wired into
the CLI, that the selector rules refuse the dangerous readings, that a hostile
``--work-item`` never reaches a path, and that the command which would most like
to erase its own trail cannot.

Feature: Resetting the-loop CLI's state for a work item
Requirement: docs/specs/issue-137/requirements.md
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from the_loop import cli_config, eventlog
from the_loop.cli import main
from the_loop.commands import sessions_cmd
from the_loop.control import ControlStore
from the_loop.poller.poller import PollState
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.workitem import CONTROL, POLL, WorkItemStore

REF = "github:octo/repo#15"
OTHER = "github:octo/repo#21"


@pytest.fixture(autouse=True)
def _no_daemon(monkeypatch, tmp_path):
    """No receiver pidfile and a fail-closed routing config, unless a test says
    otherwise: the warnings have their own tests and must not colour the rest."""
    monkeypatch.setattr(cli_config, "load_routing_config", lambda *_a, **_k: {})
    monkeypatch.setattr(
        sessions_cmd, "_state_layout", lambda: _layout(tmp_path / "unused-root")
    )


def _layout(root: Path):
    from the_loop.state import StateLayout

    return StateLayout(root=str(root))


def registry_for(tmp_path: Path) -> SessionRegistry:
    return SessionRegistry(tmp_path / "local")


def store_for(tmp_path: Path) -> WorkItemStore:
    return WorkItemStore(tmp_path / "portable")


def register(tmp_path: Path, ref: str = REF, status: str = "active") -> None:
    registry_for(tmp_path).register(
        Session(
            work_item=WorkItemRef.parse(ref),
            harness="claude",
            harness_session_id="sess-0",
            cwd=str(tmp_path),
            status=status,
        ),
        force=True,
    )


def arm(tmp_path: Path, ref: str = REF) -> None:
    ControlStore(str(tmp_path / "portable")).record(ref, "start", source="cli")


def baseline(tmp_path: Path, ref: str = REF) -> None:
    state = PollState(store_for(tmp_path))
    state.baseline_comments(ref, ["c1"], "2026-08-04T00:00:00Z")
    state.save()


def run(tmp_path: Path, *args: str) -> int:
    return main(
        [
            "sessions",
            "reset",
            "--registry-dir",
            str(tmp_path / "local"),
            "--portable-dir",
            str(tmp_path / "portable"),
            *args,
        ]
    )


# -- resetting ---------------------------------------------------------------------


def test_one_work_item_is_forgotten(tmp_path, capsys):
    """
    Scenario: An operator resets a work item after fixing a CLI bug
      Given a work item with a session, an armed control record and a poll ledger
      When the operator runs `the-loop sessions reset --work-item <ref>`
      Then all three are gone and the report names each of them
      And the work item is disarmed, so it does not re-spawn on its own
    """
    register(tmp_path)
    arm(tmp_path)
    baseline(tmp_path)

    assert run(tmp_path, "--work-item", REF) == 0

    out = capsys.readouterr().out
    assert "session" in out and "control" in out and "poll" in out
    assert registry_for(tmp_path).find_by_work_item(REF, include_closed=True) is None
    assert ControlStore(str(tmp_path / "portable")).start_requested(REF) is False
    assert PollState(store_for(tmp_path)).is_known(REF) is False


def test_several_work_items_in_one_run(tmp_path, capsys):
    """
    Scenario: A bad release affected everything in flight
      Given two work items with state
      When both are named in one invocation
      Then both are reset and the summary counts two
    """
    arm(tmp_path)
    arm(tmp_path, ref=OTHER)

    assert run(tmp_path, "--work-item", REF, "--work-item", OTHER) == 0

    out = capsys.readouterr().out
    assert REF in out and OTHER in out and "2 work items" in out
    assert store_for(tmp_path).section(REF, CONTROL) is None
    assert store_for(tmp_path).section(OTHER, CONTROL) is None


def test_all_resets_every_work_item_this_machine_knows(tmp_path, capsys):
    """
    Scenario: Reset everything after a bad release
      Given one work item known only by its session and another only by its record
      When the operator runs `--all`
      Then both are reset
    """
    register(tmp_path)
    arm(tmp_path, ref=OTHER)

    assert run(tmp_path, "--all") == 0

    out = capsys.readouterr().out
    assert REF in out and OTHER in out
    assert registry_for(tmp_path).list_sessions() == []
    assert store_for(tmp_path).section(OTHER, CONTROL) is None


def test_a_work_item_with_no_state_is_reported_not_crashed(tmp_path, capsys):
    """
    Scenario: Resetting something that was never worked here
      When the operator resets a work item this machine has never seen
      Then it exits non-zero and says there was nothing to reset
    """
    assert run(tmp_path, "--work-item", REF) == 1
    assert "nothing to reset" in capsys.readouterr().err


def test_all_on_a_clean_machine_is_reported(tmp_path, capsys):
    assert run(tmp_path, "--all") == 1
    assert "no work-item state" in capsys.readouterr().err


def test_a_live_session_is_ended_and_said_so(tmp_path, capsys, monkeypatch):
    """
    Scenario: The reset ends a running agent
      Given a work item with a live session
      When it is reset
      Then the close path runs and the output says a live session was ended
    """
    register(tmp_path)
    closed = []
    monkeypatch.setattr(
        sessions_cmd,
        "_dispatcher_for",
        lambda args: (_FakeDispatcher(closed), None),
    )

    assert run(tmp_path, "--work-item", REF) == 0

    out = capsys.readouterr().out
    assert len(closed) == 1
    assert "live" in out and "ended" in out
    assert "workspace" in out  # the fake close reports one was removed


class _FakeDispatcher:
    """Stands in for the daemon's dispatcher: records closes, removes nothing."""

    def __init__(self, closed):
        self.closed = closed
        self.control_store = None

    def close_session(self, session, routed=None, reason=""):
        self.closed.append((session.work_item.ref, reason))
        return True

    def stop(self, timeout=None):
        pass


def test_no_dispatcher_is_built_when_nothing_is_live(tmp_path, monkeypatch):
    """A records-only reset must not pay for (or fail on) a dispatcher."""

    def explode(args):  # pragma: no cover - must not be reached
        raise AssertionError("no dispatcher is needed without a live session")

    monkeypatch.setattr(sessions_cmd, "_dispatcher_for", explode)
    arm(tmp_path)
    assert run(tmp_path, "--work-item", REF) == 0


# -- dry run -------------------------------------------------------------------------


def test_dry_run_changes_nothing(tmp_path, capsys):
    """
    Scenario: Rehearsing a reset
      Given a work item with state
      When the operator passes --dry-run
      Then the report is in the conditional and nothing on disk changed
    """
    register(tmp_path)
    arm(tmp_path)

    assert run(tmp_path, "--work-item", REF, "--dry-run") == 0

    out = capsys.readouterr().out
    assert "would" in out and "dry run" in out
    assert registry_for(tmp_path).find_by_work_item(REF) is not None
    assert store_for(tmp_path).section(REF, CONTROL) is not None


def test_dry_run_names_the_checkout_it_would_remove(tmp_path, capsys, monkeypatch):
    """
    Scenario: The rehearsal must not hide the unrecoverable part
      Given a workspace-enabled config that removes checkouts on close
      And a work item with a live session
      When the operator rehearses the reset
      Then the report says the checkout would go with it
    """
    monkeypatch.setattr(
        cli_config,
        "load_routing_config",
        lambda *_a, **_k: {"workspace": {"root": str(tmp_path / "ws")}},
    )
    register(tmp_path)
    assert run(tmp_path, "--work-item", REF, "--dry-run") == 0
    out = capsys.readouterr().out
    assert "would also remove its workspace checkout" in out
    assert str(tmp_path / "ws") in out


def test_dry_run_stays_quiet_about_a_checkout_that_is_kept(
    tmp_path, capsys, monkeypatch
):
    monkeypatch.setattr(
        cli_config,
        "load_routing_config",
        lambda *_a, **_k: {
            "workspace": {"root": str(tmp_path / "ws"), "keepCheckoutOnClose": True}
        },
    )
    register(tmp_path)
    assert run(tmp_path, "--work-item", REF, "--dry-run") == 0
    assert "workspace checkout" not in capsys.readouterr().out


def test_the_same_ref_twice_is_one_reset(tmp_path, capsys):
    """Naming an item twice must not report the second as 'nothing to reset'."""
    arm(tmp_path)
    assert run(tmp_path, "--work-item", REF, "--work-item", REF) == 0
    out = capsys.readouterr()
    assert "nothing to reset" not in out.err
    assert "reset 1 work item" in out.out


def test_a_corrupt_pidfile_does_not_warn(tmp_path, capsys, monkeypatch):
    """0 and negative pids address process *groups*; the probe stays one pid."""
    root = tmp_path / "state"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sessions_cmd, "_state_layout", lambda: _layout(root))
    arm(tmp_path)
    for corrupt in ("0", "-1", "not-a-pid", ""):
        (root / "gh-webhook.pid").write_text(corrupt)
        run(tmp_path, "--work-item", REF, "--dry-run")
        assert "receiver" not in capsys.readouterr().err, corrupt


# -- the selector rules ----------------------------------------------------------------


def test_a_bare_reset_refuses_rather_than_resetting_everything(tmp_path, capsys):
    """
    Scenario: The dangerous reading has to be typed
      When `reset` is run with no selector
      Then it refuses with a usage error and nothing is touched
    """
    arm(tmp_path)
    assert run(tmp_path) == 2
    assert "--work-item" in capsys.readouterr().err
    assert store_for(tmp_path).section(REF, CONTROL) is not None


def test_both_selectors_is_refused(tmp_path, capsys):
    arm(tmp_path)
    assert run(tmp_path, "--all", "--work-item", REF) == 2
    assert "mutually exclusive" in capsys.readouterr().err
    assert store_for(tmp_path).section(REF, CONTROL) is not None


def test_hostile_refs_are_rejected_and_remove_nothing(tmp_path, capsys):
    """
    Scenario: A work-item ref never becomes a path
      Given refs carrying path separators, traversal and a leading dash
      When each is passed to reset
      Then it is refused as an invalid ref and nothing at all is removed
    """
    arm(tmp_path)
    hostile = [
        "github:octo/repo/../../etc#15",  # too many segments
        "../../etc/passwd",  # not a ref at all
        "-rf",  # an argv flag in ref's clothing
        "github:octo/repo#15/../../etc",  # trailing path after the number
    ]
    for ref in hostile:
        assert run(tmp_path, f"--work-item={ref}") == 2, ref
    assert "invalid work-item ref" in capsys.readouterr().err
    assert store_for(tmp_path).section(REF, CONTROL) is not None


def test_a_ref_that_parses_is_still_neutralised_by_the_slug(tmp_path):
    """
    Scenario: A ref that survives parsing cannot escape the state root either
      Given refs carrying a leading slash and a null byte, which `parse` accepts
      When each is passed to reset
      Then the file it resolves to is inside the store's own root, and there is
      nothing there to remove
    """
    arm(tmp_path)
    store = store_for(tmp_path)
    for ref in ("github:/etc/passwd#1", "github:octo/re\x00po#15"):
        item = WorkItemRef.parse(ref)
        assert "/" not in item.slug and "\x00" not in item.slug
        assert store.path_for(item).parent == store.root
        assert run(tmp_path, f"--work-item={ref}") == 1, ref
    assert store.section(REF, CONTROL) is not None


def test_one_bad_ref_resets_none_of_the_good_ones(tmp_path):
    """Validation is all-or-nothing: a typo in the second ref must not leave the
    first one half-reset."""
    arm(tmp_path)
    assert run(tmp_path, "--work-item", REF, "--work-item", "nonsense") == 2
    assert store_for(tmp_path).section(REF, CONTROL) is not None


def test_a_traversal_shaped_ref_that_parses_stays_inside_the_root(tmp_path):
    """`github:../..#1` parses (owner/repo are `..`), so the guard that matters
    is the slug: the file it resolves to is inside the portable root."""
    ref = "github:../..#1"
    item = WorkItemRef.parse(ref)
    assert "/" not in item.slug
    store = store_for(tmp_path)
    assert store.path_for(item).parent == store.root
    assert run(tmp_path, "--work-item", ref) == 1  # nothing recorded there


# -- --all touches only what the stores wrote ---------------------------------------


def test_a_strangers_file_in_the_state_directory_is_left_alone(tmp_path):
    """
    Scenario: The state directories are shared
      Given a file the-loop did not write in each state directory
      When `--all` resets every work item
      Then the strangers are still there
    """
    register(tmp_path)
    stranger_portable = tmp_path / "portable" / "notes.json"
    stranger_local = tmp_path / "local" / "scratch.json"
    stranger_portable.parent.mkdir(parents=True, exist_ok=True)
    stranger_local.parent.mkdir(parents=True, exist_ok=True)
    stranger_portable.write_text('{"hello": "world"}')
    stranger_local.write_text("{}")

    assert run(tmp_path, "--all") == 0

    assert stranger_portable.read_text() == '{"hello": "world"}'
    assert stranger_local.is_file()


# -- the audit trail -------------------------------------------------------------------


def test_the_event_log_is_appended_to_never_rewritten(tmp_path, monkeypatch):
    """
    Scenario: The command that could erase its own trail cannot
      Given an event log with history in it
      When a work item is reset
      Then the earlier bytes are untouched and one session.reset line is appended
    """
    log = tmp_path / "events.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text('{"ts":"2026-08-01T00:00:00Z","event":"poll.cycle"}\n')
    before = log.read_bytes()
    monkeypatch.setattr(
        eventlog,
        "configure_from_file",
        lambda source: eventlog.configure(source, path=str(log)),
    )
    arm(tmp_path)

    assert run(tmp_path, "--work-item", REF) == 0

    after = log.read_bytes()
    assert after.startswith(before)
    records = [json.loads(line) for line in log.read_text().splitlines() if line]
    reset_events = [r for r in records if r["event"] == "session.reset"]
    assert len(reset_events) == 1
    assert reset_events[0]["work_item"] == REF
    assert reset_events[0]["removed"] == [CONTROL]
    assert reset_events[0]["found"] is True


def test_a_reset_that_found_nothing_is_still_recorded(tmp_path, monkeypatch):
    log = tmp_path / "events.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        eventlog,
        "configure_from_file",
        lambda source: eventlog.configure(source, path=str(log)),
    )
    assert run(tmp_path, "--work-item", REF) == 1
    record = json.loads(log.read_text().splitlines()[-1])
    assert record["event"] == "session.reset" and record["found"] is False


def test_a_dry_run_emits_nothing(tmp_path, monkeypatch):
    log = tmp_path / "events.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        eventlog,
        "configure_from_file",
        lambda source: eventlog.configure(source, path=str(log)),
    )
    arm(tmp_path)
    assert run(tmp_path, "--work-item", REF, "--dry-run") == 0
    assert not log.exists() or "session.reset" not in log.read_text()


# -- the warnings ------------------------------------------------------------------------


def test_a_running_receiver_warns_but_does_not_block(tmp_path, capsys, monkeypatch):
    """
    Scenario: Resetting while the daemon is up
      Given a pidfile naming this very process
      When a work item is reset
      Then it is reset, and the operator is warned the daemon can write state back
    """
    import os

    root = tmp_path / "state"
    (root).mkdir(parents=True, exist_ok=True)
    (root / "gh-webhook.pid").write_text(str(os.getpid()))
    monkeypatch.setattr(sessions_cmd, "_state_layout", lambda: _layout(root))
    arm(tmp_path)

    assert run(tmp_path, "--work-item", REF) == 0

    err = capsys.readouterr().err
    assert "receiver" in err and str(os.getpid()) in err


def test_a_stale_pidfile_does_not_warn(tmp_path, capsys, monkeypatch):
    root = tmp_path / "state"
    root.mkdir(parents=True, exist_ok=True)
    (root / "gh-webhook.pid").write_text("2147483646")  # nothing is running there
    monkeypatch.setattr(sessions_cmd, "_state_layout", lambda: _layout(root))
    arm(tmp_path)
    assert run(tmp_path, "--work-item", REF) == 0
    assert "receiver" not in capsys.readouterr().err


def test_a_config_that_can_respawn_warns(tmp_path, capsys, monkeypatch):
    """
    Scenario: Clearing the poll ledger makes the thread first-sight again
      Given a config that neither requires a start nor refuses to spawn
      When a work item is reset
      Then the operator is warned it can be re-spawned by the next poll cycle
    """
    monkeypatch.setattr(
        cli_config,
        "load_routing_config",
        lambda *_a, **_k: {
            "spawnOnUnmatched": "labeled",
            "control": {"requireStartCommand": False},
        },
    )
    arm(tmp_path)

    assert run(tmp_path, "--work-item", REF) == 0

    assert "re-spawn" in capsys.readouterr().err


def test_a_fail_closed_config_does_not_warn(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(
        cli_config,
        "load_routing_config",
        lambda *_a, **_k: {
            "spawnOnUnmatched": "labeled",
            "control": {"requireStartCommand": True},
        },
    )
    arm(tmp_path)
    assert run(tmp_path, "--work-item", REF) == 0
    assert "re-spawn" not in capsys.readouterr().err


# -- failures --------------------------------------------------------------------------------


def test_one_failing_work_item_does_not_strand_the_rest(tmp_path, capsys, monkeypatch):
    """
    Scenario: One unwritable record in a multi-item run
      Given two work items, one of whose records cannot be written
      When both are reset
      Then the other is still reset, and the run exits non-zero
    """
    arm(tmp_path)
    arm(tmp_path, ref=OTHER)
    real = WorkItemStore.write_section

    def selective(self, work_item, name, data):
        ref = work_item if isinstance(work_item, str) else work_item.ref
        if ref == REF:
            raise OSError("read-only file system")
        return real(self, work_item, name, data)

    monkeypatch.setattr(WorkItemStore, "write_section", selective)

    assert run(tmp_path, "--work-item", REF, "--work-item", OTHER) == 1

    assert "read-only file system" in capsys.readouterr().err
    monkeypatch.undo()
    assert store_for(tmp_path).section(OTHER, CONTROL) is None
    assert store_for(tmp_path).section(REF, CONTROL) is not None


def test_poll_state_is_the_section_that_makes_a_thread_first_sight(tmp_path):
    """R1.5, end to end: the ledger really is gone, not merely emptied."""
    baseline(tmp_path)
    assert run(tmp_path, "--work-item", REF) == 0
    assert store_for(tmp_path).section(REF, POLL) is None
