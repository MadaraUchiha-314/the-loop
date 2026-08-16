/**
 * One stream connection per tab, and what to do when it misbehaves (issue-239).
 *
 * Three jobs, none of which the transport can do for us:
 *
 * 1. **Coalesce.** A dispatch emits four or five events in a few milliseconds.
 *    Refreshing per frame would make streaming more expensive than the 15-second
 *    poll it replaces, so frames accumulate for {@link COALESCE_MS} and flush as
 *    one invalidation.
 * 2. **Count failures and stop.** `EventSource` reconnects on its own and cannot
 *    be told otherwise, so this counts consecutive failures and closes the source
 *    at {@link MAX_CONSECUTIVE_FAILURES} — which is what makes "streaming
 *    unavailable, polling instead" a state the operator can see rather than a
 *    dead board being retried invisibly. A **terminal** failure short-circuits
 *    that count: when the browser has stopped trying, waiting for a fifth
 *    failure that can never arrive is the same frozen board by another route.
 * 3. **Say which state it is in**, in words: `live` with a timestamp,
 *    `reconnecting` with an attempt number, or `fallback` with the reason. A
 *    screen that is not updating must never look like a screen where nothing is
 *    happening.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import type { ApiError, StreamQuery, TheLoopApi } from "../api/client.ts";
import { emptyInvalidation, invalidationFor, isEmpty, mergeInvalidation, type Invalidation } from "./stream.ts";

/**
 * How long frames accumulate before one refresh goes out.
 *
 * Long enough to collapse a burst, short enough to stay an order of magnitude
 * inside the 2-second budget R1.2 sets. At 250ms the worst case is four board
 * refreshes a second; the observed burst pattern makes it one.
 */
export const COALESCE_MS = 250;

/** Consecutive connection failures before the hook stops trying and says so. */
export const MAX_CONSECUTIVE_FAILURES = 5;

export type StreamState =
  | { name: "off" }
  | { name: "connecting" }
  | { name: "live"; since: number }
  | { name: "reconnecting"; attempt: number }
  | { name: "fallback"; advice: string };

const CANNOT_STREAM =
  "This browser has no EventSource, so the stream cannot be opened — polling instead.";

export function useStream(
  api: TheLoopApi,
  enabled: boolean,
  query: StreamQuery,
  onFlush: (invalidation: Invalidation) => void,
): StreamState {
  const [state, setState] = useState<StreamState>({ name: "off" });

  // Refs, not state: changing these must never re-run the effect, or the
  // connection would be torn down and rebuilt by its own traffic.
  const pending = useRef<Invalidation>(emptyInvalidation());
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const failures = useRef(0);
  const flushRef = useRef(onFlush);
  flushRef.current = onFlush;

  const flush = useCallback(() => {
    timer.current = null;
    const invalidation = pending.current;
    pending.current = emptyInvalidation();
    if (!isEmpty(invalidation)) flushRef.current(invalidation);
  }, []);

  // The query is an object literal at every call site, so comparing it by
  // identity would reconnect on every render of the page that owns it.
  const watch = (query.workItem ?? []).join(",");
  const transcripts = (query.transcript ?? []).join(",");

  useEffect(() => {
    if (!enabled) {
      setState({ name: "off" });
      return undefined;
    }

    failures.current = 0;
    setState({ name: "connecting" });

    // Declared before the call, not after: `onError` can fire before
    // `api.stream` has returned, and a `const` assigned afterwards would be in
    // its temporal dead zone at exactly the moment the handler needs it.
    // Nulled on close, so giving up and unmounting cannot both close it.
    let closeConnection: (() => void) | null = null;
    const closeOnce = () => {
      const close = closeConnection;
      closeConnection = null;
      close?.();
    };

    const opened = api.stream(
      { workItem: watch ? watch.split(",") : [], transcript: transcripts ? transcripts.split(",") : [] },
      {
        onOpen: () => {
          // A connection that opened is proof the path works, so the budget
          // resets: a flaky link that recovers must not accumulate toward the
          // limit across an afternoon.
          failures.current = 0;
          setState({ name: "live", since: Date.now() });
        },
        onFrame: (frame) => {
          pending.current = mergeInvalidation(pending.current, invalidationFor(frame));
          if (timer.current === null) timer.current = setTimeout(flush, COALESCE_MS);
        },
        onError: (error: ApiError, terminal: boolean) => {
          failures.current += 1;
          // `terminal` means the browser closed the source and will not try
          // again — counting toward a limit it can never reach would leave the
          // board frozen behind a "reconnecting" label forever.
          if (!terminal && failures.current < MAX_CONSECUTIVE_FAILURES) {
            setState({ name: "reconnecting", attempt: failures.current });
            return;
          }
          // Give up deliberately and visibly. `advice` already names the three
          // causes a browser cannot tell apart — wrong base URL, service not
          // running, origin not allowed — in cheapest-remedy order.
          setState({ name: "fallback", advice: error.advice });
          closeOnce();
        },
      },
    );

    if (opened === null) {
      setState({ name: "fallback", advice: CANNOT_STREAM });
      return undefined;
    }
    closeConnection = opened;

    return () => {
      if (timer.current !== null) {
        clearTimeout(timer.current);
        timer.current = null;
      }
      pending.current = emptyInvalidation();
      closeOnce();
    };
  }, [api, enabled, watch, transcripts, flush]);

  return state;
}
