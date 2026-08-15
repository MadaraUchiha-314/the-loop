/**
 * The demo transport: {@link TheLoopApi} answered from `fixture.ts`.
 *
 * Control verbs mutate an in-memory copy so pause/resume/approve behave, and
 * append to the demo event log the way the real service would. Nothing here
 * persists — a reload is a fresh board — because the point is to show the
 * screens, not to be a second implementation of the-loop.
 */

import type { EventQuery, GraphQuery, TheLoopApi } from "../api/client.ts";
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
  JsonSchema,
  SessionEndpoint,
  SessionRecord,
  SessionVerb,
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
  private attentionItems: AttentionItem[] = clone(DEMO_ATTENTION);
  private eventRecords: EventRecord[] = clone(DEMO_EVENTS);
  private outer: Record<string, GraphStatus> = clone(DEMO_OUTER_GRAPHS);
  private configDocument: ConfigDocument = clone(DEMO_CONFIG);
  private inner: Record<string, GraphStatus> = clone(DEMO_INNER_GRAPHS);

  health(signal?: AbortSignal): Promise<Health> {
    return delay({ status: "ok", version: "demo" }, signal);
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

  graphDefinition(_repo: string, pr?: number, signal?: AbortSignal): Promise<GraphDefinition> {
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

  graphCheck(query: GraphQuery, signal?: AbortSignal): Promise<GraphStatus> {
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

  graphComplete(query: GraphQuery & { node?: string; actor?: string }): Promise<CoreResult> {
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

  controlSession(ref: string, verb: SessionVerb, _comment = true): Promise<CoreResult> {
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

  replySession(ref: string, _text: string, _actor = ""): Promise<CoreResult> {
    // Same convention as the control verbs: the demo behaves. The reply_sent
    // event is what closes the question card, exactly as the service's does.
    this.emit({ event: "session.reply_sent", level: "info", source: "service", work_item: ref, actor: "you" });
    return delay({ messages: [{ stream: "out", text: `demo: replied to ${ref}` }], exitCode: 0 });
  }

  transcript(ref: string, tail = 200, signal?: AbortSignal): Promise<TranscriptResponse> {
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

  controlDaemon(daemon: string, verb: DaemonVerb): Promise<CoreResult> {
    return delay({ messages: [{ stream: "out", text: `demo: ${verb} ${daemon}` }], exitCode: 0 });
  }

  /** The schedule the real route answers with; nothing restarts in the demo. */
  restart(withUpgrade = false): Promise<RestartSchedule> {
    return delay({ scheduled: true, pid: 4242, withUpgrade, logfile: ".the-loop/logs/restart.out" });
  }

  config(signal?: AbortSignal): Promise<ConfigDocument> {
    return delay(this.configDocument, signal);
  }

  configSchema(signal?: AbortSignal): Promise<JsonSchema> {
    return delay(DEMO_CONFIG_SCHEMA, signal);
  }

  /**
   * The save the real service does, minus the file: the patch is merged into the
   * in-memory config and reported back with the same fields, so the editor's
   * saved/restart-required states are exercised without a workstation.
   */
  saveConfig(patch: Record<string, unknown>): Promise<ConfigSaveResult> {
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
  }): void {
    const record: EventRecord = { ...fields, ts: new Date().toISOString() };
    this.eventRecords = [...this.eventRecords, record];
  }
}
