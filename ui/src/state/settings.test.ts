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
    saveSettings({ baseUrl: "https://tunnel.example", mode: "demo", pollSeconds: 30 }, store);
    expect(loadSettings(store)).toEqual({ baseUrl: "https://tunnel.example", mode: "demo", pollSeconds: 30 });
  });

  it("normalizes a stored URL's trailing slash", () => {
    expect(loadSettings(storage(JSON.stringify({ baseUrl: "http://h:1/" }))).baseUrl).toBe("http://h:1");
  });

  it("keeps the good fields when a neighbour is nonsense", () => {
    const stored = JSON.stringify({ baseUrl: "http://h:1", mode: "sideways", pollSeconds: "soon" });
    expect(loadSettings(storage(stored))).toEqual({
      baseUrl: "http://h:1",
      mode: "live",
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
