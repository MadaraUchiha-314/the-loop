"""Unit tests for issue-416: a file a person attached is fetched and forwarded,
never interpreted. Spec: docs/specs/issue-416/{requirements,design,testing-plan}.md
(T1, T8). Everything here is offline — the one network call takes a fake opener,
and the module-level test pins that the real one is never built.
"""

from __future__ import annotations

import io
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path

import pytest

from the_loop.channels import attachments as mod
from the_loop.channels.attachments import (
    GITHUB_HOSTS,
    MAX_BYTES,
    MAX_FILES,
    SLACK_HOSTS,
    TRANSCRIPT_RETRIES,
    Attachment,
    FetchError,
    fetch_url,
    github_attachment_urls,
    github_attachments,
    kind_of,
    record_lines,
    render_section,
    safe_name,
    slack_attachments,
    vtt_to_text,
)

PERMALINK = "https://x.slack.com/files/UHUMAN/F0IMG/shot.png"
PRIVATE = "https://files.slack.com/files-pri/T0-F0IMG/download/shot.png"


# -- doubles ---------------------------------------------------------------------------


class _Response:
    """What ``opener.open`` returns: a status, headers and a readable body."""

    def __init__(
        self, body: bytes, content_type="application/octet-stream", status=200
    ):
        self.status = status
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        self._body = io.BytesIO(body)

    def read(self, n=-1):
        return self._body.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    """A ``urllib`` opener double: ``routes`` maps a URL to a response, a
    redirect target (``("redirect", url)``) or an exception; ``requests``
    records every request made, header and all."""

    def __init__(self, routes):
        self.routes = routes
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        route = self.routes[request.full_url]
        if isinstance(route, Exception):
            raise route
        if isinstance(route, tuple) and route[0] == "redirect":
            headers = Message()
            headers["Location"] = route[1]
            raise urllib.error.HTTPError(
                request.full_url, 302, "Found", headers, io.BytesIO(b"")
            )
        return route


class _fetch_recorder:
    """A ``fetch`` double for ``slack_attachments`` / ``github_attachments``:
    records ``(url, credential, allowed_hosts, max_bytes)`` and answers with the
    same bytes for every URL — or raises ``fail``."""

    def __init__(self, content=b"png-bytes", content_type="image/png", fail=None):
        self.content, self.content_type, self.fail = content, content_type, fail
        self.calls: list = []

    def __call__(
        self, url, *, credential="", allowed_hosts=(), max_bytes=MAX_BYTES, **_
    ):
        self.calls.append((url, credential, tuple(allowed_hosts), max_bytes))
        if self.fail is not None:
            raise self.fail
        return self.content_type, self.content


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


def _audio(status="complete", preview="make the button blue", vtt=True, **over):
    file = {
        "id": "F0AUD",
        "name": "audio_message.m4a",
        "mimetype": "audio/mp4",
        "subtype": "slack_audio",
        "size": 9,
        "permalink": "https://x.slack.com/files/UHUMAN/F0AUD/audio_message.m4a",
        "url_private_download": "https://files.slack.com/files-pri/T0-F0AUD/download/audio_message.m4a",
        "transcription": {
            "status": status,
            "locale": "en-US",
            "preview": {"content": preview, "has_more": False},
        },
    }
    if vtt:
        file["vtt"] = "https://files.slack.com/files-pri/T0-F0AUD/audio_message.vtt"
    file.update(over)
    return file


VTT = """WEBVTT

NOTE Slack transcript

1
00:00:00.000 --> 00:00:02.500
<v Dana>Please make the button blue,

2
00:00:02.500 --> 00:00:04.000
and move it left.
"""


# -- T1: pure helpers ------------------------------------------------------------------


