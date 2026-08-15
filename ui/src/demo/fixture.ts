/**
 * The demo dataset.
 *
 * A page served from GitHub Pages cannot reach a loopback service, so a
 * first-time visitor would otherwise meet a connection error and nothing else.
 * This fixture answers the same calls the real client does, in the same record
 * shapes, so the screens can be evaluated before anyone opens a tunnel. It is
 * always labelled: `DemoApi.isDemo` is true and the shell shows a banner.
 *
 * The scenario is the one the design was drawn against, retold with the node
 * ids the shipped graphs actually use (`cli/the_loop/graph/pdlc-work-item-loop.yaml`
 * and `pdlc-pr-loop.yaml`) so what the demo teaches transfers to a real board.
 */

import type {
  ConfigDocument,
  JsonSchema,
  AttentionItem,
  DaemonStatus,
  EventRecord,
  GraphStatus,
  NodeReport,
  SessionRecord,
  TranscriptEntry,
  WorkItemRecord,
} from "../api/types.ts";

export const OUTER_NODES = [
  "phase-selection",
  "brainstorming",
  "requirements-definition",
  "requirements-approval",
  "design",
  "design-critic-review",
  "test-planning",
  "design-approval",
  "tasks-breakdown",
  "implementation",
  "verification",
  "self-review",
  "critic-review",
  "security-review",
  "evidence",
  "capability-docs",
  "reviewer-briefing",
  "human-approval",
  "complete",
] as const;

export const INNER_NODES = [
  "implementation",
  "verification",
  "self-review",
  "critic-review",
  "security-review",
  "reviewer-briefing",
  "pr-approval",
  "complete",
] as const;

const WORKSPACE = "/Users/you/.the-loop/workspace/github.com/octo/loop-lab";

/**
 * The fixture's clock, captured once at import.
 *
 * Relative to *now* rather than a fixed date, so the demo always reads like a
 * board someone is watching ("18m ago", not "six months ago" — or, with a date
 * in the future, a column of clamped zeroes). Captured once so it is stable for
 * the lifetime of the page and for a test run.
 */
const DEMO_NOW = Date.now();

function iso(minutesAgo: number): string {
  return new Date(DEMO_NOW - minutesAgo * 60_000).toISOString();
}

/**
 * Build a report where nodes before `current` passed, `current` carries
 * `status`, and the rest are pending. `skipped` marks opt-in nodes nobody asked
 * for — the same thing a real report says when phase-selection routed past them.
 */
function report(
  workItem: string,
  nodes: readonly string[],
  current: string,
  status: string,
  options: { skipped?: string[]; parked?: { reason: string }; messages?: string[] } = {},
): GraphStatus {
  const currentIndex = nodes.indexOf(current);
  const skipped = new Set(options.skipped ?? []);
  const reports: NodeReport[] = nodes.map((node, index) => {
    if (skipped.has(node)) return { node, status: "skip", outcome: "skipped", messages: [], attempts: 0 };
    if (index < currentIndex) return { node, status: "pass", outcome: "satisfied", messages: [], attempts: 1 };
    if (index === currentIndex) {
      return { node, status, outcome: status, messages: options.messages ?? [], attempts: 1 };
    }
    return { node, status: "pending", outcome: "", messages: [], attempts: 0 };
  });
  return {
    workItem,
    currentNode: current,
    ok: status === "pass" || status === "wait",
    parked: options.parked ? { node: current, reason: options.parked.reason, since: iso(24) } : null,
    nodes: reports,
  };
}

function frozen(nodes: readonly string[], skipped: string[] = []) {
  return nodes.map((id) => ({ id, phase: id, skipped: skipped.includes(id), selectable: true }));
}

