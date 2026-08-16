/**
 * The transport's two jobs: build the right URL for a contract that keeps refs
 * out of path segments, and turn the browser's opaque cross-origin failure into
 * the sentence that actually helps.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, HttpApi, normalizeBaseUrl } from "./client.ts";

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

/** A `fetch` double whose recorded calls stay typed, so assertions need no casts. */
function stubFetch(reply: () => Promise<Response>) {
  const mock = vi.fn((_input: string | URL | Request, _init?: RequestInit) => reply());
  vi.stubGlobal("fetch", mock);
  return {
    urlOf: (call = 0) => new URL(String(mock.mock.calls[call]![0])),
    initOf: (call = 0) => mock.mock.calls[call]![1] ?? {},
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("normalizeBaseUrl", () => {
  it("strips trailing slashes so paths do not double up", () => {
    expect(normalizeBaseUrl("http://127.0.0.1:8787/")).toBe("http://127.0.0.1:8787");
    expect(normalizeBaseUrl("  http://host:1/// ")).toBe("http://host:1");
  });
});

describe("HttpApi", () => {
  it("sends work-item refs as query parameters, never path segments", async () => {
    const calls = stubFetch(() => Promise.resolve(jsonResponse([])));

    await new HttpApi("http://127.0.0.1:8787").events({ workItem: "github:octo/repo#15", limit: 20 });

    const url = calls.urlOf();
    expect(url.pathname).toBe("/api/v1/events");
    expect(url.searchParams.get("workItem")).toBe("github:octo/repo#15");
    expect(url.searchParams.get("limit")).toBe("20");
  });

  it("repeats a list parameter rather than joining it", async () => {
    const calls = stubFetch(() => Promise.resolve(jsonResponse([])));

    await new HttpApi("http://h:1").events({ type: ["graph.parked", "graph.blocked"] });

    expect(calls.urlOf().searchParams.getAll("type")).toEqual(["graph.parked", "graph.blocked"]);
  });

  it("posts graph/check with prRepo defaulted, since the body requires the key", async () => {
    const calls = stubFetch(() =>
      Promise.resolve(jsonResponse({ workItem: "issue-15", currentNode: "design", ok: true, nodes: [] })),
    );

    await new HttpApi("http://h:1").graphCheck({ repo: "/checkout", workItem: "issue-15", pr: 16 });

    expect(JSON.parse(String(calls.initOf().body))).toEqual({
      repo: "/checkout",
      workItem: "issue-15",
      pr: 16,
      prRepo: "",
      recompute: false,
    });
  });

  it("reports an unreachable service as `network`, advising the base URL, CORS and the tunnel", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));

    const error = await new HttpApi("http://h:1").health().catch((cause: unknown) => cause);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).kind).toBe("network");
    expect((error as ApiError).advice).toMatch(/service\.cors\.allowOrigins/);
    expect((error as ApiError).advice).toMatch(/Settings/);
  });

  it("surfaces FastAPI's `detail` on a 4xx rather than the bare status line", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse({ detail: "repo path is not a directory" }, { status: 400 }))));

    const error = (await new HttpApi("http://h:1")
      .graphCheck({ repo: "/nope", workItem: "issue-1" })
      .catch((cause: unknown) => cause)) as ApiError;

    expect(error.kind).toBe("http");
    expect(error.status).toBe(400);
    expect(error.message).toBe("repo path is not a directory");
  });

  it("falls back to the status line when the error body is not JSON", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("<html>502</html>", { status: 502, statusText: "Bad Gateway" }))));

    const error = (await new HttpApi("http://h:1").health().catch((cause: unknown) => cause)) as ApiError;

    expect(error.message).toBe("502 Bad Gateway");
    expect(error.advice).toMatch(/service errored/);
  });
});

/**
 * Frame decoding (issue-239).
 *
 * This exists because a real bug lived here for ten minutes: the transcript
 * handler read `work_item`, which is what an event-log record carries, while
 * the service sends `ref`. Typecheck and lint were both green — the field names
 * are strings on an untyped payload. Only a test that puts a real frame through
 * the decoder can catch that, so here is one per frame kind.
 */
describe("HttpApi.stream", () => {
  class FakeEventSource {
    static CLOSED = 2;
    static instances: FakeEventSource[] = [];
    readonly listeners = new Map<string, Set<(event: Event) => void>>();
    readyState = 1;
    closed = false;
    readonly url: string;

    // A plain assignment, not a parameter property: `erasableSyntaxOnly` is on,
    // and a parameter property is TypeScript that has to be *compiled*, not
    // erased.
    constructor(url: string) {
      this.url = url;
      FakeEventSource.instances.push(this);
    }
    addEventListener(type: string, handler: (event: Event) => void) {
      if (!this.listeners.has(type)) this.listeners.set(type, new Set());
      this.listeners.get(type)?.add(handler);
    }
    removeEventListener(type: string, handler: (event: Event) => void) {
      this.listeners.get(type)?.delete(handler);
    }
    close() {
      this.closed = true;
    }
    /** Deliver one frame the way the browser delivers an SSE block. */
    deliver(type: string, data: string, lastEventId = "") {
      const event = new MessageEvent(type, { data, lastEventId });
      for (const handler of this.listeners.get(type) ?? []) handler(event);
    }
  }

  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
  });
  afterEach(() => vi.unstubAllGlobals());

  function open(query: Parameters<HttpApi["stream"]>[0] = {}) {
    const frames: unknown[] = [];
    const close = new HttpApi("http://h:1").stream(query, { onFrame: (f) => frames.push(f), onError: () => {} });
    return { frames, close, source: FakeEventSource.instances.at(-1)! };
  }

  it("puts the filters on the query string", () => {
    const { source } = open({ workItem: ["github:o/r#1"], transcript: ["github:o/r#2"] });
    expect(source.url).toContain("workItem=github%3Ao%2Fr%231");
    expect(source.url).toContain("transcript=github%3Ao%2Fr%232");
  });

  it("decodes a log frame, carrying the SSE id through as the cursor", () => {
    const { frames, source } = open();
    source.deliver("log", JSON.stringify({ ts: "2026-08-16T00:00:00Z", event: "graph.advanced" }), "148213");
    expect(frames).toEqual([
      { kind: "log", record: { ts: "2026-08-16T00:00:00Z", event: "graph.advanced" }, cursor: "148213" },
    ]);
  });

  it("decodes a transcript frame from `ref`, which is not `work_item`", () => {
    const { frames, source } = open();
    source.deliver("transcript", JSON.stringify({ ref: "github:o/r#1", totalLines: 412 }));
    expect(frames).toEqual([{ kind: "transcript", ref: "github:o/r#1", totalLines: 412 }]);
  });

  it("decodes a desync frame with its reason", () => {
    const { frames, source } = open();
    source.deliver("desync", JSON.stringify({ reason: "replay-window" }));
    expect(frames).toEqual([{ kind: "desync", reason: "replay-window" }]);
  });

  it("drops a frame that is not a record rather than passing a half one on", () => {
    const { frames, source } = open();
    source.deliver("log", "{not json");
    source.deliver("log", JSON.stringify({ event: "graph.advanced" })); // no ts
    source.deliver("transcript", JSON.stringify({ totalLines: 1 })); // no ref
    expect(frames).toEqual([]);
  });

  it("closes the connection when unsubscribed", () => {
    const { close, source } = open();
    close?.();
    expect(source.closed).toBe(true);
  });
});