def test_a_files_kind_and_safe_name_are_derived_from_its_metadata():
    """
    Scenario: a file's kind, safe name and saved path are derived from its metadata
      Given Slack's media type, or only a name, for a file
      When the-loop classifies it
      Then an image, an audio clip, a video, a PDF and anything else each get their kind
      And the name it is saved under is a plain file name
    """
    assert kind_of("image/png", "x") == "image"
    assert kind_of("audio/mp4", "x") == "audio"
    assert kind_of("video/quicktime", "x") == "video"
    assert kind_of("application/pdf", "x") == "pdf"
    assert kind_of("application/zip", "x") == "file"
    # No media type: the extension decides, and nothing else.
    assert kind_of("", "photo.JPG") == "image"
    assert kind_of("", "clip.m4a") == "audio"
    assert kind_of("", "notes.pdf") == "pdf"
    assert kind_of("", "notes") == "file"
    assert safe_name("shot.png") == "shot.png"
    assert safe_name("my screenshot (1).png") == "my screenshot (1).png"
    assert safe_name("") == "file"
    assert len(safe_name("a" * 200 + ".png")) <= 80


def test_a_hostile_name_stays_inside_the_directory():
    """
    Scenario: a hostile file name stays inside the work item's directory
      Given a file named with path separators, a parent reference, a control character
        and a leading dot
      When the-loop derives the saved name
      Then it is a bare file name with none of them
    """
    assert safe_name("../../etc/passwd") == "passwd"
    assert safe_name("..\\..\\boot.ini") == "boot.ini"
    assert safe_name("/tmp/evil.sh") == "evil.sh"
    assert safe_name(".bashrc") == "bashrc"
    assert safe_name("..") == "file"
    assert safe_name("a\x00b\nc.png") == "abc.png"
    assert "/" not in safe_name("x/y/z") and ".." not in safe_name("a..b")


def test_webvtt_captions_become_plain_text():
    """
    Scenario: WebVTT captions become plain text with cues stripped
      Given the captions file Slack produced for a voice clip
      When the-loop turns it into text
      Then the header, the note, the cue numbers, the timings and the voice tags are gone
      And the spoken text is one line in order
    """
    assert vtt_to_text(VTT) == "Please make the button blue, and move it left."
    assert vtt_to_text("") == ""
    assert vtt_to_text("WEBVTT\n") == ""
    # Slack repeats a cue's text when it splits a long line; consecutive
    # duplicates collapse.
    assert (
        vtt_to_text(
            "WEBVTT\n\n00:00.000 --> 00:01.000\nhello\n\n00:01.000 --> 00:02.000\nhello\n"
        )
        == "hello"
    )


def test_every_github_asset_url_shape_in_a_body_is_found_once():
    """
    Scenario: every GitHub asset URL shape in a body is found once
      Given a comment body carrying the four asset shapes, in markdown, HTML and bare
      When the-loop looks for attachments
      Then each URL is found once, in order, and an ordinary link is not
    """
    body = (
        "See ![shot](https://github.com/user-attachments/assets/aaaa-1111) and "
        '<img src="https://github.com/octo/repo/assets/12/bbbb-2222" width=300> '
        "then https://user-images.githubusercontent.com/12/cccc.png again "
        "![shot](https://github.com/user-attachments/assets/aaaa-1111) plus "
        "https://private-user-images.githubusercontent.com/12/dddd.jpg?jwt=abc "
        "but not https://github.com/octo/repo/issues/7 nor https://example.com/x.png"
    )
    assert github_attachment_urls(body) == [
        "https://github.com/user-attachments/assets/aaaa-1111",
        "https://github.com/octo/repo/assets/12/bbbb-2222",
        "https://user-images.githubusercontent.com/12/cccc.png",
        "https://private-user-images.githubusercontent.com/12/dddd.jpg?jwt=abc",
    ]
    assert github_attachment_urls("nothing here") == []
    # A GitHub Enterprise host is matched only when configured.
    ghe = "https://ghe.corp/user-attachments/assets/eeee"
    assert github_attachment_urls(ghe) == []
    assert github_attachment_urls(ghe, hosts=("ghe.corp",)) == [ghe]