function makeWorkItem(
  number: number,
  options: { command?: string; actor?: string; polledMinutesAgo?: number; skipped?: string[] } = {},
): WorkItemRecord {
  return {
    ref: `github:octo/loop-lab#${number}`,
    url: `https://github.com/octo/loop-lab/issues/${number}`,
    control: {
      command: options.command ?? "start",
      source: "comment",
      actor: options.actor ?? "maintainer",
      requestedAt: iso(options.polledMinutesAgo ?? 120),
      note: "",
    },
    poll: { seenComments: [], commentAttempts: {}, spawn: { attempts: 0, gaveUp: false, deliveryId: "" }, lastPolledAt: iso(2) },
    graph: {
      loop: "pdlc-work-item-loop",
      workItem: `issue-${number}`,
      nodes: frozen(OUTER_NODES, options.skipped ?? []),
    },
  };
}

function endpoint(number: number, overrides: Partial<SessionRecord> = {}): SessionRecord {
  return {
    ref: `github:octo/loop-lab#${number}`,
    workItem: { ref: `github:octo/loop-lab#${number}`, provider: "github", owner: "octo", repo: "loop-lab", number },
    url: `https://github.com/octo/loop-lab/issues/${number}`,
    harness: "claude",
    harnessSessionId: `0f1c${number}a2-7b3d-4e5f-9a8b-${String(number).padStart(12, "0")}`,
    cwd: `${WORKSPACE}/issue-${number}`,
    status: "active",
    createdAt: iso(180),
    lastEventAt: iso(3),
    tmuxTarget: `loop-github-octo-loop-lab-${number}`,
    recentDeliveries: [],
    ...overrides,
  };
}

const TITLES: Record<number, string> = {
  223: "Ad-hoc: bump the CI cache key",
  214: "Control plane UI over /api/v1",
  209: "Poller heartbeat drops pid",
  205: "Session announce comment loops back",
  198: "Multi-repo PR routing for GHE hosts",
  187: "Webhook replay protection",
  219: "Rate-limit the poll ingress",
  178: "Cleanup keyword on closed items",
  181: "Evidence folder linting",
  216: "feat(api): sessions/reply — bracketed paste into the pane",
  212: "fix(poll): heartbeat carries no pid",
  207: "fix(announce): mark self-authored",
  180: "feat(cleanup): keyword + authz",
};

/**
 * Titles are GitHub's, not the-loop's — no `/api/v1` route serves them, because
 * the portable record stores the ref and the URL and deliberately not a copy of
 * the ticket's mutable fields. The demo carries them so the board reads like a
 * real one; against a live service the same column shows the ref alone.
 */
export const DEMO_TITLES: Record<string, string> = Object.fromEntries(
  Object.entries(TITLES).map(([number, title]) => [`github:octo/loop-lab#${number}`, title]),
);

/** An ad-hoc item (`the-loop do`, issue-225): one session, no inner loops. */
function makeAdhocItem(number: number): WorkItemRecord {
  return {
    ...makeWorkItem(number),
    graph: {
      loop: "pdlc-adhoc-loop",
      workItem: `issue-${number}`,
      nodes: ["work", "review", "complete"].map((id) => ({ id, phase: id, skipped: false, selectable: false })),
    },
  };
}

export const DEMO_WORK_ITEMS: WorkItemRecord[] = [
  makeWorkItem(214, { skipped: ["brainstorming"] }),
  makeAdhocItem(223),
  makeWorkItem(209, { skipped: ["brainstorming", "design-critic-review"] }),
  makeWorkItem(205, { skipped: ["brainstorming"] }),
  makeWorkItem(198, { command: "pause", polledMinutesAgo: 2880 }),
  makeWorkItem(187, { command: "start", polledMinutesAgo: 4320 }),
  makeWorkItem(219, { skipped: ["brainstorming"] }),
  makeWorkItem(178, { skipped: ["brainstorming"] }),
  makeWorkItem(181, { command: "cleanup", polledMinutesAgo: 8640 }),
];

