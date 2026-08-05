"""The MCP endpoint: HTTP-only JSON-RPC over the core facade (issue-161, T10)."""

import json

from fastapi.testclient import TestClient

from the_loop.api.app import create_app
from the_loop.state import layout_from_config, legacy_layout
from the_loop.workitem import WorkItemStore


REF = "github:octo/repo#7"


def _client(tmp_path):
    config = {"state": {"root": str(tmp_path / ".the-loop")}}
    return TestClient(create_app(config)), config


def _rpc(client, method, params=None, id_=1):
    message = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        message["params"] = params
    return client.post("/mcp", json=message)


def test_initialize_and_tools_list(tmp_path):
    """
    Feature: MCP interface over the control plane
      Scenario: an agent host connects and discovers tools
        Given a running service
        When the host sends initialize and tools/list
        Then it receives the protocol handshake and the tool registry,
             with the destructive/attribution-forging tools absent

    Requirement: docs/specs/issue-161/requirements.md R5.1, R5.3
    """
    client, _ = _client(tmp_path)
    init = _rpc(client, "initialize").json()
    assert init["result"]["serverInfo"]["name"] == "the-loop"
    assert "tools" in init["result"]["capabilities"]

    tools = _rpc(client, "tools/list").json()["result"]["tools"]
    names = {t["name"] for t in tools}
    assert "list_work_items" in names
    assert "check_work_item" in names
    assert "control_session" in names
    # Exclusions are policy (design §Security design):
    assert not any("reset" in n for n in names)
    assert not any("force" in n for n in names)


def test_tools_call_round_trips_core_data(tmp_path):
    """
    Feature: MCP tools are the same core surface as REST
      Scenario: an agent lists work items
        Given a portable record on disk
        When tools/call runs list_work_items
        Then the result content is the same record the REST route serves

    Requirement: docs/specs/issue-161/requirements.md R5.1, R5.2
    """
    client, config = _client(tmp_path)
    layout = layout_from_config(config)
    store = WorkItemStore(layout.portable_dir, legacy=legacy_layout(layout))
    store.write_section(REF, "control", {"command": "start"})

    response = _rpc(
        client, "tools/call", {"name": "list_work_items", "arguments": {}}
    ).json()
    payload = json.loads(response["result"]["content"][0]["text"])
    assert response["result"]["isError"] is False
    assert [r["ref"] for r in payload] == [REF]


def test_tool_errors_are_results_not_crashes(tmp_path):
    client, _ = _client(tmp_path)
    response = _rpc(
        client,
        "tools/call",
        {"name": "get_work_item", "arguments": {"ref": "not-a-ref"}},
    ).json()
    assert response["result"]["isError"] is True


def test_unknown_tool_and_method_are_rpc_errors(tmp_path):
    client, _ = _client(tmp_path)
    unknown_tool = _rpc(client, "tools/call", {"name": "sessions_reset"}).json()
    assert unknown_tool["error"]["code"] == -32602
    unknown_method = _rpc(client, "prompts/list").json()
    assert unknown_method["error"]["code"] == -32601


def test_mcp_needs_no_credential(tmp_path):
    """
    Feature: MCP over the control plane
      Scenario: an agent host calls the endpoint with no credential
        Given a running service (auth is the gateway's job, PR #162)
        When a JSON-RPC tools/list arrives with no Authorization header
        Then it is served normally

    Requirement: docs/specs/issue-161/requirements.md R5.1
    """
    client, _ = _client(tmp_path)
    response = client.post(
        "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    )
    assert response.status_code == 200
    assert response.json()["result"]["tools"]
