"""The top-level ``hooks`` declaration and its loader (issue-344, R3, R4.1, R4.3).

Every parse rule is a negative test; the loader tests write the modules they load under
``tmp_path``, three lines at a time. Nothing reaches the network.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from the_loop.lifecycle import declaration as decl
from the_loop.lifecycle.declaration import HooksConfigError, read_declaration
from the_loop.lifecycle.executors import LocalExecutor, load
from the_loop.lifecycle.remote import RemoteExecutor

MODULE = """
from the_loop.sdk.hooks import LifecycleHooks


class Policy(LifecycleHooks):
    def __init__(self, tag="none"):
        self.tag = tag

    def work_item_start(self, ctx):
        ctx.reason = self.tag
        return ctx
"""


def _read(entries, **top):
    return read_declaration({"hooks": entries, **top})


# ------------------------------------------------------------------ parsing


def test_an_absent_or_empty_block_declares_nothing():
    assert read_declaration({}).empty
    assert read_declaration({"hooks": None}).empty
    assert read_declaration({"hooks": []}).empty
    assert read_declaration("not a mapping").empty  # type: ignore[arg-type]


def test_a_local_module_entry_parses_with_defaults():
    d = _read([{"name": "telemetry", "module": "acme.hooks"}])
    (entry,) = d.entries
    assert entry.name == "telemetry"
    assert entry.kind == "module"
    assert entry.module == "acme.hooks"
    assert entry.on == ()
    assert entry.required is False
    assert entry.enabled is True
    assert entry.target == "module acme.hooks"


def test_a_remote_entry_parses_with_defaults():
    d = _read([{"name": "compliance", "url": "https://hooks.example/the-loop"}])
    (entry,) = d.entries
    assert entry.kind == "url"
    assert entry.url == "https://hooks.example/the-loop"
    assert entry.timeout == 10.0
    assert entry.token_env == ""
    assert entry.headers == {}
    assert entry.target == "url https://hooks.example/the-loop"


@pytest.mark.parametrize("value", [{}, "x", 3, {"name": "a"}])
def test_hooks_must_be_a_list_of_mappings(value):
    with pytest.raises(HooksConfigError):
        read_declaration({"hooks": value})
    with pytest.raises(HooksConfigError):
        read_declaration({"hooks": ["bare-string"]})


@pytest.mark.parametrize("name", ["", "Telemetry", "1st", "a b", "x_y", "-a"])
def test_a_name_must_match_the_grammar(name):
    with pytest.raises(HooksConfigError) as exc:
        _read([{"name": name, "module": "a.b"}])
    assert "name" in str(exc.value)


def test_names_are_unique():
    with pytest.raises(HooksConfigError) as exc:
        _read([{"name": "a", "module": "a.b"}, {"name": "a", "url": "https://x/"}])
    assert "'a'" in str(exc.value) and "twice" in str(exc.value)


@pytest.mark.parametrize(
    "entry",
    [
        {"name": "a"},
        {"name": "a", "module": "a.b", "path": "x.py"},
        {"name": "a", "module": "a.b", "url": "https://x/"},
        {"name": "a", "path": "x.py", "url": "https://x/"},
    ],
)
def test_exactly_one_of_module_path_url(entry):
    with pytest.raises(HooksConfigError) as exc:
        _read([entry])
    assert "exactly one" in str(exc.value)


def test_an_unknown_key_is_refused():
    with pytest.raises(HooksConfigError) as exc:
        _read([{"name": "a", "module": "a.b", "bogus": 1}])
    assert "bogus" in str(exc.value)


@pytest.mark.parametrize(
    "key, value", [("tokenEnv", "T"), ("headers", {"a": "b"}), ("timeoutSeconds", 3)]
)
def test_remote_keys_are_refused_on_a_local_entry(key, value):
    with pytest.raises(HooksConfigError) as exc:
        _read([{"name": "a", "module": "a.b", key: value}])
    assert key in str(exc.value)


@pytest.mark.parametrize("key, value", [("executor", "X"), ("with", {"a": 1})])
def test_local_keys_are_refused_on_a_remote_entry(key, value):
    with pytest.raises(HooksConfigError) as exc:
        _read([{"name": "a", "url": "https://x/", key: value}])
    assert key in str(exc.value)


def test_a_module_must_be_a_dotted_name():
    with pytest.raises(HooksConfigError):
        _read([{"name": "a", "module": "not a module"}])
    with pytest.raises(HooksConfigError):
        _read([{"name": "a", "module": "../x.py"}])


def test_on_may_name_only_catalog_points():
    """Abuse case 8 / R1.3: an event type is not a hook point."""
    with pytest.raises(HooksConfigError) as exc:
        _read([{"name": "a", "module": "a.b", "on": ["session.spawned"]}])
    assert "session.spawned" in str(exc.value)
    assert "work_item_start" in str(exc.value)
    with pytest.raises(HooksConfigError):
        _read([{"name": "a", "module": "a.b", "on": "work_item_start"}])
    with pytest.raises(HooksConfigError):
        _read([{"name": "a", "module": "a.b", "on": []}])
    d = _read(
        [{"name": "a", "module": "a.b", "on": ["work_item_start", "phase_changed"]}]
    )
    assert d.entries[0].on == ("work_item_start", "phase_changed")


@pytest.mark.parametrize("key", ["required", "enabled"])
def test_booleans_must_be_booleans(key):
    with pytest.raises(HooksConfigError):
        _read([{"name": "a", "module": "a.b", key: "yes"}])


def test_timeout_must_be_a_positive_number():
    with pytest.raises(HooksConfigError):
        _read([{"name": "a", "url": "https://x/", "timeoutSeconds": 0}])
    with pytest.raises(HooksConfigError):
        _read([{"name": "a", "url": "https://x/", "timeoutSeconds": "fast"}])
    d = _read([{"name": "a", "url": "https://x/", "timeoutSeconds": 2.5}])
    assert d.entries[0].timeout == 2.5


def test_headers_must_be_a_string_mapping():
    with pytest.raises(HooksConfigError):
        _read([{"name": "a", "url": "https://x/", "headers": {"a": 1}}])
    with pytest.raises(HooksConfigError):
        _read([{"name": "a", "url": "https://x/", "headers": ["a"]}])


def test_authorization_may_not_be_a_plain_header():
    """A token belongs in the environment, named by tokenEnv — never in the config."""
    with pytest.raises(HooksConfigError) as exc:
        _read(
            [
                {
                    "name": "a",
                    "url": "https://x/",
                    "headers": {"Authorization": "Bearer t"},
                }
            ]
        )
    assert "tokenEnv" in str(exc.value)


def test_token_env_must_be_a_variable_name():
    with pytest.raises(HooksConfigError):
        _read([{"name": "a", "url": "https://x/", "tokenEnv": "not a name"}])
    with pytest.raises(HooksConfigError):
        _read([{"name": "a", "url": "https://x/", "tokenEnv": ""}])


@pytest.mark.parametrize(
    "url",
    [
        "ftp://x/",
        "file:///etc/passwd",
        "x",
        "https://",
        "http://",
        "javascript:alert(1)",
    ],
)
def test_a_url_must_be_http_or_https_with_a_host(url):
    with pytest.raises(HooksConfigError):
        _read([{"name": "a", "url": url}])


@pytest.mark.parametrize(
    "url", ["http://localhost:8000/hooks", "http://127.0.0.1/", "http://[::1]:9/x"]
)
def test_plain_http_is_allowed_on_loopback_even_with_a_token(url):
    d = _read([{"name": "a", "url": url, "tokenEnv": "T"}])
    assert d.entries[0].url == url


def test_plain_http_without_a_token_is_allowed_anywhere():
    d = _read([{"name": "a", "url": "http://hooks.internal/x"}])
    assert d.entries[0].url == "http://hooks.internal/x"


def test_a_bearer_token_over_cleartext_http_is_refused_at_load():
    """Abuse case 4 / R4.3."""
    with pytest.raises(HooksConfigError) as exc:
        _read([{"name": "a", "url": "http://hooks.internal/x", "tokenEnv": "T"}])
    assert "https" in str(exc.value)


def test_a_disabled_entry_is_kept_in_the_declaration_but_not_loaded(tmp_path):
    d = _read([{"name": "a", "module": "a.nope", "enabled": False}])
    assert d.entries[0].enabled is False
    assert load(d, tmp_path) == []


def test_the_digest_changes_with_the_declaration():
    one = _read([{"name": "a", "module": "a.b"}])
    two = _read([{"name": "a", "module": "a.c"}])
    assert one.digest() != two.digest()
    assert one.digest() == _read([{"name": "a", "module": "a.b"}]).digest()


# ------------------------------------------------------------------ paths


def test_a_path_resolves_against_the_config_file_not_the_cwd(tmp_path, monkeypatch):
    """Abuse case 1: a checkout's file at the same relative path is never imported."""
    config_dir = tmp_path / "operator"
    config_dir.mkdir()
    (config_dir / "policy.py").write_text(MODULE)
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "policy.py").write_text(
        "raise RuntimeError('the checkout was imported')"
    )
    monkeypatch.chdir(checkout)
    d = _read([{"name": "house", "path": "policy.py"}])
    (executor,) = load(d, config_dir)
    assert isinstance(executor, LocalExecutor)
    assert (
        d.entries[0].resolved_path(config_dir) == (config_dir / "policy.py").resolve()
    )


