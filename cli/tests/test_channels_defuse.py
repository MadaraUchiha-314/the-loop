"""The defuser (issue-549 task 5): text from GitHub made inert before Slack parses it.

Five steps, in the order design.md § Security design fixes, applied to both the
short form and the long form: strip markers and HTML comments, neutralise
broadcasts, defuse user mentions, keep only safe link schemes, escape the
angle-bracket syntax. Every position counts: prose, table cells, headings and
link labels.

Spec: docs/specs/issue-549/{requirements,design}.md (R2.8, abuse cases 1, 2, 4).
"""

from __future__ import annotations

import re

import pytest

from the_loop.channels.defuse import (
    SAFE_SCHEMES,
    defuse,
    defuse_user_mentions,
    escape_angle_brackets,
    keep_safe_links,
)

#: Any Slack control sequence still live after defusing: `<!…>`, `<@…>`, `<#…>`,
#: `<url|label>` or `<url>`. A defused text holds no `<` at all.
_LIVE = re.compile(r"<[!@#a-zA-Z]")

BROADCASTS = ("<!here>", "<!channel>", "<!everyone>", "<!subteam^S0123ABC|@team>")


def _assert_inert(text: str) -> None:
    assert "<" not in text, text
    assert not _LIVE.search(text)


# -- abuse case 1: broadcasts, in every position ---------------------------------


@pytest.mark.parametrize("sequence", BROADCASTS)
def test_defuse_broadcast_in_prose(sequence):
    out = defuse(f"Heads up {sequence} please look.")
    _assert_inert(out)
    assert "Heads up" in out and "please look." in out


@pytest.mark.parametrize("sequence", BROADCASTS)
def test_defuse_broadcast_in_table_cell(sequence):
    table = f"| name | note |\n|---|---|\n| a | {sequence} |\n"
    out = defuse(table)
    _assert_inert(out)
    # the table's shape is kept: the cell is still a cell
    assert out.splitlines()[0] == "| name | note |"
    assert out.splitlines()[2].startswith("| a | ")


@pytest.mark.parametrize("sequence", BROADCASTS)
def test_defuse_broadcast_in_heading(sequence):
    out = defuse(f"## Release {sequence}\n\nbody")
    _assert_inert(out)
    assert out.startswith("## Release ")


@pytest.mark.parametrize("sequence", BROADCASTS)
def test_defuse_broadcast_in_link_label(sequence):
    out = defuse(f"see [{sequence} now](https://example.com/x)")
    _assert_inert(out)
    # the link stays a link, its label defused
    assert "](https://example.com/x)" in out


def test_defuse_broadcast_in_code_is_still_neutralised():
    # a fence is no safe harbour: Slack may parse it, so fail closed
    out = defuse("```\n<!channel>\n```")
    _assert_inert(out)


# -- abuse case 2: user mentions --------------------------------------------------


@pytest.mark.parametrize(
    "mention, inert",
    [("<@U012AB3CD>", "@U012AB3CD"), ("<@W012AB3CD|someone>", "@W012AB3CD")],
)
def test_defuse_user_mention(mention, inert):
    out = defuse(f"thanks {mention}!")
    _assert_inert(out)
    assert inert in out
    assert defuse_user_mentions(mention) == inert


def test_defuse_user_mention_in_cell_and_label():
    out = defuse("| who |\n|---|\n| <@U1ABC> |\n\n[<@U2DEF>](https://example.com)")
    _assert_inert(out)
    assert "@U1ABC" in out and "@U2DEF" in out


# -- abuse case 4: unsafe schemes and breakout markup -----------------------------


@pytest.mark.parametrize(
    "target",
    [
        "javascript:alert(1)",
        "JavaScript:alert(1)",
        "data:text/html;base64,AAAA",
        "vbscript:x",
        "file:///etc/passwd",
        "slack://channel?id=C1",
    ],
)
def test_defuse_unsafe_scheme(target):
    out = defuse(f"[click me]({target})")
    # no longer a markdown link: the label and target are plain text
    assert "](" not in out
    assert "click me" in out
    _assert_inert(out)


@pytest.mark.parametrize(
    "target", ["https://example.com/a", "http://example.com", "mailto:a@example.com"]
)
def test_defuse_safe_scheme_stays_a_link(target):
    assert sorted(SAFE_SCHEMES) == ["http", "https", "mailto"]
    out = defuse(f"[docs]({target})")
    assert out == f"[docs]({target})"


def test_defuse_safe_link_target_cannot_break_out():
    # `|` and `>` in a target would close Slack's `<url|label>` once drawn as mrkdwn
    out = keep_safe_links("[x](https://example.com/a|b>c<d)")
    assert out == "[x](https://example.com/a%7Cb%3Ec%3Cd)"


def test_defuse_breakout_markup():
    cell = "| col |\n|---|\n| <https://evil.example|Click here> |\n| <#C123> |\n"
    out = defuse(cell)
    _assert_inert(out)
    assert "Click here" in out  # every word kept, as text
    assert escape_angle_brackets("<x|y>") == "&lt;x|y>"


def test_defuse_bare_autolink_with_safe_scheme_is_unwrapped():
    # `<https://…>` is markdown's autolink: kept as the bare URL Slack links itself
    assert defuse("see <https://example.com/x> now") == "see https://example.com/x now"
    assert "<" not in defuse("see <javascript:alert(1)> now")


def test_defuse_keeps_block_quotes_and_arrows():
    text = "> quoted line\n>> nested\n\na -> b"
    assert defuse(text) == text


# -- R2.8: markers ----------------------------------------------------------------


def test_defuse_strips_markers():
    text = (
        "<!-- the-loop:self-authored -->\nHello.\n"
        '<!-- the-loop:envelope {"kind": "x"} -->\n<!-- any other comment -->Done.'
    )
    out = defuse(text)
    assert "the-loop:" not in out
    assert "comment" not in out
    assert "Hello." in out and "Done." in out
    _assert_inert(out)


def test_defuse_strips_markers_before_broadcasts():
    # a marker is not mistaken for a broadcast (`<!--` is not `<!here>`)
    assert defuse("a<!-- m -->b") == "ab"


# -- properties -------------------------------------------------------------------


def test_defuse_is_idempotent():
    text = (
        "<!-- m --># T <!here>\n\n| a | <@U1> |\n|---|---|\n\n"
        "[l](javascript:x) [ok](https://e.com/a|b) <https://e.com> <x|y>"
    )
    once = defuse(text)
    assert defuse(once) == once


def test_defuse_empty():
    assert defuse("") == ""


def test_defuse_unsafe_scheme_with_parentheses_or_angle_target():
    for text in ("[go](javascript:alert(1))", "[go](<javascript:alert(1)>)"):
        out = defuse(text)
        assert "](" not in out, out
        assert "go" in out
        _assert_inert(out)


def test_defuse_unsafe_reference_definition():
    out = defuse("[go][1]\n\n[1]: javascript:alert(1)\n[2]: https://example.com")
    assert "\\[1]: javascript:alert(1)" in out  # defines nothing
    assert "\n[2]: https://example.com" in out  # a safe one is kept
