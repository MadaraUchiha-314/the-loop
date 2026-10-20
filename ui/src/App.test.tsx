/**
 * End-to-end through the React layer, against the demo transport: the Work
 * screen renders (sidebar + main pane, issue-283), a sidebar row opens its
 * item, its PRs are nested under it and open their own session (issue-300),
 * and every surface behaves the way the service does — including the
 * transcript-backed trace panel (issue-209).
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { TheLoopApi } from "./api/client.ts";
import { App } from "./App.tsx";
import { ApiProvider } from "./state/ApiContext.tsx";

function renderApp() {
  return render(
    <ApiProvider>
      <App />
    </ApiProvider>,
  );
}

beforeEach(() => {
  globalThis.localStorage.clear();
  // The provider reads settings once, on mount, so the mode must be stored
  // before render. Polling is off so the test never races a background cycle.
  globalThis.localStorage.setItem(
    "the-loop:settings:v1",
    JSON.stringify({ baseUrl: "http://127.0.0.1:8787", mode: "demo", pollSeconds: 0 }),
  );
  globalThis.location.hash = "#/";
});

afterEach(() => {
  globalThis.location.hash = "#/";
});

/** The sidebar row for one work item, once it has rendered. */
async function sidebarRow(shortRef: string): Promise<HTMLElement> {
  const rows = await screen.findAllByRole("link", { name: new RegExp(shortRef.replace("#", "#")) });
  const row = rows.find((el) => el.dataset["row"] === "item");
  expect(row).toBeDefined();
  return row!;
}