# -- T1 / T8: the one fetch ------------------------------------------------------------


def test_the_credential_goes_only_to_an_allowed_host_and_a_redirect_within_it_is_followed():
    """
    Scenario: the fetch sends the credential to the allowed host and follows a
      redirect that stays inside the allowed set
      Given an asset URL that answers with a redirect to a signed githubusercontent URL
      When the-loop fetches it with the GitHub token
      Then both requests carry the bearer token
      And the bytes and the content type come back
    """
    signed = "https://objects-origin.githubusercontent.com/x?sig=1"
    opener = FakeOpener(
        {
            "https://github.com/user-attachments/assets/a1": ("redirect", signed),
            signed: _Response(b"png", "image/png"),
        }
    )
    content_type, data = fetch_url(
        "https://github.com/user-attachments/assets/a1",
        credential="ghp_test",
        allowed_hosts=GITHUB_HOSTS,
        opener=opener,
    )
    assert (content_type, data) == ("image/png", b"png")
    assert [r.get_header("Authorization") for r in opener.requests] == [
        "Bearer ghp_test",
        "Bearer ghp_test",
    ]


def test_a_file_url_off_slacks_host_is_not_fetched_and_gets_no_token():
    """
    Scenario: a file URL off Slack's host is not fetched and no token is sent
      Given a file object whose private URL names a host that is not Slack's
      When the-loop fetches the message's files
      Then no request is made at all
      And the file is named with the off-host reason
    """
    opener = FakeOpener({})
    with pytest.raises(FetchError) as caught:
        fetch_url(
            "https://evil.example/steal",
            credential="xoxb-secret",
            allowed_hosts=SLACK_HOSTS,
            opener=opener,
        )
    assert caught.value.reason == "off-host"
    assert opener.requests == []


def test_a_redirect_off_host_is_refused_with_the_credential_unsent():
    """
    Scenario: a redirect off the allowed hosts is refused with the credential unsent
      Given a Slack file URL that redirects to a host outside Slack's
      When the-loop fetches it
      Then the first request carried the token and the second was never made
      And the failure names the off-host reason
    """
    opener = FakeOpener({PRIVATE: ("redirect", "https://evil.example/collect")})
    with pytest.raises(FetchError) as caught:
        fetch_url(
            PRIVATE, credential="xoxb-secret", allowed_hosts=SLACK_HOSTS, opener=opener
        )
    assert caught.value.reason == "off-host"
    assert [r.full_url for r in opener.requests] == [PRIVATE]


def test_a_file_over_the_cap_is_not_saved():
    """
    Scenario: a file over the cap is not saved
      Given a file whose body is one byte over the cap
      When the-loop fetches it
      Then reading stops at the cap and the failure names it
    """
    opener = FakeOpener({PRIVATE: _Response(b"x" * 11, "image/png")})
    with pytest.raises(FetchError) as caught:
        fetch_url(PRIVATE, allowed_hosts=SLACK_HOSTS, max_bytes=10, opener=opener)
    assert caught.value.reason == "over-cap"
    # Exactly at the cap is fine.
    opener = FakeOpener({PRIVATE: _Response(b"x" * 10, "image/png")})
    assert (
        fetch_url(PRIVATE, allowed_hosts=SLACK_HOSTS, max_bytes=10, opener=opener)[1]
        == b"x" * 10
    )


