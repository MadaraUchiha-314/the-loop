/**
 * The hash router (issue-374, R5.2): the fleet's routes parse, and every hash
 * that parsed before parses to the same route — a bookmark from a worker must
 * not change meaning because the service became a manager.
 */

import { describe, expect, it } from "vitest";

import { hrefFor, itemHref, parseHash } from "./route.ts";

const REF = "github:octo/loop-lab#214";

describe("parseHash · every legacy hash keeps its meaning", () => {
  it.each([
    ["", { name: "work" }],
    ["#", { name: "work" }],
    ["#/", { name: "work" }],
    ["#/dashboard", { name: "work" }],
    ["#/attention", { name: "work" }],
    ["#/sessions", { name: "work" }],
    ["#/standing", { name: "standing" }],
    ["#/events", { name: "events" }],
    ["#/settings", { name: "settings" }],
    [`#/events/${encodeURIComponent(REF)}`, { name: "events", ref: REF }],
    [`#/sessions/${encodeURIComponent(REF)}`, { name: "work", ref: REF }],
    [`#/item/${encodeURIComponent(REF)}`, { name: "work", ref: REF }],
    // A ref that was never fully encoded — the App test's deep link — still parses whole.
    ["#/item/github:octo/nope%23999", { name: "work", ref: "github:octo/nope#999" }],
    ["#/item/", { name: "work" }],
    ["#/nonsense", { name: "work" }],
  ])("%s", (hash, route) => {
    expect(parseHash(hash)).toEqual(route);
  });
});

describe("parseHash · the fleet's routes", () => {
  it("reads `#/item/<ref>@<instance>` as that instance's row of the work item", () => {
    expect(parseHash(`#/item/${encodeURIComponent(REF)}@laptop-a`)).toEqual({ name: "work", ref: REF, instance: "laptop-a" });
  });

  it("takes the `@` suffix only when it fits the instance-name grammar", () => {
    // Not a name: kept as part of the ref rather than guessed at.
    expect(parseHash("#/item/github:octo/lab%2315@Not_A_Name")).toEqual({ name: "work", ref: "github:octo/lab#15@Not_A_Name" });
    // An encoded `@` is part of the ref, never the separator.
    expect(parseHash(`#/item/${encodeURIComponent("github:octo/lab@x#15")}`)).toEqual({ name: "work", ref: "github:octo/lab@x#15" });
  });

  it("reads `#/?instance=<name>` as the board with the filter preset", () => {
    expect(parseHash("#/?instance=laptop-a")).toEqual({ name: "work", filter: "laptop-a" });
    expect(parseHash("#/?instance=")).toEqual({ name: "work" });
  });

  it("reads `#/instances` and `#/instances/<name>`", () => {
    expect(parseHash("#/instances")).toEqual({ name: "instances" });
    expect(parseHash("#/instances/cloud-1")).toEqual({ name: "instance", instance: "cloud-1" });
    expect(parseHash("#/instances/")).toEqual({ name: "instances" });
  });
});

describe("hrefFor", () => {
  it("emits the `@<instance>` suffix only when the route names one", () => {
    expect(hrefFor({ name: "work", ref: REF })).toBe(`#/item/${encodeURIComponent(REF)}`);
    expect(hrefFor({ name: "work", ref: REF, instance: "laptop-a" })).toBe(`#/item/${encodeURIComponent(REF)}@laptop-a`);
    expect(itemHref(REF)).toBe(hrefFor({ name: "work", ref: REF }));
    expect(itemHref(REF, "ci-box")).toBe(`#/item/${encodeURIComponent(REF)}@ci-box`);
  });

  it("emits the filter preset and the two instance routes, and stays round-trippable", () => {
    for (const route of [
      { name: "work" as const, filter: "laptop-a" },
      { name: "work" as const, ref: REF, instance: "laptop-a" },
      { name: "instances" as const },
      { name: "instance" as const, instance: "cloud-1" },
      { name: "standing" as const },
      { name: "settings" as const },
      { name: "events" as const, ref: REF },
    ]) {
      expect(parseHash(hrefFor(route))).toEqual(route);
    }
    expect(hrefFor({ name: "work", filter: "laptop-a" })).toBe("#/?instance=laptop-a");
    expect(hrefFor({ name: "instances" })).toBe("#/instances");
    expect(hrefFor({ name: "instance", instance: "cloud-1" })).toBe("#/instances/cloud-1");
  });
});
