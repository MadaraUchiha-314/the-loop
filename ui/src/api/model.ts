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
  TranscriptEntry,
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
 * `~/.claude/projects/<cwd with every character outside [A-Za-z0-9] replaced by ->/<session-id>.jsonl`
 * — the munge is per character (consecutive non-alphanumerics are NOT
 * collapsed), matching both the harness's real layout and the server-side
 * derivation behind `GET /api/v1/sessions/transcript` (issue-209), which
 * serves the file this path names. The path stays on screen as the caption
 * beside the trace panel: it tells the operator where the served bytes live.
 *
 * Returns null for a harness whose transcript location is not documented —
 * Cursor keeps chats in SQLite under `~/.cursor/chats/` with no stable schema.
 */
export function transcriptPath(session: SessionEndpoint | undefined | null): string | null {
  if (!session || session.harness !== "claude") return null;
  if (!session.cwd || !session.harnessSessionId) return null;
  const slug = session.cwd.replace(/[^a-zA-Z0-9]/g, "-");
  return `~/.claude/projects/${slug}/${session.harnessSessionId}.jsonl`;
}

/** The narrowing every unknown transcript field goes through — never a cast. */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** One tool invocation, with the result that answered it folded in. */
export interface ToolCallView {
  /** The `tool_use` block's id — what pairs a result to this call; may be "". */
  id: string;
  name: string;
  /** One human-readable line of the input: the command, the path, the pattern. */
  summary: string;
  /** The full input, pretty-printed, for the expanded view. */
  input: string;
  /** The paired `tool_result`'s text; "" until (unless) one arrives. */
  result: string;
  /** The paired result's `is_error`. */
  isError: boolean;
}

/** One render-ready row of the stream, projected from transcript entries. */
export interface ThreadRow {
  /** What the row is; drives the row treatment. */
  kind: "user" | "assistant" | "tool result" | "meta" | "malformed";
  /** The entry's timestamp, when it carried one. */
  time: string;
  /** User/assistant text; an orphan result's text; the raw malformed line. */
  text: string;
  /** Assistant `thinking` blocks joined — rendered collapsed. */
  thinking: string;
  /** A meta row's label: the entry's `type` (`summary`, `system`, …). */
  label: string;
  /** Tool invocations in this turn, results folded in. */
  tools: ToolCallView[];
}

/**
 * The one line that names what a tool call did, per tool — claude.ai/code's
 * collapsed-row treatment. Data, not a switch: an unknown tool falls back to a
 * compact rendering of its input, so this table may lag the harness safely.
 */
const TOOL_SUMMARY_KEYS: Record<string, string[]> = {
  Bash: ["command"],
  Read: ["file_path"],
  Write: ["file_path"],
  Edit: ["file_path"],
  NotebookEdit: ["notebook_path"],
  Grep: ["pattern"],
  Glob: ["pattern"],
  Task: ["description"],
  Agent: ["description"],
  WebFetch: ["url"],
  WebSearch: ["query"],
  Skill: ["skill"],
};

function toolSummary(name: string, input: unknown): string {
  if (isRecord(input)) {
    for (const key of TOOL_SUMMARY_KEYS[name] ?? []) {
      const value = input[key];
      if (typeof value === "string" && value !== "") return value;
    }
  }
  const compact = input === undefined ? "" : (JSON.stringify(input) ?? "");
  return compact === "{}" ? "" : compact;
}

/** The text a `tool_result`'s `content` carries — a string, or `text` blocks. */
function resultText(content: unknown): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  const texts: string[] = [];
  for (const block of content as unknown[]) {
    if (isRecord(block) && block["type"] === "text" && typeof block["text"] === "string") texts.push(block["text"]);
  }
  return texts.join("\n");
}

/**
 * Claude Code JSONL entries → the rows the stream draws.
 *
 * The line format is the harness's own, so this is a projection, not a parser:
 * it reads the fields it knows (`type`, `timestamp`, `message.content` as a
 * string or as `text`/`thinking`/`tool_use`/`tool_result` blocks), tolerates
 * anything it does not, and never throws on a shape that drifted (issue-230).
 *
 * The reshaping over the flat file: a `tool_result` entry is **folded into the
 * call it answers** — matched by `tool_use_id` against the `tool_use` blocks
 * already projected — and emits no row of its own, because the harness feeding
 * output back is not a turn. A result whose call fell outside the served tail
 * still renders, as its own `tool result` row; an entry with no derivable text
 * (`summary`, `system`, unknown shapes) renders as a labelled `meta` row.
 * Nothing projects to a blank row — that was the reported bug.
 */
