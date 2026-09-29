/**
 * The demo transport: {@link TheLoopApi} answered from `fixture.ts`.
 *
 * Control verbs mutate an in-memory copy so pause/resume/approve behave, and
 * append to the demo event log the way the real service would. Nothing here
 * persists — a reload is a fresh board — because the point is to show the
 * screens, not to be a second implementation of the-loop.
 */

import { ApiError, type EventQuery, type GraphQuery, type StreamHandlers, type StreamQuery, type TheLoopApi } from "../api/client.ts";
import type { StreamFrame } from "../state/stream.ts";
import type {
  AttentionItem,
  ConfigDocument,
  ConfigSaveResult,
  RestartSchedule,
  CoreResult,
  DaemonStatus,
  DaemonVerb,
  EventRecord,
  GraphDefinition,
  GraphStatus,
  Health,
  InstanceDocument,
  InstancesDocument,
  JsonSchema,
  SessionEndpoint,
  SessionRecord,
  SessionVerb,
  StandingCreateRequest,
  StandingResult,
  StandingSessionRecord,
  StandingVerb,
  TranscriptResponse,
  WorkItemRecord,
} from "../api/types.ts";
import {
  DEMO_ATTENTION,
  DEMO_CONFIG,
  DEMO_CONFIG_SCHEMA,
  DEMO_DAEMONS,
  DEMO_EVENTS,
  DEMO_INNER_GRAPHS,
  DEMO_OUTER_GRAPHS,
  DEMO_SESSIONS,
  DEMO_STANDING,
  DEMO_TRANSCRIPT,
  DEMO_WORK_ITEMS,
  INNER_NODES,
  OUTER_NODES,
} from "./fixture.ts";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** The service's patch semantics, in the demo: mappings merge, values replace. */
function merge(base: Record<string, unknown>, patch: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = { ...base };
  for (const [key, value] of Object.entries(patch)) {
    const before = out[key];
    if (value === null) delete out[key];
    else if (isRecord(value) && isRecord(before)) out[key] = merge(before, value);
    else out[key] = value;
  }
  return out;
}

/** The dotted key paths a patch would actually change. */
function paths(patch: Record<string, unknown>, base: Record<string, unknown>, prefix = ""): string[] {
  return Object.entries(patch).flatMap(([key, value]) => {
    const here = prefix ? `${prefix}.${key}` : key;
    const before = base[key];
    if (isRecord(value) && Object.keys(value).length) return paths(value, isRecord(before) ? before : {}, here);
    return JSON.stringify(before ?? null) === JSON.stringify(value ?? null) ? [] : [here];
  });
}

/** Enough latency to exercise the loading states, little enough to feel instant. */
const LATENCY_MS = 120;

function clone<T>(value: T): T {
  return structuredClone(value);
}

function delay<T>(value: T, signal?: AbortSignal): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => resolve(clone(value)), LATENCY_MS);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        const reason: unknown = signal.reason;
        reject(reason instanceof Error ? reason : new Error("aborted"));
      },
      { once: true },
    );
  });
}

/**
 * The fixture's instance name (issue-322): what `GET /instance` and
 * `GET /instances` answer with, and the only `instance` a keyed call may name —
 * the demo is a **worker**, so any other name is the worker's 404 (R2.6).
 */
export const DEMO_INSTANCE = "demo";

/** A worker's answer to an `instance` that is not itself: 404, nothing done. */
function notSelf(instance: string): Promise<never> {
  return Promise.reject(
    new ApiError("http", `unknown instance ${JSON.stringify(instance)}: this instance is ${JSON.stringify(DEMO_INSTANCE)}`, "demo://fixture", 404),
  );
}

/** A worker's answer to a registry write: 400 naming `instance.role` (R4.4). */
function notAManager(route: string): Promise<never> {
  return Promise.reject(
    new ApiError(
      "http",
      "instance.role is worker, so this instance manages no others and nothing can be registered here; set instance.role: manager on the instance that should",
      `demo://fixture/api/v1/instances/${route}`,
      400,
    ),
  );
}

const VERB_STATUS: Partial<Record<SessionVerb, SessionRecord["status"]>> = {
  pause: "paused",
  resume: "active",
  start: "active",
  stop: "closed",
  cleanup: "closed",
};

export class DemoApi implements TheLoopApi {
  readonly baseUrl = "demo://fixture";
  readonly isDemo = true;

