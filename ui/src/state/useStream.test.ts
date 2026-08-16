/**
 * The connection state machine (issue-239).
 *
 * Driven against a stub transport rather than a real `EventSource`, because what
 * is under test is the *policy* — coalesce a burst into one refresh, count
 * failures, and stop trying — not the browser's implementation of SSE. The
 * transport's own behaviour is asserted end to end in
 * `cli/tests/test_stream_integration.py`.
 */

import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, type StreamHandlers, type StreamQuery, type TheLoopApi } from "../api/client.ts";
import { COALESCE_MS, MAX_CONSECUTIVE_FAILURES, useStream } from "./useStream.ts";
import type { Invalidation } from "./stream.ts";

const REF = "github:octo/repo#7";

/** A transport whose connection this test opens, breaks and closes by hand. */
function stubTransport() {
  const state: { handlers: StreamHandlers | null; queries: StreamQuery[]; unsubscribes: number } = {
    handlers: null,
    queries: [],
    unsubscribes: 0,
  };
  const api = {
    isDemo: false,
    stream(query: StreamQuery, handlers: StreamHandlers) {
      state.queries.push(query);
      state.handlers = handlers;
      return () => {
        state.unsubscribes += 1;
        state.handlers = null;
      };
    },
  } as unknown as TheLoopApi;
  return { api, state };
}

function logFrame(event: string, ref = REF) {
  return { kind: "log" as const, cursor: "1", record: { ts: "2026-08-16T00:00:00Z", event, work_item: ref } };
}