const row = (partial: Partial<ThreadRow> & Pick<ThreadRow, "kind">): ThreadRow => ({
  time: "",
  text: "",
  thinking: "",
  label: "",
  tools: [],
  ...partial,
});

export function transcriptThread(entries: TranscriptEntry[]): ThreadRow[] {
  const rows: ThreadRow[] = [];
  // Calls awaiting their result, by tool_use id — across rows, since the
  // result always arrives in a later entry than its call.
  const pending = new Map<string, ToolCallView>();

  for (const entry of entries) {
    const malformed = entry["malformed"];
    if (typeof malformed === "string") {
      rows.push(row({ kind: "malformed", text: malformed }));
      continue;
    }
    const time = typeof entry["timestamp"] === "string" ? entry["timestamp"] : "";
    const type = typeof entry["type"] === "string" && entry["type"] !== "" ? entry["type"] : "entry";
    const message = entry["message"];
    if (!isRecord(message)) {
      // Not a turn (a `summary` line, harness bookkeeping) — a labelled meta
      // row with whatever text it does carry.
      const summary = entry["summary"];
      rows.push(row({ kind: "meta", time, label: type, text: typeof summary === "string" ? summary : "" }));
      continue;
    }

    const content = message["content"];
    const texts: string[] = [];
    const thinking: string[] = [];
    const tools: ToolCallView[] = [];
    const orphanResults: { text: string; isError: boolean }[] = [];
    if (typeof content === "string" && content !== "") texts.push(content);
    if (Array.isArray(content)) {
      for (const block of content as unknown[]) {
        if (!isRecord(block)) continue;
        // Empty blocks are dropped, not collected: a row whose only content
        // is "" would render blank — the very bug this projection removes.
        if (block["type"] === "text" && typeof block["text"] === "string" && block["text"] !== "") {
          texts.push(block["text"]);
        }
        if (block["type"] === "thinking" && typeof block["thinking"] === "string" && block["thinking"] !== "") {
          thinking.push(block["thinking"]);
        }
        if (block["type"] === "tool_use" && typeof block["name"] === "string") {
          const input = block["input"];
          const call: ToolCallView = {
            id: typeof block["id"] === "string" ? block["id"] : "",
            name: block["name"],
            summary: toolSummary(block["name"], input),
            input: input === undefined ? "" : (JSON.stringify(input, null, 2) ?? ""),
            result: "",
            isError: false,
          };
          tools.push(call);
          if (call.id) pending.set(call.id, call);
        }
        if (block["type"] === "tool_result") {
          const text = resultText(block["content"]);
          const isError = block["is_error"] === true;
          const id = typeof block["tool_use_id"] === "string" ? block["tool_use_id"] : "";
          const call = id ? pending.get(id) : undefined;
          if (call) {
            call.result = text;
            call.isError = isError;
            pending.delete(id);
          } else {
            // The call this answers fell outside the served tail — still
            // worth a row of its own, never a blank (the reported bug).
            orphanResults.push({ text, isError });
          }
        }
      }
    }

    for (const orphan of orphanResults) {
      rows.push(row({ kind: "tool result", time, text: orphan.text || "(no output)" }));
    }
    if (texts.length === 0 && thinking.length === 0 && tools.length === 0) {
      if (orphanResults.length === 0) {
        // Neither a turn nor a fold-in — an unknown message shape. Label it.
        const kind = type === "user" || type === "assistant" ? type : "meta";
        if (kind === "meta") rows.push(row({ kind, time, label: type }));
        // A user/assistant entry that only carried results was folded above.
      }
      continue;
    }
    const kind = type === "user" ? "user" : type === "assistant" ? "assistant" : "meta";
    rows.push(
      row({
        kind,
        time,
        label: kind === "meta" ? type : "",
        text: texts.join("\n"),
        thinking: thinking.join("\n"),
        tools,
      }),
    );
  }
  return rows;
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
  /**
   * The PR's **own** portable record — its poll ledger and cached title — or
   * `{ ref }` when the poller has never seen it. Folded in by issue-302: this
   * row is now the only one the PR gets, so what its top-level row used to
   * carry has to arrive here or be lost.
   */
  record: WorkItemRecord;
  /** The service's attention for this PR's ref, surfaced on its item's card. */
  attention: AttentionItem[];
  /** The PR loop's open `the-loop ask` question, when one is open. */
  question: EventRecord | null;
  /** The endpoint's newest event, else the record's poll stamp, else `""`. */
  lastActivity: string;
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
 * Keyed on `session.awaiting_input`, which `the-loop ask` emits (issue-208):
 * the verb posts the agent's question to the ticket/PR with the loop-prevention
 * marker stamped centrally, and records the wait as this event. Reading it
 * costs one filtered `/events` call for the whole board.
 *
 * A `session.reply_sent` newer than the question closes it — the SAME
 * open/answered rule the service's attention surface applies
 * (`cli/the_loop/core/attention.py`); change one and the other is a reviewable
 * change, or the two surfaces disagree.
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
  const claimed = pullRequestClaims(input.sessions, recordByRef, sessionByRef);

  const views: WorkItemView[] = [];
  for (const ref of refs) {
    // Somebody else's pull request is not a work item of its own (issue-302).
    if (claimed.has(ref)) continue;
    const record = recordByRef.get(ref) ?? { ref };
    const session = sessionByRef.get(ref) ?? null;
    const parsed = parseRef(ref);
    const status = input.graphs?.outer[ref] ?? null;
    // A report with no nodes is not a position, it is the absence of one — the
    // shape `/graph/check` answers with when the checkout is gone (issue-238).
    // Belt and braces: `fetchGraphs` already drops those, and this keeps any
    // other caller of `buildWorkItemViews` from rendering an empty rail where
    // the frozen node list would have said more.
    const known = status !== null && status.nodes.length > 0;
    const rail = known ? railFromStatus(status) : railFromFrozen(record);

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
      pullRequests: buildPullRequests(ref, session, input, recordByRef, attentionByRef, claimed),
      attention: attentionByRef.get(ref) ?? [],
      lastActivity: session?.lastEventAt ?? record.poll?.lastPolledAt ?? "",
      question: input.awaiting?.[ref] ?? null,
    });
  }

  // Newest activity first, then by ref so an idle board has a stable order.
  return views.toSorted((a, b) => b.lastActivity.localeCompare(a.lastActivity) || a.ref.localeCompare(b.ref));
}

