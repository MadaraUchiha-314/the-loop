"""The suite cannot write into a checked-in `.the-loop/` (issue-422).

Feature: a test run leaves the repository it runs in untouched.

The guard is `conftest._audit_state_writes`, an audit hook, and
`_no_protected_state_writes`, which fails the test that tripped it. These tests
point the guard at a directory under `tmp_path` and check what it records.

Spec: docs/specs/issue-422/bugfix.md · Testing plan row T4.
"""

import os
import shutil
import tempfile

import pytest

import conftest


@pytest.fixture
def guarded(tmp_path, monkeypatch):
    root = tmp_path / "guarded"
    root.mkdir()
    (root / "existing.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(conftest, "_PROTECTED_STATE", (os.path.join(str(root), ""),))
    conftest._protected_writes.clear()
    yield root
    conftest._protected_writes.clear()


def _recorded():
    return [
        (event, os.path.basename(path)) for event, path, _ in conftest._protected_writes
    ]


@pytest.mark.parametrize(
    "write,expected",
    [
        (lambda r: (r / "new.json").write_text("{}"), ("open", "new.json")),
        (lambda r: open(r / "existing.json", "a").close(), ("open", "existing.json")),
        (
            lambda r: os.close(os.open(r / "fd.json", os.O_WRONLY | os.O_CREAT)),
            ("open", "fd.json"),
        ),
        (lambda r: os.close(tempfile.mkstemp(dir=r)[0]), ("open", None)),
        (lambda r: (r / "sub").mkdir(), ("os.mkdir", "sub")),
        (lambda r: (r / "existing.json").unlink(), ("os.remove", "existing.json")),
    ],
    ids=["write_text", "append", "os.open", "mkstemp", "mkdir", "unlink"],
)
def test_a_write_into_a_protected_tree_is_recorded(guarded, write, expected):
    """
    Scenario: code under test writes into a protected `.the-loop/`
      Given a protected tree
      When a test writes, creates, appends to or removes a file in it
      Then the write is recorded with the event and the path
    """
    write(guarded)
    event, name = expected
    assert [e for e, _ in _recorded()] == [event]
    if name is not None:
        assert _recorded()[0][1] == name


def test_a_replace_into_a_protected_tree_is_recorded(guarded, tmp_path):
    """The atomic-write shape every store uses: a temp file, then `os.replace`."""
    staged = tmp_path / "staged.json"
    staged.write_text("{}", encoding="utf-8")
    os.replace(staged, guarded / "record.json")
    assert ("os.rename", "record.json") in _recorded()


def test_a_read_and_a_write_elsewhere_are_not(guarded, tmp_path):
    """
    Scenario: the suite reads the checked-in config and writes under tmp_path
      Given a protected tree
      When a test reads a file in it and writes a file outside it
      Then nothing is recorded
    """
    assert (guarded / "existing.json").read_text(encoding="utf-8") == "{}"
    (tmp_path / "outside.json").write_text("{}", encoding="utf-8")
    (tmp_path / "guarded-sibling").mkdir()  # a shared prefix is not the tree
    assert _recorded() == []


def test_a_name_relative_to_a_directory_fd_is_not_read_as_the_cwd(
    tmp_path, monkeypatch
):
    """
    Scenario: a test removes a tmp tree that holds its own `.the-loop/`
      Given the working directory's `.the-loop/` is protected
      When `shutil.rmtree` removes another directory's `.the-loop/`
       And a symlink elsewhere points into the protected tree
      Then nothing is recorded: the rmdir names `.the-loop` beside a dir_fd,
       and a link's target is not written
    """
    monkeypatch.chdir(tmp_path)
    protected = os.path.join(str(tmp_path / ".the-loop"), "")
    monkeypatch.setattr(conftest, "_PROTECTED_STATE", (protected,))
    other = tmp_path / "other" / ".the-loop" / "portable"
    other.mkdir(parents=True)
    (other / "record.json").write_text("{}", encoding="utf-8")
    conftest._protected_writes.clear()
    shutil.rmtree(tmp_path / "other")  # rmdir(".the-loop", dir_fd=<other>)
    # A link's *target* is not written: only the link itself is.
    os.symlink(str(tmp_path / ".the-loop"), str(tmp_path / "link"))
    try:
        assert _recorded() == []
    finally:
        conftest._protected_writes.clear()


def test_the_report_names_the_code_that_wrote(guarded):
    """The failure says where to look: this file is in the recorded stack."""
    (guarded / "new.json").write_text("{}", encoding="utf-8")
    report = conftest._protected_write_report()
    assert "new.json" in report and "test_state_isolation.py" in report
    assert conftest._protected_writes == []


def test_the_repository_and_the_working_directory_are_protected():
    """AC1/AC2: the real guard covers this checkout's `.the-loop/` and the cwd's."""
    repo_state = os.path.join(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(conftest.__file__)))
        ),
        ".the-loop",
        "",
    )
    cwd_state = os.path.join(os.path.abspath(".the-loop"), "")
    assert repo_state in conftest._PROTECTED_STATE
    assert conftest._protected(os.path.join(cwd_state, "portable", "x.json"))
