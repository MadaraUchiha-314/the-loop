/**
 * The sidebar on a fleet (issue-374, R5.2): the instance chip on the rows a
 * manager stamped, the filter beside the search box, and the health popover
 * listing each instance — and none of it on a worker, whose sidebar must be
 * the one it always was.
 */

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { buildWorkItemViews } from "../api/model.ts";
import type { SessionRecord, StandingSessionRecord, WorkItemRecord } from "../api/types.ts";
import type { StreamState } from "../state/useStream.ts";
import { CLOUD, HQ, LAPTOP, managerDocument } from "../test/manager.ts";
import { instanceOption, showsFleet, Sidebar } from "./Sidebar.tsx";

const REF = "github:octo/lab#15";
const OTHER = "github:octo/lab#16";
const PR = "github:octo/lab#17";

function item(ref: string, instance?: string): WorkItemRecord {
  return {
    ref,
    graph: { loop: "pdlc-work-item-loop", workItem: `issue-${ref.split("#")[1]}`, nodes: [{ id: "design", phase: "design" }] },
    ...(instance ? { instance } : {}),
  };
}

function session(ref: string, instance?: string, prs: string[] = []): SessionRecord {
  return {
    ref,
    workItem: { ref, provider: "github", owner: "octo", repo: "lab", number: Number(ref.split("#")[1]) },
    harness: "claude",
    harnessSessionId: `sid-${instance ?? "w"}-${ref.split("#")[1]}`,
    status: "active",
    lastEventAt: "2026-09-29T10:00:00Z",
    ...(instance ? { instance } : {}),
    pullRequests: prs.map((pr) => ({
      workItem: { ref: pr, provider: "github", owner: "octo", repo: "lab", number: Number(pr.split("#")[1]) },
      harness: "claude",
      harnessSessionId: `pr-${pr.split("#")[1]}`,
      status: "active",
    })),
  };
}

function standing(name: string, instance?: string): StandingSessionRecord {
  return {
    name,
    declared: true,
    description: "",
    autoStart: true,
    harness: "claude",
    cwd: "/w",
    tmuxTarget: `loop-standing-${name}`,
    ref: `standing:${name}`,
    status: "running",
    running: true,
    harnessSessionId: "",
    slackChannel: "",
    slackThread: "",
    startedAt: "",
    lastMessageAt: "",
    ...(instance ? { instance } : {}),
  };
}

const stream: StreamState = { name: "off" };

function renderSidebar(props: Partial<Parameters<typeof Sidebar>[0]> & { views: Parameters<typeof Sidebar>[0]["views"] }) {
  const onInstanceFilter = vi.fn();
  render(
    <Sidebar
      loading={false}
      titleFor={() => undefined}
      activeRef=""
      surface="work"
      standingSessions={[]}
      daemons={[]}
      stream={stream}
      onRefresh={() => {}}
      onCollapse={() => {}}
      serviceLabel="service · h:1"
      onInstanceFilter={onInstanceFilter}
      {...props}
    />,
  );
  return { onInstanceFilter };
}

const itemRows = () => screen.getAllByRole("link").filter((el) => el.dataset["row"] === "item");

describe("the sidebar on a worker", () => {
  it("shows no chip, no filter and no fleet in the popover", () => {
    const views = buildWorkItemViews({ workItems: [item(REF)], sessions: [session(REF)], attention: [] });
    renderSidebar({ views, instances: { role: "worker", name: "solo", instances: [HQ] } });

    expect(screen.queryByRole("combobox", { name: "Instance filter" })).toBeNull();
    expect(document.querySelectorAll("[data-instance]")).toHaveLength(0);
    expect(document.querySelector("[data-fleet]")).toBeNull();
    expect(itemRows()[0]).toHaveAttribute("href", `#/item/${encodeURIComponent(REF)}`);
  });

  it("decides the filter from the document: many rows, or a manager", () => {
    expect(showsFleet(undefined)).toBe(false);
    expect(showsFleet({ role: "worker", name: "solo", instances: [HQ] })).toBe(false);
    expect(showsFleet({ role: "manager", name: "hq", instances: [HQ] })).toBe(true);
    expect(showsFleet({ role: "worker", name: "hq", instances: [HQ, LAPTOP] })).toBe(true);
  });
});

