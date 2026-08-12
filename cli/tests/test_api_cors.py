"""Resolution and validation of the `service.cors` block (issue-211, T1/T8).

The block decides which browser **origin** may read the control plane's responses —
never who may connect, which stays `service.host`/`service.exposed`'s question. These
tests pin the defaults an operator gets with no configuration at all, and the one
combination the service refuses to serve.
"""

import pytest

from the_loop.api.config import DEFAULT_ALLOWED_ORIGINS, cors_config


def test_defaults_admit_the_published_dashboard_and_nothing_else():
    """
    Feature: the hosted dashboard works out of the box
      Scenario: no service.cors block is configured
        Given a CLI config with no cors block
        When the CORS config resolves
        Then exactly the-loop's own Pages origin is allowed, with the methods
             and headers the dashboard sends, and no credentials

    Requirement: docs/specs/issue-211/requirements.md R2.1, R2.2, R3.4
    """
    conf = cors_config({})
    assert conf["allowOrigins"] == ["https://madarauchiha-314.github.io"]
    assert conf["allowOrigins"] == list(DEFAULT_ALLOWED_ORIGINS)
    assert conf["allowMethods"] == ["GET", "POST", "OPTIONS"]
    assert conf["allowHeaders"] == ["Accept", "Content-Type"]
    assert conf["allowCredentials"] is False
    assert conf["allowPrivateNetwork"] is True


def test_the_default_origin_is_an_origin_not_a_url():
    """A browser sends scheme+host+port; a path here would match nothing."""
    (origin,) = DEFAULT_ALLOWED_ORIGINS
    assert origin == "https://madarauchiha-314.github.io"
    assert not origin.endswith("/")
    assert origin.count("/") == 2


def test_an_empty_origin_list_is_the_off_switch():
    """
    Feature: cross-origin access is opt-out-able
      Scenario: the operator sets an empty origin list
        Given service.cors.allowOrigins is []
        When the CORS config resolves
        Then no origin is allowed — the caller installs no middleware

    Requirement: docs/specs/issue-211/requirements.md R2.4
    """
    assert (
        cors_config({"service": {"cors": {"allowOrigins": []}}})["allowOrigins"] == []
    )


def test_configured_values_win_key_by_key():
    conf = cors_config(
        {
            "service": {
                "cors": {
                    "allowOrigins": ["https://ops.example.com"],
                    "allowHeaders": ["Accept", "Content-Type", "Authorization"],
                    "allowCredentials": True,
                    "allowPrivateNetwork": False,
                }
            }
        }
    )
    assert conf["allowOrigins"] == ["https://ops.example.com"]
    assert "Authorization" in conf["allowHeaders"]
    assert conf["allowCredentials"] is True
    assert conf["allowPrivateNetwork"] is False
    # Untouched keys keep their defaults rather than emptying out.
    assert conf["allowMethods"] == ["GET", "POST", "OPTIONS"]


def test_a_scalar_origin_is_one_origin_not_a_string_of_characters():
    """A hand-edited `allowOrigins: https://x` must not become 9 single-char origins."""
    conf = cors_config(
        {"service": {"cors": {"allowOrigins": "https://ops.example.com"}}}
    )
    assert conf["allowOrigins"] == ["https://ops.example.com"]


def test_a_nonsense_scalar_resolves_rather_than_raising():
    """The CLI config is loaded without schema validation, so a hand-edited
    `allowOrigins: 8787` must not raise a TypeError past `serve`'s ValueError
    handler. It resolves to one origin that matches nothing."""
    conf = cors_config({"service": {"cors": {"allowOrigins": 8787}}})
    assert conf["allowOrigins"] == ["8787"]


def test_wildcard_with_credentials_is_refused():
    """
    Feature: an unsafe CORS configuration fails closed
      Scenario: every origin is allowed to send credentials
        Given allowOrigins contains "*" and allowCredentials is true
        When the CORS config resolves
        Then it raises, naming both keys — the service will not serve it

    Requirement: docs/specs/issue-211/requirements.md R3.1
    """
    with pytest.raises(ValueError) as excinfo:
        cors_config(
            {"service": {"cors": {"allowOrigins": ["*"], "allowCredentials": True}}}
        )
    message = str(excinfo.value)
    assert "allowOrigins" in message and "allowCredentials" in message


def test_wildcard_without_credentials_is_the_operators_call():
    """`"*"` alone is permissive, not incoherent — it is documented, not blocked."""
    conf = cors_config({"service": {"cors": {"allowOrigins": ["*"]}}})
    assert conf["allowOrigins"] == ["*"]
