"""The one resolver for "which GitHub" (issue-311, R1).

Five tiers, one grammar. Most of these cases pin the *order* and the *refusals*:
the failure mode this function must never have is interpolating a string that is
not a host into a ``--hostname`` argument or a URL, and the second-worst is
letting a checkout's remote outrank what the operator wrote down.
"""

from __future__ import annotations

import logging

import pytest

from the_loop.ghhost import (
    api_base_for,
    github_host,
    host_from_remote,
    host_of_api_base,
)
from the_loop.sessions import DEFAULT_GITHUB_HOST, is_github_host

GHE = "ghe.corp.example"


def _cfg(host="", base_url=""):
    github = {}
    if host:
        github["host"] = host
    if base_url:
        github["api"] = {"baseUrl": base_url}
    return {"integrations": {"github": github}}


# -- the tiers, in order --------------------------------------------------------


def test_nothing_configured_means_github_com():
    assert github_host({}, env={}) == DEFAULT_GITHUB_HOST
    assert github_host(None, env={}) == DEFAULT_GITHUB_HOST


def test_the_explicit_key_wins_over_everything():
    host = github_host(
        _cfg(host=GHE, base_url="https://other.example/api/v3"),
        env={"GH_HOST": "third.example"},
        remote_url="git@fourth.example:o/r.git",
    )
    assert host == GHE


def test_an_enterprise_api_base_outranks_gh_host():
    host = github_host(
        _cfg(base_url="https://ghe.corp.example/api/v3"), env={"GH_HOST": "x.example"}
    )
    assert host == GHE


def test_the_public_api_base_is_not_an_answer():
    """The shipped default — `https://api.github.com` — says nothing about an
    enterprise host, so the walk continues to gh's own answer."""
    host = github_host(_cfg(base_url="https://api.github.com"), env={"GH_HOST": GHE})
    assert host == GHE


def test_gh_host_outranks_the_remote():
    host = github_host({}, env={"GH_HOST": GHE}, remote_url="git@x.example:o/r.git")
    assert host == GHE


def test_the_remote_is_the_last_answer_before_the_default():
    assert github_host({}, env={}, remote_url=f"git@{GHE}:octo/repo.git") == GHE
    assert github_host({}, env={}, remote_url="") == DEFAULT_GITHUB_HOST


def test_the_remote_is_read_only_when_a_root_is_given(tmp_path, monkeypatch):
    """A4: tier (d) is the graph's own session, never the daemon's."""
    calls = []

    def fake_remote(root):
        calls.append(root)
        return f"https://{GHE}/o/r.git"

    monkeypatch.setattr("the_loop.ghhost._origin_remote", fake_remote)
    assert github_host({}, env={}) == DEFAULT_GITHUB_HOST
    assert calls == []
    assert github_host({}, env={}, repo_root=tmp_path) == GHE
    assert calls == [tmp_path]


def test_a_github_com_remote_is_the_default_unwritten():
    assert (
        github_host({}, env={}, remote_url="git@github.com:o/r.git")
        == DEFAULT_GITHUB_HOST
    )


# -- refusals (R1.2, A1) --------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "https://ghe.corp.example",  # a scheme
        "ghe.corp.example/api/v3",  # a path
        "user@ghe.corp.example",  # credentials
        "ghe corp example",  # whitespace
        "ghe",  # not dotted, no port: not recognisable as a host
        "--hostname",  # an argv fragment
    ],
)
def test_an_invalid_configured_host_is_skipped_with_a_warning(bad, caplog):
    caplog.set_level(logging.WARNING, logger="the-loop.ghhost")
    assert github_host(_cfg(host=bad), env={"GH_HOST": GHE}) == GHE
    assert any("integrations.github.host" in r.message for r in caplog.records)


def test_an_invalid_gh_host_is_skipped_too():
    assert (
        github_host({}, env={"GH_HOST": "not a host"}, remote_url=f"https://{GHE}/o/r")
        == GHE
    )


def test_a_port_is_a_host_shape():
    assert github_host(_cfg(host="ghe.corp.example:8443"), env={}) == (
        "ghe.corp.example:8443"
    )


def test_a_configured_github_com_is_the_default():
    assert github_host(_cfg(host="github.com"), env={}) == DEFAULT_GITHUB_HOST


def test_the_tier_is_logged(caplog):
    caplog.set_level(logging.DEBUG, logger="the-loop.ghhost")
    github_host(_cfg(host=GHE), env={})
    assert any(
        GHE in r.message and "integrations.github.host" in r.message
        for r in caplog.records
    )


# -- the helpers ----------------------------------------------------------------


@pytest.mark.parametrize(
    "url, host",
    [
        ("https://ghe.corp.example/octo/repo.git", GHE),
        ("http://ghe.corp.example/git/octo/repo", GHE),
        ("ssh://git@ghe.corp.example/octo/repo", GHE),
        ("ssh://git@ghe.corp.example:2222/octo/repo", "ghe.corp.example:2222"),
        ("git@ghe.corp.example:octo/repo.git", GHE),
        ("git@github.com:octo/repo.git", "github.com"),
        ("/srv/git/octo/repo.git", ""),  # a local path has no host
        ("octo/repo", ""),
        ("", ""),
    ],
)
def test_host_from_remote_reads_every_shape_a_checkout_carries(url, host):
    assert host_from_remote(url) == host


@pytest.mark.parametrize(
    "base, host",
    [
        ("https://api.github.com", ""),
        ("https://api.github.com/", ""),
        ("", ""),
        ("https://ghe.corp.example/api/v3", GHE),
        ("https://ghe.corp.example/api/v3/", GHE),
        ("https://ghe.corp.example", GHE),
        ("not a url", ""),
    ],
)
def test_host_of_api_base(base, host):
    assert host_of_api_base(base) == host


def test_api_base_for_derives_the_enterprise_shape():
    assert api_base_for(DEFAULT_GITHUB_HOST) == "https://api.github.com"
    assert api_base_for("") == "https://api.github.com"
    assert api_base_for(GHE) == f"https://{GHE}/api/v3"


def test_is_github_host_is_the_refs_own_grammar():
    assert is_github_host("ghe.corp.example")
    assert is_github_host("ghe.corp.example:8443")
    assert is_github_host("ghe:8443")
    assert not is_github_host("ghe")
    assert not is_github_host("https://ghe.corp.example")
    assert not is_github_host("")
