"""Unit tests for the tracked-work overview table (issue-98)."""

import json

from the_loop.sessions import PauseStore, Session, SessionRegistry, WorkItemRef
from the_loop.sessions.overview import (
    build_rows,
    render_detail,
    render_table,
    work_item_url,
)

REF = "github:octo/repo#15"
OTHER = "github:octo/repo#16"


class FakePollState:
    """Minimal stand-in for PollState's read API."""

    def __init__(self, items):
        self._items = items  # ref -> (attempts, gave_up, last_polled_at)

    def tracked_refs(self):
        return sorted(self._items)

    def spawn_attempts(self, ref):
        return self._items[ref][0]

    def spawn_gave_up(self, ref):
        return self._items[ref][1]

    def last_polled_at(self, ref):
        return self._items[ref][2]


class FakeTmux:
    def __init__(self, live=None, pids=None, available=True):
        self.live = {} if live is None else live
        self.pids = {} if pids is None else pids
        self.available = available

    def is_available(self):
        return self.available

    def has_live_session(self, target):
        return self.live.get(target, False)

    def live_pane_pids(self, target):
        return self.pids.get(target, [])


def registry_with(tmp_path, *sessions):
    registry = SessionRegistry(tmp_path / "sessions")
    for session in sessions:
        registry.register(session, force=True)
    return registry


def session(ref=REF, **kwargs):
    kwargs.setdefault("harness", "claude")
    kwargs.setdefault("harness_session_id", "uuid-1")
    kwargs.setdefault("cwd", "/tmp/work")
    return Session(work_item=WorkItemRef.parse(ref), **kwargs)


def pauses(tmp_path):
    return PauseStore(tmp_path / "paused.json")


def test_url_is_derived_for_github_and_omitted_otherwise():
    assert work_item_url(WorkItemRef.parse(REF)).endswith("/octo/repo/issues/15")
    assert work_item_url(WorkItemRef.parse("jira:octo/repo#15")) == ""


def test_a_registered_session_becomes_an_active_row(tmp_path):
    rows = build_rows(
        registry_with(tmp_path, session(last_event_at="2026-07-25T10:00:00Z")),
        pauses(tmp_path),
        tmux=FakeTmux(),
    )
    assert [row.ref for row in rows] == [REF]
    row = rows[0]
    assert row.status == "active"
    assert row.harness == "claude"
    assert row.url.endswith("/issues/15")
    assert row.last_event_at == "2026-07-25T10:00:00Z"


def test_tmux_rows_carry_liveness_pid_and_attach_command(tmp_path):
    registry = registry_with(
        tmp_path, session(runner="tmux", tmux_target="loop-github-octo-repo-15")
    )
    tmux = FakeTmux(
        live={"loop-github-octo-repo-15": True},
        pids={"loop-github-octo-repo-15": [4242]},
    )
    row = build_rows(registry, pauses(tmp_path), tmux=tmux)[0]
    assert row.host == "tmux:loop-github-octo-repo-15 pid 4242"
    assert row.host_live is True
    assert row.attach == "tmux attach -t loop-github-octo-repo-15"
    assert "(live)" in row.host_display


def test_process_rows_show_the_owning_daemon_pid(tmp_path):
    import os

    registry = registry_with(tmp_path, session(owner_pid=os.getpid()))
    row = build_rows(registry, pauses(tmp_path), tmux=FakeTmux())[0]
    assert row.host == f"process:{os.getpid()}"
    assert row.host_live is True

    dead = registry_with(tmp_path / "b", session(owner_pid=999_999_999))
    assert build_rows(dead, pauses(tmp_path), tmux=FakeTmux())[0].host_live is False


def test_unavailable_tmux_reports_unknown_not_dead(tmp_path):
    registry = registry_with(tmp_path, session(runner="tmux", tmux_target="loop-x"))
    row = build_rows(registry, pauses(tmp_path), tmux=FakeTmux(available=False))[0]
    assert row.host_live is None
    assert "(?)" in row.host_display


def test_a_recorded_pr_is_linked(tmp_path):
    registry = registry_with(
        tmp_path, session(pr_ref="github:octo/repo#20", pr_url="https://pr/20")
    )
    row = build_rows(registry, pauses(tmp_path), tmux=FakeTmux())[0]
    assert row.pr_ref == "github:octo/repo#20"
    assert "github:octo/repo#20" in render_table([row])