export const DEMO_SESSIONS: SessionRecord[] = [
  endpoint(214, {
    lastEventAt: iso(4),
    pullRequests: [
      {
        workItem: { ref: "github:octo/loop-lab#216", provider: "github", owner: "octo", repo: "loop-lab", number: 216 },
        url: "https://github.com/octo/loop-lab/pull/216",
        harness: "claude",
        harnessSessionId: "77ab1c2d-3e4f-5a6b-7c8d-9e0f1a2b3c4d",
        cwd: `${WORKSPACE}/issue-214`,
        status: "active",
        createdAt: iso(140),
        lastEventAt: iso(9),
        tmuxTarget: "loop-github-octo-loop-lab-216",
        recentDeliveries: [],
      },
      {
        workItem: { ref: "github:octo/loop-docs#47", provider: "github", owner: "octo", repo: "loop-docs", number: 47 },
        url: "https://github.com/octo/loop-docs/pull/47",
        harness: "claude",
        harnessSessionId: "91d0e5f6-a7b8-4c9d-8e0f-1a2b3c4d5e6f",
        cwd: `${WORKSPACE}/issue-214`,
        status: "active",
        createdAt: iso(120),
        lastEventAt: iso(21),
        tmuxTarget: "loop-github-octo-loop-docs-47",
        recentDeliveries: [],
      },
    ],
  }),
  endpoint(209, {
    lastEventAt: iso(18),
    pullRequests: [
      {
        workItem: { ref: "github:octo/loop-lab#212", provider: "github", owner: "octo", repo: "loop-lab", number: 212 },
        url: "https://github.com/octo/loop-lab/pull/212",
        harness: "claude",
        harnessSessionId: "c3d4e5f6-a7b8-49c0-8d1e-2f3a4b5c6d7e",
        cwd: `${WORKSPACE}/issue-209`,
        status: "active",
        createdAt: iso(400),
        lastEventAt: iso(31),
        tmuxTarget: "loop-github-octo-loop-lab-212",
        recentDeliveries: [],
      },
    ],
  }),
  endpoint(205, {
    lastEventAt: iso(60),
    pullRequests: [
      {
        workItem: { ref: "github:octo/loop-lab#207", provider: "github", owner: "octo", repo: "loop-lab", number: 207 },
        url: "https://github.com/octo/loop-lab/pull/207",
        harness: "claude",
        harnessSessionId: "d4e5f6a7-b8c9-40d1-9e2f-3a4b5c6d7e8f",
        cwd: `${WORKSPACE}/issue-205`,
        status: "closed",
        createdAt: iso(900),
        lastEventAt: iso(300),
        tmuxTarget: "loop-github-octo-loop-lab-207",
        recentDeliveries: [],
      },
    ],
  }),
  endpoint(223, { lastEventAt: iso(11) }),
  endpoint(198, { status: "paused", lastEventAt: iso(2880), control: { command: "pause", source: "cli", actor: "maintainer", requestedAt: iso(2880) } }),
  endpoint(219, { lastEventAt: iso(5) }),
  endpoint(178, {
    lastEventAt: iso(31),
    pullRequests: [
      {
        workItem: { ref: "github:octo/loop-lab#180", provider: "github", owner: "octo", repo: "loop-lab", number: 180 },
        url: "https://github.com/octo/loop-lab/pull/180",
        harness: "claude",
        harnessSessionId: "e5f6a7b8-c9d0-41e2-8f3a-4b5c6d7e8f90",
        cwd: `${WORKSPACE}/issue-178`,
        status: "active",
        createdAt: iso(200),
        lastEventAt: iso(31),
        tmuxTarget: "loop-github-octo-loop-lab-180",
        recentDeliveries: [],
      },
    ],
  }),
  endpoint(181, { status: "closed", lastEventAt: iso(8640) }),
];

const SKIP_214 = ["brainstorming"];

