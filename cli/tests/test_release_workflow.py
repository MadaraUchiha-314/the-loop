"""Release workflow guard: a release can never publish a tag that `main` does not carry.

Two merges landing back to back left `v19.22.0` on the remote pointing at a bump commit
that never reached `main` (issue-460). The run for the first merge had checked out its
own event SHA, so it was already behind by the time it pushed. Its push named the branch
and the tag together without `--atomic`, so git accepted the tag and rejected the
branch. Every later run then recomputed 19.22.0 from `.cz.toml` and died on
"tag already exists".

No harness runs a GitHub Actions job locally, so these tests read `release.yml` itself
and hold the two properties that close the hole.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"


def _release_steps() -> list[dict]:
    workflow = yaml.safe_load(RELEASE_WORKFLOW.read_text())
    return workflow["jobs"]["release"]["steps"]


def test_release_builds_on_the_tip_of_main_not_the_event_sha() -> None:
    """A queued run must start from the bump commit the run before it pushed."""
    checkout = next(
        s
        for s in _release_steps()
        if str(s.get("uses", "")).startswith("actions/checkout@")
    )
    assert checkout["with"]["ref"] == "main"


def test_bump_commit_and_tag_are_pushed_atomically() -> None:
    """A rejected branch update must not leave its tag behind on the remote."""
    pushes = [s for s in _release_steps() if "git push" in str(s.get("run", ""))]
    assert pushes, "release.yml no longer pushes the bump commit"
    for step in pushes:
        assert "--atomic" in step["run"], (
            f"non-atomic push in step {step.get('name')!r}"
        )
