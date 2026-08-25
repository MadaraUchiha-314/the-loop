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

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { ApiError, TheLoopApi } from "../api/client.ts";
import {
  awaitingInput,
  buildWorkItemViews,
  innerKey,
  railFromStatus,
  railProgress,
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
import type { RefreshMode } from "./settings.ts";
import type { Invalidation } from "./stream.ts";
import { useStream, type StreamState } from "./useStream.ts";

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
  /** The stream connection's state, for the indicator (issue-239). */
  stream: StreamState;
  /**
   * Bumped when the watched session's transcript grows, so the detail page can
   * refetch it without owning a second stream connection (R3.5: one per tab).
   */
  transcriptTick: number;
}

/** How this browser keeps the board current — the viewer's Settings choice. */
export interface RefreshConfig {
  mode: RefreshMode;
  /** Used only while `mode` is `poll`. */
  pollSeconds: number;
}

export function useControlPlane(
  api: TheLoopApi,
  refreshConfig: RefreshConfig,
  /** The ref whose transcript this tab is watching, or `""` for none. */
  watchTranscript = "",
): Board {
  const [views, setViews] = useState<WorkItemView[]>([]);
  const [daemons, setDaemons] = useState<DaemonStatus[]>([]);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [loading, setLoading] = useState(true);
  const [fetchedAt, setFetchedAt] = useState<number | null>(null);
  const [nonce, setNonce] = useState(0);
  const [transcriptTick, setTranscriptTick] = useState(0);

  // A refresh must not race the poll timer into two overlapping fetches.
  const inFlight = useRef<AbortController | null>(null);
  const graphInFlight = useRef<AbortController | null>(null);

  const refresh = useCallback(() => setNonce((value) => value + 1), []);

  // Held so a streamed invalidation can re-check ONE loop against the rows the
  // last round-one fetch produced, instead of sweeping the whole board.
  const latest = useRef<{ workItems: WorkItemRecord[]; sessions: SessionRecord[]; graphs: GraphReports } | null>(null);

  /**
   * A `graph.*` frame's refresh: one `POST /graph/check`, merged into what is
   * already drawn.
   *
   * This is the whole reason there are two invalidation classes. A busy work
   * item emits several events a second, and a board sweep per frame would cost
   * more than the 15-second poll streaming replaces — so the common case, an
   * agent advancing its graph, must not be a sweep.
   */
  const refreshGraph = useCallback(
    async (refs: Set<string>) => {
      const held = latest.current;
      if (!held) return;
      // Aborted by the next full load, and on unmount, for the same reason round
      // one is: a slow targeted check must not land after a full refresh and
      // overwrite fresher rows with staler ones.
      graphInFlight.current?.abort();
      const controller = new AbortController();
      graphInFlight.current = controller;

      const reports = await fetchGraphs(
        api,
        held.workItems.filter((item) => refs.has(item.ref)),
        held.sessions.filter((session) => refs.has(session.ref)),
        controller.signal,
      );
      if (controller.signal.aborted || latest.current === null) return;

      // Merged against what is held **now**, not against the value read before
      // the await: two flushes in flight would otherwise both start from the
      // same base and the second write would drop the first one's report.
      const merged = mergeReports(latest.current.graphs, reports);
      latest.current.graphs = merged;
      setViews((current) => applyGraphs(current, merged));
    },
    [api],
  );

  const onFlush = useCallback(
    (invalidation: Invalidation) => {
      if (invalidation.lists || invalidation.all) refresh();
      else if (invalidation.graphRefs.size > 0) void refreshGraph(invalidation.graphRefs);
      if (invalidation.transcriptRefs.size > 0) setTranscriptTick((value) => value + 1);
    },
    [refresh, refreshGraph],
  );

  const streamQuery = useMemo(
    () => ({ transcript: watchTranscript ? [watchTranscript] : [] }),
    [watchTranscript],
  );
  const stream = useStream(api, refreshConfig.mode === "stream", streamQuery, onFlush);

  // Streaming keeps the timer off entirely; `manual` and a stalled stream both
  // mean "no background request", and `fallback` is the one case where the
  // viewer asked for streaming and has to be given the poll instead.
  const pollSeconds =
    refreshConfig.mode === "poll" || (refreshConfig.mode === "stream" && stream.name === "fallback")
      ? refreshConfig.pollSeconds
      : 0;

  useEffect(() => {
    let cancelled = false;

    async function load(): Promise<void> {
      inFlight.current?.abort();
      // A targeted graph check in flight is about to be answered by this fuller
      // one; letting it finish would merge a staler report over a fresher row.
      graphInFlight.current?.abort();
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

        // Held reports are passed back in so loops nothing is driving — a
        // closed session's, say — are answered from cache instead of a fresh
        // `graph/check` every cycle (issue-283, feature #9): each check builds
        // a runtime server-side, and a dormant item's answer cannot change.
        const graphs = await fetchGraphs(api, workItems, sessions, signal, latest.current?.graphs);
        if (cancelled || signal.aborted) return;
        // Held for `refreshGraph`: a streamed graph move re-checks one loop
        // against these rows rather than refetching the board to find them.
        latest.current = { workItems, sessions, graphs };
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
        graphInFlight.current?.abort();
      };
    }
    return () => {
      cancelled = true;
      inFlight.current?.abort();
      graphInFlight.current?.abort();
    };
  }, [api, pollSeconds, nonce]);

  return { views, daemons, error, loading, fetchedAt, refresh, stream, transcriptTick };
}

