/**
 * The instance pane (issue-374, R5.4): one instance managed on its own —
 * identity, daemons, config editor, restart, health, unregister — with every
 * control disabled, naming the reason, when the instance is not `live`, and
 * every call carrying `instance=<name>` when it is.
 */

import { render, screen, waitFor, within } from "@testing-library/react";

import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { App } from "../App.tsx";
import type { TheLoopApi } from "../api/client.ts";
import { ApiProvider } from "../state/ApiContext.tsx";
import { ManagerApi } from "../test/manager.ts";

function renderApp(api?: TheLoopApi) {
  return render(
    <ApiProvider api={api}>
      <App />
    </ApiProvider>,
  );
}

beforeEach(() => {
  globalThis.localStorage.clear();
  globalThis.localStorage.setItem(
    "the-loop:settings:v1",
    JSON.stringify({ baseUrl: "http://127.0.0.1:8787", mode: "demo", pollSeconds: 0 }),
  );
});

afterEach(() => {
  globalThis.location.hash = "#/";
});

describe("the instance pane for a member that is not live", () => {
  it("names the reason and disables every control with it", async () => {
    globalThis.location.hash = "#/instances/cloud-1";
    const api = new ManagerApi();
    renderApp(api);

    expect(await screen.findByRole("heading", { name: "cloud-1" })).toBeInTheDocument();
    expect(screen.getAllByRole("status").map((el) => el.textContent).join("\n")).toMatch(/Not live: connection refused/);

    const restart = screen.getByRole("button", { name: /restart instance/i });
    expect(restart).toBeDisabled();
    expect(restart).toHaveAttribute("title", "connection refused");
    // Daemons and health both: neither is read from a member that has not answered.
    expect(screen.getAllByText(/Unknown — the instance has not answered/)).toHaveLength(2);
    expect(screen.getByText(/Disabled: connection refused/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save changes" })).toBeNull();
    // Nothing was sent to it: the manager refuses to, and so does the pane.
    expect(api.targeted.filter(([, instance]) => instance === "cloud-1")).toEqual([]);
    // Unregister stays offered — it writes the manager's registry, not the member.
    expect(screen.getByRole("button", { name: /unregister cloud-1/i })).toBeEnabled();
  });
});

describe("the instance pane for a live member", () => {
  it("reads identity, health and config with instance=<name>, and lists the managed refs as chips", async () => {
    globalThis.location.hash = "#/instances/laptop-a";
    const api = new ManagerApi();
    renderApp(api);

    expect(await screen.findByRole("heading", { name: "laptop-a" })).toBeInTheDocument();
    expect(await screen.findByText("github:octo/repo#1")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Save changes" })).toBeInTheDocument();
    expect(screen.getByText(/Configuration — laptop-a/)).toBeInTheDocument();

    await waitFor(() => {
      const targeted = api.targeted.filter(([, instance]) => instance === "laptop-a").map(([method]) => method);
      expect(targeted).toEqual(expect.arrayContaining(["instance", "health", "config", "configSchema"]));
    });
    expect(api.targeted.some(([, instance]) => instance === "")).toBe(false);

    // Only laptop-a's daemons, from the manager's stamped union (hq's poller
    // is in the sidebar's health popover, not here).
    const daemons = document.querySelector('[data-card="daemons"]');
    expect(daemons).not.toBeNull();
    expect(within(daemons as HTMLElement).getByText("gh-webhook")).toBeInTheDocument();
    expect(within(daemons as HTMLElement).getAllByText("poller")).toHaveLength(1);
  });

  it("drives a daemon verb, and a restart after a confirm, against that instance", async () => {
    const user = userEvent.setup();
    globalThis.location.hash = "#/instances/laptop-a";
    const api = new ManagerApi();
    renderApp(api);
    await screen.findByRole("heading", { name: "laptop-a" });

    await user.click(await screen.findByRole("button", { name: "start" }));
    await waitFor(() => expect(api.targeted).toContainEqual(["controlDaemon", "laptop-a"]));
    expect(await screen.findByText(/start gh-webhook on laptop-a/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /restart instance…/i }));
    expect(api.targeted.filter(([method]) => method === "restart")).toEqual([]);
    await user.click(screen.getByRole("button", { name: /restart laptop-a now/i }));
    await waitFor(() => expect(api.targeted).toContainEqual(["restart", "laptop-a"]));
    expect(await screen.findByText(/Restart of laptop-a scheduled/)).toBeInTheDocument();
  });

  it("unregisters a member after a confirm and returns to the fleet", async () => {
    const user = userEvent.setup();
    globalThis.location.hash = "#/instances/laptop-a";
    const api = new ManagerApi();
    renderApp(api);
    await screen.findByRole("heading", { name: "laptop-a" });

    await user.click(screen.getByRole("button", { name: /unregister laptop-a…/i }));
    await user.click(screen.getByRole("button", { name: /unregister laptop-a for good/i }));

    await waitFor(() => expect(globalThis.location.hash).toBe("#/instances"));
    expect(api.writes).toEqual([{ verb: "unregister", name: "laptop-a" }]);
  });
});

describe("the instance pane for the manager's own row", () => {
  it("offers no Unregister — the manager is its own first member, never a registered one", async () => {
    globalThis.location.hash = "#/instances/hq";
    renderApp(new ManagerApi());

    expect(await screen.findByRole("heading", { name: "hq" })).toBeInTheDocument();
    expect(screen.getByText("this instance")).toBeInTheDocument();
    await screen.findByRole("button", { name: "Save changes" });
    expect(screen.queryByRole("button", { name: /unregister/i })).toBeNull();
  });
});

describe("the instance pane on a worker (the demo fixture)", () => {
  it("manages the one instance there is, and says so for a name it does not have", async () => {
    globalThis.location.hash = "#/instances/demo";
    renderApp();
    expect(await screen.findByRole("heading", { name: "demo" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Save changes" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /unregister/i })).toBeNull();

    globalThis.location.hash = "#/instances/nope";
    expect(await screen.findByText(/No instance/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Back to the instances/ })).toHaveAttribute("href", "#/instances");
  });
});
