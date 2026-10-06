"""The CI gate's parts, alone (issue-462, T7/T9).

``classify`` reads a CI webhook into one signal; ``CiBudget`` counts a check's
failing commits and decides what is delivered; ``render_section`` is what the
session reads. The dispatcher wiring is ``test_ci_autofix_integration.py``'s.
"""

from __future__ import annotations

import pytest

from the_loop.webhook import cimonitor
from the_loop.webhook.cimonitor import CiBudget, CiConfig, CiSignal
from the_loop.webhook.dispatcher import RoutingConfig

PR = "github:octo/repo#12"


def classify(event, payload) -> CiSignal:
    got = cimonitor.classify(event, payload)
    assert got is not None
    return got


def check_run(conclusion="failure", status="completed", action="completed", **extra):
    run = {
        "id": 77,
        "name": "test (3.12)",
        "status": status,
        "conclusion": conclusion if status == "completed" else None,
        "head_sha": "1a2b3c4d" * 5,
        "html_url": "https://github.com/octo/repo/actions/runs/1/job/77",
        "pull_requests": [{"number": 12}],
        "check_suite": {"head_branch": "feature-x"},
    }
    run.update(extra)
    return {
        "action": action,
        "check_run": run,
        "repository": {"full_name": "octo/repo"},
    }


def signal(kind="failure", sha="a" * 40, name="test"):
    return CiSignal(
        kind=kind,
        name=name,
        conclusion="failure" if kind == "failure" else "success",
        head_sha=sha,
        url="",
        pull_number=12,
    )


# -- classify --------------------------------------------------------------------


@pytest.mark.parametrize(
    "conclusion", ["failure", "timed_out", "action_required", "startup_failure"]
)
def test_a_completed_check_run_that_failed_is_a_failure(conclusion):
    got = classify("check_run", check_run(conclusion))
    assert got is not None and got.kind == "failure"
    assert got.name == "test (3.12)"
    assert got.head_sha == "1a2b3c4d" * 5
    assert got.url == "https://github.com/octo/repo/actions/runs/1/job/77"
    assert got.pull_number == 12
    assert got.conclusion == conclusion


@pytest.mark.parametrize("conclusion", ["success", "neutral", "skipped"])
def test_a_completed_check_run_that_passed_is_a_success(conclusion):
    assert classify("check_run", check_run(conclusion)).kind == "success"


@pytest.mark.parametrize(
    "payload",
    [
        check_run(status="queued", action="created"),
        check_run(status="in_progress", action="created"),
        check_run("cancelled"),
        check_run("stale"),
        check_run(action="rerequested"),
    ],
)
def test_a_running_cancelled_or_stale_check_run_is_ignored(payload):
    assert classify("check_run", payload).kind == "ignored"


@pytest.mark.parametrize(
    "state, kind",
    [
        ("failure", "failure"),
        ("error", "failure"),
        ("success", "success"),
        ("pending", "ignored"),
    ],
)
def test_a_commit_status_by_its_state(state, kind):
    payload = {
        "state": state,
        "context": "ci/jenkins",
        "sha": "b" * 40,
        "target_url": "https://jenkins.example/1",
        "repository": {"full_name": "octo/repo"},
    }
    got = classify("status", payload)
    assert got.kind == kind
    assert got.name == "ci/jenkins" and got.pull_number is None


@pytest.mark.parametrize("event", ["check_suite", "workflow_run"])
def test_an_aggregate_is_always_ignored(event):
    payload = {
        "action": "completed",
        event: {"conclusion": "failure", "head_sha": "c" * 40},
        "repository": {"full_name": "octo/repo"},
    }
    assert classify(event, payload).kind == "ignored"


def test_a_check_run_without_a_name_or_sha_is_ignored():
    assert classify("check_run", check_run(name="")).kind == "ignored"
    assert classify("check_run", check_run(head_sha="")).kind == "ignored"


def test_a_forks_check_run_names_no_pull_request():
    got = classify("check_run", check_run(pull_requests=[]))
    assert got.kind == "failure" and got.pull_number is None


def test_a_non_ci_event_is_not_classified():
    assert cimonitor.classify("issue_comment", {"comment": {"body": "x"}}) is None


# -- the budget ------------------------------------------------------------------


def test_each_new_failing_commit_is_the_next_attempt_until_the_notice():
    budget = CiBudget()
    verdicts = [budget.observe(PR, signal(sha=c * 40), 3) for c in "abcdef"]
    assert [(v.deliver, v.attempt, v.exhausted) for v in verdicts] == [
        (True, 1, False),
        (True, 2, False),
        (True, 3, False),
        (True, 4, True),  # the one "attempts spent" notice
        (False, 5, False),
        (False, 6, False),
    ]
    assert verdicts[4].reason == cimonitor.REASON_EXHAUSTED


def test_a_failure_again_on_a_counted_commit_keeps_its_attempt():
    budget = CiBudget()
    budget.observe(PR, signal(sha="a" * 40), 3)
    budget.observe(PR, signal(sha="b" * 40), 3)
    again = budget.observe(PR, signal(sha="a" * 40), 3)
    assert (again.deliver, again.attempt) == (True, 1)


