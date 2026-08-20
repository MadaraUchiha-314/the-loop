/**
 * The Standing screen against the demo transport (issue-277).
 *
 * The demo client models the service's refusals as well as its successes, so
 * these are behaviour tests rather than render checks: what the operator can do
 * to a declared session differs from what they can do to a created one, and
 * that difference is the screen's whole reason to exist.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { App } from "../App.tsx";
import { ApiProvider } from "../state/ApiContext.tsx";

function renderApp() {
  return render(
    <ApiProvider>
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
  globalThis.location.hash = "#/standing";
});

afterEach(() => {
  globalThis.location.hash = "#/";
});

/** The card for one session, once the screen has settled. */
async function card(name: string): Promise<HTMLElement> {
  const heading = await screen.findByRole("heading", { name, level: 3 }, { timeout: 4000 });
  const element = heading.closest(".lp-standing-card");
  if (!(element instanceof HTMLElement)) throw new Error(`no card for ${name}`);
  return element;
}

describe("the Standing screen, on demo data", () => {
  it("lists both kinds and says which is which", async () => {
    renderApp();

    const declared = await card("supervisor");
    expect(within(declared).getByText("declared in config")).toBeInTheDocument();
    expect(within(declared).getByText("loop-standing-supervisor")).toBeInTheDocument();

    const created = await card("triage");
    expect(within(created).getByText("created here")).toBeInTheDocument();
  });

  it("offers delete only for a created session", async () => {
    renderApp();

    const created = await card("triage");
    expect(within(created).getByRole("button", { name: /delete/i })).toBeInTheDocument();

    const declared = await card("supervisor");
    // A button whose only outcome is the service's refusal is worse than none:
    // `the-loop start` would recreate a declared session's record.
    expect(within(declared).queryByRole("button", { name: /delete/i })).toBeNull();
  });

  it("creates a session and shows it on the board", async () => {
    const user = userEvent.setup();
    renderApp();
    await card("supervisor");

    await user.click(screen.getByRole("button", { name: /create a standing session/i }));
    await user.type(screen.getByLabelText("Name"), "release-watch");
    await user.type(screen.getByLabelText("Brief"), "Watch the release.");
    await user.click(screen.getByRole("button", { name: /create and start/i }));

    const created = await card("release-watch");
    expect(within(created).getByText("created here")).toBeInTheDocument();
    expect(within(created).getByText("loop-standing-release-watch")).toBeInTheDocument();
  });

  it("refuses an invalid name before it reaches the service", async () => {
    const user = userEvent.setup();
    renderApp();
    await card("supervisor");

    await user.click(screen.getByRole("button", { name: /create a standing session/i }));
    await user.type(screen.getByLabelText("Name"), "Release Watch");

    // The same expression the schema and the core enforce, so a typo is a
    // disabled button rather than a round-trip refusal.
    expect(screen.getByRole("button", { name: /create and start/i })).toBeDisabled();
  });

  it("deletes a created session and it leaves the board", async () => {
    const user = userEvent.setup();
    renderApp();

    const created = await card("triage");
    await user.click(within(created).getByRole("button", { name: /delete…/i }));
    await user.click(await screen.findByRole("button", { name: /delete triage for good/i }));

    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: "triage", level: 3 })).toBeNull();
    });
    // …and the one it was not asked to touch is untouched.
    expect(await screen.findByRole("heading", { name: "supervisor", level: 3 })).toBeInTheDocument();
  });

  it("sends a message into a running session, and cannot into a stopped one", async () => {
    const user = userEvent.setup();
    renderApp();

    const stopped = await card("triage");
    expect(within(stopped).getByRole("button", { name: "Send" })).toBeDisabled();

    const running = await card("supervisor");
    await user.type(within(running).getByLabelText(/message supervisor/i), "what is stuck?");
    await user.click(within(running).getByRole("button", { name: "Send" }));

    expect(await screen.findByText(/delivered into supervisor/i)).toBeInTheDocument();
  });

  it("starts a stopped session", async () => {
    const user = userEvent.setup();
    renderApp();

    const stopped = await card("triage");
    await user.click(within(stopped).getByRole("button", { name: "Start" }));

    await waitFor(async () => {
      expect(within(await card("triage")).getByRole("button", { name: "Stop" })).toBeInTheDocument();
    });
  });

  it("shows the service's own sentence when it refuses", async () => {
    const user = userEvent.setup();
    renderApp();
    await card("supervisor");

    // A name the fixture already holds: the demo refuses exactly as the
    // service does, and the screen quotes it rather than re-wording it.
    await user.click(screen.getByRole("button", { name: /create a standing session/i }));
    await user.type(screen.getByLabelText("Name"), "supervisor");
    await user.click(screen.getByRole("button", { name: /create and start/i }));

    expect(await screen.findByText(/already exists/i)).toBeInTheDocument();
  });
});
