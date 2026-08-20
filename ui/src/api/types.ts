/**
 * The shapes `/api/v1` actually serves.
 *
 * The published contract (`docs/api-specs/openapi/the-loop.v1.yaml`) types most
 * responses as bare objects with `additionalProperties: true`, because the core
 * facade returns its records verbatim rather than projecting them through
 * response models. These interfaces are therefore written against the records
 * themselves — `docs/cli/state.md` for the work-item and session records,
 * `the_loop.graph.runtime.StatusReport` for the graph reports — and every field
 * a client did not put there is optional. Nothing here is load-bearing at
 * runtime: `parse.ts` narrows the untyped JSON, so a service that grows a field
 * or drops one degrades to a missing value instead of a blank screen.
 */

/** `GET /api/v1/health`. */
export interface Health {
  status: string;
  version: string;
}

/** The parsed identity of a work item or pull request. */
export interface WorkItemIdentity {
  ref: string;
  provider: string;
  owner: string;
  repo: string;
  number: number;
}

/** `control` on a portable record — what an authorized human last asked for. */
export interface ControlRecord {
  command: string;
  source?: string;
  actor?: string;
  requestedAt?: string;
  note?: string;
}

/** One frozen graph node as the portable record stores it. */
export interface FrozenNode {
  id: string;
  phase?: string;
  skipped?: boolean;
  selectable?: boolean;
  optIn?: boolean;
}

/** `GET /api/v1/work-items` — `<state.root>/portable/<slug>.json`, verbatim. */
export interface WorkItemRecord {
  ref: string;
  /** Absent for refs whose URL cannot be derived (a `jira:` ref, say). */
  url?: string;
  control?: ControlRecord | null;
  poll?: {
    seenComments?: string[];
    commentAttempts?: Record<string, number>;
    spawn?: { attempts?: number; gaveUp?: boolean; deliveryId?: string };
    lastPolledAt?: string;
  } | null;
  graph?: {
    loop?: string;
    workItem?: string;
    nodes?: FrozenNode[];
  } | null;
}

/** One addressable harness conversation: a work item's session, or a PR's. */
export interface SessionEndpoint {
  workItem: WorkItemIdentity;
  harness: string;
  harnessSessionId: string;
  cwd?: string;
  status: "active" | "paused" | "closed" | (string & {});
  createdAt?: string;
  lastEventAt?: string | null;
  tmuxTarget?: string;
  recentDeliveries?: string[];
  url?: string;
  pullRequests?: SessionEndpoint[];
}

/**
 * `GET /api/v1/sessions` — the registry record plus the two additions core
 * makes: the flat `ref` every caller keys on, and the control record.
 */
export interface SessionRecord extends SessionEndpoint {
  ref: string;
  control?: ControlRecord | null;
}

/**
 * One parsed line of a session's transcript, `GET /api/v1/sessions/transcript`.
 *
 * The line format is the harness's own and deliberately untyped by the
 * contract; a line that did not parse as a JSON object arrives as
 * `{"malformed": "<raw line>"}`. `model.ts::transcriptTurns` projects these
 * into render-ready rows.
 */
export type TranscriptEntry = Record<string, unknown>;

/** `GET /api/v1/sessions/transcript` — the harness's own JSONL, resolved and tailed. */
export interface TranscriptResponse {
  workItem: string;
  harness: string;
  harnessSessionId: string;
  /** The resolved file served — the path the trace panel captions. */
  path: string;
  /** The whole file's line count, whatever `tail` kept. */
  totalLines: number;
  /** Whether `entries` is a strict tail of a longer file. */
  truncated: boolean;
  /** Parsed JSONL lines, oldest first. */
  entries: TranscriptEntry[];
}

/** One node's verdict in a `graph/check` report. */
export interface NodeReport {
  node: string;
  /** `pass` | `skip` | `wait` | `block` | `escalated` | `fail`. */
  status: string;
  outcome: string;
  messages?: string[];
  forced?: boolean;
  attempts?: number;
}

/** `POST /api/v1/graph/check` — `the-loop check` for one work item. */
export interface GraphStatus {
  workItem: string;
  currentNode: string;
  ok: boolean;
  /** Set when the current node's exit hook returned `wait` — a human is owed. */
  parked?: { node: string; reason: string; since?: string } | null;
  nodes: NodeReport[];
  /**
   * Present and `false` only when `repo` named a path that does not resolve to a
   * directory: the checkout has been cleaned up, so the server knows nothing
   * about this work item's position and says so with a 200 rather than a 400
   * (issue-238). **Absent on every normal response**, which keeps those
   * byte-identical — so read it as `=== false`, never for truthiness.
   */
  repoResolved?: boolean;
}