/** Outer-loop reports, keyed by work-item ref. */
export const DEMO_OUTER_GRAPHS: Record<string, GraphStatus> = {
  "github:octo/loop-lab#214": report("issue-214", OUTER_NODES, "implementation", "pass", { skipped: SKIP_214 }),
  "github:octo/loop-lab#209": report("issue-209", OUTER_NODES, "verification", "pass", {
    skipped: ["brainstorming", "design-critic-review"],
  }),
  "github:octo/loop-lab#205": report("issue-205", OUTER_NODES, "human-approval", "wait", {
    skipped: SKIP_214,
    parked: {
      reason: "verification passed across all PRs and the review chain is complete; approving moves the item to complete",
    },
  }),
  "github:octo/loop-lab#198": report("issue-198", OUTER_NODES, "requirements-definition", "pass", { skipped: SKIP_214 }),
  "github:octo/loop-lab#187": report("issue-187", OUTER_NODES, "phase-selection", "wait", {
    parked: { reason: "awaiting the phase-selection checklist on the ticket" },
  }),
  "github:octo/loop-lab#219": report("issue-219", OUTER_NODES, "requirements-definition", "pass", { skipped: SKIP_214 }),
  "github:octo/loop-lab#178": report("issue-178", OUTER_NODES, "implementation", "block", {
    skipped: SKIP_214,
    messages: ["dispatch.failed at 10:31:02 — paste-buffer failed; will retry next cycle"],
  }),
  "github:octo/loop-lab#181": report("issue-181", OUTER_NODES, "complete", "pass", { skipped: SKIP_214 }),
};

/** Inner-loop reports, keyed by `${workItemRef}::${prRef}`. */
export const DEMO_INNER_GRAPHS: Record<string, GraphStatus> = {
  "github:octo/loop-lab#214::github:octo/loop-lab#216": report("issue-214", INNER_NODES, "verification", "pass"),
  "github:octo/loop-lab#214::github:octo/loop-docs#47": report("issue-214", INNER_NODES, "reviewer-briefing", "pass"),
  "github:octo/loop-lab#209::github:octo/loop-lab#212": report("issue-209", INNER_NODES, "pr-approval", "wait", {
    parked: { reason: "inner loop finished self, critic and security review; reviewer briefing posted on the PR" },
  }),
  "github:octo/loop-lab#205::github:octo/loop-lab#207": report("issue-205", INNER_NODES, "complete", "pass"),
  "github:octo/loop-lab#178::github:octo/loop-lab#180": report("issue-178", INNER_NODES, "implementation", "block", {
    messages: ["checks are failing on the head commit"],
  }),
};

export const DEMO_ATTENTION: AttentionItem[] = [
  {
    workItem: "github:octo/loop-lab#198",
    kind: "session-paused",
    detail: "session paused (last control: pause)",
  },
  {
    workItem: "github:octo/loop-lab#187",
    kind: "armed-without-session",
    detail: "start recorded but no live session on this machine",
  },
  {
    workItem: "github:octo/loop-lab#178",
    kind: "recent-error",
    detail: `dispatch.failed at ${iso(14)}`,
  },
];

export const DEMO_DAEMONS: DaemonStatus[] = [
  {
    daemon: "poller",
    running: true,
    pid: 4242,
    pidfile: ".the-loop/poll.pid",
    logfile: ".the-loop/logs/poller.out",
    startedAt: iso(600),
    lastCycleAt: iso(0.2),
  },
  {
    daemon: "gh-webhook",
    running: false,
    pid: 0,
    pidfile: ".the-loop/gh-webhook.pid",
    logfile: "",
    startedAt: "",
    lastCycleAt: "",
  },
];