/**
 * One report set laid over another — the newer entries win, per key.
 *
 * Exported for its own test because it is where a lost update would hide: the
 * caller must merge against what is held at **write** time, and a helper that
 * quietly returned one side or mutated an argument would make that impossible to
 * see.
 */
export function mergeReports(base: GraphReports, incoming: GraphReports): GraphReports {
  return {
    outer: { ...base.outer, ...incoming.outer },
    inner: { ...base.inner, ...incoming.inner },
  };
}

/**
 * Re-project the held rows onto fresher graph reports.
 *
 * Deliberately narrow: a streamed `graph.*` frame changes a work item's position
 * on its loop and nothing else, so only the rail and the fields derived from it
 * are replaced. Rebuilding the whole view from `buildWorkItemViews` would need
 * the list data again, which is exactly the request this path exists to avoid.
 */
function applyGraphs(views: WorkItemView[], graphs: GraphReports): WorkItemView[] {
  return views.map((view) => {
    const status = graphs.outer[view.ref];
    // A report with no nodes is the absence of a position, not a position — the
    // shape `/graph/check` answers with when the checkout is gone (issue-238).
    // Keeping the frozen rail is strictly more informative than blanking it.
    if (!status || status.nodes.length === 0) return view;
    const rail = railFromStatus(status);
    return {
      ...view,
      rail,
      status,
      progress: railProgress(rail),
      currentNode: status.currentNode ?? "",
      parked: status.parked ?? null,
    };
  });
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
  cached?: GraphReports,
): Promise<GraphReports> {
  const sessionByRef = new Map(sessions.map((session) => [session.ref, session]));
  const recordByRef = new Map(workItems.map((item) => [item.ref, item]));
  const jobs: GraphJob[] = [];
  const held: GraphReports = { outer: {}, inner: {} };

  for (const ref of new Set([...recordByRef.keys(), ...sessionByRef.keys()])) {
    const session = sessionByRef.get(ref);
    const repo = session?.cwd;
    const spec = specId(recordByRef.get(ref) ?? { ref });
    // No checkout on this machine means no graph state to read. The row still
    // renders — `railFromFrozen` covers it — so this is a skip, not a failure.
    if (!repo || !spec) continue;

    // A loop nothing is driving cannot move: a session that is neither active
    // nor paused holds a graph no agent advances, so a report already fetched
    // is reused instead of re-checked every poll cycle (issue-283, feature #9).
    // The first load — no cache — still reads it once.
    const dormant = session !== undefined && session.status !== "active" && session.status !== "paused";
    const cachedOuter = cached?.outer[ref];
    if (dormant && cachedOuter) {
      held.outer[ref] = cachedOuter;
      for (const pr of session.pullRequests ?? []) {
        const key = innerKey(ref, pr.workItem.ref);
        const cachedInner = cached?.inner[key];
        if (cachedInner) held.inner[key] = cachedInner;
      }
      continue;
    }

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

  const reports: GraphReports = held;
  let cursor = 0;

  async function worker(): Promise<void> {
    while (cursor < jobs.length && !signal.aborted) {
      const job = jobs[cursor++]!;
      try {
        // Sequential inside a worker is the point: N workers each taking the
        // next job as their own finishes IS the concurrency cap.
        // oxlint-disable-next-line no-await-in-loop
        const status = await job.run(signal);
        // `repoResolved: false` is the server saying the checkout is gone
        // (issue-238). Storing it would swap railFromFrozen — which still shows
        // the agreed node list — for an empty rail, so it is dropped here
        // exactly as a rejection is dropped by the catch below. `=== false`
        // on purpose: absent means a normal answer, not a falsy one.
        if (status.repoResolved === false) continue;
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
