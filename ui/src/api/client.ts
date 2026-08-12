/**
 * The HTTP client for `the-loop service start`.
 *
 * One interface, two implementations: this file talks to a real service, and
 * `../demo/client.ts` answers the same calls from a fixture so the page hosted
 * on GitHub Pages is explorable before anyone has a tunnel open. Views depend
 * on {@link TheLoopApi}, never on either concrete class.
 *
 * Two deployment facts shape the error handling. The service allows a
 * **configured list of origins** to read it — this page's is the shipped default
 * (`service.cors.allowOrigins`, issue-211) — and binds **loopback only**
 * (decision-059). So the two remaining failures are a service on another machine
 * (nothing is listening at this base URL) and an origin the operator has not
 * allowed; `fetch` reports both as an opaque `TypeError` with no status.
 * {@link ApiError} carries `kind: "network"` for that case and the views turn it
 * into the config/tunnel instructions rather than a bare "failed to fetch".
 */

import type {
  AttentionItem,
  CoreResult,
  DaemonStatus,
  DaemonVerb,
  EventRecord,
  GraphDefinition,
  GraphStatus,
  Health,
  SessionRecord,
  SessionVerb,
  WorkItemRecord,
} from "./types.ts";

export type ApiErrorKind = "network" | "http" | "malformed";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number;
  readonly url: string;

  constructor(kind: ApiErrorKind, message: string, url: string, status = 0) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.url = url;
  }

  /**
   * The sentence to put in front of an operator. A `network` failure is almost
   * never "the server errored" — nothing answered, or the browser refused to
   * let this page read what did — so it says what to change instead of what
   * broke, cheapest remedy first.
   */
  get advice(): string {
    if (this.kind === "network") {
      return (
        "Could not reach the service. Check the base URL in Settings, and that " +
        "`the-loop service start` is running. If this page's origin is not in " +
        "service.cors.allowOrigins, the browser blocks the read (CORS) — add it " +
        "there. The service binds loopback only, so one on another machine needs " +
        "an SSH tunnel or a gateway in front."
      );
    }
    if (this.status === 404) return "The service has no such route — check it is a recent the-loop.";
    if (this.status >= 500) return "The service errored. Check its log for the failing call.";
    return this.message;
  }
}

export interface GraphQuery {
  /** A filesystem path **on the machine running the service** — a checkout. */
  repo: string;
  /** The spec-folder id, e.g. `issue-214`. */
  workItem: string;
  /** A pull-request number selects that PR's inner `pdlc-pr-loop`. */
  pr?: number;
  /** Qualifies `pr` by repository when the item spans several. */
  prRepo?: string;
}

export interface EventQuery {
  type?: string[];
  workItem?: string;
  source?: string;
  level?: string;
  since?: string;
  limit?: number;
}

/** Everything the control plane reads or does, independent of transport. */
export interface TheLoopApi {
  readonly baseUrl: string;
  readonly isDemo: boolean;
  health(signal?: AbortSignal): Promise<Health>;
  workItems(signal?: AbortSignal): Promise<WorkItemRecord[]>;
  sessions(signal?: AbortSignal): Promise<SessionRecord[]>;
  attention(signal?: AbortSignal): Promise<AttentionItem[]>;
  events(query?: EventQuery, signal?: AbortSignal): Promise<EventRecord[]>;
  daemons(signal?: AbortSignal): Promise<DaemonStatus[]>;
  graphDefinition(repo: string, pr?: number, signal?: AbortSignal): Promise<GraphDefinition>;
  graphCheck(query: GraphQuery, signal?: AbortSignal): Promise<GraphStatus>;
  graphComplete(query: GraphQuery & { node?: string; actor?: string }): Promise<CoreResult>;
  controlSession(ref: string, verb: SessionVerb, comment?: boolean): Promise<CoreResult>;
  controlDaemon(daemon: string, verb: DaemonVerb): Promise<CoreResult>;
}

/** Trailing slashes make `${base}/api/v1/x` produce `//api`, so strip them. */
export function normalizeBaseUrl(raw: string): string {
  return raw.trim().replace(/\/+$/, "");
}

export const DEFAULT_BASE_URL = "http://127.0.0.1:8787";

/** How long a single call may take before it is treated as unreachable. */
const REQUEST_TIMEOUT_MS = 10_000;

export class HttpApi implements TheLoopApi {
  readonly baseUrl: string;
  readonly isDemo = false;

  constructor(baseUrl: string) {
    this.baseUrl = normalizeBaseUrl(baseUrl) || DEFAULT_BASE_URL;
  }

  private url(path: string, params?: Record<string, string | number | boolean | string[] | undefined>): string {
    const url = new URL(`${this.baseUrl}/api/v1${path}`);
    for (const [key, value] of Object.entries(params ?? {})) {
      if (value === undefined || value === "") continue;
      if (Array.isArray(value)) {
        for (const entry of value) url.searchParams.append(key, entry);
      } else {
        url.searchParams.set(key, String(value));
      }
    }
    return url.toString();
  }

