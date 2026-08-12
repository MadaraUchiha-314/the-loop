/**
 * End-to-end through the React layer, against the demo transport: the board
 * renders, a row navigates, and every surface behaves the way the service
 * does — including the transcript-backed trace panel (issue-209), which
 * shipped visibly disabled until the route existed.
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

/**
 * Assert on a dashboard row once it has settled.
 *
 * The board paints twice on purpose — the flat lists first, then one
 * `graph/check` per loop — so anything derived from a graph report (the current
 * node, a parked-gate flag) is absent on the first paint. Re-reading the row
 * inside `waitFor` is what makes that a race the test tolerates rather than one
 * it loses.
 */
async function expectInRow(rowLabel: string, text: string): Promise<void> {
  await waitFor(() => {
    const row = screen.getByRole("link", { name: rowLabel });
    expect(within(row).getByText(text)).toBeInTheDocument();
  });
}

describe("the control plane, on demo data", () => {
  it("says outright that the data is not real", async () => {
    renderApp();
    expect(await screen.findByText(/Demo data/)).toBeInTheDocument();
  });

  it("lists every tracked work item with its loop position", async () => {
    renderApp();

    // Eight fixture items, all present — the armed item with no session included.
    expect(await screen.findByText(/8 tracked/)).toBeInTheDocument();
    // The position arrives in the second round (one graph/check per loop), so
    // the row is re-read until it does rather than asserted on the first paint.
    await expectInRow("Open loop-lab#214", "implementation");
  });

  it("flags the item whose graph is parked on a human gate", async () => {
    renderApp();
    await expectInRow("Open loop-lab#205", "human gate");
  });

  it("opens a work item and shows its PRs, each on its own inner loop", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("link", { name: "Open loop-lab#214" }));

    expect(await screen.findByRole("heading", { name: /Control plane UI/ })).toBeInTheDocument();
    expect(screen.getByText(/Outer loop · pdlc-work-item-loop/)).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "loop-lab#216 ↗" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "loop-docs#47 ↗" })).toBeInTheDocument();
  });

  it("shows the agent's question and sends a reply that closes the card", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("link", { name: "Open loop-lab#214" }));

    expect(await screen.findByText(/Agent is waiting for your input/)).toBeInTheDocument();
    // An empty reply has nothing to deliver, so it cannot be sent.
    expect(screen.getByRole("button", { name: /Send to session/ })).toBeDisabled();

    await user.type(screen.getByRole("textbox", { name: /Reply to the agent/ }), "Use OAuth.");
    await user.click(screen.getByRole("button", { name: /Send to session/ }));

    // POST /sessions/reply emits session.reply_sent (the demo transport mirrors
    // it), and a reply newer than the question closes the card on refresh.
    await waitFor(() => {
      expect(screen.queryByText(/Agent is waiting for your input/)).not.toBeInTheDocument();
    });
  });

  it("renders the session's turns and tool calls from the transcript route", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("link", { name: "Open loop-lab#214" }));

    // The panel is live (issue-209): real turns, with tool invocations, and a
    // server-flagged malformed line surfaced rather than dropped.
    expect(await screen.findByText(/Reading the briefing template/)).toBeInTheDocument();
    expect(screen.getByText("Read")).toBeInTheDocument();
    expect(screen.getByText(/truncated by the harness mid-write/)).toBeInTheDocument();
    // The path caption stays: it names the file the served bytes came from.
    expect(screen.getByText(/~\/\.claude\/projects\/.*\.jsonl/)).toBeInTheDocument();
  });

  it("routes the attention tab to the union of /attention and the graph gates", async () => {
    const user = userEvent.setup();
    renderApp();

    // Gates come from the graph round; leaving before it lands would test an
    // empty board rather than the union this page exists to show.
    await expectInRow("Open loop-lab#205", "human gate");
    await user.click(screen.getByRole("link", { name: /^Attention/ }));

    expect(await screen.findByRole("heading", { name: "Needs attention" })).toBeInTheDocument();
    expect(screen.getAllByText("human gate").length).toBeGreaterThan(0);
    expect(screen.getByText("session paused")).toBeInTheDocument();
    expect(screen.getByText("armed without session")).toBeInTheDocument();
  });

  it("survives a deep link to an item that is not on this service", async () => {
    globalThis.location.hash = "#/item/github:octo/nope%23999";
    renderApp();
    await waitFor(() => expect(screen.getByText(/No work item/)).toBeInTheDocument());
  });
});