def test_a_transfer_error_is_a_failure_with_its_reason():
    """
    Scenario: a transfer error is reported, never raised through the pipeline
      Given a host that answers 403, and one that cannot be reached
      When the-loop fetches
      Then each is a transfer-failed failure carrying the status or the error's class
    """
    forbidden = urllib.error.HTTPError(
        PRIVATE, 403, "Forbidden", Message(), io.BytesIO(b"")
    )
    opener = FakeOpener({PRIVATE: forbidden})
    with pytest.raises(FetchError) as caught:
        fetch_url(PRIVATE, allowed_hosts=SLACK_HOSTS, opener=opener)
    assert caught.value.reason == "transfer-failed" and "403" in caught.value.detail
    opener = FakeOpener({PRIVATE: urllib.error.URLError("unreachable")})
    with pytest.raises(FetchError) as caught:
        fetch_url(PRIVATE, allowed_hosts=SLACK_HOSTS, opener=opener)
    assert caught.value.reason == "transfer-failed"


def test_the_default_opener_never_follows_a_redirect_by_itself():
    """
    Scenario: the real opener is built without automatic redirects
      Given the opener the-loop builds when none is injected
      Then it carries no redirect handler that would re-send a credential unchecked
    """
    opener = mod._opener()
    handlers = getattr(opener, "handlers")
    assert not any(
        isinstance(h, urllib.request.HTTPRedirectHandler)
        and type(h) is urllib.request.HTTPRedirectHandler
        for h in handlers
    )


# -- T1: Slack files -------------------------------------------------------------------


def test_a_slack_image_is_saved_under_its_id_and_named_with_its_permalink(tmp_path):
    """
    Scenario: a Slack image is fetched with the bot token and saved under the work item
      Given a message file object for an image
      When the-loop fetches the message's files
      Then the download URL was fetched with the bot token against Slack's hosts
      And the file is saved as <id>-<name> in the destination
      And the attachment carries its kind, type, size, path and permalink
    """
    fetch = _fetch_recorder()
    (got,) = slack_attachments(
        [_image()], token="xoxb-t", dest_dir=tmp_path, fetch=fetch
    )
    assert fetch.calls == [(PRIVATE, "xoxb-t", tuple(SLACK_HOSTS), MAX_BYTES)]
    assert got.kind == "image" and got.mimetype == "image/png" and got.source == "slack"
    assert got.path == str(tmp_path / "F0IMG-shot.png")
    assert Path(got.path).read_bytes() == b"png-bytes"
    assert got.size == len(b"png-bytes") and got.link == PERMALINK and got.error == ""
    # Fetched once: the second read of the same message reuses the file.
    slack_attachments([_image()], token="xoxb-t", dest_dir=tmp_path, fetch=fetch)
    assert len(fetch.calls) == 1


def test_a_voice_note_carries_slacks_transcript_from_its_captions(tmp_path):
    """
    Scenario: a voice note carries Slack's own transcript
      Given an audio clip whose transcription is complete and whose captions URL is set
      When the-loop fetches the message's files
      Then the captions are fetched with the bot token and stripped to text
      And the attachment's transcript is that text, verbatim
    """
    calls = []

    def fetch(url, *, credential="", allowed_hosts=(), **_):
        calls.append(url)
        if url.endswith(".vtt"):
            return "text/vtt", VTT.encode()
        return "audio/mp4", b"m4a-bytes"

    (got,) = slack_attachments(
        [_audio()], token="xoxb-t", dest_dir=tmp_path, fetch=fetch
    )
    assert got.kind == "audio"
    assert got.transcript == "Please make the button blue, and move it left."
    assert calls[-1].endswith(".vtt")


def test_a_voice_note_falls_back_to_the_preview_when_the_captions_cannot_be_read(
    tmp_path,
):
    """
    Scenario: the preview is the transcript when the captions cannot be fetched
      Given an audio clip whose captions URL fails
      When the-loop fetches the message's files
      Then the transcript is Slack's preview text
    """

    def fetch(url, *, credential="", allowed_hosts=(), **_):
        if url.endswith(".vtt"):
            raise FetchError("transfer-failed", "500")
        return "audio/mp4", b"m4a"

    (got,) = slack_attachments(
        [_audio()], token="xoxb-t", dest_dir=tmp_path, fetch=fetch
    )
    assert got.transcript == "make the button blue" and got.error == ""


