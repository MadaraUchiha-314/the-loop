/**
 * What this browser remembers.
 *
 * The whole point of shipping the dashboard as a static bundle is that one
 * hosted copy can point at any workstation running `the-loop service start`, so
 * the target has to live with the viewer rather than with the build. localStorage
 * is the right store for that: per-origin, per-browser, and survives a reload
 * without a backend.
 */

import { DEFAULT_BASE_URL, normalizeBaseUrl } from "../api/client.ts";

const STORAGE_KEY = "the-loop:settings:v1";

export type DataMode = "live" | "demo";

/**
 * How this browser keeps the screen current (issue-239).
 *
 * `stream` holds one `GET /api/v1/stream` open and refreshes what each frame
 * touches; `poll` is the pre-issue-239 timer, unchanged; `manual` makes no
 * background request of any kind. The viewer picks, because the right answer
 * depends on how they reach the workstation: over a flaky tunnel a failed poll
 * costs one request, while a failed stream is a screen that stops updating.
 */
export type RefreshMode = "stream" | "poll" | "manual";

const REFRESH_MODES: readonly RefreshMode[] = ["stream", "poll", "manual"];

export interface Settings {
  /** Where the service is, as the browser can reach it. */
  baseUrl: string;
  /** `live` talks to `baseUrl`; `demo` serves the bundled fixture. */
  mode: DataMode;
  /** How the screen refreshes. */
  refreshMode: RefreshMode;
  /** The interval used while `refreshMode` is `poll`. */
  pollSeconds: number;
}

export const DEFAULT_SETTINGS: Settings = {
  baseUrl: DEFAULT_BASE_URL,
  mode: "live",
  // Streaming for a NEW browser: the shipped base URL is loopback, where it
  // always works, and a wrong guess costs one failed connect plus a stated
  // reason rather than a dead board. An EXISTING browser keeps what it had —
  // see the migration in `loadSettings`.
  refreshMode: "stream",
  pollSeconds: 15,
};

export const POLL_CHOICES = [5, 15, 30, 60] as const;

/**
 * Read the stored settings, falling back field by field.
 *
 * Hand-edited or half-written storage must not blank the app, so every field is
 * validated on the way in and a bad one degrades to its default rather than
 * taking the object with it.
 */
export function loadSettings(storage: Storage | undefined = safeStorage()): Settings {
  if (!storage) return { ...DEFAULT_SETTINGS };
  let raw: string | null = null;
  try {
    raw = storage.getItem(STORAGE_KEY);
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
  if (!raw) return { ...DEFAULT_SETTINGS };

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
  if (!parsed || typeof parsed !== "object") return { ...DEFAULT_SETTINGS };

  const candidate = parsed as Partial<Record<keyof Settings, unknown>>;
  const baseUrl = typeof candidate.baseUrl === "string" ? normalizeBaseUrl(candidate.baseUrl) : "";
  const mode = candidate.mode === "demo" ? "demo" : "live";
  const storedSeconds =
    typeof candidate.pollSeconds === "number" && Number.isFinite(candidate.pollSeconds) && candidate.pollSeconds >= 0
      ? Math.min(candidate.pollSeconds, 3600)
      : null;

  return {
    baseUrl: baseUrl || DEFAULT_SETTINGS.baseUrl,
    mode,
    refreshMode: readRefreshMode(candidate.refreshMode, storedSeconds),
    // 0 is not an interval — it was how "off" used to be spelled, and it is now
    // `refreshMode: "manual"`. Keeping it here would give the poll timer a zero
    // to divide the world by.
    pollSeconds: storedSeconds && storedSeconds > 0 ? storedSeconds : DEFAULT_SETTINGS.pollSeconds,
  };
}

/**
 * The stored mode, or what the pre-issue-239 store implies.
 *
 * The storage key stays `:v1` rather than becoming `:v2`, so nobody loses their
 * base URL to this change. That makes the absence of `refreshMode` the migration
 * signal, and `pollSeconds` the only evidence of what the viewer wanted:
 * `0` meant "off", which is now `manual`; anything else meant polling at that
 * interval. Deliberately NOT defaulted to `stream` — a new browser gets
 * streaming, but switching an existing viewer onto a transport their tunnel may
 * not carry is a different decision, and not one a migration should make for
 * them.
 */
function readRefreshMode(stored: unknown, storedSeconds: number | null): RefreshMode {
  const known = REFRESH_MODES.find((mode) => mode === stored);
  if (known) return known;
  if (storedSeconds === null) return DEFAULT_SETTINGS.refreshMode;
  return storedSeconds === 0 ? "manual" : "poll";
}

export function saveSettings(settings: Settings, storage: Storage | undefined = safeStorage()): void {
  if (!storage) return;
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch {
    // A full or blocked store (private mode, storage disabled) is not worth
    // failing a save over — the session keeps the value in memory either way.
  }
}

/** `localStorage` throws on access in some privacy modes; treat that as absent. */
function safeStorage(): Storage | undefined {
  try {
    return globalThis.localStorage;
  } catch {
    return undefined;
  }
}
