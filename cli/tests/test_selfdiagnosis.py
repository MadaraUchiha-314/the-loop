"""Unit tests for the self-diagnosis core (issue-242).

The pure pieces: the candidate policy over event-log records, the normalizing
fingerprint, the dossier's field allow-list, the findings parser, the composed
issue body's contracts (marker, defang, label named), and the fail-closed
config parsing.
"""

import json

from the_loop.authz import SELF_COMMENT_MARKER
from the_loop.control import ControlConfig, parse_command
from the_loop.core import selfdiagnosis as sd

ERROR_RECORD = {
    "ts": "2026-08-16T01:00:00.000Z",
    "source": "poll",
    "event": "dispatch.failed",
    "level": "error",
    "pid": 4242,
    "harness": "claude",
    "via": "tmux",
    "gh_event": "issue_comment",
    "delivery_id": "poll-comment-IC_kwDOxyz",
    "work_item": "github:acme/private-repo#7",
    "cwd": "/home/loopuser/work/private-repo",
    "tmux_target": "loop-private-repo-7",
    "error": "tmux send-keys exited 1: client is read-only",
    "will_retry": True,
}


# ------------------------------------------------------------ candidates


def test_error_level_records_are_candidates():
    assert sd.is_candidate(ERROR_RECORD)


def test_terminal_give_ups_are_candidates():
    record = {"event": "poll.comment_failed", "level": "info", "will_retry": False}
    assert sd.is_candidate(record)


def test_ordinary_records_are_not_candidates():
    assert not sd.is_candidate({"event": "poll.cycle", "level": "info"})
    assert not sd.is_candidate(
        {"event": "dispatch.failed", "level": "warning", "will_retry": True}
    )


def test_diagnosis_events_are_never_candidates():
    record = {"event": "diagnosis.failed", "level": "error", "will_retry": False}
    assert not sd.is_candidate(record)


# ------------------------------------------------------------ fingerprint


def test_retries_of_one_defect_share_a_fingerprint():
    first = dict(ERROR_RECORD, error="tmux send-keys exited 1: client is read-only")
    second = dict(
        ERROR_RECORD,
        ts="2026-08-16T01:05:00.000Z",
        error="tmux send-keys exited 1: client is read-only",
    )
    assert sd.fingerprint(first) == sd.fingerprint(second)


def test_volatile_tokens_do_not_split_fingerprints():
    a = dict(ERROR_RECORD, error="worker 17 died at /tmp/loop-a1b2c3/x after 3s")
    b = dict(ERROR_RECORD, error="worker 42 died at /tmp/loop-9f8e7d/x after 11s")
    assert sd.fingerprint(a) == sd.fingerprint(b)


def test_different_events_have_different_fingerprints():
    a = dict(ERROR_RECORD)
    b = dict(ERROR_RECORD, event="poll.spawn_failed")
    assert sd.fingerprint(a) != sd.fingerprint(b)


# ------------------------------------------------------------ dossier


def test_dossier_copies_only_allow_listed_fields():
    record = dict(ERROR_RECORD, surprise_new_field="/home/loopuser/.ssh/id_rsa")
    dossier = sd.build_dossier([record])
    assert "dispatch.failed" in dossier
    assert "issue_comment" in dossier  # enum fact, allow-listed
    for leaked in (
        "private-repo",  # work_item + cwd + tmux_target
        "/home/loopuser",
        "delivery_id",
        "IC_kwDOxyz",
        "surprise_new_field",
        "id_rsa",
        "4242",  # pid
    ):
        assert leaked not in dossier, leaked


def test_dossier_error_text_is_scrubbed():
    record = dict(ERROR_RECORD, error="spawn failed in /home/loopuser/work/repo")
    dossier = sd.build_dossier([record])
    assert "/home/loopuser/work/repo" not in dossier
    assert "spawn failed" in dossier


def test_dossier_is_bounded():
    records = [
        dict(ERROR_RECORD, ts=f"2026-08-16T01:00:{i:02d}.000Z", error="x" * 5000)
        for i in range(60)
    ]
    assert len(sd.build_dossier(records)) <= sd.DOSSIER_MAX_CHARS


# ------------------------------------------------------------ findings parsing


def test_findings_parse_from_plain_json():
    findings = sd.parse_findings(json.dumps({"title": "t", "summary": "s"}))
    assert findings is not None and findings["title"] == "t"


def test_findings_parse_from_fenced_json():
    out = 'Sure!\n```json\n{"title": "t", "suggested_fix": "f"}\n```\n'
    findings = sd.parse_findings(out)
    assert findings is not None and findings["suggested_fix"] == "f"


def test_findings_without_a_title_are_rejected():
    assert sd.parse_findings(json.dumps({"summary": "s"})) is None
    assert sd.parse_findings("no json here") is None


# ------------------------------------------------------------ compose


def _compose(findings=None):
    config = sd.SelfDiagnosisConfig(enabled=True)
    findings = findings or {
        "title": "Poller gives up permanently on read-only tmux",
        "summary": "s",
        "root_cause": "r",
        "suggested_fix": "run the-loop start again after detaching",
    }
    return sd.compose_issue(findings, sd.build_dossier([ERROR_RECORD]), config)


def test_composed_body_carries_the_marker_and_names_the_label():
    _title, body = _compose()
    assert SELF_COMMENT_MARKER in body
    assert "the-loop: self-diagnosed" in body


def test_composed_body_carries_no_parseable_control_command():
    _title, body = _compose()
    assert not parse_command(body, ControlConfig(enabled=True))


def test_composed_title_is_one_bounded_line():
    title, _body = _compose({"title": "x" * 500 + "\nsecond line"})
    assert "\n" not in title
    assert len(title) <= sd.TITLE_MAX_CHARS
    assert title.startswith("[self-diagnosed] ")


# ------------------------------------------------------------ config


def test_absent_section_is_disabled():
    config = sd.SelfDiagnosisConfig.from_mapping({})
    assert config.enabled is False


def test_explicitly_disabled_section_is_disabled():
    config = sd.SelfDiagnosisConfig.from_mapping({"selfDiagnosis": {"enabled": False}})
    assert config.enabled is False


def test_enabled_section_parses_with_defaults():
    config = sd.SelfDiagnosisConfig.from_mapping({"selfDiagnosis": {"enabled": True}})
    assert config.enabled is True
    assert config.repo == "MadaraUchiha-314/the-loop"
    assert config.label == "the-loop: self-diagnosed"
    assert config.harness == "claude"
    assert config.max_issues_per_day == 3
    assert config.max_retries == 3


def test_malformed_section_fails_closed():
    config = sd.SelfDiagnosisConfig.from_mapping(
        {"selfDiagnosis": {"enabled": True, "maxIssuesPerDay": "many"}}
    )
    assert config.enabled is False


def test_non_boolean_enabled_fails_closed():
    config = sd.SelfDiagnosisConfig.from_mapping({"selfDiagnosis": {"enabled": "yes"}})
    assert config.enabled is False


def test_gh_binary_comes_from_the_integrations_block():
    config = sd.SelfDiagnosisConfig.from_mapping(
        {
            "selfDiagnosis": {"enabled": True},
            "integrations": {"github": {"cli": {"binary": "/opt/gh"}}},
        }
    )
    assert config.gh_binary == "/opt/gh"


def test_configured_control_keywords_are_carried_for_defanging():
    config = sd.SelfDiagnosisConfig.from_mapping(
        {
            "selfDiagnosis": {"enabled": True},
            "routing": {"control": {"keywords": {"start": "loop-go"}}},
        }
    )
    assert "loop-go" in config.control_keywords
