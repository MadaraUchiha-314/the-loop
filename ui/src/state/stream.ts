/**
 * What a streamed frame makes stale, and nothing else (issue-239).
 *
 * The board is two rounds: four flat list calls, then one `POST /graph/check`
 * per loop — and the second round is where a work item's position on its loop
 * comes from, read off `graph-state.json` on the workstation. That is why a
 * stream which only replayed `GET /api/v1/events` would not refresh the board:
 * the rail would go stale while the event list scrolled, which is a screen that
 * looks live and lies.
 *
 * So a frame maps onto **two classes**, not one:
 *
 * - `graph.*` for a ref -> re-check that one loop. One request.
 * - anything else -> refetch the four lists.
 *
 * One class would have been simpler and a regression: a busy work item emits
 * several events a second, and refreshing the whole board per frame costs more
 * than the 15-second poll this replaces.
 */

import type { EventRecord } from "../api/types.ts";

export type StreamFrame =
  | { kind: "log"; record: EventRecord; cursor: string }
  | { kind: "transcript"; ref: string; totalLines: number }
  | { kind: "desync"; reason: string };

export interface Invalidation {
  /** The four list calls — work items, sessions, attention, question events. */
  lists: boolean;
  /** Refs whose loop position needs re-reading. */
  graphRefs: Set<string>;
  /** Refs whose transcript grew. */
  transcriptRefs: Set<string>;
  /** The server could not honour our cursor: nothing held is trustworthy. */
  all: boolean;
}

export function emptyInvalidation(): Invalidation {
  return { lists: false, graphRefs: new Set(), transcriptRefs: new Set(), all: false };
}

export function invalidationFor(frame: StreamFrame): Invalidation {
  const result = emptyInvalidation();

  if (frame.kind === "desync") {
    // The server bounded a replay, or the log rotated under it. Everything held
    // may have a gap in it, so the only honest response is to refetch.
    result.all = true;
    result.lists = true;
    return result;
  }

  if (frame.kind === "transcript") {
    result.transcriptRefs.add(frame.ref);
    return result;
  }

  const ref = frame.record.work_item;
  if (frame.record.event?.startsWith("graph.") && ref) {
    result.graphRefs.add(ref);
    return result;
  }

  // Everything else, INCLUDING an event type this bundle has never heard of.
  // `EVENT_TYPES` grows every few work items; a dashboard that ignored what it
  // did not recognise would go quietly stale against a newer service, which is
  // the exact failure streaming exists to remove. Refreshing the lists is the
  // cheap, fail-safe direction.
  result.lists = true;
  return result;
}

/** Union of two invalidations, mutating neither — a burst becomes one refresh. */
export function mergeInvalidation(a: Invalidation, b: Invalidation): Invalidation {
  return {
    lists: a.lists || b.lists,
    all: a.all || b.all,
    graphRefs: new Set([...a.graphRefs, ...b.graphRefs]),
    transcriptRefs: new Set([...a.transcriptRefs, ...b.transcriptRefs]),
  };
}

export function isEmpty(invalidation: Invalidation): boolean {
  return (
    !invalidation.lists &&
    !invalidation.all &&
    invalidation.graphRefs.size === 0 &&
    invalidation.transcriptRefs.size === 0
  );
}
