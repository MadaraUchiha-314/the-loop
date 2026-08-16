"""Unit tests for the shared redaction pass (issue-242).

``redact.scrub`` is defense-in-depth beneath the self-diagnosis dossier's field
allow-list: the allow-list decides which fields exist, ``scrub`` cleans the free
text that survives. ``defang_control_keywords`` guarantees the composed issue
body can never carry a parseable control command (R6.2).
"""

from the_loop.control import ControlConfig, parse_command
from the_loop.redact import defang_control_keywords, scrub

HOME = "/home/loopuser"
KW = {"home": HOME, "user": "loopuser", "host": "loop-box.internal", "env": {}}


def test_home_directory_and_username_are_masked():
    text = f"cwd {HOME}/proj failed for loopuser"
    out = scrub(text, **KW)
    assert HOME not in out
    assert "loopuser" not in out


def test_absolute_and_tilde_paths_are_masked():
    out = scrub("open /opt/secret/place and ~/notes.txt failed", **KW)
    assert "/opt/secret/place" not in out
    assert "~/notes.txt" not in out
    assert "<redacted:path>" in out


def test_windows_paths_are_masked():
    out = scrub(r"read C:\Users\bob\cfg.ini failed", **KW)
    assert "bob" not in out


def test_urls_survive_path_masking():
    url = "https://github.com/MadaraUchiha-314/the-loop/issues/240"
    assert url in scrub(f"see {url} for details", **KW)


def test_hostname_and_email_are_masked():
    out = scrub("host loop-box.internal mailed ops@example.com", **KW)
    assert "loop-box.internal" not in out
    assert "ops@example.com" not in out


def test_token_shaped_strings_are_masked():
    token = "ghp_a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6"
    out = scrub(f"auth used {token} here", **KW)
    assert token not in out
    assert "<redacted:token>" in out


def test_ordinary_long_words_are_not_masked():
    text = "an internationalization-misconfiguration happened"
    assert scrub(text, **KW) == text


def test_sensitive_env_values_are_masked_by_value():
    env = {"MY_API_TOKEN": "supersecretvalue", "PATH": "/usr/bin:/bin"}
    out = scrub(
        "request sent supersecretvalue upstream",
        env=env,
        home=HOME,
        user="loopuser",
        host="h",
    )
    assert "supersecretvalue" not in out


def test_non_sensitive_env_names_are_not_value_scanned():
    # LANG's value is a plain locale string; masking every occurrence of "C"
    # would destroy the text. Only sensitive-NAMED variables are value-scanned.
    env = {"LANG": "C"}
    assert scrub("C is a language", env=env, home=HOME, user="u", host="h") == (
        "C is a language"
    )


def test_short_env_values_are_never_masked():
    env = {"A_SECRET": "ab"}  # < 6 chars: masking would eat the alphabet
    assert "ab" in scrub("absolutely", env=env, home=HOME, user="u", host="h")


# --------------------------------------------------------------- defang


def _parses(body: str) -> bool:
    return bool(parse_command(body, ControlConfig(enabled=True)))


def test_defanged_start_keyword_no_longer_parses():
    body = "then run the-loop start to resume"
    assert _parses(body)  # sanity: the raw body would arm
    out = defang_control_keywords(body, ["the-loop start"])
    assert not _parses(out)
    assert "the-loop" in out and "start" in out  # still readable


def test_defang_is_case_insensitive():
    out = defang_control_keywords("Then The-Loop START it", ["the-loop start"])
    assert not _parses(out)


def test_defang_handles_spaceless_keywords():
    out = defang_control_keywords("say goloop now", ["goloop"])
    assert "goloop" not in out


def test_defang_leaves_unrelated_text_alone():
    text = "restart the loop of tests, then start over"
    assert defang_control_keywords(text, ["the-loop start"]) == text
