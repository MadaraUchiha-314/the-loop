"""A file a person attached reaches the session and the ticket — end to end through
the Socket Mode handler, the poll reader, the pipeline, the fake Slack client, the
fake ledger writer and the dispatcher's prompt (issue-416). Every fetch goes through
a fake: no network, no credential. Spec: docs/specs/issue-416/testing-plan.md T2, T8.

Feature: multi-modal messages are forwarded to the session, never parsed by the loop
Requirement: docs/specs/issue-416/requirements.md#R1
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from conftest import _state_with_stores
from the_loop.channels import attachments as attachments_mod
from the_loop.channels import inbound, once
from the_loop.channels import slack as slack_mod
from the_loop.channels.attachments import SLACK_HOSTS, FetchError
from the_loop.channels.slack import (
    DEFAULT_BOT_TOKEN_ENV,
    SlackBotChannel,
    SlackChannelConfig,
    attachment_findings,
    probe_subscription,
)
from the_loop.control import ControlConfig
from the_loop.sessions import SessionRegistry, WorkItemRef
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import RoutedEvent, extract_work_items
from the_loop.workchannels import CollaborationChannelStore
from test_channels import FakeSlackClient, cli_config
from test_channels_dm import FakeProbeClient, parsed

REF = "github:octo/repo#416"
SLUG = "github-octo-repo-416"
ROOM = "C0TMP416"
CENTRAL = "C123"
DM = "D0BOT"
BOT = "UBOT"
GRANTS = ["work-item.reply", "control.command", "work-item.create", "context.added"]
PERMALINK = "https://x.slack.com/files/UHUMAN/F0IMG/shot.png"
PRIVATE = "https://files.slack.com/files-pri/T0-F0IMG/download/shot.png"
MANIFEST = Path(slack_mod.__file__).with_name("slack-app-manifest.yaml")
VTT = "WEBVTT\n\n00:00.000 --> 00:02.000\nplease make the button blue\n"


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    monkeypatch.setenv(DEFAULT_BOT_TOKEN_ENV, "xoxb-test")
    monkeypatch.setenv("GH_TOKEN", "ghp-test")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)


@pytest.fixture(autouse=True)
def _fresh_ring():
    once.reset()
    yield
    once.reset()


@pytest.fixture
def fetch(monkeypatch):
    """The one network call, faked: records ``(url, credential, allowed_hosts)`` and
    answers PNG bytes, VTT captions for a ``.vtt`` URL, or raises what ``fail`` holds."""
    fake = _FakeFetch()
    monkeypatch.setattr(attachments_mod, "fetch_url", fake)
    return fake


class _FakeFetch:
    def __init__(self):
        self.calls: list = []
        self.state: dict = {"fail": None}

    def __call__(self, url, *, credential="", allowed_hosts=(), max_bytes=0, **_):
        self.calls.append((url, credential, tuple(allowed_hosts)))
        if self.state["fail"] is not None:
            raise self.state["fail"]
        if url.endswith(".vtt"):
            return "text/vtt", VTT.encode()
        if "audio" in url:
            return "audio/mp4", b"m4a-bytes"
        return "image/png", b"png-bytes"


class Client(FakeSlackClient):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.ephemeral = []
        self.info_reads = []

    def chat_postEphemeral(self, *, channel, user, text, thread_ts=None):
        self.ephemeral.append((channel, user, text, thread_ts))
        return {"ok": True}

    def chat_getPermalink(self, *, channel, message_ts):
        return {
            "ok": True,
            "permalink": f"https://x.slack.com/archives/{channel}/p{message_ts.replace('.', '')}",
        }

    def auth_test(self):
        return {"ok": True, "user_id": BOT, "url": "https://x.slack.com/"}

    def files_info(self, *, file):
        self.info_reads.append(file)
        return {"ok": True, "file": _audio(status="complete")}


class Sink:
    def __init__(self):
        self.recorded: list = []
        self.delivered: list = []
        self.created: list = []

    def post_comment(self, item, body, **kwargs) -> tuple:
        self.recorded.append((getattr(item, "ref", str(item)), body))
        n = len(self.recorded)
        return True, "", f"https://github.com/octo/repo/issues/416#issuecomment-{n}"

    def deliver(self, ref, text, actor="", comment=True, config=None, **extra):
        self.delivered.append({"ref": ref, "text": text, "actor": actor, **extra})
        return {"delivered": True}

    def create_issue(self, repo, title, body, labels=(), gh_binary="gh"):
        self.created.append((repo, title, body))
        return True, "", "github:octo/repo#999", "https://x/999"


def _image(**over):
    file = {
        "id": "F0IMG",
        "name": "shot.png",
        "mimetype": "image/png",
        "size": 9,
        "permalink": PERMALINK,
        "url_private": PRIVATE.replace("/download", ""),
        "url_private_download": PRIVATE,
    }
    file.update(over)
    return file


def _audio(status="complete"):
    return {
        "id": "F0AUD",
        "name": "audio_message.m4a",
        "mimetype": "audio/mp4",
        "subtype": "slack_audio",
        "size": 9,
        "permalink": "https://x.slack.com/files/UHUMAN/F0AUD/audio_message.m4a",
        "url_private_download": "https://files.slack.com/files-pri/T0-F0AUD/download/audio_message.m4a",
        "vtt": "https://files.slack.com/files-pri/T0-F0AUD/audio_message.vtt",
        "transcription": {
            "status": status,
            "locale": "en-US",
            "preview": {"content": "please make the button blue", "has_more": False},
        },
    }


def config_for(tmp_path, channel=CENTRAL, **slack):
    publish = slack.pop("publish", GRANTS)
    cfg = cli_config(tmp_path, channel=channel, publish=publish, **slack)
    cfg["channels"]["slack"]["read"] = {"mode": "socket"}
    return cfg


def declare(config, target=ROOM, listen="mentions", work_item=REF):
    CollaborationChannelStore(Path(config["state"]["root"]) / "portable").add(
        work_item, f"slack@{target}", actor="octocat", source="cli", listen=listen
    )


def bot_for(config, client):
    return SlackBotChannel(
        SlackChannelConfig.from_mapping(config),
        Path(config["state"]["root"]) / "channels" / "slack.json",
        client_factory=lambda token: client,
    )


def send(
    config,
    sink,
    client,
    *,
    text,
    files=(),
    addressed=True,
    channel=ROOM,
    ts="1900.5",
    thread="",
    user="UHUMAN",
):
    event = {"ts": ts, "channel": channel, "user": user, "text": text}
    if files:
        event["files"] = list(files)
    if thread:
        event["thread_ts"] = thread
    return inbound.handle_socket_event(
        event,
        config,
        post_comment=sink.post_comment,
        deliver=sink.deliver,
        create_issue=sink.create_issue,
        client_factory=lambda token: client,
        addressed=addressed,
    )


def attachments_dir(config) -> Path:
    return Path(config["state"]["root"]) / "local" / "attachments" / SLUG


# -- R1, R3: a Slack image ----------------------------------------------------------


def test_a_slack_image_reaches_the_session_as_a_path_and_the_ticket_as_a_link(
    tmp_path, fetch
):
    """
    Scenario: a Slack image reaches the session as a path and the ticket as a link
      Given #416 declared the room C0TMP416
      When an authorized member mentions the-loop with a screenshot attached
      Then the file is fetched with the bot token against Slack's hosts
      And saved under <state.root>/local/attachments/<slug>/
      And the delivered text ends with an Attachments section naming its kind and path
      And the ticket's record carries the 📎 line with the permalink and no path
    """
    config = config_for(tmp_path)
    declare(config)
    sink, client = Sink(), Client()
    outcome = send(
        config, sink, client, text=f"<@{BOT}> like this one", files=[_image()]
    )
    assert outcome["outcome"] == "processed" and outcome["event"] == "work-item.reply"
    assert fetch.calls == [(PRIVATE, "xoxb-test", tuple(SLACK_HOSTS))]
    saved = attachments_dir(config) / "F0IMG-shot.png"
    assert saved.read_bytes() == b"png-bytes"
    delivered = sink.delivered[0]["text"]
    assert delivered.startswith("like this one\n\nAttachments (1)")
    assert (
        f"1. image · shot.png (image/png, 9 B) — saved at {saved} — {PERMALINK}"
        in delivered
    )
    assert "file-reading tool" in delivered and "UNTRUSTED" in delivered
    record = sink.recorded[0][1]
    assert f"📎 shot.png (image/png, 9 B) — {PERMALINK}" in record
    assert "files-pri" not in record and "attachments/" not in record
    assert client.reactions[-1][2] == "white_check_mark"


def test_a_voice_note_reaches_the_session_and_the_ticket_as_slacks_transcript(
    tmp_path, fetch
):
    """
    Scenario: a voice note reaches the session and the ticket as Slack's transcript
      Given #416 declared the room
      When an authorized member sends a voice clip Slack has transcribed
      Then the captions are fetched and stripped to text
      And the delivered section quotes Slack's transcript under the saved clip
      And the record quotes it beneath the 📎 line
    """
    config = config_for(tmp_path)
    declare(config)
    sink, client = Sink(), Client()
    send(config, sink, client, text=f"<@{BOT}>", files=[_audio()])
    delivered = sink.delivered[0]["text"]
    assert (
        "2." not in delivered
        and "1. audio · audio_message.m4a (audio/mp4, 9 B) — saved at" in delivered
    )
    assert 'Slack\'s transcript: "please make the button blue"' in delivered
    assert "transcribes nothing" in delivered
    record = sink.recorded[0][1]
    assert (
        "📎 audio_message.m4a (audio/mp4, 9 B) — https://x.slack.com/files/UHUMAN/F0AUD/audio_message.m4a"
        in record
    )
    assert "> > Slack's transcript: please make the button blue" in record


def test_a_processing_transcript_is_re_read_through_files_info(tmp_path, fetch):
    """
    Scenario: a transcript Slack is still producing is re-read before delivery
      Given a voice clip whose transcription is processing when the event arrives
      When the pipeline fetches it
      Then files.info is re-read and the completed transcript is delivered
    """
    config = config_for(tmp_path)
    declare(config)
    sink, client = Sink(), Client()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(attachments_mod.time, "sleep", lambda s: None)
        send(
            config, sink, client, text=f"<@{BOT}>", files=[_audio(status="processing")]
        )
    assert client.info_reads == ["F0AUD"]
    assert "please make the button blue" in sink.delivered[0]["text"]


def test_a_message_that_is_only_an_image_is_delivered(tmp_path, fetch):
    """
    Scenario: a message that is only an image is delivered
      Given #416 declared the room
      When an authorized member mentions the-loop with nothing but a screenshot
      Then it is delivered — the Attachments section is the text — and acknowledged ✅
    """
    config = config_for(tmp_path)
    declare(config)
    sink, client = Sink(), Client()
    outcome = send(config, sink, client, text=f"<@{BOT}>", files=[_image()])
    assert outcome["outcome"] == "processed" and outcome.get("delivered") is True
    assert sink.delivered[0]["text"].startswith("Attachments (1)")
    assert client.reactions[-1][2] == "white_check_mark"


def test_a_file_that_cannot_be_fetched_is_named_and_the_words_still_arrive(
    tmp_path, fetch
):
    """
    Scenario: a file that cannot be fetched is still named, and the message is delivered
      Given Slack refuses the download (the files:read scope is missing)
      When an authorized member attaches a screenshot to a reply
      Then the reply is delivered with the file named and the fixed reason
      And the record links the permalink with the same reason
    """
    config = config_for(tmp_path)
    declare(config)
    fetch.state["fail"] = FetchError("transfer-failed", "HTTP 403")
    sink, client = Sink(), Client()
    outcome = send(config, sink, client, text=f"<@{BOT}> see this", files=[_image()])
    assert outcome.get("delivered") is True
    delivered = sink.delivered[0]["text"]
    assert (
        f"1. image · shot.png (image/png, 9 B) — not fetched: the transfer failed — {PERMALINK}"
        in delivered
    )
    assert "(not fetched: the transfer failed)" in sink.recorded[0][1]
    assert not attachments_dir(config).exists()


def test_a_strangers_file_is_never_fetched(tmp_path, fetch):
    """
    Scenario: a stranger's file is never fetched
      Given #416 declared the room
      When an unlisted member mentions the-loop with a screenshot
      Then the message is dropped before its files are looked at
      And no fetch is made and nothing is saved
    """
    config = config_for(tmp_path)
    declare(config)
    sink, client = Sink(), Client()
    outcome = send(
        config, sink, client, text=f"<@{BOT}> look", files=[_image()], user="UNOBODY"
    )
    assert outcome["outcome"] == "unauthorized-actor"
    assert fetch.calls == [] and not attachments_dir(config).exists()
    assert sink.delivered == [] and sink.recorded == []


def test_a_poll_read_reply_carries_its_files(tmp_path, fetch):
    """
    Scenario: a poll-read reply carries its files
      Given a bound thread in a direct message with the bot
      When the poll reader finds a reply with a file in it
      Then the normalized message carries the file object
      And the pipeline delivers it with the Attachments section
    """
    config = config_for(tmp_path, channel=DM)
    client = Client(
        replies={
            "1800.1": [
                {"ts": "1800.1", "user": BOT, "text": "root"},
                {"ts": "1800.2", "user": "UHUMAN", "text": "here", "files": [_image()]},
            ]
        }
    )
    bot = bot_for(config, client)
    bot.bind("1800.1", REF, DM, origin="start")
    (reply,) = bot.fetch_replies()
    assert reply.files == (_image(),)
    sink = Sink()
    outcome = inbound.process_reply(
        reply,
        SlackChannelConfig.from_mapping(config),
        config,
        post_comment=sink.post_comment,
        deliver=sink.deliver,
        channel=bot,
    )
    assert outcome["outcome"] == "processed"
    assert "Attachments (1)" in sink.delivered[0]["text"]


def test_a_gate_answer_with_a_file_names_it_on_the_record(tmp_path, fetch):
    """
    Scenario: a gate answer with a file names it on the record
      Given the channel holds gate.feedback and the graph cannot be read here
      When an authorized member answers with a screenshot and the word approved
      Then the record — left to the ledger — carries the 📎 line
      And the channel delivers nothing into the pane itself
    """
    config = config_for(tmp_path, publish=[*GRANTS, "gate.feedback"])
    declare(config)
    sink, client = Sink(), Client()
    outcome = send(
        config, sink, client, text=f"<@{BOT}> approved, matches this", files=[_image()]
    )
    assert outcome["outcome"] == "processed" and outcome["event"] == "gate.feedback"
    assert f"📎 shot.png (image/png, 9 B) — {PERMALINK}" in sink.recorded[0][1]
    assert sink.delivered == []
    assert (attachments_dir(config) / "F0IMG-shot.png").is_file()


def test_a_recorded_thread_names_the_files_its_messages_carried(tmp_path, fetch):
    """
    Scenario: a recorded thread names the files its messages carried
      Given a bound thread whose second message is a screenshot with no words
      When the thread is snapshotted for record-context
      Then that message's line carries 📎 with the file's name and permalink
    """
    config = config_for(tmp_path, channel=DM)
    client = Client(
        replies={
            "1800.1": [
                {"ts": "1800.1", "user": "UHUMAN", "text": "root"},
                {"ts": "1800.2", "user": "UHUMAN", "text": "", "files": [_image()]},
            ]
        }
    )
    bot = bot_for(config, client)
    snapshot = bot.snapshot_thread(DM, "1800.1")
    assert f"📎 shot.png ({PERMALINK})" in snapshot.text
    assert fetch.calls == []


def test_a_kickoff_with_a_file_links_it_from_the_issue_body(tmp_path, fetch):
    """
    Scenario: a kickoff with a file links it from the issue body
      Given the central channel holds work-item.create and names its repository
      When an authorized member opens a work item from a top-level mention with a screenshot
      Then the issue body ends with the 📎 line and nothing is fetched
    """
    config = config_for(tmp_path, kickoff={"repo": "octo/repo", "labels": []})
    sink, client = Sink(), Client()
    outcome = send(
        config,
        sink,
        client,
        text=f"<@{BOT}> Fix the header\nIt overlaps the logo.",
        files=[_image()],
        channel=CENTRAL,
    )
    assert outcome["outcome"] == "created", outcome
    (created,) = sink.created
    assert created[1] == "Fix the header"
    body = created[2]
    line = f"📎 shot.png (image/png, 9 B) — {PERMALINK}"
    assert line in body and body.index("It overlaps the logo.") < body.index(line)
    assert fetch.calls == []


# -- R4: a GitHub attachment ---------------------------------------------------------


def _payload(body: str) -> dict:
    return {
        "action": "created",
        "repository": {"full_name": "octo/repo"},
        "sender": {"login": "someone"},
        "issue": {"number": 416, "html_url": "https://github.com/octo/repo/issues/416"},
        "comment": {
            "body": body,
            "html_url": "https://github.com/octo/repo/issues/416#issuecomment-1",
        },
    }


def _routed(body: str) -> RoutedEvent:
    payload = _payload(body)
    return RoutedEvent(
        event="issue_comment",
        action="created",
        delivery_id="d-416",
        work_items=extract_work_items("issue_comment", payload),
        payload=payload,
    )


def _dispatcher(tmp_path: Path) -> Dispatcher:
    return Dispatcher(
        registry=SessionRegistry(tmp_path / "state" / "local"),
        adapters={},
        config=RoutingConfig(control=ControlConfig(require_start_command=False)),
        cli_config={"state": {"root": str(tmp_path / "state")}},
    )


ASSET = "https://github.com/user-attachments/assets/aaaa-1111"


def test_a_github_comments_screenshot_reaches_the_pane_as_a_path_after_the_excerpt(
    tmp_path, fetch
):
    """
    Scenario: a GitHub comment's screenshot reaches the pane as a path after the excerpt
      Given a comment whose body carries an asset URL and a GitHub token in the environment
      When the dispatcher renders the event prompt
      Then the asset is fetched with the token against GitHub's hosts
      And the prompt ends with the Attachments section, after the excerpt's closing fence
      And the excerpt itself is unchanged
    """
    dispatcher = _dispatcher(tmp_path)
    prompt = dispatcher._render_prompt(
        _routed(f"looks like this ![shot]({ASSET})"),
        WorkItemRef.parse(REF),
        dispatcher._event_template,
    )
    assert fetch.calls == [(ASSET, "ghp-test", tuple(attachments_mod.GITHUB_HOSTS))]
    saved = tmp_path / "state" / "local" / "attachments" / SLUG / "aaaa-1111.png"
    assert saved.read_bytes() == b"png-bytes"
    fence, section = prompt.rsplit("```\n", 1)
    assert "Attachments" not in fence and ASSET in fence
    assert section.startswith("\nAttachments (1)")
    assert (
        f"1. image · aaaa-1111.png (image/png, 9 B) — saved at {saved} — {ASSET}"
        in section
    )


def test_a_private_asset_with_no_token_is_named_not_fetched(
    tmp_path, fetch, monkeypatch
):
    """
    Scenario: a private asset with no token is named, not fetched
      Given no GitHub token in the environment and an asset that refuses an anonymous request
      When the dispatcher renders the event prompt
      Then the request was anonymous, the section names the URL with the reason
      And it tells the session it may try the URL itself
    """
    monkeypatch.delenv("GH_TOKEN")
    fetch.state["fail"] = FetchError("transfer-failed", "HTTP 404")
    dispatcher = _dispatcher(tmp_path)
    prompt = dispatcher._render_prompt(
        _routed(f"see {ASSET}"), WorkItemRef.parse(REF), dispatcher._event_template
    )
    assert fetch.calls[0][1] == ""
    assert (
        f"not fetched: the transfer failed — {ASSET} (you may try the URL yourself)"
        in prompt
    )


def test_an_asset_seen_again_is_reused_from_disk(tmp_path, fetch):
    """
    Scenario: an asset seen again is reused from disk
      Given an asset the dispatcher already fetched for this work item
      When another event carries the same URL
      Then no request is made and the same path is named
    """
    dispatcher = _dispatcher(tmp_path)
    first = dispatcher._render_prompt(
        _routed(f"![a]({ASSET})"), WorkItemRef.parse(REF), dispatcher._event_template
    )
    second = dispatcher._render_prompt(
        _routed(f"again ![a]({ASSET})"),
        WorkItemRef.parse(REF),
        dispatcher._event_template,
    )
    assert len(fetch.calls) == 1
    assert "aaaa-1111.png" in first and "aaaa-1111.png" in second


def test_a_prompt_without_attachments_is_unchanged(tmp_path, fetch):
    """
    Scenario: a prompt whose event carries no attachment is byte-identical to before
      When the dispatcher renders an ordinary comment
      Then no fetch is made and the prompt ends with the excerpt's closing fence
    """
    dispatcher = _dispatcher(tmp_path)
    prompt = dispatcher._render_prompt(
        _routed("just words"), WorkItemRef.parse(REF), dispatcher._event_template
    )
    assert (
        fetch.calls == [] and "Attachments" not in prompt and prompt.endswith("```\n")
    )


# -- R5: the scope ------------------------------------------------------------------


def test_the_manifest_declares_files_read():
    """
    Scenario: the manifest declares files:read
      Then the app the guide imports may read a file the bot can see
      And the guide's copy of the manifest says the same
    """
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    assert "files:read" in manifest["oauth_config"]["scopes"]["bot"]
    guide = Path(__file__).resolve().parents[2] / "docs" / "guide" / "slack.md"
    if guide.is_file():
        assert "files:read" in guide.read_text(encoding="utf-8")


def test_a_missing_files_read_is_one_finding_and_unreadable_scopes_are_none(tmp_path):
    """
    Scenario: a missing files:read is one finding; unreadable scopes are none
      Given the granted scopes, with and without files:read, and unreadable
      When the-loop measures them
      Then only the missing scope is a finding, naming the scope and the consequence
      And the probe appends it after the kind's and the mention's
    """
    assert attachment_findings(None) == ()
    assert attachment_findings(("chat:write", "files:read")) == ()
    (finding,) = attachment_findings(("chat:write",))
    assert "files:read" in finding and "named" in finding and "manifest" in finding
    client = FakeProbeClient(
        info={"id": "C123", "is_channel": True},
        scopes="chat:write,channels:history,app_mentions:read",
    )
    result = probe_subscription(
        parsed(tmp_path, channel="C123"), client_factory=lambda token: client
    )
    assert [f for f in result["findings"] if "files:read" in f] == [finding]
    state = _state_with_stores(tmp_path / "state" / "channels" / "slack.json")
    assert state.cursors == {}
