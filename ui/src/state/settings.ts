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

export interface Settings {
  /** Where the service is, as the browser can reach it. */
  baseUrl: string;
  /** `live` talks to `baseUrl`; `demo` serves the bundled fixture. */
  mode: DataMode;
  /** Background refresh cadence. 0 disables polling. */
  pollSeconds: number;
}

export const DEFAULT_SETTINGS: Settings = {
  baseUrl: DEFAULT_BASE_URL,
  mode: "live",
  pollSeconds: 15,
};

export const POLL_CHOICES = [0, 5, 15, 30, 60] as const;

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
  const pollSeconds =
    typeof candidate.pollSeconds === "number" && Number.isFinite(candidate.pollSeconds) && candidate.pollSeconds >= 0
      ? Math.min(candidate.pollSeconds, 3600)
      : DEFAULT_SETTINGS.pollSeconds;

  return { baseUrl: baseUrl || DEFAULT_SETTINGS.baseUrl, mode, pollSeconds };
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
