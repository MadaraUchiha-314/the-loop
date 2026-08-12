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
  shortRef,
  specId,
  transcriptPath,
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
    expect(
      transcriptPath({
        workItem: { ref: "github:octo/repo#15", provider: "github", owner: "octo", repo: "repo", number: 15 },
        harness: "claude",
        harnessSessionId: "0f1c2d3e",
        cwd: "/Users/you/.the-loop/workspace/github.com/octo/repo/issue-15",
        status: "active",
      }),
    ).toBe("~/.claude/projects/-Users-you-the-loop-workspace-github-com-octo-repo-issue-15/0f1c2d3e.jsonl");
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
