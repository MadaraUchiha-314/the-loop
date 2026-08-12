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
  CoreResult,
  DaemonStatus,
  DaemonVerb,
  EventRecord,
  GraphDefinition,
  GraphStatus,
  Health,
  SessionRecord,
  SessionVerb,
  WorkItemRecord,
} from "../api/types.ts";
import {
  DEMO_ATTENTION,
  DEMO_DAEMONS,
  DEMO_EVENTS,
  DEMO_INNER_GRAPHS,
  DEMO_OUTER_GRAPHS,
  DEMO_SESSIONS,
  DEMO_WORK_ITEMS,
  INNER_NODES,
  OUTER_NODES,
} from "./fixture.ts";

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

  controlDaemon(daemon: string, verb: DaemonVerb): Promise<CoreResult> {
    return delay({ messages: [{ stream: "out", text: `demo: ${verb} ${daemon}` }], exitCode: 0 });
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
