/**
 * The Instances tab (issue-374, R5.3): a manager's fleet with its actions, a
 * worker's one row with the sentence saying why there is nothing to register,
 * the Register card's client-side grammar, and the service's refusal shown
 * verbatim.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { App } from "../App.tsx";
import type { TheLoopApi } from "../api/client.ts";
import { ApiProvider } from "../state/ApiContext.tsx";
import { CLOUD, HQ, LAPTOP, ManagerApi, managerDocument } from "../test/manager.ts";
import { fleetSummary, registerProblems } from "./Instances.tsx";

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
  globalThis.location.hash = "#/instances";
});

afterEach(() => {
  globalThis.location.hash = "#/";
});

/** Every validation message on the form, as one string to match against. */
const alerts = () => screen.getAllByRole("alert").map((el) => el.textContent).join("\n");

/** The table row for one instance, once the tab has settled. */
async function rowFor(name: string): Promise<HTMLElement> {
  await screen.findByRole("table", { name: "Instances" });
  const row = document.querySelector(`[data-instance-row="${name}"]`);
  if (!(row instanceof HTMLElement)) throw new Error(`no row for ${name}`);
  return row;
}

describe("the Instances tab on a worker (the demo fixture)", () => {
  it("shows the one row, no Register card, and says why", async () => {
    renderApp();

    const row = await rowFor("demo");
    expect(within(row).getByText("live")).toBeInTheDocument();
    expect(within(row).getByText("this instance")).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: "Manage" })).toHaveAttribute("href", "#/instances/demo");
    expect(within(row).queryByRole("button", { name: /unregister/i })).toBeNull();

    expect(screen.queryByLabelText(/^Name/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Register" })).toBeNull();
    expect(screen.getByText(/instance\.role: worker/)).toBeInTheDocument();
    expect(screen.getByText(/role worker/)).toBeInTheDocument();
  });
});

describe("the Instances tab on a manager", () => {
  it("lists every instance with its state in words, and the summary line", async () => {
    const api = new ManagerApi();
    renderApp(api);

    const cloud = await rowFor("cloud-1");
    expect(within(cloud).getByText("unreachable")).toBeInTheDocument();
    expect(within(cloud).getByText("connection refused")).toBeInTheDocument();
    expect(within(await rowFor("laptop-a")).getByText("live")).toBeInTheDocument();
    expect(within(await rowFor("laptop-a")).getByText("19.14.1")).toBeInTheDocument();
    expect(screen.getByText(/hq · role manager · this instance \+ 2 registered · 1 of 2 live/)).toBeInTheDocument();
    // The not-live banner names the member and its reason.
    expect(screen.getAllByRole("status").map((el) => el.textContent).join("\n")).toMatch(
      /One instance is not live: cloud-1 — connection refused/,
    );
    expect(fleetSummary(managerDocument([HQ]))).toMatch(/^hq · role manager · this instance \+ 0 registered · probed /);
    expect(fleetSummary({ role: "worker", name: "solo", instances: [HQ] })).toBe("solo · role worker");
  });

  it("offers Open only for a live row, Manage for every row, and no Unregister on the manager's own row", async () => {
    renderApp(new ManagerApi());

    const hq = await rowFor("hq");
    expect(within(hq).getByRole("link", { name: "Open" })).toHaveAttribute("href", "#/?instance=hq");
    expect(within(hq).getByRole("link", { name: "Manage" })).toHaveAttribute("href", "#/instances/hq");
    expect(within(hq).queryByRole("button", { name: /unregister/i })).toBeNull();

    const laptop = await rowFor("laptop-a");
    expect(within(laptop).getByRole("link", { name: "Open" })).toHaveAttribute("href", "#/?instance=laptop-a");
    expect(within(laptop).getByRole("button", { name: /unregister/i })).toBeInTheDocument();

    const cloud = await rowFor("cloud-1");
    const open = within(cloud).getByRole("button", { name: "Open" });
    expect(open).toBeDisabled();
    expect(open).toHaveAttribute("title", "not live");
    expect(within(cloud).getByRole("link", { name: "Manage" })).toHaveAttribute("href", "#/instances/cloud-1");
  });

  it("unregisters after a confirm step, and the row leaves the table", async () => {
    const user = userEvent.setup();
    const api = new ManagerApi();
    renderApp(api);

    const cloud = await rowFor("cloud-1");
    await user.click(within(cloud).getByRole("button", { name: /unregister…/i }));
    expect(api.writes).toEqual([]);
    await user.click(within(cloud).getByRole("button", { name: /unregister cloud-1 for good/i }));

    await waitFor(() => {
      expect(document.querySelector('[data-instance-row="cloud-1"]')).toBeNull();
    });
    expect(api.writes).toEqual([{ verb: "unregister", name: "cloud-1" }]);
    expect(await screen.findByText(/Unregistered cloud-1/)).toBeInTheDocument();
  });

  it("registers a member and shows it unreachable until it answers", async () => {
    const user = userEvent.setup();
    const api = new ManagerApi();
    renderApp(api);
    await rowFor("hq");

    await user.type(screen.getByLabelText(/^Name/), "cloud-2");
    await user.type(screen.getByLabelText(/^URL/), "http://10.0.0.10:4114/");
    await user.click(screen.getByRole("button", { name: "Register" }));

    const added = await rowFor("cloud-2");
    expect(within(added).getByText("unreachable")).toBeInTheDocument();
    expect(api.writes).toEqual([{ verb: "register", name: "cloud-2", url: "http://10.0.0.10:4114" }]);
  });

  it("validates the name grammar, uniqueness and the URL scheme before the service sees them", async () => {
    const user = userEvent.setup();
    renderApp(new ManagerApi());
    await rowFor("hq");

    const button = screen.getByRole("button", { name: "Register" });
    expect(button).toBeDisabled();

    await user.type(screen.getByLabelText(/^Name/), "Cloud_2");
    await user.type(screen.getByLabelText(/^URL/), "ftp://x");
    expect(alerts()).toMatch(/Name must fit/);
    expect(alerts()).toMatch(/URL must start with http/);
    expect(button).toBeDisabled();

    await user.clear(screen.getByLabelText(/^Name/));
    await user.type(screen.getByLabelText(/^Name/), "laptop-a");
    expect(alerts()).toMatch(/laptop-a is already registered/);
    expect(button).toBeDisabled();

    expect(registerProblems("cloud-2", "https://x", ["hq"])).toEqual({});
    expect(registerProblems("-bad", "http://x", [])).toMatchObject({ name: expect.stringMatching(/must fit/) });
    expect(registerProblems("hq", "http://x", ["hq"])).toMatchObject({ name: "hq is already registered." });
    expect(registerProblems("ok", "10.0.0.1:4114", [])).toMatchObject({ url: expect.stringMatching(/http/) });
  });

  it("shows the service's 400 verbatim when it refuses", async () => {
    const user = userEvent.setup();
    const api = new ManagerApi(managerDocument([HQ, LAPTOP, CLOUD]));
    // A row the client check does not know about yet — registered elsewhere a
    // moment ago — so the refusal comes from the service, not the form.
    renderApp(api);
    await rowFor("hq");
    api.document = managerDocument([HQ, LAPTOP, CLOUD, { ...LAPTOP, name: "ci-box" }]);

    await user.type(screen.getByLabelText(/^Name/), "ci-box");
    await user.type(screen.getByLabelText(/^URL/), "http://ci:4114");
    await user.click(screen.getByRole("button", { name: "Register" }));

    expect(await screen.findByText(/name "ci-box" is already registered/)).toBeInTheDocument();
  });
});
