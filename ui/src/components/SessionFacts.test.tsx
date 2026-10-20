/**
 * The session panel's content, relocated (issue-511, Option C): the facts
 * behind the header's **Session details** disclosure, the verbs in the header
 * actions. These assert the inventory's C column — what the popover shows in
 * full, what left for good (the current node, the tmux target row, the
 * ticket's repo and number), that the one copy control is the attach
 * command's, that the verbs still target the work item's session from a PR
 * selection, and abuse case 2: every row renders from the typed record.
 */

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { buildWorkItemViews, transcriptPath, type WorkItemView } from "../api/model.ts";
import { DemoApi } from "../demo/client.ts";
import { DEMO_ATTENTION, DEMO_INNER_GRAPHS, DEMO_OUTER_GRAPHS, DEMO_SESSIONS, DEMO_WORK_ITEMS } from "../demo/fixture.ts";
import { ApiProvider } from "../state/ApiContext.tsx";
import { WorkItemDetail } from "../views/WorkItemDetail.tsx";
import type { Chrome } from "./HeaderBar.tsx";

const chrome: Chrome = { theme: "light", onToggleTheme: () => {}, sidebarOpen: true, onOpenSidebar: () => {} };

function viewOf(shortRef: string): WorkItemView {
  const views = buildWorkItemViews({
    workItems: DEMO_WORK_ITEMS,
    sessions: DEMO_SESSIONS,
    attention: DEMO_ATTENTION,
    graphs: { outer: DEMO_OUTER_GRAPHS, inner: DEMO_INNER_GRAPHS },
  });
  const view = views.find((candidate) => candidate.shortRef === shortRef);
  if (!view) throw new Error(`no ${shortRef} in the fixture`);
  return view;
}

function renderDetail(view: WorkItemView, traceRef?: string, api = new DemoApi()) {
  const onChanged = vi.fn();
  render(
    <ApiProvider api={api}>
      <WorkItemDetail view={view} title={view.ref} onChanged={onChanged} chrome={chrome} traceRef={traceRef} />
    </ApiProvider>,
  );
  return { onChanged };
}

/** The header's Session details disclosure and its body. */
function details(): { disclosure: HTMLDetailsElement; body: HTMLElement } {
  const summary = screen.getByText((_, el) => el?.tagName === "SUMMARY" && el.getAttribute("aria-label") === "Session details");
  const disclosure = summary.closest("details") as HTMLDetailsElement;
  const body = disclosure.querySelector("[data-session-facts]") as HTMLElement;
  return { disclosure, body };
}

beforeEach(() => {
  vi.stubGlobal("EventSource", undefined);
  globalThis.localStorage?.clear();
});
afterEach(() => vi.unstubAllGlobals());

describe("Session details (issue-511 R2.3, R3.3, R6.1)", () => {
  it("Scenario: Session details is a closed details element whose body shows harness, status, started, session id, transcript path, cwd, the attach command and Open on GitHub in full", async () => {
    const view = viewOf("loop-lab#214");
    renderDetail(view);
    await screen.findByRole("log", { name: /session transcript/i });

    const { disclosure, body } = details();
    expect(disclosure.open).toBe(false);
    expect(body).not.toBeNull();

    const session = view.session!;
    const row = (key: string) => within(body).getByText(key).nextElementSibling as HTMLElement;
    expect(row("harness").textContent).toBe(session.harness);
    expect(row("status").textContent).toMatch(/active/);
    expect(within(body).getByText("started")).toBeInTheDocument();
    // In full, as the typed record carries them — no abbreviation (critic C5).
    expect(row("session id").textContent).toBe(session.harnessSessionId);
    expect(row("transcript").textContent).toBe(transcriptPath(session));
    expect(row("cwd").textContent).toBe(session.cwd);
    expect(within(body).getByRole("button", { name: /tmux attach -t/ })).toHaveTextContent(`tmux attach -t ${view.tmuxTarget}`);
    expect(within(body).getByRole("link", { name: /Open on GitHub/ })).toHaveAttribute("href", view.url);

    // Gone for good (rows 51, 55, 58, 61): drawn once elsewhere, or not at all.
    for (const key of ["current node", "target", "repo", "number", "instance"]) {
      expect(within(body).queryByText(key)).toBeNull();
    }
    // The one copy control in the popover is the attach command's (D6).
    expect(within(body).getAllByRole("button")).toHaveLength(1);
  });

  it("names a pull request's section and shows its inner loop", async () => {
    const view = viewOf("loop-lab#214");
    renderDetail(view, "github:octo/loop-lab#216");
    await screen.findByRole("log", { name: /session transcript/i });
    const { body } = details();
    expect(within(body).getByText("Pull request")).toBeInTheDocument();
    expect(within(body).getByText("inner loop")).toBeInTheDocument();
    expect(within(body).queryByText("Ticket")).toBeNull();
  });

  it("abuse case 2: every row renders from the typed record — markup in a path or an id is text, never an element", async () => {
    const base = viewOf("loop-lab#214");
    const hostile = {
      ...base.session!,
      cwd: "<b>x</b>/work",
      harnessSessionId: '<img src=x onerror="alert(1)">',
      harness: "**claude**",
    };
    const view: WorkItemView = { ...base, session: hostile, tmuxTarget: "<i>t</i>" };
    renderDetail(view);
    await screen.findByRole("log", { name: /session transcript/i });

    const { body } = details();
    const row = (key: string) => within(body).getByText(key).nextElementSibling as HTMLElement;
    expect(row("cwd").textContent).toBe("<b>x</b>/work");
    expect(row("session id").textContent).toBe('<img src=x onerror="alert(1)">');
    expect(row("harness").textContent).toBe("**claude**");
    expect(within(body).getByRole("button", { name: /tmux attach -t/ }).textContent).toBe("tmux attach -t <i>t</i>");
    expect(body.querySelector("b, i, img, strong")).toBeNull();
  });
});

