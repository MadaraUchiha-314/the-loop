"""Version-lockstep guard: every `.cz.toml` version_files target carries the version.

`cz bump` rewrites a version_files entry by replacing the CURRENT version string on
lines matching the entry's pattern — a drifted file is silently left behind at release
time (how the plugin manifests sat at 0.1.0 while releases reached 0.7.0, issue #46).
Running the check inside the CLI test suite means the existing pytest pre-commit hook
and CI gate every PR on it, with no extra pipeline wiring.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK_SCRIPT = REPO_ROOT / "scripts" / "check_version_lockstep.py"


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