def test_the_notice_is_given_once_even_for_a_rerun_of_its_commit():
    budget = CiBudget()
    for c in "ab":
        budget.observe(PR, signal(sha=c * 40), 1)
    rerun = budget.observe(PR, signal(sha="b" * 40), 1)
    assert rerun.deliver is False and rerun.reason == cimonitor.REASON_EXHAUSTED


def test_a_pass_resets_the_count():
    budget = CiBudget()
    for c in "ab":
        budget.observe(PR, signal(sha=c * 40), 3)
    passed = budget.observe(PR, signal("success", sha="c" * 40), 3)
    assert passed.deliver is False and passed.reason == cimonitor.REASON_NOT_ACTIONABLE
    assert budget.observe(PR, signal(sha="d" * 40), 3).attempt == 1


def test_an_ignored_signal_neither_counts_nor_resets():
    budget = CiBudget()
    budget.observe(PR, signal(sha="a" * 40), 3)
    ignored = budget.observe(PR, signal("ignored", sha="b" * 40), 3)
    assert (
        ignored.deliver is False and ignored.reason == cimonitor.REASON_NOT_ACTIONABLE
    )
    assert budget.observe(PR, signal(sha="c" * 40), 3).attempt == 2


def test_checks_and_pull_requests_are_counted_apart():
    budget = CiBudget()
    budget.observe(PR, signal(sha="a" * 40, name="lint"), 3)
    assert budget.observe(PR, signal(sha="b" * 40, name="test"), 3).attempt == 1
    other = "github:octo/repo#13"
    assert budget.observe(other, signal(sha="b" * 40, name="lint"), 3).attempt == 1


def test_the_least_recently_seen_check_is_forgotten_when_the_budget_is_full():
    budget = CiBudget(max_keys=2)
    budget.observe(PR, signal(sha="a" * 40, name="one"), 3)
    budget.observe(PR, signal(sha="a" * 40, name="two"), 3)
    budget.observe(PR, signal(sha="b" * 40, name="one"), 3)  # "one" seen last
    budget.observe(PR, signal(sha="a" * 40, name="three"), 3)  # evicts "two"
    assert budget.observe(PR, signal(sha="c" * 40, name="one"), 3).attempt == 3
    assert budget.observe(PR, signal(sha="b" * 40, name="two"), 3).attempt == 1


# -- the frame -------------------------------------------------------------------


def test_the_section_names_the_check_the_commit_the_attempt_and_the_command():
    failed = classify("check_run", check_run())
    verdict = CiBudget().observe(PR, failed, 3)
    text = cimonitor.render_section(failed, verdict, 3, PR)
    assert "attempt 1 of 3" in text
    assert "`test (3.12)`" in text and "`1a2b3c4`" in text
    assert "https://github.com/octo/repo/actions/runs/1/job/77" in text
    assert f"the-loop pr checks {PR} --failing" in text
    assert "untrusted" in text
    assert "Never skip, disable or delete a test" in text


def test_the_spent_section_says_stop_and_escalate():
    budget = CiBudget()
    budget.observe(PR, signal(sha="a" * 40), 1)
    verdict = budget.observe(PR, signal(sha="b" * 40), 1)
    text = cimonitor.render_section(signal(sha="b" * 40), verdict, 1, PR)
    assert "stop and escalate" in text
    assert "failed on 2 different commits" in text
    assert "routing.ci.maxAttempts" in text and "the-loop comment" in text


def test_without_a_pull_request_the_command_names_a_placeholder():
    failed = classify("check_run", check_run(pull_requests=[]))
    verdict = CiBudget().observe("github:octo/repo#15", failed, 3)
    text = cimonitor.render_section(failed, verdict, 3, "")
    assert "the-loop pr checks <your pull request> --failing" in text


# -- configuration ---------------------------------------------------------------


def test_routing_ci_defaults_to_autofix_with_three_attempts():
    config = RoutingConfig.from_mapping({})
    assert config.ci == CiConfig(autofix=True, max_attempts=3)


def test_routing_ci_is_read_from_the_mapping():
    config = RoutingConfig.from_mapping({"ci": {"autofix": False, "maxAttempts": 5}})
    assert config.ci == CiConfig(autofix=False, max_attempts=5)


def test_an_unusable_max_attempts_falls_back_to_the_default():
    assert CiConfig.from_mapping({"maxAttempts": 0}).max_attempts == 3
    assert CiConfig.from_mapping({"maxAttempts": "x"}).max_attempts == 3


def test_the_schema_takes_routing_ci_and_refuses_a_budget_of_zero():
    from the_loop import configschema
    from the_loop.migrations import CURRENT_CONFIG_VERSION

    def errors(ci):
        return configschema.validate(
            {"version": CURRENT_CONFIG_VERSION, "routing": {"ci": ci}}
        )

    assert errors({"autofix": False, "maxAttempts": 5}) == []
    assert errors({"maxAttempts": 0})
    assert errors({"retries": 2})
