/**
 * The join is the only real logic in this app, so it is the thing worth pinning:
 * the four records the API serves, keyed differently, becoming one row.
 */

import { describe, expect, it } from "vitest";

import {
  attentionEntries,
  awaitingInput,
  buildWorkItemViews,
  innerKey,
  parseRef,
  questionOf,
  railFromStatus,
  railProgress,
  relativeTime,
  rowFlag,
  sessionTree,
  shortRef,
  specId,
  transcriptPath,
  transcriptThread,
} from "./model.ts";
import type { GraphStatus, SessionRecord, WorkItemRecord } from "./types.ts";

describe("parseRef", () => {
  it("reads a github.com ref, whose host is unwritten", () => {
    expect(parseRef("github:octo/repo#15")).toEqual({
      provider: "github",
      host: "github.com",
      owner: "octo",
      repo: "repo",
      number: 15,
      ref: "github:octo/repo#15",
    });
  });

  it("reads a GitHub Enterprise ref, whose host is written", () => {
    expect(parseRef("github:ghe.corp.example/octo/repo#15")).toMatchObject({
      host: "ghe.corp.example",
      owner: "octo",
      repo: "repo",
      number: 15,
    });
  });

  it("refuses anything that is not <provider>:[<host>/]<owner>/<repo>#<number>", () => {
    expect(parseRef("octo/repo#15")).toBeNull();
    expect(parseRef("github:repo#15")).toBeNull();
    expect(parseRef("github:a/b/c/d#15")).toBeNull();
    expect(parseRef("github:octo/repo#abc")).toBeNull();
  });

  it("shortens a ref for the board, and passes unparseable input through", () => {
    expect(shortRef("github:octo/loop-lab#214")).toBe("loop-lab#214");
    expect(shortRef("not-a-ref")).toBe("not-a-ref");
  });
});

describe("specId", () => {
  it("prefers the id the record froze at phase-selection", () => {
    expect(specId({ ref: "github:octo/repo#15", graph: { workItem: "issue-15-renamed" } })).toBe("issue-15-renamed");
  });

  it("falls back to the issue-<number> convention before the gate is answered", () => {
    expect(specId({ ref: "github:octo/repo#15" })).toBe("issue-15");
  });

  it("has no answer for a ref it cannot parse", () => {
    expect(specId({ ref: "garbage" })).toBeNull();
  });
});

describe("transcriptPath", () => {
  it("derives the Claude Code JSONL from the cwd and the pre-assigned session id", () => {
    // Per-character munge, matching the harness's real layout and the
    // server-side derivation behind /sessions/transcript (issue-209): the
    // `/.` in the hidden directory becomes `--`, not one collapsed dash.
    expect(
      transcriptPath({
        workItem: { ref: "github:octo/repo#15", provider: "github", owner: "octo", repo: "repo", number: 15 },
        harness: "claude",
        harnessSessionId: "0f1c2d3e",
        cwd: "/Users/you/.the-loop/workspace/github.com/octo/repo/issue-15",
        status: "active",
      }),
    ).toBe("~/.claude/projects/-Users-you--the-loop-workspace-github-com-octo-repo-issue-15/0f1c2d3e.jsonl");
  });

  it("has no answer for cursor, whose chat store is undocumented", () => {
    expect(
      transcriptPath({
        workItem: { ref: "github:octo/repo#15", provider: "github", owner: "octo", repo: "repo", number: 15 },
        harness: "cursor",
        harnessSessionId: "abc",
        cwd: "/tmp/x",
        status: "active",
      }),
    ).toBeNull();
  });
});

