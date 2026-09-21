"""Version-lockstep guard: every `.cz.toml` version_files target carries the version.

`cz bump` rewrites a version_files entry by replacing the CURRENT version string on
lines matching the entry's pattern — a drifted file is silently left behind at release
time (how the plugin manifests sat at 0.1.0 while releases reached 0.7.0, issue #46).
`uv.lock` drifts for the opposite reason — `cz bump` cannot rewrite it at all, so the
release workflow re-runs `uv lock` and folds the result into the bump commit; when that
fold does not happen the lockfile keeps naming the previous version of the workspace
member (issue-407). Both drifts are checked by the same script.

Running the check inside the CLI test suite means the existing pytest pre-commit hook
and CI gate every PR on it, with no extra pipeline wiring.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK_SCRIPT = REPO_ROOT / "scripts" / "check_version_lockstep.py"

sys.path.insert(0, str(REPO_ROOT / "scripts"))

from check_version_lockstep import check_uv_lock  # noqa: E402

# A uv.lock trimmed to the two block shapes the check distinguishes: the editable
# workspace member whose version must track the release, and a registry package whose
# version must be ignored.
LOCK_TEMPLATE = """version = 1
revision = 3

[[package]]
name = "fastapi"
version = "0.110.0"
source = {{ registry = "https://pypi.org/simple" }}

[[package]]
name = "the-loopy-one"
version = "{member}"
source = {{ editable = "cli" }}
dependencies = [
    {{ name = "fastapi" }},
]
"""


def test_version_files_are_in_lockstep():
    """Scenario: releasing the-loop bumps every artifact that carries a version.

    Given the commitizen version in `.cz.toml`
    When the lockstep check runs over every `version_files` entry
    Then each entry's version lines carry that exact version, so the next
    `cz bump` rewrites all of them together.
    """
    result = subprocess.run(
        [sys.executable, str(CHECK_SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"version lockstep check failed:\n{result.stdout}{result.stderr}"
    )


def test_stale_uv_lock_is_reported():
    """Scenario: a release bumped the package but nobody re-ran `uv lock`.

    Given a lockfile whose editable workspace member still names the previous version
    When the lockstep check inspects it against the new commitizen version
    Then it reports the member, both versions and the command that fixes it, so the
    drift fails the PR instead of turning up as a dirty tree on a checkout.
    """
    problems = check_uv_lock("19.9.1", LOCK_TEMPLATE.format(member="19.9.0"))

    assert len(problems) == 1
    assert "the-loopy-one" in problems[0]
    assert "19.9.0" in problems[0] and "19.9.1" in problems[0]
    assert "uv lock" in problems[0]


def test_registry_package_versions_are_not_required_to_match():
    """Scenario: the lockfile pins ~70 third-party packages at their own versions.

    Given a lockfile whose member is in step and whose registry packages are not
    When the lockstep check inspects it
    Then only the editable workspace member is considered, so `fastapi 0.110.0`
    alongside a release at 19.9.1 is not drift.
    """
    assert check_uv_lock("19.9.1", LOCK_TEMPLATE.format(member="19.9.1")) == []


def test_lockfile_without_a_workspace_member_is_reported():
    """Scenario: the workspace layout changed and the check silently matches nothing.

    Given a lockfile with no editable workspace member
    When the lockstep check inspects it
    Then it reports that rather than passing — a guard that matches nothing is the
    same silent pass that let the plugin manifests drift in the first place.
    """
    problems = check_uv_lock("19.9.1", "version = 1\nrevision = 3\n")

    assert len(problems) == 1
    assert "no editable workspace member" in problems[0]