export const DEMO_EVENTS: EventRecord[] = [
  // The event `the-loop ask` appends (issue-208): the question card lights up
  // from it, and the demo's replySession emits the reply_sent that closes it.
  {
    ts: iso(4),
    event: "session.awaiting_input",
    level: "info",
    source: "session",
    work_item: "github:octo/loop-lab#214",
    actor: "claude",
    question:
      "The reply endpoint pastes into the tmux pane. Should it require an actor login for the audit trail (the event log names who answered), or accept anonymous replies on loopback?",
    comment_url: "https://github.com/octo/loop-lab/issues/214#issuecomment-2451c8ad",
  },
  { ts: iso(4), event: "graph.parked", level: "info", source: "graph", work_item: "github:octo/loop-lab#205", node: "human-approval", reason: "awaiting a human" },
  { ts: iso(6), event: "dispatch.succeeded", level: "info", source: "poll", work_item: "github:octo/loop-lab#214", delivery_id: "2451c8ad", detail: "comment pasted into loop-github-octo-loop-lab-214" },
  { ts: iso(9), event: "graph.completed", level: "info", source: "graph", work_item: "github:octo/loop-lab#214", node: "tasks-breakdown", actor: "claude" },
  { ts: iso(14), event: "dispatch.failed", level: "error", source: "poll", work_item: "github:octo/loop-lab#178", error: "paste-buffer failed", will_retry: true },
  { ts: iso(23), event: "graph.parked", level: "info", source: "graph", work_item: "github:octo/loop-lab#209", node: "pr-approval", reason: "pr-loop #212 awaiting approval" },
  { ts: iso(31), event: "graph.blocked", level: "warning", source: "graph", work_item: "github:octo/loop-lab#178", node: "implementation", reason: "checks failing on the head commit" },
  { ts: iso(47), event: "poll.cycle", level: "info", source: "poll", detail: "8 items seen, 0 spawns, 1 forwarded" },
  { ts: iso(64), event: "session.pr_spawned", level: "info", source: "session", work_item: "github:octo/loop-docs#47", harness: "claude", tmux_target: "loop-github-octo-loop-docs-47" },
  { ts: iso(93), event: "poll.spawn_failed", level: "warning", source: "poll", work_item: "github:octo/loop-lab#187", reason: "armed but spawn budget exhausted", gave_up: false },
  { ts: iso(180), event: "session.spawned", level: "info", source: "session", work_item: "github:octo/loop-lab#214", harness: "claude", harness_session_id: "0f1c214a2", tmux_target: "loop-github-octo-loop-lab-214" },
  { ts: iso(2880), event: "session.paused", level: "info", source: "session", work_item: "github:octo/loop-lab#198", actor: "maintainer" },
  { ts: iso(8640), event: "session.cleaned", level: "info", source: "session", work_item: "github:octo/loop-lab#181", actor: "maintainer", detail: "tmux killed, checkout removed" },
];

/**
 * A short transcript in Claude Code's real line format
 * (`type` / `timestamp` / `message.content` blocks), served by the demo
 * transport for any session on the board — every shape `transcriptThread`
 * projects (issue-230): tool results paired to their calls by `tool_use_id`
 * (one an error), an orphan result whose call fell outside the tail, a
 * thinking block, a `summary` bookkeeping line, and a server-flagged
 * malformed line.
 */