describe("transcriptThread", () => {
  it("projects text, tool uses and timestamps into rows with per-tool summaries", () => {
    const rows = transcriptThread([
      {
        type: "assistant",
        timestamp: "2026-08-12T10:00:05Z",
        message: {
          role: "assistant",
          content: [
            { type: "text", text: "Reading the test first." },
            { type: "tool_use", id: "t1", name: "Read", input: { file_path: "cli/tests/test_x.py" } },
          ],
        },
      },
    ]);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      kind: "assistant",
      time: "2026-08-12T10:00:05Z",
      text: "Reading the test first.",
    });
    expect(rows[0]!.tools).toEqual([
      {
        id: "t1",
        name: "Read",
        summary: "cli/tests/test_x.py",
        input: JSON.stringify({ file_path: "cli/tests/test_x.py" }, null, 2),
        result: "",
        isError: false,
      },
    ]);
  });

  it("folds a tool result into the call it answers, matched by id, and emits no row for it", () => {
    const rows = transcriptThread([
      {
        type: "assistant",
        message: {
          content: [
            { type: "tool_use", id: "a", name: "Bash", input: { command: "pytest -q" } },
            { type: "tool_use", id: "b", name: "Grep", input: { pattern: "flaky" } },
          ],
        },
      },
      // Results arrive out of order — pairing is by id, not adjacency.
      { type: "user", message: { content: [{ type: "tool_result", tool_use_id: "b", content: "3 matches" }] } },
      {
        type: "user",
        message: {
          content: [
            { type: "tool_result", tool_use_id: "a", content: [{ type: "text", text: "1 failed" }], is_error: true },
          ],
        },
      },
    ]);
    expect(rows).toHaveLength(1);
    const [bash, grep] = rows[0]!.tools;
    expect(bash).toMatchObject({ name: "Bash", summary: "pytest -q", result: "1 failed", isError: true });
    expect(grep).toMatchObject({ name: "Grep", summary: "flaky", result: "3 matches", isError: false });
  });

  it("renders an orphan tool result as its own row, never blank — the issue-230 bug", () => {
    const rows = transcriptThread([
      { type: "user", message: { content: [{ type: "tool_result", tool_use_id: "gone", content: "def test_x(): ..." }] } },
      { type: "user", message: { content: [{ type: "tool_result", content: [] }] } },
    ]);
    expect(rows[0]).toMatchObject({ kind: "tool result", text: "def test_x(): ..." });
    expect(rows[1]).toMatchObject({ kind: "tool result", text: "(no output)" });
  });

  it("captures thinking blocks collapsed rather than dropping them", () => {
    const rows = transcriptThread([
      {
        type: "assistant",
        message: { content: [{ type: "thinking", thinking: "The failure smells like a fixture." }] },
      },
    ]);
    expect(rows[0]).toMatchObject({ kind: "assistant", thinking: "The failure smells like a fixture.", text: "" });
  });

  it("labels bookkeeping and unknown shapes as meta rows, and keeps malformed lines", () => {
    const rows = transcriptThread([
      { malformed: "not json {" },
      { type: "summary", summary: "Session compacted." },
      { unrecognised: true },
      { type: "system", message: { content: "hook output" } },
    ]);
    expect(rows[0]).toMatchObject({ kind: "malformed", text: "not json {" });
    expect(rows[1]).toMatchObject({ kind: "meta", label: "summary", text: "Session compacted." });
    expect(rows[2]).toMatchObject({ kind: "meta", label: "entry" });
    expect(rows[3]).toMatchObject({ kind: "meta", label: "system", text: "hook output" });
  });

  it("falls back to compact JSON for a tool the summary table does not know", () => {
    const rows = transcriptThread([
      {
        type: "assistant",
        message: { content: [{ type: "tool_use", id: "x", name: "MysteryTool", input: { a: 1 } }] },
      },
    ]);
    expect(rows[0]!.tools[0]).toMatchObject({ name: "MysteryTool", summary: '{"a":1}' });
  });

  it("accepts string content for user turns", () => {
    const rows = transcriptThread([{ type: "user", message: { role: "user", content: "Fix the flaky test." } }]);
    expect(rows[0]).toMatchObject({ kind: "user", text: "Fix the flaky test." });
  });
});

const record = (ref: string, loop: string): WorkItemRecord => ({
  ref,
  graph: { loop, workItem: "issue-1", nodes: [] },
});

const session = (ref: string, prRefs: string[] = []): SessionRecord => ({
  ref,
  workItem: { ref, provider: "github", owner: "octo", repo: "lab", number: 1 },
  harness: "claude",
  harnessSessionId: "sid",
  status: "active",
  tmuxTarget: `tmux-${ref.split("#")[1]}`,
  pullRequests: prRefs.map((prRef) => ({
    workItem: { ref: prRef, provider: "github", owner: "octo", repo: "lab", number: 2 },
    harness: "claude",
    harnessSessionId: "sid-pr",
    status: "active",
    tmuxTarget: `tmux-${prRef.split("#")[1]}`,
  })),
});