def test_a_processing_transcript_is_re_read_a_bounded_number_of_times(tmp_path):
    """
    Scenario: a processing transcript is re-read a bounded number of times
      Given an audio clip Slack is still transcribing when the message arrives
      When the-loop fetches the message's files
      Then files.info is re-read, with a wait between reads, until it completes
      And a clip that never completes is delivered without a transcript, after the cap
    """
    reads = []
    waits = []

    def files_info(file_id):
        reads.append(file_id)
        done = len(reads) >= 2
        return {"file": _audio(status="complete" if done else "processing", vtt=False)}

    (got,) = slack_attachments(
        [_audio(status="processing", vtt=False)],
        token="xoxb-t",
        dest_dir=tmp_path,
        fetch=_fetch_recorder(b"m4a", "audio/mp4"),
        files_info=files_info,
        sleep=waits.append,
    )
    assert got.transcript == "make the button blue"
    assert reads == ["F0AUD", "F0AUD"] and len(waits) == 2

    reads.clear()
    waits.clear()
    (got,) = slack_attachments(
        [_audio(status="processing", vtt=False)],
        token="xoxb-t",
        dest_dir=tmp_path,
        fetch=_fetch_recorder(b"m4a", "audio/mp4"),
        files_info=lambda file_id: (
            reads.append(file_id),
            {"file": _audio(status="processing", vtt=False)},
        )[1],
        sleep=waits.append,
    )
    assert got.transcript == "" and got.error == ""
    assert len(reads) == TRANSCRIPT_RETRIES and len(waits) == TRANSCRIPT_RETRIES
    # No files.info at hand (a poll read): one look at the object, no wait.
    (got,) = slack_attachments(
        [_audio(status="processing", vtt=False)],
        token="xoxb-t",
        dest_dir=tmp_path,
        fetch=_fetch_recorder(b"m4a", "audio/mp4"),
    )
    assert got.transcript == ""


def test_a_clip_slack_could_not_transcribe_has_no_transcript(tmp_path):
    """
    Scenario: a clip without a transcript is delivered as a saved file
      Given an audio clip whose transcription failed, and one with no transcription block
      When the-loop fetches the message's files
      Then each is saved and carries no transcript, and no error
    """
    for file in (
        _audio(status="failed", vtt=False),
        _audio(vtt=False, transcription=None),
    ):
        (got,) = slack_attachments(
            [file],
            token="xoxb-t",
            dest_dir=tmp_path,
            fetch=_fetch_recorder(b"m4a", "audio/mp4"),
        )
        assert got.transcript == "" and got.error == "" and got.path


def test_a_file_that_cannot_be_fetched_is_still_named_with_its_reason(tmp_path):
    """
    Scenario: a file that cannot be fetched is still named with its reason
      Given no bot token, a fetch that fails, a file over the cap, and a file off Slack's host
      When the-loop fetches the message's files
      Then each attachment is returned with its permalink and a fixed reason
      And nothing is saved for it
    """
    (got,) = slack_attachments(
        [_image()], token="", dest_dir=tmp_path, fetch=_fetch_recorder()
    )
    assert got.error == "no-token" and got.link == PERMALINK and got.path == ""
    (got,) = slack_attachments(
        [_image()],
        token="xoxb-t",
        dest_dir=tmp_path,
        fetch=_fetch_recorder(fail=FetchError("transfer-failed", "403")),
    )
    assert got.error == "transfer-failed" and got.path == ""
    fetch = _fetch_recorder()
    (got,) = slack_attachments(
        [_image(size=MAX_BYTES + 1)], token="xoxb-t", dest_dir=tmp_path, fetch=fetch
    )
    assert got.error == "over-cap" and fetch.calls == []
    (got,) = slack_attachments(
        [
            _image(
                url_private_download="https://evil.example/x",
                url_private="https://evil.example/x",
            )
        ],
        token="xoxb-t",
        dest_dir=tmp_path,
        fetch=_fetch_recorder(fail=FetchError("off-host", "evil.example")),
    )
    assert got.error == "off-host"
    assert list(tmp_path.iterdir()) == []


