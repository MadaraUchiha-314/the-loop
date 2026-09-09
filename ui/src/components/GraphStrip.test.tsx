import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

describe("GraphStrip", () => {
  it("compacts by default and shows every node behind Full graph", async () => {
    const user = userEvent.setup();
    render(<GraphStrip nodes={rail("human-approval")} loop="pdlc-work-item-loop" emptyMessage="—" />);
    const list = screen.getByRole("list", { name: "loop position" });
    expect(list.querySelectorAll("[data-node]")).toHaveLength(6);
    expect(screen.getByText("15 of 19 nodes passed")).toBeInTheDocument();
    expect(screen.getByText("1 skipped")).toBeInTheDocument();
    expect(screen.getByText("at human-approval")).toBeInTheDocument();
    // The current node is the step; a skipped one is struck through.
    expect(list.querySelector('[aria-current="step"]')).toHaveTextContent("Human approval");

    await user.click(screen.getByRole("button", { name: /Full graph/ }));
    expect(list.querySelectorAll("[data-node]")).toHaveLength(19);
    expect(screen.getByText("Brainstorming").className).toContain("line-through");
    expect(screen.getByRole("button", { name: /Collapse graph/ })).toHaveAttribute("aria-expanded", "true");
  });

  it("says why when there is no rail", () => {
    render(<GraphStrip nodes={[]} loop="pdlc-work-item-loop" emptyMessage="No checkout recorded." />);
    expect(screen.getByText("No checkout recorded.")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "loop position" })).toBeNull();
  });
});