/**
 * Which refs are somebody else's pull request: PR ref -> the work item whose
 * sidebar row draws it as a nested child.
 *
 * A labeled pull request has two identities on this machine, and both are
 * written on purpose. The poller flushes a portable record keyed by the PR's
 * own ref (`state.flush(item.ref)` in `poller/poller.py`) because that ledger
 * is what stops the next cycle re-reading the same comments; the registry
 * appends a session endpoint for the same PR to the record of the work item it
 * delivers (`link_pull_request`, one level deep by design). Unioned without
 * reconciliation, the board draws one PR twice — once live under its parent,
 * once as a top-level shell whose session is somewhere else (issue-302). The
 * nested row wins, because that is where the PR's session, rail and transcript
 * actually are.
 *
 * Only a claim that is really *drawn* counts. A loop with no outer/inner split
 * renders treeless, so its linked endpoint never becomes a row: honouring that
 * claim would delete the pull request from the board rather than move it. And a
 * PR **no** session claims — one linked to no issue, which `extract_work_items`
 * deliberately routes as its own work item — is nobody's child and stays where
 * it is.
 *
 * Neither does a PR that has a **session record of its own**: it was worked
 * standalone before it was linked, so the top-level record is the live one and
 * the nested endpoint is the stub `link_pull_request` writes (no tmux target,
 * no conversation id). `SessionRegistry.record_owning` resolves that ref to its
 * own record for the same reason, and folding it away would hide a running
 * session behind a row that cannot reach it. An extra row is the cheaper wrong
 * answer.
 */
function pullRequestClaims(
  sessions: SessionRecord[],
  recordByRef: Map<string, WorkItemRecord>,
  sessionByRef: Map<string, SessionRecord>,
): Map<string, string> {
  const claims = new Map<string, string>();
  for (const session of sessions) {
    if (treeless(recordByRef.get(session.ref))) continue;
    for (const endpoint of session.pullRequests ?? []) {
      const ref = endpoint.workItem.ref;
      // A work item does not deliver itself. `link_pull_request` refuses to
      // record such an entry; a record that carries one anyway must not be able
      // to erase its own row.
      if (ref === session.ref || sessionByRef.has(ref)) continue;
      if (!claims.has(ref)) claims.set(ref, session.ref);
    }
  }
  // The registry nests exactly one level — `Session.from_dict` drops a nested
  // endpoint's own `pullRequests` — so a two-level claim can only come from a
  // hand-edited record. Fail closed to "top-level" rather than drop both rows.
  // Decided against the *snapshot*, never the map being edited: a mutual pair
  // resolved in map order would delete one claim and then honour the other.
  const claimedRefs = new Set(claims.keys());
  for (const [ref, owner] of claims) if (claimedRefs.has(owner)) claims.delete(ref);
  return claims;
}