export const DEMO_TRANSCRIPT: TranscriptEntry[] = [
  { type: "summary", summary: "Context compacted — 14 earlier turns summarised." },
  {
    // The call this answers sits before the served tail — it renders as its
    // own output row rather than disappearing.
    type: "user",
    timestamp: iso(43),
    message: {
      role: "user",
      content: [{ type: "tool_result", tool_use_id: "toolu_00", content: "…tail of an earlier `bun run test` run…" }],
    },
  },
  {
    type: "user",
    timestamp: iso(42),
    message: { role: "user", content: "Wire the reviewer briefing into the PR before requesting review." },
  },
  {
    type: "assistant",
    timestamp: iso(41),
    message: {
      role: "assistant",
      content: [
        { type: "thinking", thinking: "The briefing template is a gate — read it before touching the PR body." },
        { type: "text", text: "Reading the briefing template and the PR body first." },
        {
          type: "tool_use",
          id: "toolu_01",
          name: "Read",
          input: { file_path: "skills/the-loop/templates/pr-briefing.md" },
        },
      ],
    },
  },
  {
    type: "user",
    timestamp: iso(41),
    message: {
      role: "user",
      content: [{ type: "tool_result", tool_use_id: "toolu_01", content: "# <PR title> — reviewer briefing…" }],
    },
  },
  {
    type: "assistant",
    timestamp: iso(39),
    message: {
      role: "assistant",
      content: [
        { type: "text", text: "Template read. Drafting the briefing with the focus order and the mermaid map." },
        { type: "tool_use", id: "toolu_02", name: "Write", input: { file_path: "briefing.md" } },
        { type: "tool_use", id: "toolu_03", name: "Bash", input: { command: "gh pr edit --body-file briefing.md" } },
      ],
    },
  },
  {
    type: "user",
    timestamp: iso(38),
    message: {
      role: "user",
      content: [
        { type: "tool_result", tool_use_id: "toolu_02", content: "wrote briefing.md" },
        {
          type: "tool_result",
          tool_use_id: "toolu_03",
          content: [{ type: "text", text: "gh: Validation Failed — body too long" }],
          is_error: true,
        },
      ],
    },
  },
  { malformed: "…truncated by the harness mid-write…" },
  {
    type: "assistant",
    timestamp: iso(36),
    message: { role: "assistant", content: [{ type: "text", text: "Briefing posted; requesting review next." }] },
  },
];

/**
 * A small, believable CLI config and the slice of its schema the demo renders — enough
 * for the Settings editor to show real sections, prose and controls with no service in
 * reach. It is deliberately not the whole 100-key schema: the demo demonstrates the
 * screen, and a copy of the shipped schema here would be a second one to keep current.
 */
export const DEMO_CONFIG: ConfigDocument = {
  path: "~/.the-loop/cli-config.yaml",
  exists: true,
  version: "0.4.0",
  config: {
    version: "0.4.0",
    routing: {
      enabled: true,
      defaultHarness: "claude",
      authorizedUsers: ["octocat"],
      maxConcurrentDispatches: 4,
    },
    polling: { intervalSeconds: 60, sources: [] },
    eventLog: { enabled: true, path: ".the-loop/logs/events.jsonl" },
  },
};

export const DEMO_CONFIG_SCHEMA: JsonSchema = {
  type: "object",
  additionalProperties: false,
  properties: {
    version: { type: "string", description: "Schema version of this file." },
    routing: {
      type: "object",
      description: "What happens to an event once accepted: who may drive the loop, and how sessions are hosted.",
      properties: {
        enabled: { type: "boolean", default: false, description: "Route events to registered harness sessions." },
        defaultHarness: {
          type: "string",
          enum: ["claude", "cursor"],
          default: "claude",
          description: "Which harness a spawned session runs.",
        },
        authorizedUsers: {
          type: "array",
          items: { type: "string" },
          description: "Logins whose comments may command the loop. Empty means nothing is actioned (fail closed).",
        },
        maxConcurrentDispatches: { type: "integer", minimum: 1, default: 4 },
      },
    },
    polling: {
      type: "object",
      description: "The poller's cadence and the repositories it watches.",
      properties: {
        intervalSeconds: { type: "integer", minimum: 5, default: 60 },
        sources: {
          type: "array",
          items: { type: "object", properties: { provider: { type: "string" } } },
          description: "Poll sources. Rendered as JSON: a list of records has no typed control.",
        },
      },
    },
    eventLog: {
      type: "object",
      description: "The structured JSONL trail `the-loop events` reads.",
      properties: {
        enabled: { type: "boolean", default: true },
        path: { type: "string", default: ".the-loop/logs/events.jsonl" },
      },
    },
  },
};
