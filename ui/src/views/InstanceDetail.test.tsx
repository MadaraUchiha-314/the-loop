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
import { DEMO_GATEWAY } from "../demo/fixture.ts";
import { ManagerApi } from "../test/manager.ts";
import { gatewayWords } from "./InstanceDetail.tsx";

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
    // Daemons, health and the gateway card (issue-496): none is read from a member
    // that has not answered.
    expect(screen.getAllByText(/Unknown — the instance has not answered/)).toHaveLength(3);
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

describe("the Gateway card (issue-496, R10.3)", () => {
  async function renderWith(doc: (typeof DEMO_GATEWAY)[keyof typeof DEMO_GATEWAY]) {
    globalThis.location.hash = "#/instances/laptop-a";
    const api = new ManagerApi();
    api.gatewayDocuments["laptop-a"] = { ...doc, instance: "laptop-a" };
    renderApp(api);
    expect(await screen.findByRole("heading", { name: "laptop-a" })).toBeInTheDocument();
    const card = document.querySelector('[data-card="gateway"]');
    expect(card).not.toBeNull();
    await waitFor(() => expect(within(card as HTMLElement).queryByText("Reading…")).toBeNull());
    return { api, card: card as HTMLElement };
  }

  it("connected: the words carry the state, the subjects table has an accessible name, the Daemons rows read off · gateway configured", async () => {
    const { api, card } = await renderWith(DEMO_GATEWAY.connected);
    expect(within(card).getByText("connected · long-poll")).toBeInTheDocument();
    expect(within(card).getByText("laptop-a")).toBeInTheDocument();
    expect(within(card).getByRole("table", { name: "This instance's queue, by subject" })).toBeInTheDocument();
    expect(within(card).getByText("loop-github-octo-repo-15")).toBeInTheDocument();
    expect(within(card).getByText("reviewer")).toBeInTheDocument();
    expect(within(card).getByText(/ok · slack socket up · 2 ingresses running/)).toBeInTheDocument();
    // the dot is decorative: the state is readable without it
    const dots = card.querySelectorAll('[aria-hidden="true"]');
    expect(dots.length).toBeGreaterThan(0);
    const daemons = document.querySelector('[data-card="daemons"]') as HTMLElement;
    expect(within(daemons).getByText("off · gateway configured")).toBeInTheDocument();
    expect(within(daemons).queryByRole("button", { name: "start" })).toBeNull();
    expect(api.targeted.some(([method, instance]) => method === "gateway" && instance === "laptop-a")).toBe(true);
  });

  it("connecting: names the attempt and shows no queue", async () => {
    const { card } = await renderWith(DEMO_GATEWAY.connecting);
    expect(within(card).getByText("connecting · attempt 3")).toBeInTheDocument();
    expect(within(card).queryByRole("table")).toBeNull();
  });

  it("refused: says who holds the name and what this instance does about it", async () => {
    const { card } = await renderWith(DEMO_GATEWAY.refused);
    expect(within(card).getByText("refused · duplicate instance (409)")).toBeInTheDocument();
    expect(within(card).getByRole("alert").textContent).toMatch(/another process is already polling as/);
    expect(within(card).getByRole("alert").textContent).toMatch(/c0ffee42/);
  });

  it("unreachable: says it retries and does not fall back", async () => {
    const { card } = await renderWith(DEMO_GATEWAY.unreachable);
    expect(within(card).getByText("unreachable · retrying")).toBeInTheDocument();
    expect(within(card).getByRole("alert").textContent).toMatch(/not falling back/);
  });

  it("not configured: says the instance runs its own ingresses, and the Daemons rows keep their verbs", async () => {
    const { card } = await renderWith(DEMO_GATEWAY.none);
    expect(within(card).getByText("not configured")).toBeInTheDocument();
    expect(within(card).getByText(/runs its own webhook receiver, poller and Slack listener/)).toBeInTheDocument();
    const daemons = document.querySelector('[data-card="daemons"]') as HTMLElement;
    expect(within(daemons).queryByText("off · gateway configured")).toBeNull();
    expect(within(daemons).getByRole("button", { name: "start" })).toBeInTheDocument();
  });

  it("gatewayWords is the one vocabulary", () => {
    expect(gatewayWords({ configured: false, state: "off" })).toEqual({ words: "not configured", dot: "skipped" });
    expect(gatewayWords({ configured: true, state: "connected", mode: { pollIntervalSeconds: 5, longPollSeconds: 0 } }).words).toBe("connected · polling");
    expect(gatewayWords({ configured: true, state: "unreachable" }).dot).toBe("blocked");
    // issue-519: the gateway posting for this instance is one more state word
    expect(gatewayWords({ configured: true, state: "connected", mode: { pollIntervalSeconds: 5, longPollSeconds: 20 }, slackPosting: "on" }).words).toBe(
      "connected · long-poll · posting via gateway",
    );
    expect(gatewayWords({ configured: true, state: "connected", mode: { pollIntervalSeconds: 5, longPollSeconds: 20 }, slackPosting: "disabled" }).words).toBe(
      "connected · long-poll",
    );
  });
});
