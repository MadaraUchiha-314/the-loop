/**
 * End-to-end through the React layer, against the demo transport: the board
 * renders, a row navigates, and the two surfaces the service cannot back yet
 * stay visibly disabled rather than quietly pretending to work.
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

  it("shows the agent's question but keeps the reply box disabled, and says why", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("link", { name: "Open loop-lab#214" }));

    expect(await screen.findByText(/Agent is waiting for your input/)).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /Reply to the agent/ })).toBeDisabled();

    const send = screen.getByRole("button", { name: /Send to session/ });
    expect(send).toBeDisabled();
    expect(send).toHaveAttribute("title", expect.stringContaining("POST /api/v1/sessions/reply"));
  });

  it("does not claim to show turns and tool calls it cannot read", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("link", { name: "Open loop-lab#214" }));

    expect(await screen.findByText(/Turns and tool calls are not served by/)).toBeInTheDocument();
    // The derivable transcript path is offered instead, so the operator can tail it.
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
