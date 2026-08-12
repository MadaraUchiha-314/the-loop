/**
 * The transport's two jobs: build the right URL for a contract that keeps refs
 * out of path segments, and turn the browser's opaque cross-origin failure into
 * the sentence that actually helps.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

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
