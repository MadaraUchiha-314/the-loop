// The control-plane API client (issue-161 R6). Shapes mirror
// specs/openapi/the-loop.v1.yaml — the authored contract.

export interface WorkItemRecord {
  ref: string;
  url?: string;
  control?: { command?: string; actor?: string; at?: string };
  poll?: Record<string, unknown>;
}

export interface SessionInfo {
  workItem: string;
  harness: string;
  harnessSessionId: string;
  tmuxTarget: string;
  status: string;
  lastEventAt: string;
  control: string;
}

export interface NodeReport {
  node: string;
  status: string;
  messages: string[];
}

export interface CheckReport {
  workItem: string;
  ok: boolean;
  currentNode: string;
  nodes: NodeReport[];
}

export interface AttentionItem {
  workItem: string;
  kind: string;
  detail: string;
}

export interface DaemonStatus {
  daemon: string;
  running: boolean;
  pid: number;
  pidfile: string;
}

export interface EventRecord {
  ts?: string;
  source?: string;
  level?: string;
  event?: string;
  work_item?: string;
  [key: string]: unknown;
}

const API_BASE_KEY = "the-loop:apiBase";

const DEFAULT_API_BASE = "http://127.0.0.1:4114";

/** ?api= wins and is remembered, then localStorage, then the build-time
 * VITE_API_BASE, then loopback. The service carries no credential (auth is the
 * gateway's job — owner decision, PR #162), so there is nothing to leak to a
 * chosen origin; one static bundle serves any deployment by pinning its own
 * API origin at build time via VITE_API_BASE (R6.1). */
export function apiBase(): string {
  const fromQuery = new URLSearchParams(window.location.search).get("api");
  if (fromQuery) {
    localStorage.setItem(API_BASE_KEY, fromQuery);
    return fromQuery;
  }
  const pinned = import.meta.env.VITE_API_BASE as string | undefined;
  return localStorage.getItem(API_BASE_KEY) ?? pinned ?? DEFAULT_API_BASE;
}

export function setApiBase(candidate: string): void {
  localStorage.setItem(API_BASE_KEY, candidate);
}

export class ApiError extends Error {
  constructor(
    public status: number,
    detail: string,
  ) {
    super(detail);
  }
}

async function request<T>(
  method: "GET" | "POST",
  path: string,
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(`${apiBase()}/api/v1${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const parsed = (await response.json()) as { detail?: string };
      if (parsed.detail) detail = parsed.detail;
    } catch {
      /* keep the status text */
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<{ status: string; version: string }>("GET", "/health"),
  workItems: () => request<WorkItemRecord[]>("GET", "/work-items"),
  sessions: () => request<SessionInfo[]>("GET", "/sessions"),
  attention: () => request<AttentionItem[]>("GET", "/attention"),
  daemons: () => request<DaemonStatus[]>("GET", "/daemons"),
  events: (limit = 20) =>
    request<EventRecord[]>("GET", `/events?limit=${limit}`),
  check: (repo: string, workItem: string) =>
    request<CheckReport>("POST", "/graph/check", {
      repo,
      workItem,
      recompute: true,
    }),
  controlSession: (ref: string, verb: string) =>
    request<{ verb: string; workItem: string; exitCode: number; output: string }>(
      "POST",
      "/sessions/control",
      { ref, verb },
    ),
};