describe("useStream", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("does not connect at all when the mode is not streaming", () => {
    const { api, state } = stubTransport();
    renderHook(() => useStream(api, false, {}, vi.fn()));
    expect(state.handlers).toBeNull();
  });

  it("reports live once the connection opens", () => {
    const { api, state } = stubTransport();
    const { result } = renderHook(() => useStream(api, true, {}, vi.fn()));
    expect(result.current.name).toBe("connecting");
    act(() => state.handlers?.onOpen?.());
    expect(result.current.name).toBe("live");
  });

  it("collapses a burst of frames into one refresh covering all of them", () => {
    const { api, state } = stubTransport();
    const onFlush = vi.fn<(invalidation: Invalidation) => void>();
    renderHook(() => useStream(api, true, {}, onFlush));

    act(() => {
      state.handlers?.onOpen?.();
      state.handlers?.onFrame(logFrame("graph.advanced"));
      state.handlers?.onFrame(logFrame("graph.blocked", "github:octo/repo#8"));
      state.handlers?.onFrame(logFrame("session.spawned"));
    });
    expect(onFlush).not.toHaveBeenCalled(); // still inside the window

    act(() => void vi.advanceTimersByTime(COALESCE_MS));
    expect(onFlush).toHaveBeenCalledTimes(1);

    const invalidation = onFlush.mock.calls[0]![0];
    expect(invalidation.lists).toBe(true);
    expect([...invalidation.graphRefs].toSorted()).toEqual([REF, "github:octo/repo#8"].toSorted());
  });

  it("does not flush when nothing arrived", () => {
    const { api, state } = stubTransport();
    const onFlush = vi.fn();
    renderHook(() => useStream(api, true, {}, onFlush));
    act(() => state.handlers?.onOpen?.());
    act(() => void vi.advanceTimersByTime(COALESCE_MS * 5));
    expect(onFlush).not.toHaveBeenCalled();
  });

  it("shows reconnecting while the browser retries, counting attempts", () => {
    const { api, state } = stubTransport();
    const { result } = renderHook(() => useStream(api, true, {}, vi.fn()));
    act(() => state.handlers?.onOpen?.());

    act(() => state.handlers?.onError(new ApiError("network", "dropped", "u"), false));
    expect(result.current.name).toBe("reconnecting");
    if (result.current.name === "reconnecting") expect(result.current.attempt).toBe(1);

    act(() => state.handlers?.onError(new ApiError("network", "dropped", "u"), false));
    if (result.current.name === "reconnecting") expect(result.current.attempt).toBe(2);
  });

  /**
   * `EventSource` retries forever and cannot be told to stop. Without this the
   * page would sit on a dead board reconnecting invisibly, which is the failure
   * R4.4 exists to prevent — so the hook closes the source itself.
   */
  it("gives up after the failure limit and hands back the advice", () => {
    const { api, state } = stubTransport();
    const { result } = renderHook(() => useStream(api, true, {}, vi.fn()));
    act(() => state.handlers?.onOpen?.());

    const failures = MAX_CONSECUTIVE_FAILURES;
    for (let i = 0; i < failures; i += 1) {
      act(() => state.handlers?.onError(new ApiError("network", "nothing is listening", "u"), false));
    }

    expect(result.current.name).toBe("fallback");
    if (result.current.name === "fallback") {
      expect(result.current.advice).toContain("service.cors.allowOrigins");
    }
    expect(state.unsubscribes).toBe(1); // it stopped trying, rather than retrying invisibly
  });

  it("forgets past failures once a connection opens again", () => {
    const { api, state } = stubTransport();
    const { result } = renderHook(() => useStream(api, true, {}, vi.fn()));
    act(() => state.handlers?.onOpen?.());

    for (let i = 0; i < MAX_CONSECUTIVE_FAILURES - 1; i += 1) {
      act(() => state.handlers?.onError(new ApiError("network", "dropped", "u"), false));
    }
    act(() => state.handlers?.onOpen?.());
    expect(result.current.name).toBe("live");

    // A flaky link that recovers must not accumulate toward the limit.
    for (let i = 0; i < MAX_CONSECUTIVE_FAILURES - 1; i += 1) {
      act(() => state.handlers?.onError(new ApiError("network", "dropped", "u"), false));
    }
    expect(result.current.name).toBe("reconnecting");
  });

  it("reports a transport that cannot stream at all rather than waiting", () => {
    const api = { isDemo: false, stream: () => null } as unknown as TheLoopApi;
    const { result } = renderHook(() => useStream(api, true, {}, vi.fn()));
    expect(result.current.name).toBe("fallback");
  });

  it("closes the connection when it unmounts", () => {
    const { api, state } = stubTransport();
    const { unmount } = renderHook(() => useStream(api, true, {}, vi.fn()));
    unmount();
    expect(state.unsubscribes).toBe(1);
  });

  it("reconnects with the new watch when the viewed transcript changes", () => {
    const { api, state } = stubTransport();
    const { rerender } = renderHook(({ ref }: { ref: string }) => useStream(api, true, { transcript: [ref] }, vi.fn()), {
      initialProps: { ref: REF },
    });
    expect(state.queries.at(-1)?.transcript).toEqual([REF]);

    rerender({ ref: "github:octo/repo#8" });
    expect(state.unsubscribes).toBe(1);
    expect(state.queries.at(-1)?.transcript).toEqual(["github:octo/repo#8"]);
  });

  /**
   * The failure a real browser found and a stub never would.
   *
   * `EventSource` retries a *dropped* connection, but a response it will not
   * accept — a 404 from a service too old for the route, a CORS rejection — is
   * **terminal**: it closes the source and never tries again. Counting to five
   * therefore never gets there, and the page sits on "reconnecting (1)" with a
   * frozen board forever, which is the exact state R4.1 exists to prevent.
   */
  it("falls back at once when the browser gave up rather than retrying", () => {
    const { api, state } = stubTransport();
    const { result } = renderHook(() => useStream(api, true, {}, vi.fn()));

    act(() => state.handlers?.onError(new ApiError("network", "closed by the browser", "u"), true));

    expect(result.current.name).toBe("fallback");
    expect(state.unsubscribes).toBe(1);
  });

  it("still counts a merely dropped connection toward the limit", () => {
    const { api, state } = stubTransport();
    const { result } = renderHook(() => useStream(api, true, {}, vi.fn()));
    act(() => state.handlers?.onOpen?.());
    act(() => state.handlers?.onError(new ApiError("network", "dropped", "u"), false));
    expect(result.current.name).toBe("reconnecting");
  });
});
