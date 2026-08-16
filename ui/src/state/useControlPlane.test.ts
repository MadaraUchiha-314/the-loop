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
import { fetchGraphs } from "./useControlPlane.ts";

const REF = "github:acme/widgets#7";

const WORK_ITEM: WorkItemRecord = {
  ref: REF,
  graph: { workItem: "issue-7", nodes: [{ id: "design", phase: "design" }] },
} as WorkItemRecord;

const SESSION: SessionRecord = {
  ref: REF,
  workItem: { ref: REF, provider: "github", owner: "acme", repo: "widgets", number: 7 },
  harness: "claude",
  harnessSessionId: "s1",
  cwd: "/gone/worktrees/acme/widgets/7",
  status: "closed",
} as SessionRecord;

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