def test_a_tilde_and_an_absolute_path_are_accepted(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "p.py").write_text(MODULE)
    d = _read(
        [{"name": "a", "path": "~/p.py"}, {"name": "b", "path": str(tmp_path / "p.py")}]
    )
    assert (
        d.entries[0].resolved_path(tmp_path / "elsewhere")
        == (tmp_path / "p.py").resolve()
    )
    assert len(load(d, tmp_path / "elsewhere")) == 2


def test_a_path_must_be_a_py_file():
    with pytest.raises(HooksConfigError):
        _read([{"name": "a", "path": "hooks/policy.txt"}])


# ------------------------------------------------------------------ loading


def _write_module(tmp_path, body=MODULE, name="policy.py"):
    (tmp_path / name).write_text(body)
    return tmp_path


def test_load_builds_one_executor_per_enabled_entry_in_order(tmp_path):
    _write_module(tmp_path)
    d = _read(
        [
            {"name": "first", "path": "policy.py", "with": {"tag": "one"}},
            {"name": "second", "url": "https://x/"},
            {"name": "third", "path": "policy.py"},
        ]
    )
    executors = load(d, tmp_path)
    assert [e.name for e in executors] == ["first", "second", "third"]
    assert isinstance(executors[0], LocalExecutor)
    assert isinstance(executors[1], RemoteExecutor)
    assert executors[0].hooks.tag == "one"  # type: ignore[attr-defined]
    assert executors[2].hooks.tag == "none"  # type: ignore[attr-defined]


