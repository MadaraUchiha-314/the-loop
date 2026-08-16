/**
 * A checkout that is gone has no position to report, and the board already
 * renders that case from the frozen record. What is pinned here is that the
 * server saying so out loud (`repoResolved: false`, issue-238) reaches the same
 * place the old rejection did: no report stored, so `buildWorkItemViews` falls
 * back to `railFromFrozen`.
 */

import { describe, expect, it, vi } from "vitest";

import type { TheLoopApi } from "../api/client.ts";
import type { GraphStatus, SessionRecord, WorkItemRecord } from "../api/types.ts";
import { fetchGraphs, mergeReports } from "./useControlPlane.ts";

const REF = "github:acme/widgets#7";

const WORK_ITEM: WorkItemRecord = {
  ref: REF,
  graph: { workItem: "issue-7", nodes: [{ id: "design", phase: "design" }] },
};

const SESSION: SessionRecord = {
  ref: REF,
  workItem: { ref: REF, provider: "github", owner: "acme", repo: "widgets", number: 7 },
  harness: "claude",
  harnessSessionId: "s1",
  cwd: "/gone/worktrees/acme/widgets/7",
  status: "closed",
};

function apiAnswering(status: GraphStatus): TheLoopApi {
  return { graphCheck: vi.fn(() => Promise.resolve(status)) } as unknown as TheLoopApi;
}

describe("fetchGraphs", () => {
  it("stores nothing when the server says the checkout did not resolve", async () => {
    const api = apiAnswering({
      workItem: "issue-7",
      currentNode: "",
      ok: false,
      nodes: [],
      repoResolved: false,
    });

    const reports = await fetchGraphs(api, [WORK_ITEM], [SESSION], new AbortController().signal);

    expect(reports).toEqual({ outer: {}, inner: {} });
  });

  it("stores the report when the server answered with a position", async () => {
    const status: GraphStatus = {
      workItem: "issue-7",
      currentNode: "design",
      ok: true,
      nodes: [{ node: "design", status: "pass", outcome: "pass" }],
    };

    const reports = await fetchGraphs(
      apiAnswering(status),
      [WORK_ITEM],
      [SESSION],
      new AbortController().signal,
    );

    expect(reports.outer[REF]).toEqual(status);
  });
});

describe("mergeReports (issue-239)", () => {
  const a: GraphStatus = { workItem: "issue-1", currentNode: "design", ok: true, nodes: [] };
  const b: GraphStatus = { workItem: "issue-2", currentNode: "tasks-breakdown", ok: true, nodes: [] };
  const newerA: GraphStatus = { workItem: "issue-1", currentNode: "implementation", ok: true, nodes: [] };

  it("keeps entries the incoming set does not mention", () => {
    const merged = mergeReports({ outer: { one: a, two: b }, inner: {} }, { outer: { one: newerA }, inner: {} });
    expect(merged.outer["one"]).toBe(newerA);
    expect(merged.outer["two"]).toBe(b);
  });

  it("merges the inner loops independently of the outer ones", () => {
    const merged = mergeReports({ outer: { one: a }, inner: { "one::pr" : b } }, { outer: {}, inner: {} });
    expect(merged.outer["one"]).toBe(a);
    expect(merged.inner["one::pr"]).toBe(b);
  });

  /**
   * The lost-update hazard this exists to make visible: two coalesced flushes can
   * be in flight at once, and each must merge against what is held when it
   * *writes*, not what it read before its await. A helper that mutated its base
   * would hide the difference.
   */
  it("mutates neither argument", () => {
    const base = { outer: { one: a }, inner: {} };
    const incoming = { outer: { two: b }, inner: {} };
    mergeReports(base, incoming);
    expect(Object.keys(base.outer)).toEqual(["one"]);
    expect(Object.keys(incoming.outer)).toEqual(["two"]);
  });
});
