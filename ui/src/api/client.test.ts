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

  /**
   * The `instance` parameter (issue-374, R2.6 / R5.1): sent only when named —
   * a query parameter on a GET, a body field on a POST — so a worker that
   * became a manager sees byte-identical requests from a browser that names
   * nothing, and a manager routes what a browser does name.
   */
  describe("the instance parameter", () => {
    it("is absent from a GET when not named, and a query parameter when it is", async () => {
      const calls = stubFetch(() => Promise.resolve(jsonResponse({})));
      const api = new HttpApi("http://h:1");

      await api.transcript("github:o/r#1", 50);
      await api.transcript("github:o/r#1", 50, undefined, "laptop-a");
      await api.config();
      await api.config(undefined, "ci-box");
      await api.health(undefined, "");
      await api.instance(undefined, "cloud-1");

      expect(calls.urlOf(0).searchParams.has("instance")).toBe(false);
      expect(calls.urlOf(0).searchParams.get("ref")).toBe("github:o/r#1");
      expect(calls.urlOf(1).searchParams.get("instance")).toBe("laptop-a");
      expect(calls.urlOf(2).searchParams.has("instance")).toBe(false);
      expect(calls.urlOf(3).pathname).toBe("/api/v1/config");
      expect(calls.urlOf(3).searchParams.get("instance")).toBe("ci-box");
      expect(calls.urlOf(4).searchParams.has("instance")).toBe(false);
      expect(calls.urlOf(5).pathname).toBe("/api/v1/instance");
      expect(calls.urlOf(5).searchParams.get("instance")).toBe("cloud-1");
    });

    it("is absent from a POST body when not named, and a body field when it is", async () => {
      const calls = stubFetch(() => Promise.resolve(jsonResponse({})));
      const api = new HttpApi("http://h:1");

      await api.controlSession("github:o/r#1", "pause");
      await api.controlSession("github:o/r#1", "pause", true, "laptop-a");
      await api.replySession("github:o/r#1", "yes", "", "laptop-a");
      await api.graphCheck({ repo: "/c", workItem: "issue-1" }, undefined, "laptop-a");
      await api.graphComplete({ repo: "/c", workItem: "issue-1", node: "design" }, "laptop-a");
      await api.controlDaemon("poller", "stop", "ci-box");
      await api.saveConfig({ routing: { enabled: false } }, "ci-box");
      await api.restart(false, "ci-box");
      await api.controlStandingSession("triage", "stop", "ci-box");
      await api.sayToStandingSession("triage", "hi", "", "ci-box");
      await api.deleteStandingSession("triage", "ci-box");
      await api.createStandingSession({ name: "n" }, "ci-box");
      await api.restart();

      const body = (call: number) => JSON.parse(String(calls.initOf(call).body)) as Record<string, unknown>;
      expect(body(0)).toEqual({ ref: "github:o/r#1", verb: "pause", comment: true });
      expect(body(1)).toEqual({ ref: "github:o/r#1", verb: "pause", comment: true, instance: "laptop-a" });
      expect(body(2)).toMatchObject({ ref: "github:o/r#1", text: "yes", instance: "laptop-a" });
      expect(body(3)).toMatchObject({ repo: "/c", workItem: "issue-1", recompute: false, instance: "laptop-a" });
      expect(body(4)).toMatchObject({ node: "design", instance: "laptop-a" });
      expect(body(5)).toEqual({ daemon: "poller", verb: "stop", instance: "ci-box" });
      expect(body(6)).toEqual({ patch: { routing: { enabled: false } }, instance: "ci-box" });
      expect(body(7)).toEqual({ withUpgrade: false, instance: "ci-box" });
      expect(body(8)).toEqual({ name: "triage", verb: "stop", instance: "ci-box" });
      expect(body(9)).toMatchObject({ name: "triage", text: "hi", instance: "ci-box" });
      expect(body(10)).toEqual({ name: "triage", instance: "ci-box" });
      expect(body(11)).toEqual({ name: "n", instance: "ci-box" });
      expect(body(12)).toEqual({ withUpgrade: false });
      expect("instance" in body(12)).toBe(false);
    });
  });

  describe("the instances family (issue-374, R3.1 / R4.2)", () => {
    it("reads the fleet from GET /instances", async () => {
      const calls = stubFetch(() => Promise.resolve(jsonResponse({ role: "worker", name: "a", instances: [] })));
      const document = await new HttpApi("http://h:1").instances();
      expect(calls.urlOf().pathname).toBe("/api/v1/instances");
      expect(calls.initOf().method).toBeUndefined();
      expect(document.role).toBe("worker");
    });

    it("registers and unregisters through the two POST routes with the documented bodies", async () => {
      const calls = stubFetch(() => Promise.resolve(jsonResponse({ role: "manager", name: "hq", instances: [] })));
      const api = new HttpApi("http://h:1");
      await api.registerInstance("cloud-2", "http://10.0.0.10:4114");
      await api.unregisterInstance("cloud-2");
      expect(calls.urlOf(0).pathname).toBe("/api/v1/instances/register");
      expect(JSON.parse(String(calls.initOf(0).body))).toEqual({ name: "cloud-2", url: "http://10.0.0.10:4114" });
      expect(calls.urlOf(1).pathname).toBe("/api/v1/instances/unregister");
      expect(JSON.parse(String(calls.initOf(1).body))).toEqual({ name: "cloud-2" });
    });

    it("surfaces a worker's 400 naming instance.role verbatim", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn(() => Promise.resolve(jsonResponse({ detail: "instance.role is worker: nothing can be registered here" }, { status: 400 }))),
      );
      const error = (await new HttpApi("http://h:1").registerInstance("x", "http://x").catch((cause: unknown) => cause)) as ApiError;
      expect(error.status).toBe(400);
      expect(error.message).toMatch(/instance\.role/);
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
