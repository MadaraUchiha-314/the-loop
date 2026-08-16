/** Stored settings must degrade field by field: a hand-edited store cannot blank the app. */

import { describe, expect, it } from "vitest";

import { DEFAULT_SETTINGS, loadSettings, saveSettings } from "./settings.ts";

function storage(initial?: string): Storage {
  const map = new Map<string, string>();
  if (initial !== undefined) map.set("the-loop:settings:v1", initial);
  return {
    get length() {
      return map.size;
    },
    clear: () => map.clear(),
    getItem: (key: string) => map.get(key) ?? null,
    key: (index: number) => [...map.keys()][index] ?? null,
    removeItem: (key: string) => void map.delete(key),
    setItem: (key: string, value: string) => void map.set(key, value),
  };
}

describe("loadSettings", () => {
  it("returns the defaults for an empty store", () => {
    expect(loadSettings(storage())).toEqual(DEFAULT_SETTINGS);
  });

  it("round-trips what was saved", () => {
    const store = storage();
    const saved = { baseUrl: "https://tunnel.example", mode: "demo", refreshMode: "poll", pollSeconds: 30 } as const;
    saveSettings(saved, store);
    expect(loadSettings(store)).toEqual(saved);
  });

  it("normalizes a stored URL's trailing slash", () => {
    expect(loadSettings(storage(JSON.stringify({ baseUrl: "http://h:1/" }))).baseUrl).toBe("http://h:1");
  });

  it("keeps the good fields when a neighbour is nonsense", () => {
    const stored = JSON.stringify({ baseUrl: "http://h:1", mode: "sideways", pollSeconds: "soon" });
    expect(loadSettings(storage(stored))).toEqual({
      baseUrl: "http://h:1",
      mode: "live",
      // `pollSeconds` was unreadable, so there is no pre-issue-239 intent to
      // migrate and the fresh-browser default applies.
      refreshMode: DEFAULT_SETTINGS.refreshMode,
      pollSeconds: DEFAULT_SETTINGS.pollSeconds,
    });
  });

  it("survives a store holding something that is not JSON at all", () => {
    expect(loadSettings(storage("{not json"))).toEqual(DEFAULT_SETTINGS);
  });

  it("treats an absent store (privacy mode) as defaults, not a crash", () => {
    expect(loadSettings(undefined)).toEqual(DEFAULT_SETTINGS);
    expect(() => saveSettings(DEFAULT_SETTINGS, undefined)).not.toThrow();
  });

  it("clamps an absurd poll interval instead of scheduling it", () => {
    expect(loadSettings(storage(JSON.stringify({ pollSeconds: 999_999 }))).pollSeconds).toBe(3600);
    expect(loadSettings(storage(JSON.stringify({ pollSeconds: -5 }))).pollSeconds).toBe(DEFAULT_SETTINGS.pollSeconds);
  });
});

describe("refreshMode (issue-239)", () => {
  it("defaults a fresh browser to streaming", () => {
    expect(loadSettings(storage()).refreshMode).toBe("stream");
  });

  it("round-trips each mode", () => {
    for (const mode of ["stream", "poll", "manual"] as const) {
      const store = storage();
      saveSettings({ ...DEFAULT_SETTINGS, refreshMode: mode }, store);
      expect(loadSettings(store).refreshMode).toBe(mode);
    }
  });

  it("falls back to streaming for a mode nobody ships", () => {
    const stored = JSON.stringify({ baseUrl: "http://h:1", refreshMode: "telepathy" });
    expect(loadSettings(storage(stored)).refreshMode).toBe("stream");
  });

  /**
   * The migration is the one thing here that can silently break an existing
   * viewer: settings written before this field existed hold only `pollSeconds`,
   * and the key is deliberately still `:v1` so nobody loses their base URL.
   */
  describe("settings written before refreshMode existed", () => {
    it("reads pollSeconds: 0 as manual, keeping the base URL", () => {
      const stored = JSON.stringify({ baseUrl: "https://tunnel.example", mode: "live", pollSeconds: 0 });
      const loaded = loadSettings(storage(stored));
      expect(loaded.refreshMode).toBe("manual");
      expect(loaded.baseUrl).toBe("https://tunnel.example");
    });

    it("reads any other interval as polling at that interval", () => {
      const stored = JSON.stringify({ baseUrl: "http://h:1", mode: "live", pollSeconds: 30 });
      const loaded = loadSettings(storage(stored));
      expect(loaded.refreshMode).toBe("poll");
      expect(loaded.pollSeconds).toBe(30);
    });

    it("does not switch a viewer to a transport their tunnel may not carry", () => {
      // The default for a NEW browser is streaming; the default for an EXISTING
      // one is whatever they already chose. Those are different questions.
      const stored = JSON.stringify({ baseUrl: "http://h:1", pollSeconds: 15 });
      expect(loadSettings(storage(stored)).refreshMode).not.toBe("stream");
    });
  });
});