/** A loop with no outer/inner split: one session, and no nested PR rows. */
function treeless(record: WorkItemRecord | undefined): boolean {
  return TREELESS_LOOPS.has(record?.graph?.loop ?? "");
}

function buildPullRequests(
  workItemRef: string,
  session: SessionRecord | null,
  input: BuildInput,
  recordByRef: Map<string, WorkItemRecord>,
  attentionByRef: Map<string, AttentionItem[]>,
  claimed: Map<string, string>,
): PullRequestView[] {
  const parent = parseRef(workItemRef);
  return (session?.pullRequests ?? []).map((endpoint) => {
    const ref = endpoint.workItem.ref;
    const parsed = parseRef(ref);
    const status = input.graphs?.inner[innerKey(workItemRef, ref)] ?? null;
    const record = recordByRef.get(ref) ?? { ref };
    // Whether *this* row is the only one the PR gets. It is not when the claim
    // was refused — a treeless owner draws no nested rows, a hand-edited
    // two-level claim is discarded — and the PR keeps a top-level row of its
    // own. Reporting its wait in both places would be the duplicate this work
    // item removes, wearing different clothes (issue-302).
    const sole = claimed.get(ref) === workItemRef;
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
      record,
      attention: sole ? (attentionByRef.get(ref) ?? []) : [],
      question: sole ? (input.awaiting?.[ref] ?? null) : null,
      // The same fallback a work item's own row uses, so a PR whose endpoint
      // has never recorded an event still shows the age its top-level row did.
      lastActivity: endpoint.lastEventAt ?? record.poll?.lastPolledAt ?? "",
    };
  });
}

/** One selectable session in the sidebar tree. */
export interface SessionNode {
  /** What `/sessions/transcript` and `/sessions/reply` are called with. */
  ref: string;
  shortRef: string;
  /**
   * What the row prints. A PR in the work item's own repository is just its
   * number (`#216`) — the parent row above it already names the repository, and
   * repeating it is the noise nesting exists to remove; a PR somewhere else
   * keeps the qualified `loop-docs#47` (issue-300).
   */
  label: string;
  /** `outer` — the work item's own loop; `inner` — one PR's `pdlc-pr-loop`. */
  scope: "outer" | "inner";
  state: SessionState;
  tmuxTarget: string;
  /** Newest activity on this session, `""` when none was recorded. */
  lastActivity: string;
}

/** One work item's group in the Work sidebar: the item, then its sessions. */
export interface SessionTreeItem {
  view: WorkItemView;
  /**
   * `pdlc-adhoc-loop` / `pdlc-contribution-loop` / `pdlc-review-loop` items
   * run no outer/inner split — one session, no tree (issue-230, issue-279).
   */
  treeless: boolean;
  outer: SessionNode;
  /** One child per PR inner loop; always empty for a treeless item. */
  inner: SessionNode[];
}

const TREELESS_LOOPS = new Set([
  "pdlc-adhoc-loop",
  "pdlc-contribution-loop",
  "pdlc-review-loop",
]);

/**
 * The Work sidebar: every work item, its sessions as a two-level tree.
 *
 * Two levels is not a rendering choice — the registry's nesting is one level
 * deep by design (a PR does not have pull requests), so the tree mirrors the
 * data it draws. Written for the pre-298 Sessions screen and left unrendered by
 * that screen's retirement; issue-300 nests the sidebar on it rather than
 * re-deriving a second, divergent notion of "this item's PRs".
 */
export function sessionTree(views: WorkItemView[]): SessionTreeItem[] {
  return views.map((view) => {
    const flat = treeless(view.record);
    return {
      view,
      treeless: flat,
      outer: {
        ref: view.ref,
        shortRef: view.shortRef,
        label: view.shortRef,
        scope: "outer" as const,
        state: view.sessionState,
        tmuxTarget: view.tmuxTarget,
        lastActivity: view.lastActivity,
      },
      inner: flat
        ? []
        : view.pullRequests.map((pr) => ({
            ref: pr.ref,
            shortRef: pr.shortRef,
            label: pr.prRepo ? pr.shortRef : `#${pr.number}`,
            scope: "inner" as const,
            state: pr.sessionState,
            tmuxTarget: pr.tmuxTarget,
            lastActivity: pr.lastActivity,
          })),
    };
  });
}

