"""Unit tests for the comment-preserving config writer (issue-222, T1).

The claim these tests carry is narrow and load-bearing: **a save changes the values it was
asked to change and nothing else.** So the fixture is not a three-line snippet that would
pass whatever we wrote — it is `skills/the-loop/templates/cli-config.yaml`, the ~270-line
commented file operators actually have, and the assertions are about what is still in it
afterwards.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml

from the_loop import yamlpatch

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = REPO_ROOT / "skills" / "the-loop" / "templates" / "cli-config.yaml"

SAMPLE = """# top comment
root:
  # a comment about items
  items:
    - one
    - two
  # comment after the block
  other: 1
  empty: {}
  flow: [a, b]
  inline: {x: 1}
top: 2
# end comment
"""


def _comments(text: str) -> list:
    return [line for line in text.splitlines() if line.lstrip().startswith("#")]


# -- deep_merge / changed_paths ----------------------------------------------------


def test_deep_merge_merges_mappings_replaces_values_and_drops_nulls():
    base = {"a": {"b": 1, "c": 2}, "list": [1, 2], "gone": True}
    merged = yamlpatch.deep_merge(base, {"a": {"b": 9}, "list": [3], "gone": None})
    assert merged == {"a": {"b": 9, "c": 2}, "list": [3]}
    assert base == {"a": {"b": 1, "c": 2}, "list": [1, 2], "gone": True}  # not mutated


def test_changed_paths_ignores_values_the_file_already_carries():
    current = yaml.safe_load(SAMPLE)
    assert yamlpatch.changed_paths(current, {}) == []
    assert yamlpatch.changed_paths(current, {"top": 2}) == []
    assert yamlpatch.changed_paths(current, {"root": {"missing": None}}) == []
    assert yamlpatch.changed_paths(current, {"top": 3, "root": {"other": 1}}) == ["top"]


# -- splicing ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "patch",
    [
        pytest.param({"root": {"other": 42}}, id="existing-scalar"),
        pytest.param({"root": {"items": ["x", "y", "z"]}}, id="block-sequence"),
        pytest.param({"root": {"flow": ["q"]}}, id="flow-sequence"),
        pytest.param({"root": {"empty": {"k": "v"}}}, id="empty-container"),
        pytest.param({"root": {"inline": {"y": 2}}}, id="flow-mapping-insert"),
        pytest.param({"root": {"fresh": True}}, id="missing-leaf"),
        pytest.param({"brand": {"new": {"deep": 1}}}, id="missing-parent-chain"),
        pytest.param({"top": [1, 2]}, id="scalar-becomes-a-list"),
        pytest.param({"root": {"items": [{"a": 1}, {"b": [2]}]}}, id="list-of-objects"),
        pytest.param({"root": {"other": None}}, id="delete-a-key"),
        pytest.param({"top": None}, id="delete-a-top-level-key"),
    ],
)
def test_every_shape_lands_the_intended_document(patch):
    """
    Feature: the config editor writes what it was asked to write
      Scenario: a patch of any shape is applied to a commented config
        Given a config with block, flow and empty containers and comments throughout
        When a patch replaces, inserts or removes a key
        Then the file re-parses to exactly the merged document

    Requirement: docs/specs/issue-222/requirements.md R2.1, R2.2, R2.3, R2.6
    """
    result = yamlpatch.apply(SAMPLE, patch)
    assert yaml.safe_load(result) == yamlpatch.deep_merge(yaml.safe_load(SAMPLE), patch)


def test_a_save_keeps_every_comment_and_every_untouched_line():
    """
    Feature: a save does not damage the operator's file
      Scenario: one value changes in the shipped template
        Given the ~270-line commented cli-config template
        When routing.enabled is changed
        Then every comment survives and every other line is byte-identical

    Requirement: docs/specs/issue-222/requirements.md R2.1
    """
    text = TEMPLATE.read_text(encoding="utf-8")
    result = yamlpatch.apply(text, {"routing": {"enabled": True}})

    assert _comments(result) == _comments(text)
    before, after = text.splitlines(), result.splitlines()
    assert len(before) == len(after)
    differing = [i for i, (b, a) in enumerate(zip(before, after)) if b != a]
    assert len(differing) == 1
    assert "enabled" in after[differing[0]]
    assert yaml.safe_load(result)["routing"]["enabled"] is True


def test_every_value_in_the_template_can_be_rewritten_in_place():
    """
    Feature: no key in the shipped config is unwritable
      Scenario: every leaf of the template is patched with a new value
        Given the shipped cli-config template
        When each leaf in turn is replaced
        Then each result re-parses to the intended document, keeping every comment

    Requirement: docs/specs/issue-222/requirements.md R2.1, R2.2
    """
    text = TEMPLATE.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    replacements: dict = {
        str: "changed",
        bool: None,  # handled below: flip it
        int: 4242,
        float: 1.5,
        list: ["replaced"],
        dict: {"replaced": True},
    }
    checked = 0
    for path, value in _leaves(data):
        new = not value if isinstance(value, bool) else replacements[type(value)]
        patch: Any = new
        for token in reversed(path):
            patch = {token: patch}
        result = yamlpatch.apply(text, patch)
        assert yaml.safe_load(result) == yamlpatch.deep_merge(data, patch), path
        assert _comments(result) == _comments(text), path
        checked += 1
    assert checked > 50  # the template is a real config, not a stub


def test_a_no_op_patch_returns_the_file_untouched():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert yamlpatch.apply(text, {}) == text
    assert yamlpatch.apply(text, {"routing": {"enabled": False}}) == text


def test_a_missing_file_is_created_with_its_modeline():
    """
    Feature: a workstation with no config gets one
      Scenario: the first save on a machine that has never been configured
        Given no config file
        When a patch is applied to empty text with a header
        Then the result is a document whose first line is the schema modeline

    Requirement: docs/specs/issue-222/requirements.md R2.4
    """
    header = "# yaml-language-server: $schema=https://example.invalid/s.json\n"
    result = yamlpatch.apply(
        "", {"version": "0.4.0", "routing": {"enabled": True}}, header
    )
    assert result.splitlines()[0] == header.rstrip("\n")
    assert yaml.safe_load(result) == {"version": "0.4.0", "routing": {"enabled": True}}


def test_a_key_beneath_a_scalar_is_refused_rather_than_guessed():
    with pytest.raises(yamlpatch.SpliceError):
        yamlpatch.apply(SAMPLE, {"top": {"nested": 1}})


def test_a_document_that_is_not_a_mapping_is_rejected():
    with pytest.raises(ValueError):
        yamlpatch.apply("- a\n- b\n", {"x": 1})


def test_an_unverifiable_splice_raises_instead_of_returning_text(monkeypatch):
    """
    Feature: an edit that cannot be proven is not written
      Scenario: the splicer produces text that does not hold the intended data
        Given a patch whose rendering is sabotaged
        When apply() re-parses its own output
        Then it raises, naming the key path, and returns nothing to write

    Requirement: docs/specs/issue-222/requirements.md R2.8
    """
    monkeypatch.setattr(yamlpatch, "_dump_inline", lambda value: "0")
    with pytest.raises(yamlpatch.SpliceError) as excinfo:
        yamlpatch.apply(SAMPLE, {"root": {"other": 7}})
    assert "root.other" in str(excinfo.value)


def _leaves(data, prefix=()):
    for key, value in data.items():
        if isinstance(value, dict) and value:
            yield from _leaves(value, prefix + (key,))
        else:
            yield prefix + (key,), value