describe("sessionTree", () => {
  it("builds a two-level tree: the outer session, then one child per PR endpoint", () => {
    const views = buildWorkItemViews({
      workItems: [record("github:octo/lab#1", "pdlc-work-item-loop")],
      sessions: [session("github:octo/lab#1", ["github:octo/lab#2"])],
      attention: [],
    });
    const tree = sessionTree(views);
    expect(tree).toHaveLength(1);
    expect(tree[0]!.adhoc).toBe(false);
    expect(tree[0]!.outer).toMatchObject({ ref: "github:octo/lab#1", scope: "outer", state: "active" });
    expect(tree[0]!.inner).toEqual([
      { ref: "github:octo/lab#2", shortRef: "lab#2", scope: "inner", state: "active", tmuxTarget: "tmux-2" },
    ]);
  });

  it("flags ad-hoc and contribution loops treeless — one session, no inner level", () => {
    for (const loop of ["pdlc-adhoc-loop", "pdlc-contribution-loop"]) {
      const views = buildWorkItemViews({
        workItems: [record("github:octo/lab#1", loop)],
        // Even a linked PR endpoint stays out of an ad-hoc item's tree.
        sessions: [session("github:octo/lab#1", ["github:octo/lab#2"])],
        attention: [],
      });
      const tree = sessionTree(views);
      expect(tree[0]!.adhoc).toBe(true);
      expect(tree[0]!.inner).toEqual([]);
    }
  });
});

function status(current: string, overrides: Partial<GraphStatus> = {}): GraphStatus {
  return {
    workItem: "issue-15",
    currentNode: current,
    ok: true,
    parked: null,
    nodes: [
      { node: "requirements-definition", status: "pass", outcome: "satisfied" },
      { node: "brainstorming", status: "skip", outcome: "skipped" },
      { node: "design", status: "pass", outcome: "satisfied" },
      { node: "implementation", status: "pass", outcome: "" },
      { node: "verification", status: "pending", outcome: "" },
    ],
    ...overrides,
  };
}

describe("railFromStatus", () => {
  it("marks passed nodes done, the pointer current, and opt-outs skipped", () => {
    const rail = railFromStatus(status("implementation"));
    expect(rail.map((node) => node.state)).toEqual(["done", "skipped", "done", "current", "pending"]);
  });

  it("draws a blocked current node as blocked, not as merely in progress", () => {
    const report = status("implementation");
    report.nodes[3] = { node: "implementation", status: "block", outcome: "blocked", messages: ["checks failing"] };
    const rail = railFromStatus(report);
    expect(rail[3]).toMatchObject({ state: "blocked", detail: "checks failing" });
  });

  it("counts progress over the nodes actually walked, ignoring skips", () => {
    expect(railProgress(railFromStatus(status("implementation")))).toBe("2/4");
  });
});

const RECORD: WorkItemRecord = {
  ref: "github:octo/repo#15",
  url: "https://github.com/octo/repo/issues/15",
  control: { command: "start", actor: "maintainer" },
  graph: { loop: "pdlc-work-item-loop", workItem: "issue-15", nodes: [{ id: "design" }] },
};

const SESSION: SessionRecord = {
  ref: "github:octo/repo#15",
  workItem: { ref: "github:octo/repo#15", provider: "github", owner: "octo", repo: "repo", number: 15 },
  harness: "claude",
  harnessSessionId: "0f1c",
  cwd: "/checkout/issue-15",
  status: "active",
  lastEventAt: "2026-08-12T10:00:00Z",
  tmuxTarget: "loop-github-octo-repo-15",
  pullRequests: [
    {
      workItem: { ref: "github:octo/repo#16", provider: "github", owner: "octo", repo: "repo", number: 16 },
      harness: "claude",
      harnessSessionId: "77ab",
      status: "active",
      tmuxTarget: "loop-github-octo-repo-16",
    },
    {
      workItem: { ref: "github:octo/docs#47", provider: "github", owner: "octo", repo: "docs", number: 47 },
      harness: "claude",
      harnessSessionId: "91d0",
      status: "active",
      tmuxTarget: "loop-github-octo-docs-47",
    },
  ],
};