describe("the verbs in the header (issue-511 R3.3, R3.4, R5.2)", () => {
  it("Scenario: pause, resume, stop and start render in the header and call controlSession with the work item's ref", async () => {
    const user = userEvent.setup();
    const api = new DemoApi();
    const control = vi.spyOn(api, "controlSession");
    const view = viewOf("loop-lab#214");
    const { onChanged } = renderDetail(view, undefined, api);
    await screen.findByRole("log", { name: /session transcript/i });

    const header = screen.getByRole("banner");
    const verbs = within(header).getByRole("group", { name: "Controls" });
    expect(within(verbs).getByRole("button", { name: "pause" })).toBeInTheDocument();
    expect(within(verbs).getByRole("button", { name: "stop" })).toBeInTheDocument();
    expect(within(verbs).queryByText("work item")).toBeNull();

    await user.click(within(verbs).getByRole("button", { name: "pause" }));
    await vi.waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(control).toHaveBeenCalledWith(view.ref, "pause", true, view.instance);
  });

  it("Scenario: with a PR session selected the verbs carry a visible work item label and still target the work item", async () => {
    const user = userEvent.setup();
    const api = new DemoApi();
    const control = vi.spyOn(api, "controlSession");
    const view = viewOf("loop-lab#214");
    const { onChanged } = renderDetail(view, "github:octo/loop-lab#216", api);
    await screen.findByRole("log", { name: /session transcript/i });

    const verbs = within(screen.getByRole("banner")).getByRole("group", { name: "Controls · work item session" });
    expect(within(verbs).getByText("work item")).toBeInTheDocument();
    await user.click(within(verbs).getByRole("button", { name: "stop" }));
    await vi.waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(control).toHaveBeenCalledWith(view.ref, "stop", true, view.instance);
  });

  it("offers start for an item with no session, and says so", async () => {
    const view = viewOf("loop-lab#187");
    renderDetail(view);
    await screen.findByText(/No transcript served/);
    const verbs = within(screen.getByRole("banner")).getByRole("group", { name: "Controls" });
    expect(within(verbs).getByRole("button", { name: "start" })).toBeInTheDocument();
  });

  it("Scenario: copy ref and copy attach command write the clipboard", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    const view = viewOf("loop-lab#214");
    renderDetail(view);
    await screen.findByRole("log", { name: /session transcript/i });

    await user.click(screen.getByRole("button", { name: "Copy work item ref" }));
    expect(writeText).toHaveBeenCalledWith(view.ref);
    const { disclosure, body } = details();
    disclosure.open = true;
    await user.click(within(body).getByRole("button", { name: /tmux attach -t/ }));
    expect(writeText).toHaveBeenCalledWith(`tmux attach -t ${view.tmuxTarget}`);
  });
});
