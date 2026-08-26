/**
 * End-to-end through the React layer, against the demo transport: the Work
 * screen renders (sidebar + inbox + main pane, issue-283), a sidebar row
 * opens its item, and every surface behaves the way the service does —
 * including the transcript-backed trace panel (issue-209).
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

  it("lists every tracked work item in the sidebar, grouped by state", async () => {
    renderApp();

    // Nine fixture items in the overview line — the armed item with no session
    // and the ad-hoc item (issue-230) included.
    expect(await screen.findByText(/9 work items tracked/)).toBeInTheDocument();
    expect(await sidebarRow("loop-lab#214")).toBeInTheDocument();
    // Grouping by state (issue-283, feature #6): the group headers render.
    expect(screen.getByText("Running")).toBeInTheDocument();
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

  it("shows the inbox grouped by work item, gates above errors", async () => {
    renderApp();

    // The overview pane is the inbox (issue-283 B3/B4): the human gate is
    // approvable in place, and the paused/armed waits are listed.
    await waitFor(() => {
      expect(screen.getAllByText("human gate").length).toBeGreaterThan(0);
    });
    expect(screen.getAllByRole("button", { name: "Approve" }).length).toBeGreaterThan(0);
    expect(screen.getAllByText("session paused").length).toBeGreaterThan(0);
    expect(screen.getAllByText("armed without session").length).toBeGreaterThan(0);
  });

  it("opens a work item and shows its PRs, each on its own inner loop", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(await sidebarRow("loop-lab#214"));

    expect(await screen.findByRole("heading", { name: /Control plane UI/ })).toBeInTheDocument();
    // The outer loop draws as the header's tick rail (issue-298); its position
    // caption names the current node among the phases the item kept.
    expect(screen.getAllByRole("list", { name: "loop position" }).length).toBeGreaterThan(0);
    expect(await screen.findByRole("link", { name: "loop-lab#216 ↗" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "loop-docs#47 ↗" })).toBeInTheDocument();
  });

  it("shows the agent's question and sends a reply that closes the card", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(await sidebarRow("loop-lab#214"));

    expect(await screen.findByText(/The loop asks/)).toBeInTheDocument();
    // An empty reply has nothing to deliver, so it cannot be sent.
    expect(screen.getByRole("button", { name: /Send to session/ })).toBeDisabled();

    await user.type(screen.getByRole("textbox", { name: /Reply to the agent/ }), "Use OAuth.");
    await user.click(screen.getByRole("button", { name: /Send to session/ }));

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
