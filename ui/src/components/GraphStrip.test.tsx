import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { RailNode } from "../api/model.ts";
import { compactRail, GraphStrip, humanize, railLabel } from "./GraphStrip.tsx";

const ids = [
  "phase-selection",
  "brainstorming",
  "requirements-definition",
  "requirements-approval",
  "design",
  "test-planning",
  "design-approval",
  "tasks-breakdown",
  "implementation",
  "verification",
  "self-review",
  "critic-review",
  "security-review",
  "evidence",
  "capability-docs",
  "reviewer-briefing",
  "human-approval",
  "complete",
  "cleanup",
];

function rail(current: string): RailNode[] {
  const at = ids.indexOf(current);
  return ids.map((id, index) => ({
    id,
    label: id,
    state: id === "brainstorming" ? "skipped" : index < at ? "done" : index === at ? "current" : "pending",
    detail: "",
  }));
}

describe("compactRail", () => {
  it("keeps the first, the last and two either side of the current node, one gap between", () => {
    const entries = compactRail(rail("human-approval"));
    expect(entries.map((entry) => (entry === "gap" ? "···" : entry.id))).toEqual([
      "phase-selection",
      "···",
      "capability-docs",
      "reviewer-briefing",
      "human-approval",
      "complete",
      "cleanup",
    ]);
  });

  it("anchors on the first node when nothing is current", () => {
    const done: RailNode[] = ids.map((id) => ({ id, label: id, state: "done", detail: "" }));
    const entries = compactRail(done);
    expect(entries.map((entry) => (entry === "gap" ? "···" : entry.id))).toEqual([
      "phase-selection",
      "brainstorming",
      "requirements-definition",
      "···",
      "cleanup",
    ]);
  });

  it("does not fold a short rail at all", () => {
    const short = rail("human-approval").slice(0, 4);
    expect(compactRail(short)).toHaveLength(4);
  });
});

describe("railLabel and humanize", () => {
  it("names the current node among the kept phases", () => {
    expect(railLabel(rail("design"))).toBe("design · 4 of 18");
    expect(humanize("human-approval")).toBe("Human approval");
  });
});

describe("GraphStrip (issue-511: the band behind Full graph)", () => {
  it("renders nothing while collapsed — the header carries the position and the control", () => {
    render(<GraphStrip nodes={rail("human-approval")} loop="pdlc-work-item-loop" expanded={false} />);
    expect(screen.queryByRole("region", { name: "Loop position" })).toBeNull();
    expect(screen.queryByRole("list", { name: "loop position" })).toBeNull();
    expect(document.querySelectorAll("[data-node]")).toHaveLength(0);
  });

  it("shows every node when expanded, the current one as the step, with no counts and no second statement of the position", () => {
    render(<GraphStrip nodes={rail("human-approval")} loop="pdlc-work-item-loop" expanded />);
    const region = screen.getByRole("region", { name: "Loop position" });
    const list = screen.getByRole("list", { name: "loop position" });
    expect(list.querySelectorAll("[data-node]")).toHaveLength(19);
    expect(list.querySelector('[aria-current="step"]')).toHaveTextContent("Human approval");
    expect(screen.getByText("Brainstorming").className).toContain("line-through");
    expect(within(region).getByText("pdlc-work-item-loop")).toBeInTheDocument();
    expect(region.textContent).not.toMatch(/of \d+ nodes passed/);
    expect(region.textContent).not.toMatch(/skipped/);
    expect(region.textContent).not.toMatch(/\bat human-approval/);
    // The strip owns no toggle any more: the header's Full graph button does.
    expect(within(region).queryByRole("button")).toBeNull();
  });

  it("marks the pointer node as the step even when it is blocked, and only it (critic round 1, R6.2)", () => {
    const nodes = rail("implementation");
    for (const node of nodes) if (node.id === "implementation" || node.id === "design") node.state = "blocked";
    render(<GraphStrip nodes={nodes} loop="pdlc-work-item-loop" expanded current="implementation" />);
    const steps = document.querySelectorAll('[aria-current="step"]');
    expect(steps).toHaveLength(1);
    expect(steps[0]).toHaveTextContent("Implementation");
  });

  it("renders nothing for an empty rail — the header says why, in the Full graph slot", () => {
    render(<GraphStrip nodes={[]} loop="pdlc-work-item-loop" expanded />);
    expect(screen.queryByRole("region", { name: "Loop position" })).toBeNull();
  });
});