describe("the control plane, on demo data", () => {
  it("says outright that the data is not real", async () => {
    renderApp();
    expect(await screen.findByText(/Demo data/)).toBeInTheDocument();
  });

  it("lists every tracked work item in the sidebar, grouped by what it needs", async () => {
    renderApp();

    // Two groups (issue-511, Option C): Needs you · Everything else — the
    // armed item with no session and the ad-hoc item (issue-230) included.
    expect(await screen.findByText("Needs you")).toBeInTheDocument();
    expect(await screen.findByText("Everything else")).toBeInTheDocument();
    expect(screen.queryByText("In flight")).toBeNull();
    expect(await sidebarRow("loop-lab#214")).toBeInTheDocument();
    expect(await sidebarRow("loop-lab#181")).toBeInTheDocument();
    // Nothing selected: the canvas shows the most recently active item
    // (the fixture's armed #187, whose spawn failure is the newest event).
    expect(await screen.findByRole("heading", { name: /Webhook replay protection/ })).toBeInTheDocument();
  });

  it("flags the item whose graph is parked on a human gate", async () => {
    renderApp();
    // The gate arrives with the graph round (one check per loop), so the row
    // is re-read until the flag lands rather than asserted on the first paint.
    await waitFor(async () => {
      const row = await sidebarRow("loop-lab#205");
      expect(within(row).getByText("human gate")).toBeInTheDocument();
    });
  });

  it("offers the parked human gate on the item's canvas, approvable in place", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(await sidebarRow("loop-lab#205"));

    // The gate arrives with the graph round, so the card is awaited. The banner
    // says "Human gate" and how long it has waited — never the node: the phase
    // chip is the one statement of the position (issue-511 R2.1, R2.5).
    const banner = (await screen.findByText("Human gate")).closest("[role='status']") as HTMLElement;
    expect(banner.textContent).not.toMatch(/Human gate — /);
    expect(banner.textContent).not.toContain("human-approval");
    expect(within(banner).getByText(/waiting/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Approve — advance graph/ })).toBeInTheDocument();
    // Scenario: the current node is written once — the phase chip.
    const main = screen.getByRole("main");
    expect(within(main).getAllByText("human-approval", { selector: "span" })).toHaveLength(1);
  });

  it("opens a work item with the rail in the header and one trace tab per PR session", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(await sidebarRow("loop-lab#214"));

    expect(await screen.findByRole("heading", { name: /Control plane UI/ })).toBeInTheDocument();
    // The node row is the map behind the header's Full graph control
    // (issue-511); the phase chip is the one statement of the position.
    expect(screen.queryByRole("list", { name: "loop position" })).toBeNull();
    const fullGraph = await screen.findByRole("button", { name: /Full graph/ });
    expect(fullGraph).toHaveAttribute("aria-expanded", "false");
    await user.click(fullGraph);
    expect(screen.getAllByRole("list", { name: "loop position" }).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /Collapse graph/ })).toHaveAttribute("aria-expanded", "true");
    // The PRs' sessions are reachable as trace tabs (issue-172/230). They are
    // links on the same hash the sidebar's nested rows use (issue-300), so the
    // two selectors cannot disagree about what the canvas shows.
    const tabs = await screen.findByRole("navigation", { name: "Sessions" });
    const tab = within(tabs).getByRole("link", { name: "loop-lab#216" });
    expect(tab).toHaveAttribute("href", `#/item/${encodeURIComponent("github:octo/loop-lab#216")}`);
    expect(within(tabs).getByRole("link", { name: "loop-docs#47" })).toBeInTheDocument();
  });

  it("nests the selected work item's pull requests under it in the sidebar", async () => {
    const user = userEvent.setup();
    renderApp();

    // The item's own row still reads the way it did; once it is selected its
    // PRs hang off it in a list of their own, named for the item so a screen
    // reader keeps the nesting the indent shows (issue-300, issue-511 R3.2).
    expect(screen.queryByRole("list", { name: "Pull requests for loop-lab#214" })).toBeNull();
    await user.click(await sidebarRow("loop-lab#214"));
    const prs = await screen.findByRole("list", { name: "Pull requests for loop-lab#214" });
    const rows = within(prs).getAllByRole("link");
    expect(rows).toHaveLength(2);
    // Same repository as the work item: the number alone. Elsewhere: qualified.
    expect(within(prs).getByText("#216")).toBeInTheDocument();
    expect(within(prs).getByText("loop-docs#47")).toBeInTheDocument();

    // An item whose loop runs no inner PR loops brings no nested list at all —
    // the ad-hoc item (issue-230) has no PR sessions to show.
    expect(screen.queryByRole("list", { name: "Pull requests for loop-lab#223" })).not.toBeInTheDocument();
  });

  it("draws a linked pull request once, under its work item and not beside it", async () => {
    const user = userEvent.setup();
    renderApp();
    await user.click(await sidebarRow("loop-lab#214"));

    // The fixture gives #216 both identities a real board gives a labeled PR:
    // its own portable record (the poller's ledger) and a session endpoint
    // nested under #214, which delivers it. It is one pull request, so it gets
    // one row — the nested one, where its session and transcript are
    // (issue-302).
    const prs = await screen.findByRole("list", { name: "Pull requests for loop-lab#214" });
    expect(within(prs).getByText("#216")).toBeInTheDocument();

    const rows = screen.getAllByRole("link").filter((el) => el.dataset["row"] === "item");
    expect(rows.some((el) => el.getAttribute("aria-label")?.includes("loop-lab#216"))).toBe(false);
  });

  it("opens the PR's own session from its nested sidebar row", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(await sidebarRow("loop-lab#214"));
    const prs = await screen.findByRole("list", { name: "Pull requests for loop-lab#214" });
    await user.click(within(prs).getByRole("link", { name: /#216/ }));

    // The canvas stays on the owning work item and switches the viewed trace to
    // that PR's session: the tab is current, and the row is the selected one.
    expect(await screen.findByRole("heading", { name: /Control plane UI/ })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("link", { name: "loop-lab#216" })).toHaveAttribute("aria-current", "page");
    });
    const row = within(prs).getByRole("link", { name: /#216/ });
    expect(row).toHaveAttribute("aria-current", "page");
    // …and the work item's own row is no longer the current one, but still
    // marks that the canvas is on it.
    const owner = await sidebarRow("loop-lab#214");
    expect(owner).not.toHaveAttribute("aria-current");
    expect(owner).toHaveAttribute("data-owner", "true");
  });

  it("shows the agent's question; the chat bar's reply closes the card", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(await sidebarRow("loop-lab#214"));

    expect(await screen.findByText(/The loop asks/)).toBeInTheDocument();
    // The card carries no reply box of its own (issue-298): the chat bar at
    // the pane's foot IS the reply, posting the same POST /sessions/reply.
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();

    await user.type(screen.getByRole("textbox", { name: /Message the session/ }), "Use OAuth.");
    await user.click(screen.getByRole("button", { name: "Send" }));

    // POST /sessions/reply emits session.reply_sent (the demo transport mirrors
    // it), and a reply newer than the question closes the card on refresh.
    await waitFor(() => {
      expect(screen.queryByText(/The loop asks/)).not.toBeInTheDocument();
    });
  });

  it("renders the session's turns from the transcript route, quiet by default", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(await sidebarRow("loop-lab#214"));

    // The panel is live (issue-209): real turns, and a server-flagged malformed
    // line surfaced rather than dropped. The tool calls are behind the switch
    // now (issue-419), so the reading column is prose and findings only.
    expect(await screen.findByText(/Reading the briefing template/)).toBeInTheDocument();
    expect(screen.getByText(/truncated by the harness mid-write/)).toBeInTheDocument();
    expect(screen.queryByText("Read")).not.toBeInTheDocument();
    expect(document.querySelectorAll("[data-tools]")).toHaveLength(0);
    // The path moved to the session panel: it still names the served file.
    expect(screen.getByText(/~\/\.claude\/projects\/.*\.jsonl/)).toBeInTheDocument();
  });

  it("reveals the whole trace behind the Verbose switch, from the mouse and the keyboard", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(await sidebarRow("loop-lab#214"));
    await screen.findByText(/Reading the briefing template/);

    // Off at load (issue-419) — the switch names the whole stream, not the tools.
    const toggle = screen.getByRole("switch", { name: "Verbose" });
    expect(toggle).toHaveAttribute("aria-checked", "false");
    expect(screen.queryByRole("switch", { name: "Tool calls" })).not.toBeInTheDocument();

    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-checked", "true");
    expect(document.querySelectorAll("[data-tools]").length).toBeGreaterThan(0);
    expect(screen.getByText("Read")).toBeInTheDocument();

    await user.click(toggle);
    expect(document.querySelectorAll("[data-tools]")).toHaveLength(0);

    toggle.focus();
    await user.keyboard(" ");
    expect(toggle).toHaveAttribute("aria-checked", "true");
    await user.keyboard("{Enter}");
    expect(toggle).toHaveAttribute("aria-checked", "false");
  });

  it("switches theme from the header and keeps the choice in this browser", async () => {
    const user = userEvent.setup();
    renderApp();
    await sidebarRow("loop-lab#214");

    // jsdom has no matchMedia, so with nothing chosen the page is light.
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    await user.click(screen.getByRole("button", { name: "Switch to dark theme" }));
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(JSON.parse(globalThis.localStorage.getItem("the-loop:settings:v1") ?? "{}").theme).toBe("dark");

    await user.click(screen.getByRole("button", { name: "Switch to light theme" }));
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(JSON.parse(globalThis.localStorage.getItem("the-loop:settings:v1") ?? "{}").theme).toBe("light");
  });

  it("collapses the sidebar and reopens it from the header; the session panel is no longer a column", async () => {
    const user = userEvent.setup();
    renderApp();
    await sidebarRow("loop-lab#214");

    await user.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    expect(screen.queryByRole("complementary", { name: "Work items" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Open sidebar" }));
    expect(await screen.findByRole("complementary", { name: "Work items" })).toBeInTheDocument();

    // Option C (issue-511): no session column, so no panel controls either —
    // the facts are behind the header's Session details disclosure.
    expect(screen.queryByRole("complementary", { name: "Session" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Close panel" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Open session panel" })).toBeNull();
    expect(document.querySelector("[data-session-details] > summary")).toHaveAttribute("aria-label", "Session details");
  });

  it("Scenario: the header meta is the ref chip, the phase chip, the note and the age — the repository line and the instance chip are gone", async () => {
    const user = userEvent.setup();
    renderApp();
    await user.click(await sidebarRow("loop-lab#205"));
    await screen.findByText("Human gate");

    const header = screen.getByRole("banner");
    const meta = header.querySelector("h1 + div") as HTMLElement;
    expect(within(meta).getByText("github:octo/loop-lab#205")).toHaveClass("ref-chip");
    expect(within(meta).getByText("human-approval")).toBeInTheDocument();
    expect(within(meta).getByText("parked — awaiting a human")).toBeInTheDocument();
    expect(within(meta).getByText(/^updated /)).toBeInTheDocument();
    expect(within(meta).getByRole("button", { name: /Full graph/ })).toHaveAttribute("aria-expanded", "false");
    // The repository is drawn once, inside the ref chip: no bare `octo/loop-lab` line.
    expect(within(meta).queryByText("octo/loop-lab")).toBeNull();
    expect(within(meta).queryByText("loop-lab", { selector: ":not(.ref-chip)" })).toBeNull();
    expect(meta.querySelector("[data-instance]")).toBeNull();
    // One statement of the position: the parked node appears once in the whole main column.
    expect(within(screen.getByRole("main")).getAllByText("human-approval", { selector: "span" })).toHaveLength(1);
  });

  it("filters the sidebar by what is typed into the search box, behind the search toggle", async () => {
    const user = userEvent.setup();
    renderApp();
    await sidebarRow("loop-lab#214");

    await user.click(screen.getByRole("button", { name: "Search and filter" }));
    await user.type(screen.getByRole("searchbox", { name: "Search work items" }), "webhook replay");
    expect(screen.getAllByRole("link").filter((el) => el.dataset["row"] === "item")).toHaveLength(1);
    expect(await sidebarRow("loop-lab#187")).toBeInTheDocument();
  });

  it("survives a deep link to an item that is not on this service", async () => {
    globalThis.location.hash = "#/item/github:octo/nope%23999";
    renderApp();
    await waitFor(() => expect(screen.getByText(/No work item/)).toBeInTheDocument());
  });

  it("lands a pre-283 sessions deep link on the owning work item", async () => {
    globalThis.location.hash = "#/sessions/github%3Aocto%2Floop-lab%23214";
    renderApp();
    expect(await screen.findByRole("heading", { name: /Control plane UI/ })).toBeInTheDocument();
  });
});

/** A `matchMedia` that answers every min-width query with "narrower than that". */
const narrowViewport = (query: string) =>
  ({ matches: false, media: query, addEventListener: () => {}, removeEventListener: () => {} }) as unknown as MediaQueryList;

describe("nothing lost, nothing trusted (issue-511 R5.3, R5.4, R6.3, fail-closed)", () => {
  it("Scenario: loading, empty board, missing deep link, no-transcript fallback, truncated tail and blocked composer render their sentences in the C layout", async () => {
    const user = userEvent.setup();
    renderApp();
    // #187 is armed with no session: the trace falls back to the event trail
    // and the composer is blocked with its reason — the one hint still drawn.
    await user.click(await sidebarRow("loop-lab#187"));
    expect(await screen.findByText(/No transcript served for this session/)).toBeInTheDocument();
    expect(screen.getByText(/Falling back to the event-log trail/)).toBeInTheDocument();
    expect(screen.getByText("No session is registered for this ref on the service's machine.", { selector: "span" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /Message the session/ })).toBeDisabled();
    // The truncated tail is asserted in WorkItemDetail.test.tsx: the demo
    // transcript is shorter than the tail the column asks for.
  });

  it("keeps the connection banner above the columns when the service cannot be reached", async () => {
    const failing = new Proxy({} as TheLoopApi, {
      get: (_target, key) => {
        if (key === "baseUrl") return "http://127.0.0.1:8787";
        if (key === "isDemo") return false;
        return () => Promise.reject(new TypeError("fetch failed"));
      },
    });
    render(
      <ApiProvider api={failing}>
        <App />
      </ApiProvider>,
    );
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/reach|connect|service/i);
  });

  /** A hash is opened and its landmark awaited, one mount at a time: the hash is global state. */
  async function lands(hash: string, landmark: () => Promise<unknown>): Promise<void> {
    globalThis.location.hash = hash;
    const { unmount } = renderApp();
    await landmark();
    unmount();
  }

  it("Scenario: every hash the 20.5.1 app parses lands on the same surface", async () => {
    const cases: [string, () => Promise<unknown>][] = [
      ["#/", () => screen.findByRole("heading", { name: /Webhook replay protection/ })],
      ["#/item/github%3Aocto%2Floop-lab%23205", () => screen.findByText("Human gate")],
      ["#/standing", () => screen.findByRole("heading", { name: /Standing/ })],
      ["#/settings", () => screen.findByText("CLI config")],
      ["#/instances", () => screen.findByRole("heading", { name: /Instances/ })],
      ["#/events", () => screen.findByRole("heading", { name: /Webhook replay protection/ })],
      ["#/sessions/github%3Aocto%2Floop-lab%23214", () => screen.findByRole("heading", { name: /Control plane UI/ })],
    ];
    await cases.reduce((chain, [hash, landmark]) => chain.then(() => lands(hash, landmark)), Promise.resolve());
  });

  it("Scenario: below 768 px the sidebar starts closed and reopens from the header", async () => {
    const user = userEvent.setup();
    Object.defineProperty(globalThis, "matchMedia", { value: narrowViewport, configurable: true, writable: true });
    try {
      renderApp();
      await screen.findByRole("heading", { name: /Webhook replay protection/ });
      expect(screen.queryByRole("complementary", { name: "Work items" })).toBeNull();
      await user.click(screen.getByRole("button", { name: "Open sidebar" }));
      expect(await screen.findByRole("complementary", { name: "Work items" })).toBeInTheDocument();
      // The Session details disclosure starts closed at every width (R6.3).
      expect((document.querySelector("[data-session-details]") as HTMLDetailsElement).open).toBe(false);
    } finally {
      Reflect.deleteProperty(globalThis, "matchMedia");
    }
  });
});