describe("buildWorkItemViews", () => {
  it("joins the portable record, the session and the graph report into one row", () => {
    const [view] = buildWorkItemViews({
      workItems: [RECORD],
      sessions: [SESSION],
      attention: [],
      graphs: { outer: { "github:octo/repo#15": status("implementation") }, inner: {} },
    });

    expect(view).toMatchObject({
      shortRef: "repo#15",
      sessionState: "active",
      repoPath: "/checkout/issue-15",
      specId: "issue-15",
      currentNode: "implementation",
      progress: "2/4",
    });
  });

  it("falls back to the frozen rail for a report that carries no position at all", () => {
    // The shape `/graph/check` answers with when the checkout is gone
    // (issue-238). An empty node list is the ABSENCE of a position, so rendering
    // it as one would replace the agreed node list with a blank rail — including
    // for a client that does not know to drop it.
    const [view] = buildWorkItemViews({
      workItems: [RECORD],
      sessions: [SESSION],
      attention: [],
      graphs: {
        outer: {
          "github:octo/repo#15": {
            workItem: "issue-15",
            currentNode: "",
            ok: false,
            nodes: [],
            repoResolved: false,
          },
        },
        inner: {},
      },
    });

    expect(view!.rail.length).toBeGreaterThan(0);
    expect(view!.rail.map((node) => node.id)).toEqual(RECORD.graph!.nodes!.map((node) => node.id));
  });

  it("keeps an armed work item with no session — that is what the inbox is for", () => {
    const views = buildWorkItemViews({
      workItems: [RECORD],
      sessions: [],
      attention: [{ workItem: RECORD.ref, kind: "armed-without-session", detail: "start recorded" }],
    });
    expect(views).toHaveLength(1);
    expect(views[0]).toMatchObject({ sessionState: "none", repoPath: "" });
    // With no report, the rail still shows the phases the item froze.
    expect(views[0]!.rail.map((n) => n.id)).toEqual(["design"]);
  });

  it("keeps a session with no portable record — `sessions register` can make one", () => {
    const views = buildWorkItemViews({ workItems: [], sessions: [SESSION], attention: [] });
    expect(views).toHaveLength(1);
    expect(views[0]!.ref).toBe("github:octo/repo#15");
  });

  it("qualifies a PR by repository only when it lives somewhere else (issue-183)", () => {
    const [view] = buildWorkItemViews({ workItems: [RECORD], sessions: [SESSION], attention: [] });
    expect(view!.pullRequests.map((pr) => pr.prRepo)).toEqual(["", "octo/docs"]);
  });

  it("attaches each PR's inner-loop report under its composite key", () => {
    const [view] = buildWorkItemViews({
      workItems: [RECORD],
      sessions: [SESSION],
      attention: [],
      graphs: {
        outer: {},
        inner: { [innerKey("github:octo/repo#15", "github:octo/repo#16")]: status("verification") },
      },
    });
    expect(view!.pullRequests[0]!.status?.currentNode).toBe("verification");
    expect(view!.pullRequests[1]!.status).toBeNull();
  });
});

describe("attentionEntries", () => {
  it("folds in the graph gates /attention deliberately leaves out, urgent first", () => {
    const views = buildWorkItemViews({
      workItems: [RECORD],
      sessions: [SESSION],
      attention: [{ workItem: RECORD.ref, kind: "session-paused", detail: "session paused" }],
      graphs: {
        outer: {
          "github:octo/repo#15": status("human-approval", {
            parked: { node: "human-approval", reason: "approval required" },
          }),
        },
        inner: {},
      },
    });

    const entries = attentionEntries(views);
    expect(entries.map((entry) => entry.kind)).toEqual(["human gate", "session paused"]);
    expect(entries[0]!.detail).toBe("human-approval — approval required");
  });

  it("keeps one row per open question when /attention reports the same wait", () => {
    // issue-208: the service's `awaiting-input` kind and the event-derived
    // question entry describe the same wait; the entry with the Reply action wins.
    const views = buildWorkItemViews({
      workItems: [RECORD],
      sessions: [SESSION],
      attention: [{ workItem: RECORD.ref, kind: "awaiting-input", detail: "agent is waiting for input: ?" }],
      awaiting: { [RECORD.ref]: { ts: "2026-08-12T10:00:00Z", event: "session.awaiting_input", question: "?" } },
    });
    const entries = attentionEntries(views);
    expect(entries.map((entry) => entry.kind)).toEqual(["needs input"]);
  });

  it("keeps the raw awaiting-input row when the event window missed the question", () => {
    const views = buildWorkItemViews({
      workItems: [RECORD],
      sessions: [SESSION],
      attention: [{ workItem: RECORD.ref, kind: "awaiting-input", detail: "agent is waiting for input: ?" }],
    });
    const entries = attentionEntries(views);
    expect(entries.map((entry) => entry.kind)).toEqual(["awaiting input"]);
  });
});