  private workItemRecords: WorkItemRecord[] = clone(DEMO_WORK_ITEMS);
  private sessionRecords: SessionRecord[] = clone(DEMO_SESSIONS);
  private standing: StandingSessionRecord[] = clone(DEMO_STANDING);
  private attentionItems: AttentionItem[] = clone(DEMO_ATTENTION);
  private eventRecords: EventRecord[] = clone(DEMO_EVENTS);
  private outer: Record<string, GraphStatus> = clone(DEMO_OUTER_GRAPHS);
  private configDocument: ConfigDocument = clone(DEMO_CONFIG);
  private inner: Record<string, GraphStatus> = clone(DEMO_INNER_GRAPHS);

  health(signal?: AbortSignal, instance = ""): Promise<Health> {
    if (instance && instance !== DEMO_INSTANCE) return notSelf(instance);
    return delay({ status: "ok", version: "demo", role: "worker" }, signal);
  }

  instance(signal?: AbortSignal, instance = ""): Promise<InstanceDocument> {
    if (instance && instance !== DEMO_INSTANCE) return notSelf(instance);
    const refs = new Set([...this.workItemRecords.map((item) => item.ref), ...this.sessionRecords.map((s) => s.ref)]);
    return delay(
      {
        name: DEMO_INSTANCE,
        role: "worker",
        scope: { mode: "open", workItems: [] },
        managed: [...refs].toSorted().map((ref) => ({ ref, sources: ["control"] })),
        sessionCount: this.sessionRecords.filter((s) => s.status !== "closed").length,
      },
      signal,
    );
  }

  /** One row, itself — what a worker serves (R5.6). */
  instances(signal?: AbortSignal): Promise<InstancesDocument> {
    const refs = new Set([...this.workItemRecords.map((item) => item.ref), ...this.sessionRecords.map((s) => s.ref)]);
    return delay(
      {
        role: "worker",
        name: DEMO_INSTANCE,
        instances: [
          {
            name: DEMO_INSTANCE,
            url: this.baseUrl,
            state: "live",
            version: "demo",
            mode: "open",
            managedCount: refs.size,
            sessionCount: this.sessionRecords.filter((s) => s.status !== "closed").length,
            probedAt: new Date().toISOString(),
          },
        ],
      },
      signal,
    );
  }

  registerInstance(_name: string, _url: string): Promise<InstancesDocument> {
    return notAManager("register");
  }

  unregisterInstance(_name: string): Promise<InstancesDocument> {
    return notAManager("unregister");
  }

  workItems(signal?: AbortSignal): Promise<WorkItemRecord[]> {
    return delay(this.workItemRecords, signal);
  }

  sessions(signal?: AbortSignal): Promise<SessionRecord[]> {
    return delay(this.sessionRecords, signal);
  }

  attention(signal?: AbortSignal): Promise<AttentionItem[]> {
    return delay(this.attentionItems, signal);
  }

  events(query: EventQuery = {}, signal?: AbortSignal): Promise<EventRecord[]> {
    let events = this.eventRecords;
    if (query.type?.length) events = events.filter((event) => query.type?.includes(event.event));
    if (query.workItem) events = events.filter((event) => event.work_item === query.workItem);
    if (query.level && query.level !== "all") events = events.filter((event) => event.level === query.level);
    if (query.source) events = events.filter((event) => event.source === query.source);
    // The service returns oldest-first and the views sort; match that here so
    // demo and live disagree about nothing a view can observe.
    const ordered = events.toSorted((a, b) => a.ts.localeCompare(b.ts));
    return delay(ordered.slice(-(query.limit ?? 100)), signal);
  }

  daemons(signal?: AbortSignal): Promise<DaemonStatus[]> {
    return delay(DEMO_DAEMONS, signal);
  }

  graphDefinition(_repo: string, pr?: number, signal?: AbortSignal, instance = ""): Promise<GraphDefinition> {
    if (instance && instance !== DEMO_INSTANCE) return notSelf(instance);
    const nodes = pr === undefined ? OUTER_NODES : INNER_NODES;
    return delay(
      {
        version: "1",
        name: pr === undefined ? "pdlc-work-item-loop" : "pdlc-pr-loop",
        start: nodes[0],
        specRoot: "docs/specs",
        nodes: nodes.map((id) => ({ id, phase: id })),
        edges: nodes.slice(0, -1).map((from, index) => ({ from, to: nodes[index + 1]!, on: "pass" })),
      },
      signal,
    );
  }

