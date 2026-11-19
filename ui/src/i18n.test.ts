/**
 * The UI's half of the catalog checks (issue-540, R3.2): `t()` behaves like the
 * CLI's lookup, every key the UI's source passes to `t()` exists, and every
 * `ui.*` entry is used by the UI — the Python catalog test skips the `ui.`
 * prefix because this test owns it.
 */

import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { catalogKeys, format, t } from "./i18n.ts";

const SRC = dirname(fileURLToPath(import.meta.url));

/** Every non-test source file under `ui/src`. */
function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return entry.name === "test" ? [] : sourceFiles(path);
    return /\.tsx?$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name) ? [path] : [];
  });
}

/** The literal keys passed to `t(` across the UI's source. */
function usedKeys(): Set<string> {
  const keys = new Set<string>();
  for (const file of sourceFiles(SRC)) {
    for (const match of readFileSync(file, "utf8").matchAll(/\bt\(\s*"([^"]+)"/g)) keys.add(match[1] ?? "");
  }
  return keys;
}

describe("t()", () => {
  it("fills named fields in one pass, leaving a substituted value literal", () => {
    expect(t("ui.app.service.worker", { host: "{host}" })).toBe("service · {host}");
  });

  it("reads {{ and }} as literal braces and never re-expands a value", () => {
    expect(format("{{x}} {name} {{{name}}}", { name: "{x}" })).toBe("{x} {x} {{x}}");
    expect(t("ui.instances.register.problem.name")).toBe("Name must fit ^[a-z0-9][a-z0-9-]{0,39}$.");
  });

  it("throws, naming the key, when the key is absent", () => {
    expect(() => t("ui.no-such.key")).toThrow(/ui\.no-such\.key/);
  });

  it("throws when a field the text uses has no value", () => {
    expect(() => t("ui.app.service.worker")).toThrow(/host/);
  });
});

describe("the catalog's ui.* entries", () => {
  const used = usedKeys();
  const catalog = new Set(catalogKeys());

  it("finds keys in the source (the scan works)", () => {
    expect(used.size).toBeGreaterThan(50);
  });

  it("holds every key the UI's source passes to t()", () => {
    expect([...used].filter((key) => !catalog.has(key))).toEqual([]);
  });

  it("only holds ui.* keys the UI reads", () => {
    expect([...used].filter((key) => !key.startsWith("ui."))).toEqual([]);
    expect([...catalog].filter((key) => key.startsWith("ui.") && !used.has(key))).toEqual([]);
  });
});