/** The flag a dashboard row wears, or null. Human gates outrank paused sessions. */
export function rowFlag(view: WorkItemView): { label: string; urgent: boolean } | null {
  // A PR loop's question used to raise the chip on the PR's own top-level row.
  // That row is gone (issue-302) and a nested row carries no chip by design
  // (issue-300 R2.4), so the question surfaces on the item that owns it —
  // restoring what the removed row showed, and nothing more.
  if (view.question || view.pullRequests.some((pr) => pr.question)) {
    return { label: "needs input", urgent: true };
  }
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
  /** How many raw reports collapsed into this entry (issue-283 B3). */
  count: number;
  /** The newest raw timestamp behind it, `""` when none is known. */
  at: string;
  /** Priority tier — lower is more actionable (issue-283 B4). */
  tier: number;
  /**
   * Set on a human-gate entry: what `POST /graph/complete` needs to approve it
   * from the inbox card (issue-283, feature #2). `repo` is `""` when no
   * session on this machine recorded a checkout — the button disables.
   */
  gate?: { repo: string; workItem: string; node: string; pr?: number; prRepo?: string };
}

/** needs input > human gate > awaiting/armed/paused > errors (issue-283 B4). */
const TIER_NEEDS_INPUT = 0;
const TIER_GATE = 1;
const TIER_WAITING = 2;
const TIER_ERROR = 3;

const KIND_TIER: Record<string, number> = {
  "awaiting-input": TIER_NEEDS_INPUT,
  "session-paused": TIER_WAITING,
  "armed-without-session": TIER_WAITING,
  "recent-error": TIER_ERROR,
};

/**
 * The inbox: what `/attention` reports, plus the graph gates it cannot see.
 *
 * Gate waits are repo-scoped — they live in each checkout's `graph-state.json`,
 * which is why `core.attention` deliberately leaves them out and documents that
 * they surface through `graphs.check` per work item. Having already fetched
 * those reports for the rails, the UI folds them back in here.
 *
 * Two rules the raw list does not have (issue-283 B3/B4): entries are
 * **deduplicated per (work item, kind)** — the service reports one
 * `recent-error` per error event, so one flaky item would otherwise fill the
 * inbox with copies differing only in timestamp; the newest survives with a
 * count. And ordering is **tiered** — a question outranks a gate outranks a
 * wait outranks an error, newest first within a tier — so the one entry that
 * needs a human is never buried under stale errors.
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
        count: 1,
        at: view.question.ts,
        tier: TIER_NEEDS_INPUT,
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
        count: 1,
        at: view.parked.since ?? "",
        tier: TIER_GATE,
        gate: { repo: view.repoPath, workItem: view.specId ?? "", node: view.parked.node },
      });
    }
    // A pull request the sidebar draws under this item has no card of its own
    // — its top-level row was the duplicate issue-302 removed — so everything
    // reported against the PR's ref surfaces here, named for the pull request
    // the way the gate entry has always been.
    for (const pr of view.pullRequests) {
      if (pr.question) {
        entries.push({
          key: `${view.ref}:${pr.ref}:question`,
          kind: "needs input · PR",
          ref: view.ref,
          shortRef: pr.shortRef,
          detail: questionOf(pr.question),
          urgent: true,
          action: "Reply",
          count: 1,
          at: pr.question.ts,
          tier: TIER_NEEDS_INPUT,
        });
      }
      if (pr.status?.parked) {
        entries.push({
          key: `${view.ref}:${pr.ref}:gate`,
          kind: "human gate · PR",
          ref: view.ref,
          shortRef: pr.shortRef,
          detail: `${pr.status.parked.node} — ${pr.status.parked.reason}`,
          urgent: true,
          action: "Review",
          count: 1,
          at: pr.status.parked.since ?? "",
          tier: TIER_GATE,
          gate: {
            repo: view.repoPath,
            workItem: view.specId ?? "",
            node: pr.status.parked.node,
            pr: pr.number,
            prRepo: pr.prRepo,
          },
        });
      }
      for (const [kind, held] of collapseByKind(pr.attention, pr.question !== null)) {
        const tier = KIND_TIER[kind] ?? TIER_WAITING;
        entries.push({
          key: `${view.ref}:${pr.ref}:${kind}`,
          kind: `${kind.replaceAll("-", " ")} · PR`,
          ref: view.ref,
          shortRef: pr.shortRef,
          detail: held.item.detail,
          urgent: tier <= TIER_GATE,
          action: "Open",
          count: held.count,
          at: held.at,
          tier,
        });
      }
    }
    for (const [kind, held] of collapseByKind(view.attention, view.question !== null)) {
      const tier = KIND_TIER[kind] ?? TIER_WAITING;
      entries.push({
        key: `${view.ref}:${kind}`,
        kind: kind.replaceAll("-", " "),
        ref: view.ref,
        shortRef: view.shortRef,
        detail: held.item.detail,
        urgent: tier <= TIER_GATE,
        action: "Open",
        count: held.count,
        at: held.at,
        tier,
      });
    }
  }
  // Most actionable tier first; newest first within a tier; ref as the stable
  // tie-break so an idle board keeps its order.
  return entries.toSorted(
    (a, b) => a.tier - b.tier || b.at.localeCompare(a.at) || a.ref.localeCompare(b.ref),
  );
}

/**
 * Dedupe raw attention reports per kind: newest timestamp wins, the rest become
 * a count badge (issue-283 B3).
 *
 * `asked` is whether a richer question entry — same wait, with a Reply action
 * — is already on the board for this ref (issue-208). The service reports the
 * wait as `awaiting-input` too, and the raw row would then be a duplicate; it
 * is kept only when the event window missed the question the service can still
 * see. One function for a work item and for its pull requests, so the two
 * cannot drift (issue-302).
 */
