"""The long-form renderer and splitter (issue-549 task 6).

The long form goes to Slack whole, as ``markdown`` blocks of at most
LONG_FORM_PART_CHARS characters. A split falls between top-level blocks, never
inside a table, code block, list item or word; an oversized code block splits at
lines with its fence reopened; an oversized table becomes code first; parts
carry ``(n/m)`` marks. Pure functions over strings.

Spec: docs/specs/issue-549/{requirements,design}.md (R1.1, R2.1–R2.6, abuse case 3).
"""

from __future__ import annotations

import math
import pytest
import re
import time

from the_loop.channels.render import (
    LONG_FORM_PART_CHARS,
    block_spans,
    render_long_form,
    split_long_form,
    table_as_code,
)

_MARK = re.compile(r"^_\((\d+)/(\d+)\)_\n\n")
_WORD = re.compile(r"\S+")


def _words(text: str):
    return _WORD.findall(text)


def _unmark(part: str) -> str:
    return _MARK.sub("", part, count=1)


def _paragraph(n: int, size: int = 400) -> str:
    sentence = f"Paragraph {n} says something useful about the change. "
    return (sentence * (size // len(sentence) + 1))[:size].rstrip()


# -- block boundaries --------------------------------------------------------------


def test_block_spans_finds_top_level_blocks():
    text = "# Title\n\nprose one\nprose two\n\n- a\n- b\n  more\n\n```py\nx = 1\n```\n| a | b |\n|---|---|\n| 1 | 2 |"
    kinds = [span.kind for span in block_spans(text.split("\n"))]
    assert kinds == ["heading", "paragraph", "list", "code", "table"]


def test_split_short_text_is_one_part_unchanged():
    text = "# Title\n\nSome prose.\n\n- a\n- b"
    parts, tables = split_long_form(text, 1000)
    assert parts == [text]
    assert tables == 0


def test_split_falls_between_top_level_blocks():
    blocks = [_paragraph(n, 300) for n in range(10)]
    text = "\n\n".join(blocks)
    parts, _ = split_long_form(text, 1000)
    assert len(parts) > 1
    for part in parts:
        assert len(part) <= 1000
        # every part is whole blocks: each paragraph appears whole in one part
        for chunk in part.split("\n\n"):
            assert chunk in blocks
    assert "\n\n".join(parts) == text


def test_split_never_inside_a_table_or_code_block_or_list_item():
    table = "| a | b |\n|---|---|\n" + "\n".join(f"| {n} | v{n} |" for n in range(20))
    code = "```\n" + "\n".join(f"line {n}" for n in range(20)) + "\n```"
    items = "\n".join(f"- item {n} with words" for n in range(15))
    text = "\n\n".join([_paragraph(1, 500), table, _paragraph(2, 500), code, items])
    parts, _ = split_long_form(text, 800)
    joined = "\n\n".join(parts)
    assert joined == text
    for whole in (table, code, items):
        assert any(whole in part for part in parts), "a block was split"


def test_split_never_inside_a_word():
    # one paragraph, one line, larger than a part: cut at spaces
    words = [f"word{n}" for n in range(600)]
    text = " ".join(words)
    parts, _ = split_long_form(text, 500)
    assert len(parts) > 1
    for part in parts:
        assert len(part) <= 500
        for word in part.split():
            assert word in words
    assert sum((part.split() for part in parts), []) == words


def test_split_oversized_code_block_reopens_the_fence():
    body = [f"print({n})  # a line of code" for n in range(200)]
    code = "```python\n" + "\n".join(body) + "\n```"
    parts, _ = split_long_form(code, 1000)
    assert len(parts) > 1
    seen = []
    for part in parts:
        assert len(part) <= 1000
        lines = part.split("\n")
        assert lines[0] == "```python"
        assert lines[-1] == "```"
        seen.extend(lines[1:-1])
    assert seen == body


def test_split_oversized_code_block_starts_in_the_room_left():
    lead = _paragraph(0, 200)
    body = [f"x{n} = {n}" for n in range(300)]
    text = lead + "\n\n```\n" + "\n".join(body) + "\n```"
    parts, _ = split_long_form(text, 1000)
    # the first part holds the paragraph and the start of the code
    assert parts[0].startswith(lead + "\n\n```\n")
    assert len(parts[0]) > 900


def test_split_oversized_table_becomes_code():
    rows = [f"| {n} | name {n} | a longer description of row {n} |" for n in range(60)]
    table = "| id | name | description |\n|---|---|---|\n" + "\n".join(rows)
    parts, tables = split_long_form(table, 1000)
    assert tables == 1
    assert len(parts) > 1
    cells = []
    for part in parts:
        lines = part.split("\n")
        assert lines[0] == "```" and lines[-1] == "```"
        assert len(part) <= 1000
        for line in lines[1:-1]:
            if set(line) <= {"-", "+"}:
                continue
            cells.extend(cell.strip() for cell in line.split(" | "))
    # every cell kept, in order; no row dropped
    expected = ["id", "name", "description"]
    for n in range(60):
        expected += [str(n), f"name {n}", f"a longer description of row {n}"]
    assert cells == expected


def test_table_as_code_aligns_columns():
    lines = ["| a | bbb |", "|---|---|", "| cc | d |"]
    assert table_as_code(lines) == ["```", "a  | bbb", "---+----", "cc | d", "```"]


def test_table_as_code_never_grows_a_crafted_table():
    lines = ["|" + "|" * 50, "|" + "x" * 40 + "|" + "|" * 49] * 20
    out = table_as_code(lines)
    assert sum(len(line) for line in out[1:-1]) <= sum(len(line) for line in lines)


# -- the long form ---------------------------------------------------------------


def test_render_long_form_one_part_has_no_mark():
    form = render_long_form("Hello **world**.\n\n| a | b |\n|---|---|\n| 1 | 2 |")
    assert form.parts == ("Hello **world**.\n\n| a | b |\n|---|---|\n| 1 | 2 |",)


def test_render_long_form_empty_has_no_parts():
    assert render_long_form("").parts == ()
    assert render_long_form("<!-- the-loop:marker -->\n").parts == ()


def test_split_parts_carry_n_of_m_marks():
    text = "\n\n".join(_paragraph(n, 3000) for n in range(12))
    form = render_long_form(text)
    total = len(form.parts)
    assert total > 1
    for n, part in enumerate(form.parts, 1):
        mark = _MARK.match(part)
        assert mark and (int(mark.group(1)), int(mark.group(2))) == (n, total)
        assert len(part) <= LONG_FORM_PART_CHARS
    assert _words(" ".join(_unmark(p) for p in form.parts)) == _words(text)


def test_split_long_form_is_defused_and_details_unfolded():
    text = (
        "<!-- the-loop:self -->\n<details>\n<summary>More</summary>\n\n"
        "ping <!here> and <@U123>\n\n</details>"
    )
    (part,) = render_long_form(text).parts
    assert "<" not in part
    assert "**More**" in part
    assert "@U123" in part


def test_split_keeps_every_word():
    text = "\n\n".join(
        [
            "# Heading",
            _paragraph(1, 9000),
            "```\n" + "\n".join(f"code {n}" for n in range(3000)) + "\n```",
            "- " + "\n- ".join(f"item {n}" for n in range(500)),
        ]
    )
    form = render_long_form(text)
    got = _words(" ".join(_unmark(part) for part in form.parts))
    fences = {"```"}
    assert [w for w in got if w not in fences] == [
        w for w in _words(text) if w not in fences
    ]


# -- abuse case 3: a crafted 64 KB comment ----------------------------------------


def _crafted_64k() -> str:
    """GitHub's maximum comment length, made of the things that cost the most:
    broadcasts and mentions to defuse, links to check, an oversized table and
    an oversized code block, unclosed markup, and long unbroken lines."""
    pieces = []
    n = 0
    while sum(len(p) + 2 for p in pieces) < 30_000:
        pieces.append(
            f"<!here> <@U{n:06d}> [x](javascript:alert({n})) [ok](https://e.com/{n}) "
            f"**bold *nested ~~strike `code` <!channel> <details> {n}"
        )
        n += 1
    pieces.append(
        "| a | b | c |\n|---|---|---|\n"
        + "\n".join(f"| {k} | <!everyone> | {'y' * 30} |" for k in range(250))
    )
    pieces.append("```\n" + "\n".join("z" * 70 for _ in range(150)) + "\n```")
    pieces.append("<<<<" * 500)
    text = "\n\n".join(pieces)
    return (text + "\n\n" + "w " * 40_000)[:65_536]


def test_abuse_64k_body_bounded_parts_and_time():
    text = _crafted_64k()
    assert len(text) == 65_536
    started = time.perf_counter()
    form = render_long_form(text)
    elapsed = time.perf_counter() - started
    assert elapsed < 2.0, f"rendering took {elapsed:.2f}s"
    assert all(len(part) <= LONG_FORM_PART_CHARS for part in form.parts)
    assert all("<" not in part for part in form.parts)
    # bounded: the defused length over the budget, plus one per table as code
    defused = sum(len(_unmark(part)) for part in form.parts)
    bound = math.ceil(defused / LONG_FORM_PART_CHARS) + form.tables_as_code
    assert len(form.parts) <= bound, (len(form.parts), bound)


def test_abuse_64k_rendering_is_linear():
    # twice the input must not cost much more than twice the time
    small = _crafted_64k()[:32_768]
    large = _crafted_64k()

    def cost(text):
        started = time.perf_counter()
        for _ in range(3):
            render_long_form(text)
        return time.perf_counter() - started

    cost(small)  # warm up
    assert cost(large) < 4 * cost(small) + 0.05


def test_abuse_adversarial_block_sizes_stay_bounded():
    # blocks just over half a part each: greedy packing can fit only one per
    # part, so the count is bounded by twice the length over the budget
    text = "\n\n".join(_paragraph(n, 5600) for n in range(12))
    form = render_long_form(text)
    assert len(form.parts) <= 2 * math.ceil(len(text) / LONG_FORM_PART_CHARS)


# -- self-review round 1: a fence opener longer than a part -----------------------


@pytest.mark.parametrize(
    "text",
    ["```" + "a" * 11000 + "\nbody\n```", "```" + "a" * 12000 + "\n```"],
)
def test_a_code_block_with_an_oversized_info_string_splits_and_keeps_every_word(
    text,
):
    """R1.1, R2.4, abuse case 3: an info string longer than a part ends, within
    the budget, with every character kept (no hang, nothing dropped)."""
    started = time.monotonic()
    long_form = render_long_form(text)
    assert time.monotonic() - started < 5
    assert long_form.parts
    assert all(len(part) <= LONG_FORM_PART_CHARS for part in long_form.parts)
    assert sum(part.count("a") for part in long_form.parts) >= text.count("a")


def test_a_fence_marker_longer_than_a_part_never_floods_the_conversation():
    """Abuse case 3 (self-review round 2): a fence of thousands of backticks is
    split as plain lines, within the budget, in a handful of parts."""
    fence = "`" * 5510
    text = fence + "\n" + ("word " * 2000) + "\n" + fence
    long_form = render_long_form(text)
    assert len(long_form.parts) <= 4
    assert all(len(part) <= LONG_FORM_PART_CHARS for part in long_form.parts)
    assert sum(part.count("word") for part in long_form.parts) == 2000


def test_an_info_line_inside_a_code_block_does_not_close_it():
    """R1.1 (critic round): "```KEEP" inside a block is text; only a bare fence
    closes it, so nothing is lost when the block is split."""
    text = "```\n" + "x" * 12000 + "\n```KEEP\nend\n```"
    joined = "\n".join(render_long_form(text).parts)
    assert "KEEP" in joined and "end" in joined


def test_a_data_row_that_looks_like_a_rule_is_kept():
    """R1.1, R2.3 (critic round): only the second line is the rule line."""
    from the_loop.channels.render import table_as_code

    drawn = "\n".join(table_as_code(["| Header |", "| --- |", "| --KEEP |", "| v |"]))
    assert "--KEEP" in drawn


def test_a_ragged_table_is_kept_as_written_in_linear_time():
    """Abuse case 3 (critic round): one wide row and many short ones is not
    padded to width x rows."""
    from the_loop.channels.render import table_as_code

    n = 4000
    lines = ["|" + " a |" * n, "| --- |"] + ["| x |"] * n
    started = time.monotonic()
    drawn = table_as_code(lines)
    assert time.monotonic() - started < 0.5
    assert len(drawn) == len(lines) + 2


def test_abuse_a_heading_of_spaces_renders_in_linear_time():
    """Abuse case 3 (security review): "# a" + spaces + "b" backtracked in cubic
    time through the heading pattern; a 64 KB one now costs what prose costs."""
    from the_loop.channels.base import Event
    from the_loop.channels.mrkdwn import to_mrkdwn
    from the_loop.channels.shortform import build_short_form, long_form_adds

    text = "# a" + " " * 64000 + "b"
    started = time.monotonic()
    render_long_form(text)
    to_mrkdwn(text)
    event = Event(event_type="comment.agent", work_item="github:o/r#7", text=text)
    short = build_short_form(event, session_authored=True)
    long_form_adds(event, short)
    assert time.monotonic() - started < 2


def test_a_heading_keeps_its_words_without_the_closing_hashes():
    from the_loop.channels.mrkdwn import to_mrkdwn

    assert to_mrkdwn("## Plan ##") == "*Plan*"
    assert to_mrkdwn("# C# notes") == "*C# notes*"