def test_a_local_executor_handles_the_points_its_class_overrides(tmp_path):
    _write_module(tmp_path)
    (executor,) = load(_read([{"name": "a", "path": "policy.py"}]), tmp_path)
    assert executor.handles("work_item_start")
    assert not executor.handles("session_spawn")


def test_on_narrows_and_may_not_widen_a_local_executor(tmp_path):
    _write_module(tmp_path)
    (executor,) = load(
        _read([{"name": "a", "path": "policy.py", "on": ["session_spawn"]}]), tmp_path
    )
    assert not executor.handles("work_item_start"), "on narrows to what is listed"
    assert not executor.handles("session_spawn"), (
        "a method the class lacks is not handled"
    )


def test_a_remote_executor_handles_every_point_unless_narrowed(tmp_path):
    (every, some) = load(
        _read(
            [
                {"name": "e", "url": "https://x/"},
                {"name": "s", "url": "https://x/", "on": ["phase_changed"]},
            ]
        ),
        tmp_path,
    )
    assert every.handles("work_item_start") and every.handles("work_item_complete")
    assert some.handles("phase_changed") and not some.handles("work_item_start")


def test_a_missing_path_fails_the_load_naming_the_entry(tmp_path):
    with pytest.raises(HooksConfigError) as exc:
        load(_read([{"name": "house", "path": "nope.py"}]), tmp_path)
    assert "house" in str(exc.value) and "nope.py" in str(exc.value)


def test_a_missing_module_fails_the_load_naming_the_entry(tmp_path):
    with pytest.raises(HooksConfigError) as exc:
        load(
            _read([{"name": "tele", "module": "acme_no_such_module_344.hooks"}]),
            tmp_path,
        )
    assert "tele" in str(exc.value)


def test_a_module_that_raises_fails_the_load(tmp_path):
    """Abuse case 6."""
    _write_module(tmp_path, "raise RuntimeError('boom at import')")
    with pytest.raises(HooksConfigError) as exc:
        load(_read([{"name": "a", "path": "policy.py"}]), tmp_path)
    assert "boom at import" in str(exc.value)


def test_a_constructor_that_raises_fails_the_load(tmp_path):
    _write_module(
        tmp_path,
        MODULE.replace("self.tag = tag", "raise ValueError('bad tag ' + tag)"),
    )
    with pytest.raises(HooksConfigError) as exc:
        load(
            _read([{"name": "a", "path": "policy.py", "with": {"tag": "x"}}]), tmp_path
        )
    assert "bad tag x" in str(exc.value)


