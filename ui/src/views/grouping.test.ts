import { describe, expect, it } from "vitest";

import { buildWorkItemViews, type WorkItemView } from "../api/model.ts";
import { DEMO_ATTENTION, DEMO_INNER_GRAPHS, DEMO_OUTER_GRAPHS, DEMO_SESSIONS, DEMO_WORK_ITEMS } from "../demo/fixture.ts";
import { filterViews, itemStatus, sidebarGroup } from "./grouping.ts";

const views = buildWorkItemViews({
  workItems: DEMO_WORK_ITEMS,
  sessions: DEMO_SESSIONS,
  attention: DEMO_ATTENTION,
  graphs: { outer: DEMO_OUTER_GRAPHS, inner: DEMO_INNER_GRAPHS },
});

function view(shortRef: string): WorkItemView {
  const found = views.find((candidate) => candidate.shortRef === shortRef);
  if (!found) throw new Error(`no ${shortRef} in the fixture`);
  return found;
}

describe("sidebarGroup", () => {
  it("puts an item parked on a human gate under Needs you, with a red dot", () => {
    expect(sidebarGroup(view("loop-lab#205"))).toBe("needs-you");
    expect(itemStatus(view("loop-lab#205"))).toBe("blocked");
  });

  it("puts a blocked loop under Needs you", () => {
    expect(sidebarGroup(view("loop-lab#178"))).toBe("needs-you");
  });

  it("puts a live session under In flight, pulsing", () => {
    expect(sidebarGroup(view("loop-lab#209"))).toBe("in-flight");
    expect(itemStatus(view("loop-lab#209"))).toBe("active");
  });

  it("puts a loop that walked every kept node under Shipped, green", () => {
    expect(sidebarGroup(view("loop-lab#181"))).toBe("shipped");
    expect(itemStatus(view("loop-lab#181"))).toBe("done");
  });

  it("leaves a paused session under Idle, grey", () => {
    expect(sidebarGroup(view("loop-lab#198"))).toBe("idle");
    expect(itemStatus(view("loop-lab#198"))).toBe("skipped");
  });
});

const titleFor = (ref: string) => (ref.endsWith("#214") ? "Control plane UI" : undefined);

describe("filterViews", () => {

  it("returns everything for a blank query", () => {
    expect(filterViews(views, "  ", titleFor)).toHaveLength(views.length);
  });

  it("matches the number, the title, the repository and the node, case-insensitively", () => {
    expect(filterViews(views, "#214", titleFor).map((v) => v.shortRef)).toEqual(["loop-lab#214"]);
    expect(filterViews(views, "control PLANE", titleFor).map((v) => v.shortRef)).toEqual(["loop-lab#214"]);
    expect(filterViews(views, "loop-lab", titleFor).length).toBe(views.length);
    expect(filterViews(views, "human-approval", titleFor).some((v) => v.shortRef === "loop-lab#205")).toBe(true);
  });

  it("matches nothing for a query nothing carries", () => {
    expect(filterViews(views, "zzz-not-here", titleFor)).toEqual([]);
  });
});
