/**
 * The view model: what the screens render, derived from what `/api/v1` serves.
 *
 * The API hands back four independent records — the portable work item, the
 * local session, the derived attention list and the graph report — keyed by
 * different things and none of them shaped like a row in a table. Joining them
 * is the only real logic in this app, so it lives here as pure functions over
 * plain data, with the fetching left to `../state/useControlPlane.ts` and the
 * markup to the views. That is also what makes it testable without a service.
 */

import type {
  AttentionItem,
  ControlRecord,
  EventRecord,
  GraphStatus,
  NodeReport,
  SessionEndpoint,
  SessionRecord,
  WorkItemRecord,
} from "./types.ts";

/** Mirrors `the_loop.sessions.registry.WorkItemRef` (`DEFAULT_GITHUB_HOST`). */
export const DEFAULT_GITHUB_HOST = "github.com";

const REF_RE = /^(?<provider>[a-z][a-z0-9_-]*):(?<path>[^#\s]+)#(?<number>\d+)$/i;

export interface ParsedRef {
  provider: string;
  host: string;
  owner: string;
  repo: string;
  number: number;
  ref: string;
}

/**
 * `<provider>:[<host>/]<owner>/<repo>#<number>`, or null when it is not a ref.
 *
 * The host is optional and unwritten when it is the provider's default, exactly
 * as the CLI writes it — so `github:octo/repo#15` and
 * `github:github.com/octo/repo#15` parse to the same work item.
 */
export function parseRef(ref: string): ParsedRef | null {
  const match = REF_RE.exec(ref.trim());
  if (!match?.groups) return null;
  const parts = match.groups["path"]!.split("/");
  if (parts.length !== 2 && parts.length !== 3) return null;
  // Three segments means the host is written out (GitHub Enterprise); two means
  // it is the provider's default and left unwritten.
  const host = parts.length === 3 ? (parts[0] ?? "") : "";
  if (parts.length === 3 && !host) return null;
  const owner = parts.at(-2);
  const repo = parts.at(-1);
  if (!owner || !repo) return null;
  const provider = match.groups["provider"]!;
  return {
    provider,
    host: host || (provider === "github" ? DEFAULT_GITHUB_HOST : ""),
    owner,
    repo,
    number: Number(match.groups["number"]),
    ref: ref.trim(),
  };
}

/** `github:octo/loop-lab#214` → `loop-lab#214`; anything unparseable passes through. */
export function shortRef(ref: string): string {
  const parsed = parseRef(ref);
  return parsed ? `${parsed.repo}#${parsed.number}` : ref;
}

/**
 * The spec-folder id a graph call needs (`issue-214`).
 *
 * The portable record names it outright once the phase-selection gate has been
 * answered (`graph.workItem`); before that the convention is the only source,
 * so fall back to it rather than refusing to show a position.
 */
export function specId(item: Pick<WorkItemRecord, "ref" | "graph">): string | null {
  const recorded = item.graph?.workItem;
  if (recorded) return recorded;
  const parsed = parseRef(item.ref);
  return parsed ? `issue-${parsed.number}` : null;
}

export type SessionState = "active" | "paused" | "closed" | "none";

const SESSION_STATES: readonly SessionState[] = ["active", "paused", "closed"];

export function sessionState(session: SessionEndpoint | undefined | null): SessionState {
  if (!session) return "none";
  const found = SESSION_STATES.find((state) => state === session.status);
  return found ?? "none";
}

/**
 * Where Claude Code keeps this session's transcript.
 *
 * `~/.claude/projects/<cwd with every non-alphanumeric run replaced by ->/<session-id>.jsonl`.
 * the-loop records both halves — `cwd` and the pre-assigned `harnessSessionId` —
 * so the path is derivable without asking the harness. It is shown, not read:
 * nothing in `/api/v1` serves file contents, so the trace panel offers the path
 * for `tail`/`jq` until a transcript endpoint exists (see ui/README.md).
 *
 * Returns null for a harness whose transcript location is not documented —
 * Cursor keeps chats in SQLite under `~/.cursor/chats/` with no stable schema.
 */
export function transcriptPath(session: SessionEndpoint | undefined | null): string | null {
  if (!session || session.harness !== "claude") return null;
  if (!session.cwd || !session.harnessSessionId) return null;
  const slug = session.cwd.replace(/[^a-zA-Z0-9]+/g, "-");
  return `~/.claude/projects/${slug}/${session.harnessSessionId}.jsonl`;
}

/** How a node mark is drawn on a rail. */
export type NodeVisualState = "done" | "current" | "pending" | "skipped" | "blocked";

export interface RailNode {
  id: string;
  label: string;
  state: NodeVisualState;
  /** The node's `messages`, for the title attribute. */
  detail: string;
}

/**
 * The rail for one loop.
 *
 * Reports are read positionally: everything before `currentNode` that passed is
 * done, the current node is current, and anything the runtime called `block`,
 * `fail` or `escalated` is drawn as blocked so a stuck item does not read as
 * merely "in progress".
 */
export function railFromStatus(status: GraphStatus | null | undefined): RailNode[] {
  if (!status) return [];
  return status.nodes.map((node) => ({
    id: node.node,
    label: node.node,
    state: nodeVisualState(node, status.currentNode),
    detail: (node.messages ?? []).join("\n"),
  }));
}

function nodeVisualState(node: NodeReport, currentNode: string): NodeVisualState {
  if (node.status === "skip") return "skipped";
  if (node.node === currentNode) {
    return node.status === "block" || node.status === "fail" || node.status === "escalated"
      ? "blocked"
      : "current";
  }
  if (node.status === "pass") return "done";
  if (node.status === "block" || node.status === "fail" || node.status === "escalated") return "blocked";
  return "pending";
}

/**
 * A rail for an item whose graph could not be read — the frozen node list from
 * the portable record, with no pointer. Better than an empty row: it still says
 * which phases this item agreed to walk.
 */
export function railFromFrozen(item: WorkItemRecord): RailNode[] {
  return (item.graph?.nodes ?? []).map((node) => ({
    id: node.id,
    label: node.id,
    state: node.skipped ? ("skipped" as const) : ("pending" as const),
    detail: node.phase ? `phase: ${node.phase}` : "",
  }));
}

/** `3/8` — position along the rail, counting only nodes that are walked. */
export function railProgress(rail: RailNode[]): string {
  const walked = rail.filter((node) => node.state !== "skipped");
  const index = walked.findIndex((node) => node.state === "current" || node.state === "blocked");
  const reached = index === -1 ? walked.filter((n) => n.state === "done").length : index;
  return `${reached}/${walked.length}`;
}

export interface PullRequestView {
  ref: string;
  shortRef: string;
  number: number;
  /** Present when the PR lives in a repository other than the work item's. */
  prRepo: string;
  url: string | undefined;
  session: SessionEndpoint;
  sessionState: SessionState;
  tmuxTarget: string;
  rail: RailNode[];
  /** Null until the inner-loop graph report for this PR has been fetched. */
  status: GraphStatus | null;
}

export interface WorkItemView {
  ref: string;
  shortRef: string;
  number: number;
  url: string | undefined;
  record: WorkItemRecord;
  control: ControlRecord | null;
  session: SessionRecord | null;
  sessionState: SessionState;
  tmuxTarget: string;
  /** The checkout the graph calls need; `""` when no session recorded one. */
  repoPath: string;
  specId: string | null;
  rail: RailNode[];
  status: GraphStatus | null;
  progress: string;
  currentNode: string;
  /** The exit hook parked this node awaiting a human — the graph gate. */
  parked: GraphStatus["parked"];
  pullRequests: PullRequestView[];
  attention: AttentionItem[];
  lastActivity: string;
  /** The agent's open question, when one was asked via `the-loop ask`. */
  question: EventRecord | null;
}

export interface GraphReports {
  /** Keyed by work-item ref. */
  outer: Record<string, GraphStatus | undefined>;
  /** Keyed by `${workItemRef}::${prRef}`. */
  inner: Record<string, GraphStatus | undefined>;
}

export function innerKey(workItemRef: string, prRef: string): string {
  return `${workItemRef}::${prRef}`;
}

/**
 * The open question per work item, if any.
 *
 * Keyed on `session.awaiting_input`, which nothing emits yet: the design's
 * conclusion was that an agent should ask through a `the-loop ask` verb — routed
 * to a ticket or PR comment and recorded as that event — rather than posting
 * with `gh` itself, which is what `the_loop/interaction.py` directs it to do
 * today. Reading the event the verb *would* emit costs one filtered `/events`
 * call and means the board lights up on its own the day the verb ships. Against
 * today's service the map is simply empty.
 *
 * A `session.reply_sent` newer than the question closes it.
 */
export function awaitingInput(events: EventRecord[]): Record<string, EventRecord> {
  const open: Record<string, EventRecord> = {};
  const answered: Record<string, string> = {};
  // Oldest first, so the last write per ref wins.
  for (const event of events) {
    const ref = eventRef(event);
    if (!ref) continue;
    if (event.event === "session.awaiting_input") open[ref] = event;
    if (event.event === "session.reply_sent") answered[ref] = event.ts;
  }
  for (const [ref, asked] of Object.entries(open)) {
    const reply = answered[ref];
    if (reply !== undefined && reply >= asked.ts) delete open[ref];
  }
  return open;
}

/** The question text an `awaiting_input` event carries, however it spelled it. */
export function questionOf(event: EventRecord | undefined): string {
  for (const value of [event?.["question"], event?.["reason"], event?.["detail"]]) {
    if (typeof value === "string" && value !== "") return value;
  }
  return "";
}

export interface BuildInput {
  workItems: WorkItemRecord[];
  sessions: SessionRecord[];
  attention: AttentionItem[];
  graphs?: GraphReports;
  /** Open `the-loop ask` questions, keyed by work-item ref. */
  awaiting?: Record<string, EventRecord>;
}

/**
 * Join the four records into one row per work item.
 *
 * Every work item the service knows about appears, whether or not it has a
 * session — an armed item with no live session is precisely the thing the
 * attention list exists to surface, so dropping it here would hide it.
 */
export function buildWorkItemViews(input: BuildInput): WorkItemView[] {
  const sessionByRef = new Map(input.sessions.map((session) => [session.ref, session]));
  const attentionByRef = new Map<string, AttentionItem[]>();
  for (const item of input.attention) {
    const list = attentionByRef.get(item.workItem) ?? [];
    list.push(item);
    attentionByRef.set(item.workItem, list);
  }

  // A session with no portable record still belongs on the board: `sessions
  // register` can create one for an item the poller has never seen.
  const refs = new Set<string>([...input.workItems.map((i) => i.ref), ...input.sessions.map((s) => s.ref)]);
  const recordByRef = new Map(input.workItems.map((item) => [item.ref, item]));

  const views: WorkItemView[] = [];
  for (const ref of refs) {
    const record = recordByRef.get(ref) ?? { ref };
    const session = sessionByRef.get(ref) ?? null;
    const parsed = parseRef(ref);
    const status = input.graphs?.outer[ref] ?? null;
    const rail = status ? railFromStatus(status) : railFromFrozen(record);

    views.push({
      ref,
      shortRef: shortRef(ref),
      number: parsed?.number ?? 0,
      url: record.url ?? session?.url,
      record,
      control: record.control ?? session?.control ?? null,
      session,
      sessionState: sessionState(session),
      tmuxTarget: session?.tmuxTarget ?? "",
      repoPath: session?.cwd ?? "",
      specId: specId(record),
      rail,
      status,
      progress: railProgress(rail),
      currentNode: status?.currentNode ?? "",
      parked: status?.parked ?? null,
      pullRequests: buildPullRequests(ref, session, input.graphs),
      attention: attentionByRef.get(ref) ?? [],
      lastActivity: session?.lastEventAt ?? record.poll?.lastPolledAt ?? "",
      question: input.awaiting?.[ref] ?? null,
    });
  }

  // Newest activity first, then by ref so an idle board has a stable order.
  return views.toSorted((a, b) => b.lastActivity.localeCompare(a.lastActivity) || a.ref.localeCompare(b.ref));
}

function buildPullRequests(
  workItemRef: string,
  session: SessionRecord | null,
  graphs: GraphReports | undefined,
): PullRequestView[] {
  const parent = parseRef(workItemRef);
  return (session?.pullRequests ?? []).map((endpoint) => {
    const ref = endpoint.workItem.ref;
    const parsed = parseRef(ref);
    const status = graphs?.inner[innerKey(workItemRef, ref)] ?? null;
    // `prRepo` qualifies the number only when the PR is somewhere else; sending
    // it needlessly would point the graph call at `pr-loops/<owner>__<repo>/`
    // for an item whose state lives at `pr-loops/pr-<n>/` (issue-183).
    const elsewhere =
      parsed !== null && parent !== null && (parsed.owner !== parent.owner || parsed.repo !== parent.repo);
    return {
      ref,
      shortRef: shortRef(ref),
      number: endpoint.workItem.number,
      prRepo: elsewhere && parsed ? `${parsed.owner}/${parsed.repo}` : "",
      url: endpoint.url,
      session: endpoint,
      sessionState: sessionState(endpoint),
      tmuxTarget: endpoint.tmuxTarget ?? "",
      rail: railFromStatus(status),
      status,
    };
  });
}

/** The flag a dashboard row wears, or null. Human gates outrank paused sessions. */
export function rowFlag(view: WorkItemView): { label: string; urgent: boolean } | null {
  if (view.question) return { label: "needs input", urgent: true };
  if (view.parked) return { label: "human gate", urgent: true };
  if (view.rail.some((node) => node.state === "blocked")) return { label: "blocked", urgent: true };
  if (view.attention.some((a) => a.kind === "recent-error")) return { label: "error", urgent: false };
  if (view.attention.some((a) => a.kind === "armed-without-session")) return { label: "no session", urgent: false };
  if (view.sessionState === "paused") return { label: "paused", urgent: false };
  return null;
}

export interface AttentionEntry {
  key: string;
  kind: string;
  ref: string;
  shortRef: string;
  detail: string;
  urgent: boolean;
  action: string;
}

/**
 * The inbox: what `/attention` reports, plus the graph gates it cannot see.
 *
 * Gate waits are repo-scoped — they live in each checkout's `graph-state.json`,
 * which is why `core.attention` deliberately leaves them out and documents that
 * they surface through `graphs.check` per work item. Having already fetched
 * those reports for the rails, the UI folds them back in here.
 */
export function attentionEntries(views: WorkItemView[]): AttentionEntry[] {
  const entries: AttentionEntry[] = [];
  for (const view of views) {
    if (view.question) {
      entries.push({
        key: `${view.ref}:question`,
        kind: "needs input",
        ref: view.ref,
        shortRef: view.shortRef,
        detail: questionOf(view.question),
        urgent: true,
        action: "Reply",
      });
    }
    if (view.parked) {
      entries.push({
        key: `${view.ref}:gate`,
        kind: "human gate",
        ref: view.ref,
        shortRef: view.shortRef,
        detail: `${view.parked.node} — ${view.parked.reason}`,
        urgent: true,
        action: "Review",
      });
    }
    for (const pr of view.pullRequests) {
      if (!pr.status?.parked) continue;
      entries.push({
        key: `${view.ref}:${pr.ref}:gate`,
        kind: "human gate · PR",
        ref: view.ref,
        shortRef: pr.shortRef,
        detail: `${pr.status.parked.node} — ${pr.status.parked.reason}`,
        urgent: true,
        action: "Review",
      });
    }
    for (const [index, item] of view.attention.entries()) {
      entries.push({
        key: `${view.ref}:${item.kind}:${index}`,
        kind: item.kind.replaceAll("-", " "),
        ref: view.ref,
        shortRef: view.shortRef,
        detail: item.detail,
        urgent: item.kind === "recent-error",
        action: "Open",
      });
    }
  }
  // Urgent first, otherwise the order the service reported them in.
  return entries.toSorted((a, b) => Number(b.urgent) - Number(a.urgent));
}

/** `2026-08-12T10:41:12Z` → `10:41:12`, and anything unparseable unchanged. */
export function timeOf(ts: string): string {
  const date = new Date(ts);
  if (Number.isNaN(date.getTime())) return ts;
  return date.toLocaleTimeString(undefined, { hour12: false });
}

const pad = (n: number) => String(n).padStart(2, "0");

/** `2026-08-12T10:41:12Z` → `2026-08-12 10:41:12` in the viewer's zone. */
export function stampOf(ts: string): string {
  const date = new Date(ts);
  if (Number.isNaN(date.getTime())) return ts || "—";
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  );
}

/** `18m ago`, `2d ago`, `—`. `now` is injected so the formatting is testable. */
export function relativeTime(ts: string, now: number = Date.now()): string {
  if (!ts) return "—";
  const then = new Date(ts).getTime();
  if (Number.isNaN(then)) return ts;
  const seconds = Math.max(0, Math.round((now - then) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

/** The work item an event belongs to — the log carries one field or the other. */
export function eventRef(event: EventRecord): string {
  return event.work_item ?? (event.work_items ?? []).join(", ");
}

/** Event levels map onto the design's three tag treatments. */
export function levelTag(level: string | undefined): string {
  if (level === "error") return "tag-neutral";
  if (level === "warning" || level === "warn") return "tag-outline";
  return "tag-accent";
}

/** The envelope every event carries; the rest is what makes it worth reading. */
const EVENT_ENVELOPE = new Set(["ts", "event", "level", "source", "pid", "work_item", "work_items"]);

/**
 * An event's own fields as one line.
 *
 * The log is deliberately open — "event-specific fields, all optional" — so
 * there is no fixed set to render. Printing whatever the emitter put there
 * beats a hardcoded per-type formatter that silently drops the field that
 * explains the failure.
 */
export function describeEvent(event: EventRecord): string {
  const parts: string[] = [];
  for (const [key, value] of Object.entries(event)) {
    if (EVENT_ENVELOPE.has(key)) continue;
    if (value === "" || value === null || value === undefined) continue;
    parts.push(`${key}=${renderValue(value)}`);
  }
  return parts.join("  ") || "—";
}

function renderValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value) ?? String(value === undefined);
}