  private async request<T>(
    path: string,
    init: RequestInit & { params?: Record<string, string | number | boolean | string[] | undefined> } = {},
    signal?: AbortSignal,
  ): Promise<T> {
    const { params, ...rest } = init;
    const url = this.url(path, params);

    // Two abort sources — the caller's (a view unmounting) and our own timeout.
    // AbortSignal.any keeps both live without the caller having to know.
    const timeout = AbortSignal.timeout(REQUEST_TIMEOUT_MS);
    const composed = signal ? AbortSignal.any([signal, timeout]) : timeout;

    const headers = new Headers(rest.headers);
    headers.set("Accept", "application/json");
    if (rest.body !== undefined && rest.body !== null) headers.set("Content-Type", "application/json");

    let response: Response;
    try {
      response = await fetch(url, { ...rest, signal: composed, headers });
    } catch (cause) {
      if (signal?.aborted) throw cause;
      const reason = cause instanceof Error ? cause.message : String(cause);
      throw new ApiError("network", reason, url);
    }

    if (!response.ok) {
      // FastAPI's error shape is `{"detail": …}`; anything else falls back to
      // the status line so an intermediary's HTML error page is still legible.
      let detail = `${response.status} ${response.statusText}`;
      try {
        const body: unknown = await response.json();
        if (body !== null && typeof body === "object" && "detail" in body && typeof body.detail === "string") {
          detail = body.detail;
        }
      } catch {
        /* not JSON — keep the status line */
      }
      throw new ApiError("http", detail, url, response.status);
    }

    let body: unknown;
    try {
      body = await response.json();
    } catch {
      throw new ApiError("malformed", "response was not JSON", url, response.status);
    }
    // The contract types most responses as bare objects, so this is the one
    // place the untyped JSON becomes a typed record. `types.ts` makes every
    // field a client did not put there optional, so a shape that drifted
    // degrades to missing values rather than a crash.
    // oxlint-disable-next-line typescript/no-unsafe-type-assertion
    return body as T;
  }

  private post<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>(path, { method: "POST", body: JSON.stringify(body) });
  }

  health(signal?: AbortSignal): Promise<Health> {
    return this.request<Health>("/health", {}, signal);
  }

  workItems(signal?: AbortSignal): Promise<WorkItemRecord[]> {
    return this.request<WorkItemRecord[]>("/work-items", {}, signal);
  }

  sessions(signal?: AbortSignal): Promise<SessionRecord[]> {
    return this.request<SessionRecord[]>("/sessions", {}, signal);
  }

  attention(signal?: AbortSignal): Promise<AttentionItem[]> {
    return this.request<AttentionItem[]>("/attention", {}, signal);
  }

  events(query: EventQuery = {}, signal?: AbortSignal): Promise<EventRecord[]> {
    return this.request<EventRecord[]>(
      "/events",
      {
        params: {
          type: query.type,
          workItem: query.workItem,
          source: query.source,
          level: query.level,
          since: query.since,
          limit: query.limit ?? 100,
        },
      },
      signal,
    );
  }

  daemons(signal?: AbortSignal): Promise<DaemonStatus[]> {
    return this.request<DaemonStatus[]>("/daemons", {}, signal);
  }

  graphDefinition(repo: string, pr?: number, signal?: AbortSignal): Promise<GraphDefinition> {
    return this.request<GraphDefinition>("/graph", { params: { repo, pr } }, signal);
  }

  graphCheck(query: GraphQuery, signal?: AbortSignal): Promise<GraphStatus> {
    // A read, but a POST: `repo` is a filesystem path and `workItem` a ref, and
    // the contract keeps both out of path segments (they contain `/` and `#`).
    return this.request<GraphStatus>(
      "/graph/check",
      { method: "POST", body: JSON.stringify({ ...query, prRepo: query.prRepo ?? "", recompute: false }) },
      signal,
    );
  }

  graphComplete(query: GraphQuery & { node?: string; actor?: string }): Promise<CoreResult> {
    return this.post<CoreResult>("/graph/complete", {
      repo: query.repo,
      workItem: query.workItem,
      node: query.node ?? "",
      actor: query.actor ?? "",
      pr: query.pr,
      prRepo: query.prRepo ?? "",
    });
  }

  controlSession(ref: string, verb: SessionVerb, comment = true): Promise<CoreResult> {
    return this.post<CoreResult>("/sessions/control", { ref, verb, comment });
  }

  controlDaemon(daemon: string, verb: DaemonVerb): Promise<CoreResult> {
    return this.post<CoreResult>("/daemons/control", { daemon, verb });
  }
}
