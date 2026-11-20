"""Unit tests for the strict duration parser (issue-551, R6.5)."""

import pytest

from the_loop.durations import clamp, parse_duration


@pytest.mark.parametrize(
    "text,seconds",
    [("45s", 45), ("1s", 1), ("30m", 1800), ("2h", 7200), ("90m", 5400)],
)
def test_a_number_with_a_unit_is_seconds(text, seconds):
    """
    Feature: durations are a number with a unit
      Scenario: a session states how long it waits
        Given `45s`, `30m` or `2h`
        When the duration is parsed
        Then it is that many seconds

    Requirement: docs/specs/issue-551/requirements.md R6.5
    """
    assert parse_duration(text) == seconds


@pytest.mark.parametrize(
    "text",
    [
        "",
        "30",  # no unit
        "m",  # no number
        "0s",
        "0m",
        "00h",
        "-5m",
        "+5m",
        "1.5h",
        "1,5h",
        " 30m",
        "30m ",
        "30 m",
        "30m\n",
        "1h30m",
        "30M",
        "2d",  # the unit list is closed: s, m, h
        "30min",
        "٣٠m",  # digits other than 0-9
        "1e3s",
    ],
)
def test_anything_else_is_refused(text):
    """
    Feature: durations are parsed strictly
      Scenario: a duration is not `<positive integer><s|m|h>`
        Given text with whitespace, a decimal, a zero, a sign or another unit
        When the duration is parsed
        Then it is refused, and the message names the text and the accepted form

    Requirement: docs/specs/issue-551/design.md §Security design (durations)
    """
    with pytest.raises(ValueError) as refused:
        parse_duration(text)
    assert repr(text) in str(refused.value)
    assert "45s" in str(refused.value)


@pytest.mark.parametrize("value", [None, 30, 1.5, b"30m"])
def test_a_value_that_is_not_text_is_refused(value):
    with pytest.raises(ValueError):
        parse_duration(value)  # type: ignore[arg-type]


# -- the operator's minimum (R6.5) -------------------------------------------------


@pytest.mark.parametrize(
    "seconds, minimum, used",
    [(60, 1800, 1800), (1799, 1800, 1800), (1800, 1800, 1800), (7200, 1800, 7200)],
)
def test_a_wait_under_the_minimum_is_raised_to_it(seconds, minimum, used):
    assert clamp(seconds, minimum) == used


def test_a_parsed_duration_under_the_minimum_is_raised():
    assert clamp(parse_duration("5m"), 1800) == 1800
    assert clamp(parse_duration("2h"), 1800) == 7200
