"""T11 ticket-side run against the Jira Cloud sandbox, project LOOPTEST.

Drives the-loop's own JiraClient / JiraProvider / JiraPollProvider. Prints no secret,
no site host and no account id. Writes raw captures (redacted) under OUT for evidence.
Deletes the test ticket at the end, whatever happens.
"""

import json
import os
import re
import sys
import time
from pathlib import Path

from the_loop.authz import JIRA_SELF_MARKER, is_self_authored
from the_loop.graph.integrations.jira import JiraProvider
from the_loop.jiraapi import JiraApiConfig, JiraClient
from the_loop.jiraformat import from_jira
from the_loop.poller.jira import JiraPollProvider
from the_loop.sessions import WorkItemRef

FIX = Path(sys.argv[1])  # cli/tests/fixtures/jira
OUT = Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)

site = re.sub(r"^https?://", "", os.environ["JIRA_SANDBOX_SITE"]).strip("/").lower()
PROJECT = os.environ.get("T11_PROJECT", "LOOPTEST")
LABELS = ["the-loop: auto-execute"]
cfg_doc = {
    "integrations": {
        "jira": {
            "site": site,
            "deployment": "cloud",
            "api": {"emailEnv": ["JIRA_EMAIL"], "tokenEnv": ["JIRA_API_TOKEN"]},
            "projects": {PROJECT: {"repository": "MadaraUchiha-314/the-loop"}},
        }
    }
}
cfg = JiraApiConfig.from_cli_config(cfg_doc)
client = JiraClient(cfg)
provider = JiraProvider(client=client)
poller = JiraPollProvider([PROJECT], LABELS, site, client)
me = client.myself()


def redact(text: str) -> str:
    text = text.replace(site, "<sandbox>")
    text = text.replace(me, "<service-account-id>")
    return re.sub(r"[0-9a-f]{24}|[0-9]{6}:[0-9a-f-]{36}", "<account-id>", text)


def save(name: str, data) -> None:
    raw = (
        data
        if isinstance(data, str)
        else json.dumps(data, indent=2, ensure_ascii=False)
    )
    (OUT / name).write_text(redact(raw))


results = []


def step(name, ok, note=""):
    results.append({"step": name, "ok": bool(ok), "note": note})
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {note}")


key = None
try:
    issue = client.create_issue(
        PROJECT,
        "the-loop T11 probe (issue-475) — safe to delete",
        "Created by the-loop's T11 verification. Deleted at teardown.",
    )
    key = issue.key
    ref = WorkItemRef.parse(f"jira:{site}/{key}")
    step("create ticket", key.startswith(PROJECT + "-"), f"key {PROJECT}-<n>")

    # 1. Comment: a real the-loop body (the phase-selection checklist read-back).
    checklist_md = (FIX / "checklist.read.txt").read_text()
    res = provider.call("add-comment", ref=ref.ref, body=checklist_md)
    step("add-comment (checklist body, ADF)", res.get("result", {}).get("html_url"))
    briefing_md = (FIX / "pr-briefing.read.txt").read_text()
    provider.call("add-comment", ref=ref.ref, body=briefing_md)

    # 2. Read back via the SDK: raw ADF + Jira's own HTML rendering.
    sdk = client.sdk()
    raw = sdk._get_json(f"issue/{key}/comment", params={"expand": "renderedBody"})
    comments = raw.get("comments") or []
    save("checklist.posted.adf.json", comments[0]["body"])
    save("checklist.rendered.html", comments[0].get("renderedBody", ""))
    save("pr-briefing.rendered.html", comments[1].get("renderedBody", ""))
    adf = json.dumps(comments[0]["body"])
    step("Jira stored a taskList (real checkboxes)", '"taskList"' in adf)
    rendered = comments[1].get("renderedBody", "")
    step(
        "Jira renders tables/headings/code from ADF",
        "<table" in rendered
        and "<h" in rendered
        and ("<pre" in rendered or "code" in rendered),
    )
    step(
        "self-marker survives storage",
        JIRA_SELF_MARKER in from_jira(comments[0]["body"]),
    )

    # 3. Author id == myself; the-loop's own comment is recognised as self.
    author = comments[0]["author"]["accountId"]
    step("comment author == myself", author == me)
    ours = client.comments(key)
    step("JiraComment.is_self on our comment", all(c.is_self for c in ours))
    step("is_self_authored(read-back body)", is_self_authored(ours[0].body_md))

    # 4. Labels through the provider (Jira-safe mapping on the way out).
    provider.call("set-labels", ref=ref.ref, labels=["loop:implementation", *LABELS])
    labels = provider.call("get-labels", ref=ref.ref)["labels"]
    save("labels.json", labels)
    step(
        "set-labels (Jira-safe)",
        "the-loop:auto-execute" in labels and "loop:implementation" in labels,
        f"labels={sorted(labels)}",
    )
    provider.call("remove-label", ref=ref.ref, label="loop:implementation")
    labels2 = provider.call("get-labels", ref=ref.ref)["labels"]
    step("remove-label", "loop:implementation" not in labels2)

    # 5. The poller's JQL finds the armed ticket (search index can lag a few seconds).
    found = False
    for _ in range(10):
        items = poller.list_work_items()
        if any(i.ref == ref.ref for i in items):
            found = True
            break
        time.sleep(3)
    step("poller lists the armed ticket via /search/jql", found)
    if found:
        item = next(i for i in poller.list_work_items() if i.ref == ref.ref)
        pc = poller.list_comments(item)
        step(
            "poller reads comments; ours dropped as self",
            len(pc) >= 2 and all(getattr(c, "author", "") for c in pc),
        )

    # 6. Tick a box in Jira (API edit of the stored ADF, taskItem state TODO→DONE),
    #    then read it back as Markdown.
    body = comments[0]["body"]

    def tick_first(node):
        if isinstance(node, dict):
            if (
                node.get("type") == "taskItem"
                and node.get("attrs", {}).get("state") == "TODO"
            ):
                node["attrs"]["state"] = "DONE"
                return True
            return any(tick_first(c) for c in node.get("content", []))
        return False

    tick_first(body)
    sdk._session.put(
        sdk._get_url(f"issue/{key}/comment/{comments[0]['id']}"),
        data=json.dumps({"body": body}),
    )
    back = client.comments(key)[0].body_md
    save("checklist.after-tick.read.md", back)
    step(
        "ticked taskItem reads back as `- [x]`",
        re.search(r"^\s*- \[x\] ", back, re.M) is not None,
    )

    # 7. Transition to Done through the provider; closure seen by the poller.
    res = provider.call("transition", ref=ref.ref, to="done")
    step(
        "transition to done",
        res.get("result") == "ok",
        f"via {res.get('transition')!r}",
    )
    closure = poller.closure(ref)
    step(
        "poller sees closure (statusCategory done)",
        closure is not None and closure.state == "closed",
    )
except Exception as exc:  # noqa: BLE001
    step("unexpected error", False, redact(f"{type(exc).__name__}: {exc}"))
finally:
    if key:
        try:
            client.sdk().issue(key).delete()
            step("teardown: delete test ticket", True)
        except Exception as exc:  # noqa: BLE001
            step("teardown: delete test ticket", False, redact(type(exc).__name__))
    save("results.json", results)
    sys.exit(0 if all(r["ok"] for r in results) else 1)