def test_a_module_defining_no_subclass_fails_the_load(tmp_path):
    _write_module(tmp_path, "X = 1\n")
    with pytest.raises(HooksConfigError) as exc:
        load(_read([{"name": "a", "path": "policy.py"}]), tmp_path)
    assert "LifecycleHooks" in str(exc.value)


def test_a_module_defining_several_subclasses_needs_an_executor(tmp_path):
    _write_module(tmp_path, MODULE + "\n\nclass Other(Policy):\n    pass\n")
    with pytest.raises(HooksConfigError) as exc:
        load(_read([{"name": "a", "path": "policy.py"}]), tmp_path)
    assert "Policy" in str(exc.value) and "Other" in str(exc.value)
    (executor,) = load(
        _read([{"name": "a", "path": "policy.py", "executor": "Other"}]), tmp_path
    )
    assert isinstance(executor, LocalExecutor)
    assert type(executor.hooks).__name__ == "Other"


def test_an_imported_subclass_is_not_the_modules_own(tmp_path):
    """Importing LifecycleHooks (or another module's class) must not count as defining one."""
    _write_module(
        tmp_path, "from the_loop.sdk.hooks import LifecycleHooks\nX = LifecycleHooks\n"
    )
    with pytest.raises(HooksConfigError):
        load(_read([{"name": "a", "path": "policy.py"}]), tmp_path)


def test_executor_may_name_an_instance_but_then_takes_no_with(tmp_path):
    _write_module(tmp_path, MODULE + "\nhooks = Policy(tag='instance')\n")
    (executor,) = load(
        _read([{"name": "a", "path": "policy.py", "executor": "hooks"}]), tmp_path
    )
    assert isinstance(executor, LocalExecutor)
    assert executor.hooks.tag == "instance"  # type: ignore[attr-defined]
    with pytest.raises(HooksConfigError) as exc:
        load(
            _read(
                [
                    {
                        "name": "a",
                        "path": "policy.py",
                        "executor": "hooks",
                        "with": {"tag": "x"},
                    }
                ]
            ),
            tmp_path,
        )
    assert "with" in str(exc.value)


def test_executor_must_name_a_lifecycle_hooks_class_or_instance(tmp_path):
    _write_module(tmp_path, MODULE + "\nNOT_HOOKS = object()\n")
    with pytest.raises(HooksConfigError):
        load(
            _read([{"name": "a", "path": "policy.py", "executor": "NOT_HOOKS"}]),
            tmp_path,
        )
    with pytest.raises(HooksConfigError):
        load(
            _read([{"name": "a", "path": "policy.py", "executor": "missing"}]), tmp_path
        )


def test_a_bad_with_is_the_constructors_error_named_for_the_entry(tmp_path):
    _write_module(tmp_path)
    with pytest.raises(HooksConfigError) as exc:
        load(_read([{"name": "a", "path": "policy.py", "with": {"nope": 1}}]), tmp_path)
    assert "a" in str(exc.value)


def test_with_must_be_a_mapping():
    with pytest.raises(HooksConfigError):
        _read([{"name": "a", "module": "a.b", "with": ["x"]}])


def test_a_module_file_is_executed_once_per_process(tmp_path):
    counter = tmp_path / "count"
    counter.write_text("0")
    body = (
        "from pathlib import Path\n"
        f"p = Path({str(counter)!r}); p.write_text(str(int(p.read_text()) + 1))\n"
        + MODULE
    )
    _write_module(tmp_path, body)
    d = _read([{"name": "a", "path": "policy.py"}, {"name": "b", "path": "policy.py"}])
    load(d, tmp_path)
    load(d, tmp_path)
    assert counter.read_text() == "1"


def test_the_installed_module_form_loads_from_sys_path(tmp_path, monkeypatch):
    pkg = tmp_path / "acme_hooks_344"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "policy.py").write_text(MODULE)
    monkeypatch.syspath_prepend(str(tmp_path))
    (executor,) = load(
        _read([{"name": "a", "module": "acme_hooks_344.policy"}]), tmp_path
    )
    assert executor.handles("work_item_start")


def test_config_base_dir_is_the_files_directory():
    assert decl.config_base_dir(Path("/etc/the-loop/cli-config.yaml")) == Path(
        "/etc/the-loop"
    )
    assert decl.config_base_dir(Path("cli-config.yaml")) == Path(os.getcwd())