describe("the sidebar on a manager", () => {
  const views = () =>
    buildWorkItemViews({
      workItems: [item(REF, "laptop-a"), item(REF, "ci-box"), item(OTHER, "hq")],
      sessions: [session(REF, "laptop-a", [PR]), session(REF, "ci-box"), session(OTHER, "hq")],
      attention: [],
    });

  it("chips every stamped row — work item, PR and standing session — and links each to its instance's hash", () => {
    renderSidebar({
      views: views(),
      instances: managerDocument(),
      standingSessions: [standing("triage", "ci-box")],
    });

    const rows = itemRows();
    expect(rows).toHaveLength(3);
    // The same ref on two instances is two rows, each addressed with its `@<instance>`.
    const fifteen = rows.filter((el) => el.getAttribute("aria-label")?.startsWith("lab#15"));
    expect(fifteen.map((el) => el.getAttribute("href") ?? "").toSorted((a, b) => a.localeCompare(b))).toEqual([
      `#/item/${encodeURIComponent(REF)}@ci-box`,
      `#/item/${encodeURIComponent(REF)}@laptop-a`,
    ]);
    for (const row of fifteen) expect(within(row).getByText(row.dataset["instance"]!)).toBeInTheDocument();

    const prs = screen.getByRole("list", { name: "Pull requests for lab#15" });
    const pr = within(prs).getByRole("link");
    expect(pr).toHaveAttribute("href", `#/item/${encodeURIComponent(PR)}@laptop-a`);
    expect(within(pr).getByText("laptop-a")).toBeInTheDocument();

    const standingRow = screen.getAllByRole("link").find((el) => el.dataset["row"] === "standing")!;
    expect(within(standingRow).getByText("ci-box")).toBeInTheDocument();
  });

  it("offers the filter with every instance, naming the own row and a member's state", async () => {
    const user = userEvent.setup();
    const { onInstanceFilter } = renderSidebar({ views: views(), instances: managerDocument() });

    const select = screen.getByRole("combobox", { name: "Instance filter" });
    const options = within(select).getAllByRole("option").map((option) => option.textContent);
    expect(options).toEqual(["All instances (3)", "hq · this instance", "laptop-a", "cloud-1 · unreachable"]);
    expect(instanceOption({ ...LAPTOP, state: "mismatched" }, false)).toBe("laptop-a · mismatched");

    await user.selectOptions(select, "laptop-a");
    expect(onInstanceFilter).toHaveBeenCalledWith("laptop-a");
  });

  it("filters the loaded rows to the chosen instance", () => {
    renderSidebar({
      views: views(),
      instances: managerDocument(),
      instanceFilter: "ci-box",
      standingSessions: [standing("triage", "ci-box"), standing("watch", "laptop-a")],
    });

    const rows = itemRows();
    expect(rows).toHaveLength(1);
    expect(rows[0]).toHaveAttribute("data-instance", "ci-box");
    expect(screen.getAllByRole("link").filter((el) => el.dataset["row"] === "standing")).toHaveLength(1);
  });

  it("highlights only the selected instance's row when a ref is on two", () => {
    renderSidebar({ views: views(), instances: managerDocument(), activeRef: REF, activeInstance: "ci-box" });
    const current = itemRows().filter((el) => el.getAttribute("aria-current") === "page");
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveAttribute("data-instance", "ci-box");
  });

  it("lists each instance with its state in the health popover, and reads degraded for a down member", () => {
    renderSidebar({ views: views(), instances: managerDocument([HQ, LAPTOP, CLOUD]) });
    expect(screen.getByLabelText("Service health: degraded")).toBeInTheDocument();
    const fleet = document.querySelector("[data-fleet]")!;
    expect(fleet).not.toBeNull();
    expect(within(fleet as HTMLElement).getByText("cloud-1")).toBeInTheDocument();
    expect(within(fleet as HTMLElement).getByText("unreachable · connection refused")).toBeInTheDocument();
    expect(within(fleet as HTMLElement).getByText("this instance · 3 managed")).toBeInTheDocument();
  });

  it("links to the Instances tab from the nav row", () => {
    renderSidebar({ views: views(), instances: managerDocument(), surface: "instances" });
    const link = screen.getByRole("link", { name: "Instances" });
    expect(link).toHaveAttribute("href", "#/instances");
    expect(link).toHaveAttribute("aria-current", "page");
  });
});
