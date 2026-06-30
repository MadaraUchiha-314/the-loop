"""Unit tests for the the-loop CLI. Run with: pytest (from the cli/ directory)."""

import hashlib
import hmac

import pytest

from the_loop.cli import build_parser, main
from the_loop.commands import iter_commands
from the_loop.webhook import verify_signature, make_handler


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
    handler = make_handler(path="/webhook", secret=None)
    assert isinstance(handler, type)
