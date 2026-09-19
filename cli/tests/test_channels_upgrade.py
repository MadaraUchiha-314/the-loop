"""What an installation from before issue-389 reads as, unchanged (T10).
Spec: docs/specs/issue-389/testing-plan.md T10.

A declaration without `listen` is a `mentions` room; a roster entry without
`slack` keeps working and one without either id is skipped; a channel state
file without `snapshots` loads with none; an app whose granted scopes lack
`app_mentions:read` is reported, by name, with the consequence. The
pre-change shapes are written here, as the files of that time were.
"""

from __future__ import annotations

import json
from pathlib import Path

from the_loop.channels.slack import (
    DEFAULT_BOT_TOKEN_ENV,
    mention_findings,
    probe_subscription,
)
from the_loop.channels.state import ChannelState, ChannelStores
from the_loop.collaborators import CollaboratorRecord, CollaboratorStore
from the_loop.workchannels import CollaborationChannel, CollaborationChannelStore

REF = "github:octo/repo#389"


def _strip(data, key):
    """``data`` with every ``key`` removed, at any depth — the file as it was
    written before the key existed."""
    if isinstance(data, dict):
        return {k: _strip(v, key) for k, v in data.items() if k != key}
    if isinstance(data, list):
        return [_strip(v, key) for v in data]
    return data


def test_a_declaration_without_listen_is_a_mentions_room(tmp_path):
    root = tmp_path / "state"
    store = CollaborationChannelStore(root / "portable")
    store.add(REF, "slack@C0OLD", actor="octocat", source="cli")
    stripped = 0
    for path in (root / "portable").glob("*.json"):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if "collaborationChannels" not in raw:
            continue  # the index
        assert "listen" in json.dumps(raw)
        path.write_text(json.dumps(_strip(raw, "listen")), encoding="utf-8")
        stripped += 1
    assert stripped == 1
    record = CollaborationChannelStore(root / "portable").for_type(REF, "slack")
    assert record is not None and record.listen == "mentions"
    stores = ChannelStores.beside(root / "channels" / "slack.json")
    assert stores.listen_mode("C0OLD") == "mentions"
    assert stores.listen_mode("C0NEVER") == "mentions"


def test_a_declaration_with_an_unknown_listen_reads_as_mentions():
    record = CollaborationChannel.from_dict(
        {"ref": "slack@C1", "listen": "everything", "addedBy": "x"}
    )
    assert record is not None and record.listen == "mentions"


def test_a_roster_entry_without_slack_keeps_working_and_one_without_ids_is_skipped(
    tmp_path,
):
    store = CollaboratorStore(tmp_path / "portable")
    store.add(REF, login="octocat", actor="owner", source="cli")
    for path in (tmp_path / "portable").glob("*.json"):
        raw = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps(_strip(raw, "slack")), encoding="utf-8")
    again = CollaboratorStore(tmp_path / "portable")
    assert again.is_collaborator("octocat", REF)
    assert again.slack_ids(REF) == []
    assert not again.is_collaborator_slack("UANY", REF)
    assert CollaboratorRecord.from_dict({"login": "octocat"}) is not None
    assert CollaboratorRecord.from_dict({}) is None
    assert CollaboratorRecord.from_dict({"slack": "not-an-id"}) is None
    assert CollaboratorRecord.from_dict({"login": "octocat", "slack": "bad"}) is None


def test_a_state_file_without_snapshots_loads_with_none(tmp_path):
    path = tmp_path / "state" / "channels" / "slack.json"
    path.parent.mkdir(parents=True)
    # The file as the channel wrote it before issue-389: the same maps, no
    # `snapshots` key.
    fresh = ChannelState()
    fresh.bind("1700.1", REF, "D123", origin="event")
    fresh.save(path)
    payload = _strip(json.loads(path.read_text(encoding="utf-8")), "snapshots")
    assert "snapshots" not in payload
    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = ChannelState.load(path)
    assert loaded.snapshots == {}
    assert loaded.snapshot_for("D123:1700.1") is None
    assert loaded.work_item_for("1700.1") == REF
    loaded.note_snapshot("D123:1700.1", REF, "1700.9", 3)
    loaded.save(path)
    noted = ChannelState.load(path).snapshot_for("D123:1700.1")
    assert noted is not None and noted["last"] == "1700.9"


def test_an_app_without_the_mention_scope_is_reported_by_name(tmp_path, monkeypatch):
    from test_channels_dm import FakeProbeClient, parsed

    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    client = FakeProbeClient(
        info={"id": "D0AU0SGP30T", "is_im": True}, scopes="chat:write,im:history"
    )
    result = probe_subscription(
        parsed(tmp_path, channel="D0AU0SGP30T"), client_factory=lambda token: client
    )
    findings = [f for f in result["findings"] if "app_mentions:read" in f]
    assert len(findings) == 1
    assert "nothing typed reaches the-loop" in findings[0]
    assert "direct message" in findings[0].lower() or "--listen all" in findings[0]
    assert mention_findings(None) == ()
    assert mention_findings(("chat:write", "app_mentions:read")) == ()
    assert Path(__file__).exists()