  graphCheck(query: GraphQuery, signal?: AbortSignal, instance = ""): Promise<GraphStatus> {
    if (instance && instance !== DEMO_INSTANCE) return notSelf(instance);
    const ref = this.refForSpec(query.workItem);
    const status =
      query.pr === undefined
        ? this.outer[ref]
        : this.inner[
            Object.keys(this.inner).find((key) => key.startsWith(`${ref}::`) && key.endsWith(`#${query.pr}`)) ?? ""
          ];
    if (!status) return Promise.reject(new Error(`no demo graph for ${query.workItem}`));
    return delay(status, signal);
  }

  graphComplete(query: GraphQuery & { node?: string; actor?: string }, instance = ""): Promise<CoreResult> {
    if (instance && instance !== DEMO_INSTANCE) return notSelf(instance);
    const ref = this.refForSpec(query.workItem);
    const status = query.pr === undefined ? this.outer[ref] : undefined;
    if (status?.parked) {
      const index = status.nodes.findIndex((node) => node.node === status.currentNode);
      const nextNode = status.nodes.slice(index + 1).find((node) => node.status !== "skip");
      status.nodes[index] = { ...status.nodes[index]!, status: "pass", outcome: "approved" };
      status.parked = null;
      if (nextNode) status.currentNode = nextNode.node;
      this.emit({
        event: "graph.advanced",
        level: "info",
        source: "graph",
        work_item: ref,
        node: status.currentNode,
        actor: query.actor || "you",
      });
    }
    return delay({ messages: [{ stream: "out", text: `demo: ${query.workItem} advanced` }], exitCode: 0 });
  }

  controlSession(ref: string, verb: SessionVerb, _comment = true, instance = ""): Promise<CoreResult> {
    if (instance && instance !== DEMO_INSTANCE) return notSelf(instance);
    const status = VERB_STATUS[verb];
    this.sessionRecords = this.sessionRecords.map((session) =>
      session.ref === ref && status
        ? { ...session, status, control: { command: verb, source: "cli", actor: "you", requestedAt: new Date().toISOString() } }
        : session,
    );
    if (verb === "resume") {
      this.attentionItems = this.attentionItems.filter(
        (item) => !(item.workItem === ref && item.kind === "session-paused"),
      );
    }
    if (verb === "pause") {
      this.attentionItems = [
        ...this.attentionItems,
        { workItem: ref, kind: "session-paused", detail: "session paused (last control: pause)" },
      ];
    }
    this.emit({ event: `session.${verb === "stop" ? "closed" : `${verb}d`}`, level: "info", source: "session", work_item: ref, actor: "you" });
    return delay({ messages: [{ stream: "out", text: `demo: ${verb} ${ref}` }], exitCode: 0 });
  }

  replySession(ref: string, _text: string, _actor = "", instance = ""): Promise<CoreResult> {
    if (instance && instance !== DEMO_INSTANCE) return notSelf(instance);
    // Same convention as the control verbs: the demo behaves. The reply_sent
    // event is what closes the question card, exactly as the service's does.
    this.emit({ event: "session.reply_sent", level: "info", source: "service", work_item: ref, actor: "you" });
    return delay({ messages: [{ stream: "out", text: `demo: replied to ${ref}` }], exitCode: 0 });
  }

  // -- standing sessions (issue-277) ----------------------------------------
  //
  // Same convention as the control verbs: the demo *behaves*, so the screen can
  // be explored — created and deleted included — before anyone has a service
  // running. The refusals are modelled too, because they are the part of the
  // contract an operator most needs to meet before they meet it for real.

  standingSessions(signal?: AbortSignal): Promise<StandingSessionRecord[]> {
    return delay(this.standing, signal);
  }