def test_files_past_the_cap_of_ten_are_named_not_fetched(tmp_path):
    """
    Scenario: files past the cap of ten are named, not fetched
      Given a message with twelve files
      When the-loop fetches them
      Then the first ten are fetched and the last two carry the too-many reason
    """
    fetch = _fetch_recorder()
    files = [_image(id=f"F{n:02d}", name=f"{n}.png") for n in range(12)]
    got = slack_attachments(files, token="xoxb-t", dest_dir=tmp_path, fetch=fetch)
    assert len(got) == 12 and len(fetch.calls) == MAX_FILES
    assert [a.error for a in got[MAX_FILES:]] == ["too-many", "too-many"]
    assert all(a.link for a in got)


# -- T1: GitHub assets -----------------------------------------------------------------


def test_a_github_asset_is_fetched_with_the_token_and_reused_on_a_second_sight(
    tmp_path,
):
    """
    Scenario: a GitHub asset is fetched with the token, named by its id, and reused
      Given an asset URL and a GitHub token
      When the-loop fetches it twice
      Then the first fetch carries the token against GitHub's hosts and saves the file
        with an extension from its content type
      And the second makes no request and returns the same path
    """
    fetch = _fetch_recorder()
    url = "https://github.com/user-attachments/assets/aaaa-1111"
    (got,) = github_attachments([url], token="ghp_t", dest_dir=tmp_path, fetch=fetch)
    assert fetch.calls == [(url, "ghp_t", tuple(GITHUB_HOSTS), MAX_BYTES)]
    assert got.source == "github" and got.link == url and got.kind == "image"
    assert got.path == str(tmp_path / "aaaa-1111.png") and got.name == "aaaa-1111.png"
    (again,) = github_attachments([url], token="ghp_t", dest_dir=tmp_path, fetch=fetch)
    assert again.path == got.path and len(fetch.calls) == 1


def test_a_github_asset_without_a_token_is_fetched_anonymously_and_a_failure_is_named(
    tmp_path,
):
    """
    Scenario: a private asset with no token is named, not fetched
      Given no GitHub token
      When the-loop fetches an asset that answers 404 to an anonymous request
      Then the request was made without a credential
      And the attachment carries the URL and the transfer-failed reason
    """
    fetch = _fetch_recorder(fail=FetchError("transfer-failed", "404"))
    url = "https://github.com/user-attachments/assets/private-1"
    (got,) = github_attachments([url], token="", dest_dir=tmp_path, fetch=fetch)
    assert fetch.calls[0][1] == ""
    assert got.error == "transfer-failed" and got.link == url and got.path == ""


def test_a_github_enterprise_host_joins_the_allowed_set_when_configured(tmp_path):
    """
    Scenario: a configured GitHub Enterprise host is an allowed destination
      Given an asset on ghe.corp and that host configured
      When the-loop fetches it
      Then the allowed hosts passed to the fetch include ghe.corp beside GitHub's
    """
    fetch = _fetch_recorder()
    url = "https://ghe.corp/user-attachments/assets/eeee"
    github_attachments(
        [url], token="t", dest_dir=tmp_path, hosts=("ghe.corp",), fetch=fetch
    )
    assert "ghe.corp" in fetch.calls[0][2] and set(GITHUB_HOSTS) <= set(
        fetch.calls[0][2]
    )


# -- T1 / T8: the two renderings -------------------------------------------------------