function collapseByKind(
  items: AttentionItem[],
  asked: boolean,
): Map<string, { item: AttentionItem; count: number; at: string }> {
  const byKind = new Map<string, { item: AttentionItem; count: number; at: string }>();
  for (const item of items) {
    if (item.kind === "awaiting-input" && asked) continue;
    const at = item.at ?? "";
    const held = byKind.get(item.kind);
    if (!held) {
      byKind.set(item.kind, { item, count: 1, at });
    } else {
      held.count += 1;
      if (at > held.at) {
        held.at = at;
        held.item = item;
      }
    }
  }
  return byKind;
}

/** One inbox card per work item: its entries, led by the most actionable. */
export interface AttentionGroup {
  ref: string;
  shortRef: string;
  entries: AttentionEntry[];
  /** The group's rank — its most actionable entry's tier and newest time. */
  tier: number;
  at: string;
}

/**
 * The inbox grouped by work item (issue-283, feature 3): one card per item
 * listing everything it needs — a gate plus its errors — instead of one card
 * per raw event. Groups sort exactly as entries do.
 */
export function attentionByItem(views: WorkItemView[]): AttentionGroup[] {
  const groups = new Map<string, AttentionGroup>();
  for (const entry of attentionEntries(views)) {
    const held = groups.get(entry.ref);
    if (held) {
      held.entries.push(entry);
    } else {
      groups.set(entry.ref, {
        ref: entry.ref,
        shortRef: shortRef(entry.ref),
        entries: [entry],
        tier: entry.tier,
        at: entry.at,
      });
    }
  }
  return [...groups.values()].toSorted(
    (a, b) => a.tier - b.tier || b.at.localeCompare(a.at) || a.ref.localeCompare(b.ref),
  );
}

/** Which sidebar band a work item belongs to (issue-283, feature 6). */
export type ItemGroup = "needs-you" | "running" | "idle";

export function itemGroup(view: WorkItemView): ItemGroup {
  if (view.question || view.parked || view.rail.some((node) => node.state === "blocked")) {
    return "needs-you";
  }
  if (view.sessionState === "active") return "running";
  return "idle";
}

const pad = (n: number) => String(n).padStart(2, "0");

/**
 * A trace row's stamp: `10:41:12` for today, `2026-08-12 10:41` otherwise
 * (issue-283 B12) — a five-day-old row must never read as if it happened this
 * morning. `now` is injected so the boundary is testable. Anything unparseable
 * passes through.
 */
export function timeOf(ts: string, now: Date = new Date()): string {
  const date = new Date(ts);
  if (Number.isNaN(date.getTime())) return ts;
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();
  if (sameDay) return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

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