  createStandingSession(body: StandingCreateRequest, instance = ""): Promise<StandingResult> {
    if (instance && instance !== DEMO_INSTANCE) return notSelf(instance);
    const name = body.name.trim();
    if (!/^[a-z0-9][a-z0-9-]{0,39}$/.test(name)) {
      return Promise.reject(new Error(`invalid standing-session name ${JSON.stringify(name)}`));
    }
    if (this.standing.some((session) => session.name === name)) {
      return Promise.reject(new Error(`standing session ${JSON.stringify(name)} already exists`));
    }
    const created: StandingSessionRecord = {
      name,
      declared: false,
      description: body.description ?? "",
      autoStart: body.autoStart ?? true,
      harness: body.harness || "claude",
      cwd: body.cwd || "/home/you/dev/the-loop",
      tmuxTarget: `loop-standing-${name}`,
      ref: `standing:${name}`,
      status: "running",
      running: true,
      harnessSessionId: `demo-${name}`,
      slackChannel: body.slackEnabled ? (body.slackChannel ?? "") : "",
      slackThread: body.slackEnabled ? `${Date.now() / 1000}` : "",
      startedAt: new Date().toISOString(),
      lastMessageAt: "",
      outcome: "started",
      detail: `started loop-standing-${name} (claude demo-${name})`,
    };
    this.standing = [...this.standing, created];
    this.emit({ event: "standing.created", level: "info", source: "service", standing: name, actor: "you" });
    this.emit({ event: "standing.started", level: "info", source: "service", standing: name });
    return delay({ sessions: [created], ok: true });
  }

  deleteStandingSession(name: string, instance = ""): Promise<StandingResult> {
    if (instance && instance !== DEMO_INSTANCE) return notSelf(instance);
    const session = this.standing.find((candidate) => candidate.name === name);
    if (!session) return Promise.reject(new Error(`no standing session ${JSON.stringify(name)} has been created`));
    if (session.declared) {
      return Promise.reject(
        new Error(
          `standing session ${JSON.stringify(name)} is declared in standingSessions.sessions, ` +
            "so deleting its record would not remove it — remove the entry from the config, or stop it",
        ),
      );
    }
    this.standing = this.standing.filter((candidate) => candidate.name !== name);
    this.emit({ event: "standing.deleted", level: "info", source: "service", standing: name, actor: "you" });
    return delay({ sessions: [{ ...session, outcome: "deleted", running: false, status: "absent" }], ok: true });
  }

  controlStandingSession(name: string, verb: StandingVerb, instance = ""): Promise<StandingResult> {
    if (instance && instance !== DEMO_INSTANCE) return notSelf(instance);
    const running = verb !== "stop";
    let touched: StandingSessionRecord | undefined;
    this.standing = this.standing.map((session) => {
      if (session.name !== name) return session;
      touched = {
        ...session,
        running,
        status: running ? "running" : "stopped",
        startedAt: running ? new Date().toISOString() : session.startedAt,
        outcome: verb === "stop" ? "stopped" : session.harnessSessionId ? "resumed" : "started",
        detail: `demo: ${verb} loop-standing-${name}`,
      };
      return touched;
    });
    if (!touched) return Promise.reject(new Error(`no standing session ${JSON.stringify(name)}`));
    this.emit({ event: `standing.${verb === "stop" ? "stopped" : "started"}`, level: "info", source: "service", standing: name });
    return delay({ sessions: [touched], ok: true });
  }

  sayToStandingSession(name: string, _text: string, _actor = "", instance = ""): Promise<CoreResult> {
    if (instance && instance !== DEMO_INSTANCE) return notSelf(instance);
    const session = this.standing.find((candidate) => candidate.name === name);
    if (!session?.running) {
      return Promise.reject(new Error(`standing session ${JSON.stringify(name)} has no live tmux pane to paste into`));
    }
    this.standing = this.standing.map((candidate) =>
      candidate.name === name ? { ...candidate, lastMessageAt: new Date().toISOString() } : candidate,
    );
    this.emit({ event: "standing.said", level: "info", source: "service", standing: name, actor: "you" });
    return delay({ messages: [{ stream: "out", text: `demo: delivered into loop-standing-${name}` }], exitCode: 0 });
  }

  transcript(ref: string, tail = 200, signal?: AbortSignal, instance = ""): Promise<TranscriptResponse> {
    if (instance && instance !== DEMO_INSTANCE) return notSelf(instance);
    // Same convention as the control verbs: the demo behaves. Any session on
    // the board (the work item's own or a PR endpoint's) answers with the
    // fixture transcript; a ref with none refuses the way the service does.
    const endpoint = this.sessionRecords
      .flatMap((session): SessionEndpoint[] => [session, ...(session.pullRequests ?? [])])
      .find((candidate) => candidate.workItem.ref === ref);
    if (!endpoint) return Promise.reject(new Error(`no session registered for ${ref}, so no transcript can be resolved`));
    const entries = tail > 0 ? DEMO_TRANSCRIPT.slice(-tail) : DEMO_TRANSCRIPT;
    const slug = (endpoint.cwd ?? "").replace(/[^a-zA-Z0-9]/g, "-");
    return delay(
      {
        workItem: ref,
        harness: endpoint.harness,
        harnessSessionId: endpoint.harnessSessionId,
        path: `~/.claude/projects/${slug}/${endpoint.harnessSessionId}.jsonl`,
        totalLines: DEMO_TRANSCRIPT.length,
        truncated: entries.length < DEMO_TRANSCRIPT.length,
        entries,
      },
      signal,
    );
  }

