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
  const row = rows.find((el) => el.className.includes("lp-side-row"));
  expect(row).toBeDefined();
  return row!;
}

describe("the control plane, on demo data", () => {
  it("says outright that the data is not real", async () => {
    renderApp();
    expect(await screen.findByText(/Demo data/)).toBeInTheDocument();
  });

  it("lists every tracked work item in one flat sidebar list, newest first", async () => {
    renderApp();

    // One flat "Work items" list (issue-298) — the armed item with no session
    // and the ad-hoc item (issue-230) included, ordered by recency.
    expect(await screen.findByText("Work items")).toBeInTheDocument();
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

    // The gate arrives with the graph round, so the card is awaited.
    expect(await screen.findByText(/Human gate — human-approval/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Approve — advance graph/ })).toBeInTheDocument();
  });

  it("opens a work item with the rail in the header and one trace tab per PR session", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(await sidebarRow("loop-lab#214"));

    expect(await screen.findByRole("heading", { name: /Control plane UI/ })).toBeInTheDocument();
    // The outer loop draws as the header's tick rail (issue-298); its position
    // caption names the current node among the phases the item kept.
    expect(screen.getAllByRole("list", { name: "loop position" }).length).toBeGreaterThan(0);
    // The PRs' sessions are reachable as trace tabs (issue-172/230). They are
    // links on the same hash the sidebar's nested rows use (issue-300), so the
    // two selectors cannot disagree about what the canvas shows.
    const tab = await screen.findByRole("link", { name: "loop-lab#216" });
    expect(tab).toHaveAttribute("href", `#/item/${encodeURIComponent("github:octo/loop-lab#216")}`);
    expect(screen.getByRole("link", { name: "loop-docs#47" })).toBeInTheDocument();
  });

  it("nests each work item's pull requests under it in the sidebar", async () => {
    renderApp();

    // The item's own row still reads the way it did; its PRs hang off it in a
    // list of their own, named for the item so a screen reader keeps the
    // nesting the indent shows (issue-300).
    await sidebarRow("loop-lab#214");
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

  it("opens the PR's own session from its nested sidebar row", async () => {
    const user = userEvent.setup();
    renderApp();

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
    expect(owner.className).toContain("owner");
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

  it("renders the session's turns and tool calls from the transcript route", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(await sidebarRow("loop-lab#214"));

    // The panel is live (issue-209): real turns, with tool invocations, and a
    // server-flagged malformed line surfaced rather than dropped.
    expect(await screen.findByText(/Reading the briefing template/)).toBeInTheDocument();
    expect(screen.getByText("Read")).toBeInTheDocument();
    expect(screen.getByText(/truncated by the harness mid-write/)).toBeInTheDocument();
    // The path caption stays: it names the file the served bytes came from.
    expect(screen.getByText(/~\/\.claude\/projects\/.*\.jsonl/)).toBeInTheDocument();
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