def test_poll_only_items_show_as_tracked_or_spawn_failed(tmp_path):
    poll_state = FakePollState(
        {
            REF: (0, False, "2026-07-25T10:00:00Z"),
            OTHER: (3, True, "2026-07-25T10:00:00Z"),
        }
    )
    rows = {
        row.ref: row
        for row in build_rows(
            SessionRegistry(tmp_path / "sessions"),
            pauses(tmp_path),
            poll_state=poll_state,
            tmux=FakeTmux(),
        )
    }
    assert rows[REF].status == "tracked"
    assert rows[OTHER].status == "spawn-failed"
    assert rows[OTHER].spawn_attempts == 3
    assert all(row.tracked for row in rows.values())


def test_a_session_row_is_enriched_rather_than_duplicated(tmp_path):
    poll_state = FakePollState({REF: (1, False, "2026-07-25T11:00:00Z")})
    rows = build_rows(
        registry_with(tmp_path, session()),
        pauses(tmp_path),
        poll_state=poll_state,
        tmux=FakeTmux(),
    )
    assert len(rows) == 1
    assert rows[0].status == "active" and rows[0].tracked is True
    assert rows[0].last_polled_at == "2026-07-25T11:00:00Z"


def test_a_paused_session_reads_as_paused(tmp_path):
    store = pauses(tmp_path)
    store.pause(REF, reason="waiting on review")
    row = build_rows(registry_with(tmp_path, session()), store, tmux=FakeTmux())[0]
    assert row.status == "paused"
    assert row.pause_sources == ["local"]
    assert row.pause_reason == "waiting on review"


def test_a_pause_with_no_session_and_no_poll_entry_still_shows(tmp_path):
    store = pauses(tmp_path)
    store.pause(OTHER, reason="parked before it started")
    rows = build_rows(SessionRegistry(tmp_path / "sessions"), store, tmux=FakeTmux())
    assert [row.ref for row in rows] == [OTHER]
    assert rows[0].status == "paused"


def test_status_and_work_item_filters(tmp_path):
    store = pauses(tmp_path)
    store.pause(OTHER)
    registry = registry_with(tmp_path, session(), session(ref=OTHER))
    assert [row.ref for row in build_rows(registry, store, status="paused")] == [OTHER]
    assert [row.ref for row in build_rows(registry, store, status="active")] == [REF]
    assert [row.ref for row in build_rows(registry, store, work_item=REF)] == [REF]


def test_rows_sort_active_first_then_paused_then_closed(tmp_path):
    store = pauses(tmp_path)
    store.pause("github:octo/repo#2")
    registry = registry_with(
        tmp_path,
        session(ref="github:octo/repo#3", status="closed"),
        session(ref="github:octo/repo#2"),
        session(ref="github:octo/repo#1"),
    )
    statuses = [row.status for row in build_rows(registry, store, tmux=FakeTmux())]
    assert statuses == ["active", "paused", "closed"]


def test_table_renders_a_header_and_dashes_for_missing_fields(tmp_path):
    text = render_table(
        build_rows(
            registry_with(tmp_path, session()), pauses(tmp_path), tmux=FakeTmux()
        )
    )
    header, row = text.splitlines()
    assert header.split() == [
        "Work",
        "item",
        "Status",
        "Harness",
        "Runner",
        "Where",
        "PR",
        "Last",
        "event",
    ]
    assert "-" in row  # no PR, no last event yet


def test_empty_table_is_just_the_header():
    assert len(render_table([]).splitlines()) == 1


def test_json_rows_carry_the_same_facts(tmp_path):
    store = pauses(tmp_path)
    store.pause(REF, reason="parked")
    row = build_rows(registry_with(tmp_path, session()), store, tmux=FakeTmux())[0]
    data = json.loads(json.dumps(row.to_dict()))
    assert data["ref"] == REF
    assert data["paused"] is True
    assert data["pauseSources"] == ["local"]
    assert data["pr"] == {"ref": "", "url": ""}


def test_detail_view_lists_every_field(tmp_path):
    registry = registry_with(
        tmp_path,
        session(runner="tmux", tmux_target="loop-x", pr_url="https://pr/20"),
    )
    tmux = FakeTmux(live={"loop-x": True}, pids={"loop-x": [7]})
    detail = render_detail(build_rows(registry, pauses(tmp_path), tmux=tmux)[0])
    for label in ("Work item", "URL", "Paused", "Attach", "Pull request", "Where"):
        assert label in detail
    assert "tmux attach -t loop-x" in detail
    assert "https://pr/20" in detail
