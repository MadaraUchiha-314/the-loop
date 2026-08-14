/**
 * The form is derived, not written, so these tests pin the derivation: which schema node
 * becomes which control, and which draft becomes which patch (issue-222).
 */

import { describe, expect, it } from "vitest";

import { allFields, deleteIn, diff, getIn, kindOf, sectionsOf, setIn } from "./configModel.ts";
import type { JsonSchema } from "./types.ts";

const SCHEMA: JsonSchema = {
  type: "object",
  properties: {
    version: { type: "string", description: "Schema version of this file." },
    routing: {
      type: "object",
      description: "What happens to an event once accepted.",
      properties: {
        enabled: { type: "boolean", default: false, description: "Route events to sessions." },
        defaultHarness: { type: "string", enum: ["claude", "cursor"], default: "claude" },
        authorizedUsers: { type: "array", items: { type: "string" } },
        maxConcurrentDispatches: { type: "integer", minimum: 1, maximum: 32, default: 4 },
        tmux: {
          type: "object",
          description: "Session hosting.",
          properties: { keepSessionOnClose: { type: "boolean", default: true } },
        },
      },
    },
    collaborators: {
      type: "array",
      description: "The operator's own notification recipients.",
      items: { type: "object", properties: { handle: { type: "string" } } },
    },
  },
};

describe("sectionsOf", () => {
  it("makes one section per top-level property, in the schema's order", () => {
    expect(sectionsOf(SCHEMA).map((section) => section.path.join("."))).toEqual([
      "version",
      "routing",
      "collaborators",
    ]);
  });

  it("carries the schema's own prose into the section", () => {
    const [, routing] = sectionsOf(SCHEMA);
    expect(routing?.description).toBe("What happens to an event once accepted.");
  });

  it("nests a nested object as a nested group, keeping the key path", () => {
    const [, routing] = sectionsOf(SCHEMA);
    expect(routing?.groups.map((group) => group.path)).toEqual([["routing", "tmux"]]);
    expect(routing?.groups[0]?.fields[0]?.path).toEqual(["routing", "tmux", "keepSessionOnClose"]);
  });

  it("reaches every leaf, including the ones with no typed control", () => {
    const paths = allFields(sectionsOf(SCHEMA)).map((field) => field.path.join("."));
    expect(paths).toContain("routing.maxConcurrentDispatches");
    expect(paths).toContain("collaborators");
  });

  it("keeps the schema's default as a default, and its range as a range", () => {
    const field = allFields(sectionsOf(SCHEMA)).find((entry) => entry.path.join(".") === "routing.maxConcurrentDispatches");
    expect(field).toMatchObject({ kind: "integer", default: 4, minimum: 1, maximum: 32 });
  });
});

describe("kindOf", () => {
  it.each([
    [{ type: "string" }, "string"],
    [{ type: "boolean" }, "boolean"],
    [{ type: "integer" }, "integer"],
    [{ type: "number" }, "number"],
    [{ type: "string", enum: ["a", "b"] }, "enum"],
    [{ type: "array", items: { type: "string" } }, "stringList"],
    [{ type: "array", items: { type: "object" } }, "structured"],
    [{ type: "object" }, "structured"],
    [{}, "structured"],
  ])("reads %o as %s", (schema, expected) => {
    expect(kindOf(schema as JsonSchema)).toBe(expected);
  });
});

describe("getIn / setIn / deleteIn", () => {
  const source = { routing: { enabled: false, tmux: { keep: true } } };

  it("reads and writes by key path without mutating the original", () => {
    expect(getIn(source, ["routing", "tmux", "keep"])).toBe(true);
    const next = setIn(source, ["routing", "tmux", "keep"], false);
    expect(getIn(next, ["routing", "tmux", "keep"])).toBe(false);
    expect(source.routing.tmux.keep).toBe(true);
  });

  it("creates the missing branch on the way down", () => {
    expect(getIn(setIn({}, ["a", "b", "c"], 1), ["a", "b", "c"])).toBe(1);
  });

  it("reads a missing path as undefined rather than throwing", () => {
    expect(getIn(source, ["nope", "deeper"])).toBeUndefined();
  });

  it("removes a key", () => {
    expect(getIn(deleteIn(source, ["routing", "enabled"]), ["routing", "enabled"])).toBeUndefined();
  });
});

describe("diff", () => {
  const original = { routing: { enabled: false, authorizedUsers: ["octocat"] }, polling: { intervalSeconds: 60 } };

  it("sends nothing when nothing changed", () => {
    expect(diff(original, structuredClone(original))).toEqual({});
  });

  it("sends only the keys that changed, nested where the config nests them", () => {
    const draft = setIn(structuredClone(original), ["routing", "enabled"], true);
    expect(diff(original, draft)).toEqual({ routing: { enabled: true } });
  });

  it("treats a re-typed identical value as no change", () => {
    const draft = setIn(structuredClone(original), ["routing", "authorizedUsers"], ["octocat"]);
    expect(diff(original, draft)).toEqual({});
  });

  it("asks for a removal with an explicit null", () => {
    expect(diff(original, deleteIn(structuredClone(original), ["polling", "intervalSeconds"]))).toEqual({
      polling: { intervalSeconds: null },
    });
  });

  it("sends a whole new subtree when the draft grew one", () => {
    const draft = setIn(structuredClone(original), ["service", "port"], 4114);
    expect(diff(original, draft)).toEqual({ service: { port: 4114 } });
  });
});