describe("rowFlag", () => {
  it("ranks a human gate above a paused session", () => {
    const [view] = buildWorkItemViews({
      workItems: [RECORD],
      sessions: [{ ...SESSION, status: "paused" }],
      attention: [],
      graphs: {
        outer: { "github:octo/repo#15": status("human-approval", { parked: { node: "human-approval", reason: "x" } }) },
        inner: {},
      },
    });
    expect(rowFlag(view!)).toEqual({ label: "human gate", urgent: true });
  });

  it("has nothing to say about a healthy running item", () => {
    const [view] = buildWorkItemViews({
      workItems: [RECORD],
      sessions: [SESSION],
      attention: [],
      graphs: { outer: { "github:octo/repo#15": status("implementation") }, inner: {} },
    });
    expect(rowFlag(view!)).toBeNull();
  });
});

describe("relativeTime", () => {
  const now = new Date("2026-08-12T12:00:00Z").getTime();

  it("scales the unit to the gap", () => {
    expect(relativeTime("2026-08-12T11:59:30Z", now)).toBe("30s ago");
    expect(relativeTime("2026-08-12T11:42:00Z", now)).toBe("18m ago");
    expect(relativeTime("2026-08-12T05:00:00Z", now)).toBe("7h ago");
    expect(relativeTime("2026-08-09T12:00:00Z", now)).toBe("3d ago");
  });

  it("says nothing rather than lying about a missing or unparseable stamp", () => {
    expect(relativeTime("", now)).toBe("—");
    expect(relativeTime("whenever", now)).toBe("whenever");
  });
});

const ask = (ref: string, ts: string, question = "which one?") => ({
  ts,
  event: "session.awaiting_input",
  work_item: ref,
  question,
});
const answer = (ref: string, ts: string) => ({ ts, event: "session.reply_sent", work_item: ref });

describe("awaitingInput", () => {
  it("reads the question the proposed `the-loop ask` verb would record", () => {
    const open = awaitingInput([ask("github:octo/repo#15", "2026-08-12T10:00:00Z")]);
    expect(questionOf(open["github:octo/repo#15"])).toBe("which one?");
  });

  it("closes a question once a reply is newer than it", () => {
    expect(
      awaitingInput([ask("github:octo/repo#15", "2026-08-12T10:00:00Z"), answer("github:octo/repo#15", "2026-08-12T10:05:00Z")]),
    ).toEqual({});
  });

  it("keeps a question asked again after the last reply", () => {
    const open = awaitingInput([
      ask("github:octo/repo#15", "2026-08-12T10:00:00Z"),
      answer("github:octo/repo#15", "2026-08-12T10:05:00Z"),
      ask("github:octo/repo#15", "2026-08-12T10:09:00Z", "and now?"),
    ]);
    expect(questionOf(open["github:octo/repo#15"])).toBe("and now?");
  });

  it("finds nothing in a log from a service that has no such verb", () => {
    expect(awaitingInput([{ ts: "2026-08-12T10:00:00Z", event: "poll.cycle" }])).toEqual({});
  });

  it("falls back through the fields an event might carry the text in", () => {
    expect(questionOf({ ts: "t", event: "e", reason: "from reason" })).toBe("from reason");
    expect(questionOf(undefined)).toBe("");
  });
});

describe("rowFlag, with an open question", () => {
  it("ranks needs-input above a human gate", () => {
    const [view] = buildWorkItemViews({
      workItems: [RECORD],
      sessions: [SESSION],
      attention: [],
      awaiting: { "github:octo/repo#15": { ts: "2026-08-12T10:00:00Z", event: "session.awaiting_input", question: "?" } },
      graphs: {
        outer: { "github:octo/repo#15": status("human-approval", { parked: { node: "human-approval", reason: "x" } }) },
        inner: {},
      },
    });
    expect(rowFlag(view!)).toEqual({ label: "needs input", urgent: true });
    // …and both still reach the inbox, question first.
    expect(attentionEntries([view!]).map((e) => e.kind)).toEqual(["needs input", "human gate"]);
  });
});