  controlDaemon(daemon: string, verb: DaemonVerb, instance = ""): Promise<CoreResult> {
    if (instance && instance !== DEMO_INSTANCE) return notSelf(instance);
    return delay({ messages: [{ stream: "out", text: `demo: ${verb} ${daemon}` }], exitCode: 0 });
  }

  /** The schedule the real route answers with; nothing restarts in the demo. */
  restart(withUpgrade = false, instance = ""): Promise<RestartSchedule> {
    if (instance && instance !== DEMO_INSTANCE) return notSelf(instance);
    return delay({ scheduled: true, pid: 4242, withUpgrade, logfile: ".the-loop/logs/restart.out" });
  }

  config(signal?: AbortSignal, instance = ""): Promise<ConfigDocument> {
    if (instance && instance !== DEMO_INSTANCE) return notSelf(instance);
    return delay(this.configDocument, signal);
  }

  configSchema(signal?: AbortSignal, instance = ""): Promise<JsonSchema> {
    if (instance && instance !== DEMO_INSTANCE) return notSelf(instance);
    return delay(DEMO_CONFIG_SCHEMA, signal);
  }

  /**
   * The save the real service does, minus the file: the patch is merged into the
   * in-memory config and reported back with the same fields, so the editor's
   * saved/restart-required states are exercised without a workstation.
   */
  saveConfig(patch: Record<string, unknown>, instance = ""): Promise<ConfigSaveResult> {
    if (instance && instance !== DEMO_INSTANCE) return notSelf(instance);
    const changed = paths(patch, this.configDocument.config);
    this.configDocument = { ...this.configDocument, config: merge(this.configDocument.config, patch) };
    return delay({
      ...this.configDocument,
      changed,
      restartRequired: changed.filter((key) => key.startsWith("service.")),
      written: changed.length > 0,
    });
  }

  /** `issue-214` → the ref that owns it, so a graph call can be answered. */
  private refForSpec(specFolder: string): string {
    const number = specFolder.replace(/^\D+/, "");
    return (
      this.workItemRecords.find((item) => item.ref.endsWith(`#${number}`))?.ref ?? `github:octo/loop-lab#${number}`
    );
  }

  /**
   * `Omit<EventRecord, "ts">` would not do: the record's index signature makes
   * `Omit` drop every known key, so the required `event` goes with it. The
   * fields the demo actually emits are spelled out instead.
   */
  private emit(fields: {
    event: string;
    level?: string;
    source?: string;
    work_item?: string;
    actor?: string;
    node?: string;
    /** A standing session's name — it has no work item to key on (issue-277). */
    standing?: string;
  }): void {
    const record: EventRecord = { ...fields, ts: new Date().toISOString() };
    this.eventRecords = [...this.eventRecords, record];
    for (const subscriber of this.streamSubscribers) {
      subscriber({ kind: "log", record, cursor: String(this.eventRecords.length) });
    }
  }

  private streamSubscribers = new Set<(frame: StreamFrame) => void>();

  /**
   * Streaming, on the fixture (issue-239).
   *
   * Demo mode is not exempt from a feature: the hosted page has to be
   * explorable before anyone has a tunnel open, and a "streaming" mode that did
   * nothing there would misrepresent the thing it is demonstrating. Every
   * control verb below already calls `emit`, so the fixture has a real source of
   * change to push — the frames a demo viewer sees are the ones their own clicks
   * produced, which is exactly what the live stream does.
   *
   * No timer inventing traffic: a fake event arriving on its own would teach a
   * viewer that the dashboard shows things that did not happen.
   */
  stream(_query: StreamQuery, handlers: StreamHandlers): (() => void) | null {
    this.streamSubscribers.add(handlers.onFrame);
    // Asynchronously, so a caller that sets state in `onOpen` is not doing it
    // during its own render — the same shape a real connection has.
    const opened = setTimeout(() => handlers.onOpen?.(), 0);
    return () => {
      clearTimeout(opened);
      this.streamSubscribers.delete(handlers.onFrame);
    };
  }
}
