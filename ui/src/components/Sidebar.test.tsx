/**
 * The sidebar on a fleet (issue-374, R5.2): the instance chip on the rows a
 * manager stamped, the filter behind the search toggle, and the health popover
 * listing each instance — and none of it on a worker, whose sidebar must be
 * the one it always was.
 *
 * And the sidebar de-cluttered to issue-511's Option C: one-line rows that
 * carry what is needed to choose — number, title, the urgent flag — pull
 * requests nested under the selected item only, two groups with a count on
 * Needs you alone, no Standing group, and the finder behind one icon.
 */

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { buildWorkItemViews } from "../api/model.ts";
import type { SessionRecord, WorkItemRecord } from "../api/types.ts";
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

const stream: StreamState = { name: "off" };

function renderSidebar(props: Partial<Parameters<typeof Sidebar>[0]> & { views: Parameters<typeof Sidebar>[0]["views"] }) {
  const onInstanceFilter = vi.fn();
  render(
    <Sidebar
      loading={false}
      titleFor={() => undefined}
      activeRef=""
      surface="work"
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

  it("chips every stamped row — work item and PR — and links each to its instance's hash", () => {
    renderSidebar({ views: views(), instances: managerDocument(), activeRef: REF, activeInstance: "laptop-a" });

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
  });

  it("offers the filter with every instance, naming the own row and a member's state", async () => {
    const user = userEvent.setup();
    const { onInstanceFilter } = renderSidebar({ views: views(), instances: managerDocument() });

    await user.click(screen.getByRole("button", { name: "Search and filter" }));
    const select = screen.getByRole("combobox", { name: "Instance filter" });
    const options = within(select).getAllByRole("option").map((option) => option.textContent);
    expect(options).toEqual(["All instances (3)", "hq · this instance", "laptop-a", "cloud-1 · unreachable"]);
    expect(instanceOption({ ...LAPTOP, state: "mismatched" }, false)).toBe("laptop-a · mismatched");

    await user.selectOptions(select, "laptop-a");
    expect(onInstanceFilter).toHaveBeenCalledWith("laptop-a");
  });

  it("filters the loaded rows to the chosen instance", () => {
    renderSidebar({ views: views(), instances: managerDocument(), instanceFilter: "ci-box" });

    const rows = itemRows();
    expect(rows).toHaveLength(1);
    expect(rows[0]).toHaveAttribute("data-instance", "ci-box");
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

describe("the sidebar de-cluttered (issue-511, Option C)", () => {
  const titleFor = (ref: string) => (ref === REF ? "Session announce comment loops back" : ref === OTHER ? "Other thing" : undefined);
  const graphs = {
    outer: {
      [REF]: {
        currentNode: "human-approval",
        parked: { node: "human-approval", reason: "approve the PR", since: "2026-09-29T09:00:00Z" },
        nodes: [{ id: "design", phase: "design", state: "done" }],
      },
    },
    inner: {},
  };

  const board = () =>
    buildWorkItemViews({
      workItems: [item(REF), item(OTHER)],
      sessions: [session(REF, undefined, [PR]), { ...session(OTHER), status: "paused" }],
      attention: [],
      graphs: graphs as never,
    });

  it("Scenario: a sidebar row is one line carrying the number, the title and the urgent flag, and its accessible name carries all three", () => {
    renderSidebar({ views: board(), titleFor });
    const row = itemRows().find((el) => el.getAttribute("aria-label")?.startsWith("lab#15"))!;
    expect(row).toHaveAttribute("aria-label", "lab#15 — Session announce comment loops back — human gate");
    expect(within(row).getByText("#15")).toBeInTheDocument();
    expect(within(row).getByText("Session announce comment loops back")).toHaveClass("truncate");
    expect(within(row).getByText("human gate")).toBeInTheDocument();
    // Nothing that is only needed once the item is open: no repository, no node, no age.
    expect(row.textContent).not.toContain("lab ·");
    expect(row.textContent).not.toMatch(/ago/);
    expect(row.textContent).not.toContain("human-approval");
    expect(row.querySelectorAll(":scope > div")).toHaveLength(1);
  });

  it("Scenario: a paused, merged or closed item shows no flag on its row", () => {
    const paused = board().find((view) => view.ref === OTHER)!;
    const merged = { ...paused, ended: { state: "merged", reason: "pr-merged" } };
    renderSidebar({ views: [paused, merged], titleFor });
    for (const row of itemRows()) {
      expect(row.textContent).not.toMatch(/paused|merged|closed/);
      expect(row.getAttribute("aria-label")).toBe("lab#16 — Other thing");
    }
  });

  it("Scenario: pull request rows nest only under the selected item", () => {
    const { unmount } = render(<></>);
    unmount();
    renderSidebar({ views: board(), titleFor });
    expect(screen.queryByRole("list", { name: "Pull requests for lab#15" })).toBeNull();
  });

  it("nests the pull requests, without their age, when the item or one of its PRs is selected", () => {
    renderSidebar({ views: board(), titleFor, activeRef: PR });
    const prs = screen.getByRole("list", { name: "Pull requests for lab#15" });
    const pr = within(prs).getByRole("link");
    expect(pr).toHaveAttribute("aria-current", "page");
    expect(pr.textContent).not.toMatch(/ago/);
    const owner = itemRows().find((el) => el.getAttribute("aria-label")?.startsWith("lab#15"))!;
    expect(owner).toHaveAttribute("data-owner", "true");
  });

  it("Scenario: only the Needs you group shows a count", () => {
    renderSidebar({ views: board(), titleFor });
    const needsYou = screen.getByText("Needs you").parentElement!;
    expect(within(needsYou).getByText("1")).toBeInTheDocument();
    const everything = screen.getByText("Everything else").parentElement!;
    expect(everything.querySelectorAll("span")).toHaveLength(1);
    expect(screen.queryByText("In flight")).toBeNull();
    expect(screen.queryByText("Shipped")).toBeNull();
    expect(screen.queryByText("Idle")).toBeNull();
  });

  it("Scenario: the Standing group does not render in the sidebar", () => {
    renderSidebar({ views: board(), titleFor });
    expect(screen.queryByText("Standing", { selector: "span" })).toBeNull();
    expect(document.querySelector("[data-row='standing']")).toBeNull();
    expect(screen.queryByText(/Manage standing sessions/)).toBeNull();
    // The surface nav still reaches the Standing surface (R3.4).
    expect(screen.getByRole("link", { name: "Standing" })).toHaveAttribute("href", "#/standing");
  });

  it("Scenario: the search box and the instance filter appear behind the search toggle, which carries aria-expanded", async () => {
    const user = userEvent.setup();
    renderSidebar({ views: board(), titleFor, instances: managerDocument() });
    const toggle = screen.getByRole("button", { name: "Search and filter" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("searchbox", { name: "Search work items" })).toBeNull();
    expect(screen.queryByRole("combobox", { name: "Instance filter" })).toBeNull();

    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("searchbox", { name: "Search work items" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Instance filter" })).toBeInTheDocument();

    await user.type(screen.getByRole("searchbox", { name: "Search work items" }), "other");
    expect(itemRows()).toHaveLength(1);
  });

  it("Scenario: an instance filter renders on a fleet and not on a worker", async () => {
    const user = userEvent.setup();
    renderSidebar({ views: board(), titleFor, instances: { role: "worker", name: "solo", instances: [HQ] } });
    await user.click(screen.getByRole("button", { name: "Search and filter" }));
    expect(screen.getByRole("searchbox", { name: "Search work items" })).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Instance filter" })).toBeNull();
  });

  it("sorts Everything else by last activity, newest first", () => {
    const views = board();
    const other = views.find((view) => view.ref === OTHER)!;
    other.lastActivity = "2026-09-30T10:00:00Z";
    const third = { ...other, ref: "github:octo/lab#18", shortRef: "lab#18", number: 18, key: "github:octo/lab#18", lastActivity: "2026-09-28T10:00:00Z" };
    renderSidebar({ views: [third, ...views], titleFor: () => undefined });
    const everything = screen.getByText("Everything else").parentElement!.parentElement!;
    const labels = within(everything).getAllByRole("link").map((el) => el.getAttribute("aria-label"));
    expect(labels).toEqual(["lab#16", "lab#18"]);
  });
});

describe("the sidebar fails closed and renders untrusted text as text (issue-511 security)", () => {
  it("abuse case 1: a title with markup renders as text in the one-line row and in its accessible name", () => {
    const views = buildWorkItemViews({ workItems: [item(REF)], sessions: [session(REF)], attention: [] });
    renderSidebar({ views, titleFor: () => '<b>x</b><img src=x onerror="alert(1)">' });
    const row = itemRows()[0]!;
    expect(row.getAttribute("aria-label")).toBe('lab#15 — <b>x</b><img src=x onerror="alert(1)">');
    expect(within(row).getByText('<b>x</b><img src=x onerror="alert(1)">')).toBeInTheDocument();
    expect(row.querySelector("b, img")).toBeNull();
  });

  it("reads degraded in the footer when a daemon is stopped — the word survives the de-cluttering", () => {
    const views = buildWorkItemViews({ workItems: [item(REF)], sessions: [session(REF)], attention: [] });
    renderSidebar({ views, daemons: [{ daemon: "poller", running: false }] as never });
    expect(screen.getByLabelText("Service health: degraded")).toBeInTheDocument();
  });

  it("says Loading… and then that nothing is tracked, in the C layout", () => {
    const { unmount } = render(
      <Sidebar
        views={[]}
        loading
        titleFor={() => undefined}
        activeRef=""
        surface="work"
        daemons={[]}
        stream={stream}
        onRefresh={() => {}}
        onCollapse={() => {}}
        serviceLabel="service"
      />,
    );
    expect(screen.getByText("Loading…")).toBeInTheDocument();
    unmount();
    renderSidebar({ views: [] });
    expect(screen.getByText(/Nothing is tracked on this machine yet/)).toBeInTheDocument();
  });
});
