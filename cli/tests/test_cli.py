"""Unit tests for the the-loop CLI. Run with: pytest (from the cli/ directory)."""

import hashlib
import hmac
import json
from pathlib import Path

import pytest

from the_loop.cli import build_parser, main
from the_loop.commands import iter_commands
from the_loop.scenarios import collect_scenarios, extract_from_text
from the_loop.webhook import verify_signature, make_handler

FIXTURES = Path(__file__).parent / "fixtures"


def test_gh_webhook_is_registered():
    names = {c.name for c in iter_commands()}
    assert "gh-webhook" in names


def test_parser_builds_and_lists_subcommands():
    parser = build_parser()
    # gh-webhook start should parse with its defaults
    args = parser.parse_args(["gh-webhook", "start"])
    assert args.command == "gh-webhook"
    assert args.action == "start"
    assert args.port == 8787
    assert hasattr(args, "_handler")


def test_version_exits_zero():
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0


def test_version_matches_installed_package_metadata():
    """Regression for issue #78: `--version` must report the installed package
    version derived from metadata, not a hardcoded string that silently froze
    at 0.1.0 while releases advanced."""
    from importlib.metadata import version

    import the_loop

    assert the_loop.__version__ == version("the-loopy-one")
    assert the_loop.__version__ != "0.1.0"


def test_version_output_carries_package_version(capsys):
    """The `--version` flag prints `the-loop <version>` using the derived
    version, so the reported string tracks the installed package."""
    import the_loop

    with pytest.raises(SystemExit):
        main(["--version"])
    out = capsys.readouterr().out
    assert out.strip() == f"the-loop {the_loop.__version__}"


def test_missing_command_errors():
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code != 0


def test_verify_signature_none_without_secret():
    assert verify_signature(None, b"body", "sha256=whatever") is None


def test_verify_signature_roundtrip():
    secret = "s3cret"
    body = b'{"hello":"world"}'
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    good = "sha256=" + digest
    assert verify_signature(secret, body, good) is True
    assert verify_signature(secret, body, "sha256=deadbeef") is False
    assert verify_signature(secret, body, None) is False


def test_make_handler_returns_class():
    handler = make_handler(path="/gh-webhook", secret=None)
    assert isinstance(handler, type)


# -- scenarios command -------------------------------------------------------


def test_scenarios_is_registered():
    names = {c.name for c in iter_commands()}
    assert "scenarios" in names


def test_extract_python_docstring_scenarios():
    text = (
        '"""\n'
        "Feature: Checkout pricing\n"
        "Requirement: docs/specs/issue-11/requirements.md#R2\n"
        "\n"
        "Scenario: Cart total includes regional tax\n"
        "    Given a cart with one $10.00 item\n"
        "    When priced in a 10% tax region\n"
        "    Then the total is $11.00\n"
        '"""\n'
    )
    scenarios = extract_from_text(text, file="t.py")
    assert len(scenarios) == 1
    s = scenarios[0]
    assert s.feature == "Checkout pricing"
    assert s.scenario == "Cart total includes regional tax"
    assert s.requirement == "docs/specs/issue-11/requirements.md#R2"
    assert len(s.steps) == 3


def test_extract_js_block_comment_and_requirement_after_scenario():
    text = (
        "/*\n"
        " * Feature: Auth\n"
        " * Scenario: Login with a valid token\n"
        " *   Requirement: docs/specs/issue-11/requirements.md#R1\n"
        " *   Given a valid token\n"
        " *   Then access is granted\n"
        " */\n"
    )
    scenarios = extract_from_text(text)
    assert len(scenarios) == 1
    assert scenarios[0].feature == "Auth"
    assert scenarios[0].requirement.endswith("#R1")


def test_feature_carries_across_scenarios():
    text = "Feature: Wallet\nScenario: A\n  Given x\nScenario: B\n  Then y\n"
    scenarios = extract_from_text(text)
    assert [s.scenario for s in scenarios] == ["A", "B"]
    assert all(s.feature == "Wallet" for s in scenarios)


def test_collect_scenarios_from_fixture():
    scenarios = collect_scenarios(FIXTURES, ["*integration*.py"], display_root=FIXTURES)
    titles = {s.scenario for s in scenarios}
    assert "Cart total includes regional tax" in titles
    assert "Free shipping over the threshold" in titles


def test_scenarios_command_json_output(capsys):
    rc = main(
        [
            "scenarios",
            "--root",
            str(FIXTURES),
            "--glob",
            "*integration*.py",
            "--format",
            "json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert any(
        item["scenario"] == "Cart total includes regional tax" for item in payload
    )


def test_scenarios_command_table_output(capsys):
    rc = main(["scenarios", "--root", str(FIXTURES), "--glob", "*integration*.py"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Feature" in out and "Scenario" in out
    assert "Checkout pricing" in out
