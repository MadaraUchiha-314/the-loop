"""The one string catalog (issue-540, R2).

Human-facing messages live in ``the_loop/strings/en.json``, keyed by stable dotted
identifiers and read through :func:`the_loop.strings.t`. These tests pin the lookup
contract (formatting, the locale fallback, failing loudly on a missing key) and the
catalog's own shape. They also check that every key the code looks up exists, and
that each message's placeholders are the ones its call sites fill.
"""

import ast
import json
import re
import string
from pathlib import Path

import pytest

from the_loop import strings

PACKAGE = Path(strings.__file__).resolve().parents[1]
EN = Path(strings.__file__).with_name("en.json")
KEY = re.compile(r"^[a-z0-9-]+(\.[a-z0-9_-]+)+$")


@pytest.fixture
def locales(tmp_path, monkeypatch):
    """A locale directory holding a copy of en.json, selected for the test."""
    (tmp_path / "en.json").write_text(EN.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(strings, "_DIR", tmp_path)
    strings._reset()
    yield tmp_path
    strings._reset()


# -- the catalog's shape -----------------------------------------------------------


def test_en_is_one_flat_object_of_strings_with_dotted_keys():
    data = json.loads(EN.read_text(encoding="utf-8"))
    assert isinstance(data, dict) and data
    for key, value in data.items():
        assert KEY.match(key), key
        assert isinstance(value, str) and value, key


def test_placeholders_are_named_fields_only():
    for key, value in strings.catalog("en").items():
        for _, field, _, _ in string.Formatter().parse(value):
            if field is not None:
                assert field.isidentifier(), f"{key}: positional or odd field {field!r}"


# -- the lookup ----------------------------------------------------------------------


def test_t_formats_named_variables():
    assert strings.t("bodies.mirror.work-item.reply", who="ann", source="slack") == (
        "reply from ann on the **slack** channel, recorded here as the answer of record"
    )


def test_a_missing_key_raises_naming_it():
    with pytest.raises(KeyError, match="no.such.key"):
        strings.t("no.such.key")


def test_values_are_inserted_literally():
    """Abuse case 2: untrusted text is a value, never re-read as a placeholder."""
    text = strings.t("bodies.mirror.work-item.reply", who="{source}", source="$x")
    assert text.startswith("reply from {source} on the **$x** channel")


def test_section_returns_suffix_to_text():
    section = strings.section("digest.pointer")
    assert section == {
        "code": "code: {n} lines",
        "table": "table: {n} rows",
        "trace": "stack trace: {n} lines",
    }


# -- locales and fallback (R2.3) -------------------------------------------------------


def test_a_locale_overrides_what_it_translates_and_falls_back_for_the_rest(
    locales, monkeypatch
):
    (locales / "xx.json").write_text(
        json.dumps({"digest.pointer.code": "kode: {n} linjer"}), encoding="utf-8"
    )
    monkeypatch.setenv("THE_LOOP_LOCALE", "xx")
    strings._reset()
    assert strings.t("digest.pointer.code", n=3) == "kode: 3 linjer"
    assert strings.t("digest.pointer.table", n=2) == "table: 2 rows"
    assert strings.section("digest.pointer")["trace"] == "stack trace: {n} lines"


def test_set_locale_selects_explicitly(locales):
    (locales / "xx.json").write_text(
        json.dumps({"digest.pointer.code": "kode"}), encoding="utf-8"
    )
    strings.set_locale("xx")
    assert strings.t("digest.pointer.code") == "kode"
    strings.set_locale("en")
    assert strings.t("digest.pointer.code", n=1) == "code: 1 lines"


@pytest.mark.parametrize("body", ["not json", "[1, 2]", '{"a.b": 3}'])
def test_an_invalid_locale_warns_and_falls_back(locales, monkeypatch, caplog, body):
    (locales / "xx.json").write_text(body, encoding="utf-8")
    monkeypatch.setenv("THE_LOOP_LOCALE", "xx")
    strings._reset()
    assert strings.t("digest.pointer.code", n=1) == "code: 1 lines"
    assert "xx.json" in caplog.text


def test_a_missing_locale_falls_back_to_en(locales, monkeypatch):
    monkeypatch.setenv("THE_LOOP_LOCALE", "zz")
    strings._reset()
    assert strings.t("digest.pointer.code", n=1) == "code: 1 lines"


@pytest.mark.parametrize("locale", ["../en", "en/../x", "", "EN_us!"])
def test_a_locale_name_cannot_leave_the_directory(locale):
    with pytest.raises(ValueError):
        strings.set_locale(locale)


def test_a_broken_en_catalog_is_an_error(locales):
    (locales / "en.json").write_text("{", encoding="utf-8")
    with pytest.raises(ValueError):
        strings.t("digest.pointer.code")


# -- the code and the catalog agree (R2.6) ---------------------------------------------


def _lookups():
    """Every literal ``strings.t("…")`` key and ``strings.section("…")`` prefix
    in the package, with the keyword names passed to ``t``."""
    keys, prefixes = {}, set()
    for path in PACKAGE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            ):
                continue
            owner = node.func.value
            if not (isinstance(owner, ast.Name) and owner.id == "strings"):
                continue
            if not node.args or not isinstance(node.args[0], ast.Constant):
                continue
            literal = node.args[0].value
            if node.func.attr == "t":
                keys.setdefault(literal, set()).update(
                    k.arg for k in node.keywords if k.arg
                )
            elif node.func.attr == "section":
                prefixes.add(literal)
    return keys, prefixes


def test_every_key_the_code_looks_up_exists_with_matching_placeholders():
    catalog = strings.catalog("en")
    keys, prefixes = _lookups()
    assert prefixes, "expected the migrated dictionaries to use strings.section"
    for key, passed in keys.items():
        assert key in catalog, f"{key} is looked up but missing from en.json"
        used = {f for _, f, _, _ in string.Formatter().parse(catalog[key]) if f}
        assert used == passed, f"{key}: text uses {used}, call passes {passed}"
    for prefix in prefixes:
        assert any(k.startswith(prefix + ".") for k in catalog), prefix


def test_every_catalog_entry_is_used():
    keys, prefixes = _lookups()
    for key in strings.catalog("en"):
        assert key in keys or any(key.startswith(p + ".") for p in prefixes), (
            f"{key} is in en.json but nothing looks it up"
        )
