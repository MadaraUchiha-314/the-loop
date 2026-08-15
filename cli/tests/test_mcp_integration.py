"""The MCP interface, over the official SDK's streamable HTTP (issue-161, T10).

These drive the **real** protocol through the SDK — initialize, the
initialized notification, tools/list, tools/call — rather than asserting on a
hand-rolled JSON-RPC shape, because the protocol is the SDK's now (owner
decision, PR #162: "Follow official SDKs").
"""

import json
import re

import pytest
from fastapi.testclient import TestClient

from the_loop.api.app import create_app
from the_loop.api.mcp import MCP_PATH
from the_loop.state import layout_from_config, legacy_layout
from the_loop.workitem import WorkItemStore

REF = "github:octo/repo#7"
#: The SDK's DNS-rebinding protection pins Host; use the configured bind.
BASE_URL = "http://127.0.0.1:4114"
HEADERS = {"Accept": "application/json, text/event-stream"}


def _sse_payloads(text: str):
    """Every JSON object carried by an SSE (or plain JSON) MCP response."""
    if not text.lstrip().startswith("event:") and not text.lstrip().startswith("data:"):
        return [json.loads(text)]
    return [json.loads(m) for m in re.findall(r"^data: (.+)$", text, re.MULTILINE)]


class McpClient:
    """A minimal MCP client over the mounted app — handshake then calls."""

    def __init__(self, client: TestClient):
        self._client = client
        response = self._post(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "tests", "version": "1"},
                },
            }
        )
        assert response.status_code == 200, response.text
        self.session_id = response.headers.get("mcp-session-id")
        self.initialize_result = _sse_payloads(response.text)[0]["result"]
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _post(self, message):
        headers = dict(HEADERS)
        if getattr(self, "session_id", None):
            headers["mcp-session-id"] = self.session_id
        return self._client.post(MCP_PATH, json=message, headers=headers)

    def request(self, method, params=None, id_=99):
        message = {"jsonrpc": "2.0", "id": id_, "method": method}
        if params is not None:
            message["params"] = params
        response = self._post(message)
        assert response.status_code == 200, response.text
        return _sse_payloads(response.text)[0]


@pytest.fixture()
def mcp(tmp_path):
    config = {"state": {"root": str(tmp_path / ".the-loop")}}
    with TestClient(create_app(config), base_url=BASE_URL) as client:
        yield McpClient(client), config


def test_initialize_reports_the_loop_server(mcp):
    """
    Feature: MCP interface over the official SDK
      Scenario: an agent host performs the protocol handshake
        Given a running control-plane service
        When the host sends initialize
        Then the SDK answers with the-loop's server identity and tool capability

    Requirement: docs/specs/issue-161/requirements.md R5.1
    """
    client, _ = mcp
    result = client.initialize_result
    assert result["serverInfo"]["name"] == "the-loop"
    assert "tools" in result["capabilities"]
    assert client.session_id


def test_tools_list_is_the_core_surface_minus_exclusions(mcp):
    """
    Feature: MCP tools are generated from the core facade
      Scenario: an agent discovers what it may do
        Given the tool registry built from the core surface
        When the host calls tools/list
        Then the read and manage operations are present, and the destructive /
             attribution-forging ones (sessions reset, graph force) are absent

    Requirement: docs/specs/issue-161/requirements.md R5.1, R5.3
    """
    client, _ = mcp
    tools = client.request("tools/list")["result"]["tools"]
    names = {t["name"] for t in tools}
    assert {
        "list_work_items",
        "check_work_item",
        "control_session",
        "session_transcript",
    } <= names
    assert not any("reset" in n for n in names)
    assert not any("force" in n for n in names)
    # The SDK derives each schema from the annotations — no hand-written JSON.
    by_name = {t["name"]: t for t in tools}
    assert "ref" in by_name["get_work_item"]["inputSchema"]["properties"]


def test_tools_call_round_trips_core_data(mcp):
    """
    Feature: MCP tools serve the same data as REST
      Scenario: an agent lists work items
        Given a portable record written by an ingress
        When the host calls the list_work_items tool
        Then the result carries the same record the REST route serves

    Requirement: docs/specs/issue-161/requirements.md R5.1, R5.2
    """
    client, config = mcp
    layout = layout_from_config(config)
    store = WorkItemStore(layout.portable_dir, legacy=legacy_layout(layout))
    store.write_section(REF, "control", {"command": "start"})

    result = client.request("tools/call", {"name": "list_work_items", "arguments": {}})[
        "result"
    ]
    assert result.get("isError") is not True
    assert REF in json.dumps(result)


def test_tool_error_is_reported_not_crashed(mcp):
    """A bad ref comes back as a tool error, leaving the session usable."""
    client, _ = mcp
    result = client.request(
        "tools/call", {"name": "get_work_item", "arguments": {"ref": "not-a-ref"}}
    )["result"]
    assert result["isError"] is True


def test_unknown_tool_is_an_error(mcp):
    client, _ = mcp
    payload = client.request("tools/call", {"name": "sessions_reset", "arguments": {}})
    assert "error" in payload or payload["result"]["isError"] is True


def test_the_endpoint_answers_on_mcp_without_a_redirect():
    """
    Feature: MCP over HTTP
      Scenario: a client posts to the documented endpoint URL
        Given the control-plane service
        When a client POSTs an initialize request to /mcp exactly
        Then it is answered there — never 307'd to /mcp/, which a client that
             does not follow redirects on POST would fail to complete

    Requirement: docs/specs/issue-161/requirements.md R5.1
    """
    with TestClient(create_app({}), base_url=BASE_URL, follow_redirects=False) as http:
        response = http.post(
            MCP_PATH,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "probe", "version": "1"},
                },
            },
            headers=HEADERS,
        )
    assert response.status_code == 200
    assert _sse_payloads(response.text)[0]["result"]["serverInfo"]["name"] == "the-loop"


def test_mcp_can_be_disabled_per_config():
    """
    Feature: MCP over HTTP
      Scenario: a REST-only deployment turns the MCP layer off
        Given service.mcp.enabled false in the CLI config
        When the app is built and a client POSTs to /mcp
        Then no MCP app is mounted at all — /mcp answers 404 — while the REST
             surface keeps answering

    Requirement: docs/specs/issue-228/requirements.md R1.6
    """
    config = {"service": {"mcp": {"enabled": False}}}
    with TestClient(create_app(config), base_url=BASE_URL) as http:
        assert http.get("/api/v1/health").status_code == 200
        response = http.post(
            MCP_PATH,
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            headers=HEADERS,
        )
    assert response.status_code == 404
