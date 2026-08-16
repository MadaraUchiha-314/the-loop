/**
 * What a streamed frame makes stale (issue-239).
 *
 * A pure function, tested as one: the whole point of two invalidation classes is
 * that a graph move costs one `graph/check` rather than a board sweep, and that
 * is a claim about this mapping and nothing else.
 */

import { describe, expect, it } from "vitest";

import { invalidationFor, mergeInvalidation, emptyInvalidation, type StreamFrame } from "./stream.ts";

const REF = "github:octo/repo#7";
const OTHER = "github:octo/repo#8";

function log(event: string, fields: Record<string, unknown> = {}): StreamFrame {
  return { kind: "log", cursor: "1", record: { ts: "2026-08-16T00:00:00Z", event, ...fields } };
}

describe("invalidationFor", () => {
  it("sends a graph event to that one work item's loop position", () => {
    const result = invalidationFor(log("graph.advanced", { work_item: REF }));
    expect([...result.graphRefs]).toEqual([REF]);
    expect(result.lists).toBe(false);
  });

  it("covers every graph.* type, not a list of the ones that exist today", () => {
    for (const event of ["graph.advanced", "graph.blocked", "graph.parked", "graph.frozen", "graph.invented_later"]) {
      expect([...invalidationFor(log(event, { work_item: REF })).graphRefs]).toEqual([REF]);
    }
  });

  it("sends a session or dispatch event to the list calls", () => {
    for (const event of ["session.spawned", "dispatch.succeeded", "control.command", "workspace.prepared"]) {
      const result = invalidationFor(log(event, { work_item: REF }));
      expect(result.lists).toBe(true);
      expect([...result.graphRefs]).toEqual([]);
    }
  });

  /**
   * The fail-safe direction. `EVENT_TYPES` grows every few work items, and a
   * dashboard that ignored what it did not recognise would go quietly stale
   * against a newer service — the exact failure streaming exists to remove.
   */
  it("refreshes the lists for an event type it has never heard of", () => {
    expect(invalidationFor(log("something.invented_next_year")).lists).toBe(true);
  });

  it("routes a transcript frame to that ref's transcript, and nothing else", () => {
    const result = invalidationFor({ kind: "transcript", ref: REF, totalLines: 412 });
    expect([...result.transcriptRefs]).toEqual([REF]);
    expect(result.lists).toBe(false);
    expect([...result.graphRefs]).toEqual([]);
  });

  /** The server bounds what it will replay; the client's answer is to refetch. */
  it("treats a desync as everything being stale", () => {
    const result = invalidationFor({ kind: "desync", reason: "replay-window" });
    expect(result.lists).toBe(true);
    expect(result.all).toBe(true);
  });

  it("still refreshes the lists when a graph event names no work item", () => {
    // A malformed or partial record must not be silently dropped.
    expect(invalidationFor(log("graph.advanced")).lists).toBe(true);
  });
});

describe("mergeInvalidation", () => {
  it("collapses a burst into one refresh covering all of it", () => {
    const merged = [
      log("graph.advanced", { work_item: REF }),
      log("graph.blocked", { work_item: OTHER }),
      log("session.spawned", { work_item: REF }),
    ].reduce((acc, frame) => mergeInvalidation(acc, invalidationFor(frame)), emptyInvalidation());

    expect(merged.lists).toBe(true);
    expect([...merged.graphRefs].toSorted()).toEqual([REF, OTHER].toSorted());
  });

  it("is a no-op against the empty invalidation", () => {
    const one = invalidationFor(log("graph.advanced", { work_item: REF }));
    expect(mergeInvalidation(emptyInvalidation(), one)).toEqual(one);
  });

  it("does not mutate either argument", () => {
    const a = invalidationFor(log("graph.advanced", { work_item: REF }));
    const b = invalidationFor(log("session.spawned", { work_item: OTHER }));
    mergeInvalidation(a, b);
    expect(a.lists).toBe(false);
    expect([...b.graphRefs]).toEqual([]);
  });
});
