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
const TOKEN_KEY = "the-loop:token";

const DEFAULT_API_BASE = "http://127.0.0.1:4114";

/** Origins the bearer token may ever be sent to: loopback, plus the build-time
 * VITE_API_BASE when the deployment pins one. A `?api=` override or a stored
 * value is honored ONLY if it resolves to one of these — otherwise it is
 * ignored and the default is used.
 *
 * Why: the token is the full control-plane credential (the service can spawn
 * harness sessions). Without this gate, a single crafted same-origin link like
 * `…/?api=https://evil.example` would persist an attacker origin and make every
 * request attach `Authorization: Bearer <token>` to it — a one-click token
 * exfiltration (issue-161 security review). An allowlist keeps the token from
 * ever leaving a trusted origin. */
function allowedOrigin(candidate: string): boolean {
  let url: URL;
  try {
    url = new URL(candidate);
  } catch {
    return false;
  }
  if (url.hostname === "127.0.0.1" || url.hostname === "localhost" || url.hostname === "[::1]") {
    return true;
  }
  const pinned = import.meta.env.VITE_API_BASE as string | undefined;
  if (pinned) {
    try {
      return new URL(pinned).origin === url.origin;
    } catch {
      return false;
    }
  }
  return false;
}

/** ?api= wins and is remembered, then localStorage, then the build-time
 * default, then loopback — but only an allowlisted origin (loopback or the
 * pinned VITE_API_BASE) is ever accepted, so the token cannot be sent to an
 * attacker-chosen host. One static bundle still serves any deployment (R6.1):
 * pin its own origin at build time via VITE_API_BASE. */
export function apiBase(): string {
  const fromQuery = new URLSearchParams(window.location.search).get("api");
  if (fromQuery && allowedOrigin(fromQuery)) {
    localStorage.setItem(API_BASE_KEY, fromQuery);
    return fromQuery;
  }
  const stored = localStorage.getItem(API_BASE_KEY);
  if (stored && allowedOrigin(stored)) {
    return stored;
  }
  const pinned = import.meta.env.VITE_API_BASE as string | undefined;
  return pinned ?? DEFAULT_API_BASE;
}

/** Persist an operator-entered API base, but only if it is an allowlisted
 * origin (loopback or the pinned VITE_API_BASE). Returns whether it was
 * accepted, so the UI can tell the operator when a value was refused rather
 * than silently ignoring it. */
export function setApiBase(candidate: string): boolean {
  if (!allowedOrigin(candidate)) {
    return false;
  }
  localStorage.setItem(API_BASE_KEY, candidate);
  return true;
}

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? "";
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
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
  const headers: Record<string, string> = {
    Authorization: `Bearer ${getToken()}`,
  };
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