def _attachments():
    return [
        Attachment(
            name="shot.png",
            kind="image",
            mimetype="image/png",
            size=120 * 1024,
            source="slack",
            link=PERMALINK,
            path="/state/local/attachments/x/F0IMG-shot.png",
        ),
        Attachment(
            name="audio_message.m4a",
            kind="audio",
            mimetype="audio/mp4",
            size=80 * 1024,
            source="slack",
            link="https://x.slack.com/files/UHUMAN/F0AUD/audio_message.m4a",
            path="/state/local/attachments/x/F0AUD-audio_message.m4a",
            transcript="make the button blue",
        ),
        Attachment(
            name="big.zip",
            kind="file",
            mimetype="application/zip",
            size=40 * 1024 * 1024,
            source="slack",
            link="https://x.slack.com/files/UHUMAN/F0ZIP/big.zip",
            error="over-cap",
        ),
    ]


def test_the_section_names_kind_path_link_reason_and_frames_everything_as_untrusted():
    """
    Scenario: the section names kind, path, link, reason and frames everything untrusted
      Given an image, a voice note with a transcript and a file that was not fetched
      When the-loop renders the section the session reads
      Then it opens by saying what the files are, that an image or PDF is read with the
        session's own tool, that a transcript is Slack's, and that all of it is UNTRUSTED
      And each line carries the kind, the name, the type and size, the path or the reason,
        and the link
    """
    section = render_section(_attachments())
    head, *lines = section.splitlines()
    assert head.startswith("Attachments (3)")
    assert "file-reading tool" in section and "UNTRUSTED" in section
    assert "Slack's own" in section and "transcribes nothing" in section
    assert (
        "1. image · shot.png (image/png, 120 KB) — saved at /state/local/attachments/x/F0IMG-shot.png — "
        + PERMALINK
        in section
    )
    assert (
        "2. audio · audio_message.m4a (audio/mp4, 80 KB) — saved at /state/local/attachments/x/F0AUD-audio_message.m4a"
        in section
    )
    assert '   Slack\'s transcript: "make the button blue"' in section
    assert (
        "3. file · big.zip (application/zip, 40.0 MB) — not fetched: over the 25 MiB cap — https://x.slack.com/files/UHUMAN/F0ZIP/big.zip"
        in section
    )
    assert render_section([]) == ""


def test_a_github_section_tells_the_session_it_may_try_the_url_itself():
    """
    Scenario: a GitHub asset that was not fetched is named with the URL to try
      Given an asset the daemon could not fetch
      When the-loop renders the section
      Then the line names the reason and says the session may try the URL
    """
    url = "https://github.com/user-attachments/assets/private-1"
    section = render_section(
        [
            Attachment(
                name="private-1",
                kind="file",
                mimetype="",
                size=0,
                source="github",
                link=url,
                error="transfer-failed",
            )
        ]
    )
    assert (
        f"1. file · private-1 — not fetched: the transfer failed — {url} (you may try the URL yourself)"
        in section
    )
    assert "no token" in render_section(
        [
            Attachment(
                name="p",
                kind="file",
                mimetype="",
                size=0,
                source="github",
                link=url,
                error="no-token",
            )
        ]
    )


def test_the_record_lines_carry_the_permalink_and_the_transcript_never_a_path():
    """
    Scenario: the record lines carry the permalink and the transcript, never a path
      Given the same three attachments
      When the-loop renders the ledger's lines
      Then each is a 📎 line with the name, type, size and permalink
      And the transcript is quoted beneath its clip
      And no local path, download URL or reason-free omission appears
    """
    lines = record_lines(_attachments())
    assert lines.splitlines() == [
        f"📎 shot.png (image/png, 120 KB) — {PERMALINK}",
        "📎 audio_message.m4a (audio/mp4, 80 KB) — https://x.slack.com/files/UHUMAN/F0AUD/audio_message.m4a",
        "> Slack's transcript: make the button blue",
        "📎 big.zip (application/zip, 40.0 MB) — https://x.slack.com/files/UHUMAN/F0ZIP/big.zip (not fetched: over the 25 MiB cap)",
    ]
    assert "/state/" not in lines and "files-pri" not in lines
    assert record_lines([]) == ""
