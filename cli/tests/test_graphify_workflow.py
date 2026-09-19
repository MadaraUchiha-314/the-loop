"""The knowledge-graph workflow's invariants (issue-385).

``.github/workflows/graphify.yml`` rebuilds graphify's knowledge graph of this repository
on every merge to ``main`` and commits the result back. Two of its properties are security
properties, and a workflow file has no other test:

- the Anthropic key reaches exactly one job, and that job never runs for a pull request,
  so a fork cannot borrow the secret by editing the pipeline;
- the only job with write access to the repository is that same job.

The rest pins what a reviewer would otherwise re-read on every change: the graph is built
by a pinned graphify with the Anthropic SDK beside it, the output is committed through
``scripts/graphify-commit.sh`` and never by an inline ``git push``, the generated tree is
kept out of markdownlint and its caches out of git.

Pure filesystem reads: no network, no subprocess, no fixtures.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "graphify.yml"
COMMIT_SCRIPT = REPO_ROOT / "scripts" / "graphify-commit.sh"
GITIGNORE = REPO_ROOT / ".gitignore"
MARKDOWNLINT = REPO_ROOT / ".markdownlint-cli2.jsonc"
MAKEFILE = REPO_ROOT / "Makefile"

pytestmark = pytest.mark.skipif(
    not (REPO_ROOT / ".github").is_dir(),
    reason="repository workflows not present (source distribution)",
)


def _workflow() -> dict:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # YAML 1.1 reads a bare ``on`` key as the boolean True; accept either spelling.
    data["on"] = data.get("on", data.get(True))
    return data


def _steps_text(job: dict) -> str:
    return json.dumps(job.get("steps", []))


# ---------------------------------------------------------------------- triggers


def test_the_graph_is_rebuilt_on_main_and_never_from_a_pull_request() -> None:
    """R1.1/R3.1: the LLM-backed rebuild runs for a push to ``main`` and a manual
    dispatch only; the pull-request path is a separate, secret-free rehearsal."""
    wf = _workflow()
    on = wf["on"]
    assert on["push"]["branches"] == ["main"]
    assert "workflow_dispatch" in on
    assert set(on) == {"push", "pull_request", "workflow_dispatch"}
    # A pull request rehearses only when the pipeline itself changes.
    assert set(on["pull_request"]["paths"]) == {
        ".github/workflows/graphify.yml",
        "scripts/graphify-commit.sh",
    }


def test_rebuilds_queue_rather_than_cancel_each_other() -> None:
    """R1.4: a rebuild in flight is never cancelled by the next merge — the queued run
    picks up the newer tree, and the tokens already spent are not thrown away."""
    wf = _workflow()
    assert wf["concurrency"] == {"group": "graphify", "cancel-in-progress": False}


# ---------------------------------------------------------------------- the secret


def test_the_api_key_reaches_exactly_the_rebuild_job() -> None:
    """R3.1/R3.2 (abuse case 1): ``ANTHROPIC_API_KEY`` is read from a secret in the
    ``rebuild`` job only, and that job is conditioned away for pull requests."""
    wf = _workflow()
    jobs = wf["jobs"]
    assert set(jobs) == {"dry-run", "rebuild"}

    rebuild = jobs["rebuild"]
    assert "github.event_name != 'pull_request'" in rebuild["if"]
    assert rebuild["environment"] == "graphify"
    assert "secrets.ANTHROPIC_API_KEY" in _steps_text(rebuild)

    dry_run = jobs["dry-run"]
    assert "github.event_name == 'pull_request'" in dry_run["if"]
    assert "secrets." not in _steps_text(dry_run), (
        "the pull-request rehearsal must reference no secret at all"
    )
    assert "environment" not in dry_run


def test_write_access_is_confined_to_the_rebuild_job() -> None:
    """R3.3: the workflow's default permission is read-only; ``contents: write`` is
    granted to the job that commits the graph and to nothing else."""
    wf = _workflow()
    assert wf["permissions"] == {"contents": "read"}
    jobs = wf["jobs"]
    assert jobs["rebuild"]["permissions"] == {"contents": "write"}
    assert "permissions" not in jobs["dry-run"]


# ---------------------------------------------------------------------- the build


def test_graphify_is_pinned_and_carries_the_anthropic_sdk() -> None:
    """R1.2/R2.1: both jobs install one pinned graphify with the ``anthropic`` package
    beside it — the ``claude`` backend imports it, and the tool has no extra that does."""
    wf = _workflow()
    version = wf["env"]["GRAPHIFY_VERSION"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", str(version)), version
    for name, job in wf["jobs"].items():
        text = _steps_text(job)
        assert "--with anthropic" in text, f"{name}: anthropic SDK not installed"
        assert "graphifyy==${GRAPHIFY_VERSION}" in text, f"{name}: graphify not pinned"


def test_the_rebuild_extracts_with_claude_then_names_the_communities() -> None:
    """R2.1/R2.2: the rebuild runs ``graphify extract`` with the ``claude`` backend and
    the pinned model, then ``cluster-only`` with the same backend for the report."""
    wf = _workflow()
    text = _steps_text(wf["jobs"]["rebuild"])
    assert 'graphify extract . --backend claude --model \\"$GRAPHIFY_MODEL\\"' in text
    assert (
        'graphify cluster-only . --backend claude --model \\"$GRAPHIFY_MODEL\\"' in text
    )
    assert re.fullmatch(r"claude-[a-z0-9-]+", wf["env"]["GRAPHIFY_MODEL"])
    # The failure an operator will hit first is a missing secret; it is named, not
    # left to a stack trace three steps later.
    assert "ANTHROPIC_API_KEY is not set" in text


def test_the_rehearsal_builds_without_an_llm_and_pushes_nothing() -> None:
    """R1.3: the pull-request job runs the AST-only pipeline and never calls the
    commit script."""
    wf = _workflow()
    text = _steps_text(wf["jobs"]["dry-run"])
    assert "graphify extract . --code-only" in text
    assert "graphify cluster-only . --no-label" in text
    assert "graphify-commit.sh" not in text
    assert "git push" not in text


def test_the_graph_is_committed_through_the_script_only() -> None:
    """R1.5: the push back to ``main`` goes through ``scripts/graphify-commit.sh`` — the
    one place the rebase-and-retry lives and the one the integration suite drives."""
    wf = _workflow()
    text = _steps_text(wf["jobs"]["rebuild"])
    assert "scripts/graphify-commit.sh main" in text
    assert "git push" not in text
    # The semantic cache is carried by the Actions cache, never committed (decision-133
    # D4) — restored before the extraction and saved even when a later step fails, so a
    # red run does not cost the next one a full re-extraction.
    assert "actions/cache/restore@" in text
    assert "actions/cache/save@" in text
    assert '"path": "graphify-out/cache"' in text
    save = next(
        s
        for s in wf["jobs"]["rebuild"]["steps"]
        if "actions/cache/save" in s.get("uses", "")
    )
    assert save["if"] == "always()"
    assert COMMIT_SCRIPT.is_file()
    assert COMMIT_SCRIPT.stat().st_mode & 0o111, "the commit script must be executable"


# ---------------------------------------------------------------------- the tree


def test_generated_caches_and_machine_sidecars_are_ignored() -> None:
    """R1.6: what graphify regenerates in seconds, and what names this machine, stays
    out of git; what carries information across runs is tracked."""
    text = GITIGNORE.read_text(encoding="utf-8")
    for pattern in (
        "graphify-out/cache/",
        "graphify-out/.graphify_*",
        "!graphify-out/.graphify_labels.json",
        "!graphify-out/.graphify_labels.json.sig",
    ):
        assert re.search(rf"^{re.escape(pattern)}\s*$", text, re.MULTILINE), pattern


def test_the_generated_report_is_not_linted() -> None:
    """R1.6: ``GRAPH_REPORT.md`` is generated; the source is linted, not the output —
    the same rule the synced reference copy already follows."""
    text = MARKDOWNLINT.read_text(encoding="utf-8")
    assert '"graphify-out/**"' in text


def test_the_local_refresh_is_the_same_pipeline() -> None:
    """R1.3: ``make graph`` runs the no-LLM half of what CI runs, from the root."""
    text = MAKEFILE.read_text(encoding="utf-8")
    assert re.search(r"^graph:\n(\t.*\n)+", text, re.MULTILINE)
    assert "graphify extract . --code-only" in text
    assert "graphify cluster-only . --no-label" in text
