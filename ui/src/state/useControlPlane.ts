/**
 * The board: everything the dashboard, the detail page and the inbox read.
 *
 * Two rounds, because the second depends on the first. Round one is the four
 * flat lists (`/work-items`, `/sessions`, `/attention`, `/daemons`). Round two
 * is one `graph/check` per loop — and a graph call needs a **checkout path**,
 * which only the session record knows (`cwd`), plus the spec-folder id, which
 * only the work-item record knows. That is why loop position cannot come from a
 * single request, and why an item with no session shows its frozen node list
 * with no pointer instead of an error.
 *
 * Graph reports are gathered with `allSettled` and a small concurrency cap: one
 * unreadable checkout must not blank the whole board, and a 20-item board must
 * not open 40 sockets at once against a single-worker uvicorn.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import type { ApiError, TheLoopApi } from "../api/client.ts";
import {
  awaitingInput,
  buildWorkItemViews,
  innerKey,
  specId,
  type GraphReports,
  type WorkItemView,
} from "../api/model.ts";
import type {
  AttentionItem,
  DaemonStatus,
  EventRecord,
  GraphStatus,
  SessionRecord,
  WorkItemRecord,
} from "../api/types.ts";

/**
 * The event types that put a work item in "waiting on you" — one filtered call
 * for the whole board rather than one per row. `awaiting_input` is emitted by
 * `the-loop ask` and closed by the `reply_sent` the reply route emits
 * (issue-208). See ui/README.md.
 */
const QUESTION_EVENTS = ["session.awaiting_input", "session.reply_sent"];

/** Simultaneous graph checks. Reads are cheap but not free — they build a runtime. */
const GRAPH_CONCURRENCY = 4;

export interface Board {
  views: WorkItemView[];
  daemons: DaemonStatus[];
  /** Set when round one failed — the screens have nothing to draw. */
  error: ApiError | Error | null;
  /** True only for the first load; a background refresh does not blank the page. */
  loading: boolean;
  /** When the last successful round-one fetch completed. */
  fetchedAt: number | null;
  refresh: () => void;
}

export function useControlPlane(api: TheLoopApi, pollSeconds: number): Board {
  const [views, setViews] = useState<WorkItemView[]>([]);
  const [daemons, setDaemons] = useState<DaemonStatus[]>([]);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [loading, setLoading] = useState(true);
  const [fetchedAt, setFetchedAt] = useState<number | null>(null);
  const [nonce, setNonce] = useState(0);

  // A refresh must not race the poll timer into two overlapping fetches.
  const inFlight = useRef<AbortController | null>(null);

  const refresh = useCallback(() => setNonce((value) => value + 1), []);

  useEffect(() => {
    let cancelled = false;

    async function load(): Promise<void> {
      inFlight.current?.abort();
      const controller = new AbortController();
      inFlight.current = controller;
      const { signal } = controller;

      try {
        const [workItems, sessions, attention, daemonList, questionEvents] = await Promise.all([
          api.workItems(signal),
          api.sessions(signal),
          api.attention(signal),
          // Neither the daemon chips nor the question flag is worth failing the
          // board over; both degrade to "nothing to show".
          api.daemons(signal).catch(() => [] as DaemonStatus[]),
          api.events({ type: QUESTION_EVENTS, limit: 200 }, signal).catch(() => [] as EventRecord[]),
        ]);
        if (cancelled || signal.aborted) return;

        const awaiting = awaitingInput(questionEvents);
        setDaemons(daemonList);
        // Draw the board before the graph round so a slow checkout does not
        // hold back the rows that are already answerable.
        setViews(buildWorkItemViews({ workItems, sessions, attention, awaiting }));
        setError(null);
        setFetchedAt(Date.now());
        setLoading(false);

        const graphs = await fetchGraphs(api, workItems, sessions, signal);
        if (cancelled || signal.aborted) return;
        setViews(buildWorkItemViews({ workItems, sessions, attention, awaiting, graphs }));
      } catch (cause) {
        if (cancelled || signal.aborted) return;
        setError(cause instanceof Error ? cause : new Error(String(cause)));
        setLoading(false);
      }
    }

    void load();

    if (pollSeconds > 0) {
      const timer = setInterval(() => void load(), pollSeconds * 1000);
      return () => {
        cancelled = true;
        clearInterval(timer);
        inFlight.current?.abort();
      };
    }
    return () => {
      cancelled = true;
      inFlight.current?.abort();
    };
  }, [api, pollSeconds, nonce]);

  return { views, daemons, error, loading, fetchedAt, refresh };
}

interface GraphJob {
  key: string;
  outer: boolean;
  run: (signal: AbortSignal) => Promise<GraphStatus>;
}

/**
 * Round two: one graph report per loop, for every ref that has both halves of
 * the join. Exported for its own test (issue-238) — it is a pure function of
 * its arguments, and asserting on it directly says which of the poll effect,
 * the abort wiring and this projection broke.
 */
export async function fetchGraphs(
  api: TheLoopApi,
  workItems: WorkItemRecord[],
  sessions: SessionRecord[],
  signal: AbortSignal,
): Promise<GraphReports> {
  const sessionByRef = new Map(sessions.map((session) => [session.ref, session]));
  const recordByRef = new Map(workItems.map((item) => [item.ref, item]));
  const jobs: GraphJob[] = [];

  for (const ref of new Set([...recordByRef.keys(), ...sessionByRef.keys()])) {
    const session = sessionByRef.get(ref);
    const repo = session?.cwd;
    const spec = specId(recordByRef.get(ref) ?? { ref });
    // No checkout on this machine means no graph state to read. The row still
    // renders — `railFromFrozen` covers it — so this is a skip, not a failure.
    if (!repo || !spec) continue;

    jobs.push({ key: ref, outer: true, run: (s) => api.graphCheck({ repo, workItem: spec }, s) });

    for (const pr of session?.pullRequests ?? []) {
      const number = pr.workItem.number;
      const sameRepo = pr.workItem.owner === session?.workItem.owner && pr.workItem.repo === session?.workItem.repo;
      const prRepo = sameRepo ? "" : `${pr.workItem.owner}/${pr.workItem.repo}`;
      jobs.push({
        key: innerKey(ref, pr.workItem.ref),
        outer: false,
        run: (s) => api.graphCheck({ repo, workItem: spec, pr: number, prRepo }, s),
      });
    }
  }

  const reports: GraphReports = { outer: {}, inner: {} };
  let cursor = 0;

  async function worker(): Promise<void> {
    while (cursor < jobs.length && !signal.aborted) {
      const job = jobs[cursor++]!;
      try {
        // Sequential inside a worker is the point: N workers each taking the
        // next job as their own finishes IS the concurrency cap.
        // oxlint-disable-next-line no-await-in-loop
        const status = await job.run(signal);
        if (job.outer) reports.outer[job.key] = status;
        else reports.inner[job.key] = status;
      } catch {
        // An unreadable checkout, a spec folder that does not exist yet, a
        // repo moved off this machine: all of them mean "no position known",
        // which the rail already renders. Nothing to escalate.
      }
    }
  }

  await Promise.all(Array.from({ length: Math.min(GRAPH_CONCURRENCY, jobs.length) }, worker));
  return reports;
}

export type { AttentionItem };