/** One node of the graph definition, as `GET /api/v1/graph` reports it. */
export interface GraphDefinitionNode {
  id: string;
  phase?: string;
  actor?: string;
  optIn?: boolean;
  skippable?: boolean;
  required?: boolean;
  [key: string]: unknown;
}

/** `GET /api/v1/graph` — which graph this checkout runs on. */
export interface GraphDefinition {
  version: string;
  name: string;
  start: string;
  specRoot: string;
  nodes: GraphDefinitionNode[];
  edges: { from: string; to: string; on?: string }[];
}

/** One line of `<state.root>/logs/events.jsonl`. */
export interface EventRecord {
  ts: string;
  event: string;
  source?: string;
  level?: "debug" | "info" | "warning" | "error" | (string & {});
  pid?: number;
  work_item?: string;
  work_items?: string[];
  actor?: string;
  node?: string;
  reason?: string;
  error?: string;
  harness?: string;
  harness_session_id?: string;
  delivery_id?: string;
  [key: string]: unknown;
}

/** `GET /api/v1/attention`. */
export interface AttentionItem {
  workItem: string;
  /** `session-paused` | `armed-without-session` | `recent-error`. */
  kind: string;
  detail: string;
}

/** `GET /api/v1/daemons`. */
export interface DaemonStatus {
  daemon: string;
  running: boolean;
  pid: number;
  pidfile: string;
  logfile: string;
  startedAt: string;
  lastCycleAt: string;
}

/** Core's uniform "what I would have printed" envelope on the control verbs. */
export interface CoreResult {
  messages?: { stream: "out" | "err" | (string & {}); text: string }[];
  exitCode?: number;
  [key: string]: unknown;
}

/**
 * One standing session (issue-277) — a session that belongs to no work item.
 *
 * `declared` says where its definition comes from: a `standingSessions.sessions`
 * entry, or (false) the registry record a `create` wrote. `running` is tmux's
 * answer now, not the record's claim, which is why it is separate from `status`.
 */
export interface StandingSessionRecord {
  name: string;
  declared: boolean;
  description: string;
  autoStart: boolean;
  harness: string;
  cwd: string;
  tmuxTarget: string;
  ref: string;
  status: string;
  running: boolean;
  harnessSessionId: string;
  slackChannel: string;
  slackThread: string;
  startedAt: string;
  lastMessageAt: string;
  /** Present only on the rows a control verb returns. */
  outcome?: string;
  detail?: string;
}

export type StandingVerb = "start" | "stop" | "restart";

/** The body of `POST /api/v1/standing-sessions/create`. */
export interface StandingCreateRequest {
  name: string;
  harness?: string;
  cwd?: string;
  prompt?: string;
  description?: string;
  slackEnabled?: boolean;
  slackChannel?: string;
  autoStart?: boolean;
}

/** What the standing verbs return: one row per session they touched. */
export interface StandingResult {
  sessions: StandingSessionRecord[];
  ok: boolean;
}

export type SessionVerb = "start" | "pause" | "resume" | "stop" | "cleanup";
export type DaemonVerb = "start" | "stop" | "restart" | "status";

/**
 * A JSON Schema node, as `GET /api/v1/config/schema` serves it — `$ref`s already
 * resolved server-side, so this is a plain tree. Only the keywords the config editor
 * renders from are named; the rest ride along in the index signature.
 */
export interface JsonSchema {
  type?: string | string[];
  title?: string;
  description?: string;
  default?: unknown;
  enum?: unknown[];
  properties?: Record<string, JsonSchema>;
  items?: JsonSchema;
  additionalProperties?: boolean | JsonSchema;
  minimum?: number;
  maximum?: number;
  [key: string]: unknown;
}

/** `GET /api/v1/config` — the operator's CLI config, and where it lives. */
export interface ConfigDocument {
  /** The resolved path on the machine running the service. */
  path: string;
  /** False when nothing has been configured on that machine yet — not an error. */
  exists: boolean;
  version: string;
  config: Record<string, unknown>;
}

/** `POST /api/v1/config` — what the save did. */
export interface ConfigSaveResult extends ConfigDocument {
  /** Dotted key paths whose value actually changed. */
  changed: string[];
  /** Of those, the ones the service reads only at boot. */
  restartRequired: string[];
  written: boolean;
}

/**
 * `POST /api/v1/restart` — a whole-system restart, **scheduled** (issue-228).
 * The service cannot stop itself synchronously and still answer, so the
 * response promises a detached `the-loop restart` process, not a finished
 * restart; the page sees the service drop and come back within seconds.
 */
export interface RestartSchedule {
  scheduled: boolean;
  /** Pid of the detached restart process (not the service's). */
  pid: number;
  withUpgrade: boolean;
  /** Where that process logs, under the workstation's state root. */
  logfile: string;
}
