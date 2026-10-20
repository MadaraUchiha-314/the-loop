/**
 * The trace panel and the chat bar (issue-239, Requirement 6).
 *
 * These assert the half of R6 that is **behaviour**: the panel is a scroll
 * container with an accessible name, the chat bar is beside it rather than a
 * transcript's length below it, and the rule that decides whether an arriving
 * entry may move the scroll position.
 *
 * They do not assert the half that is **rendering**. jsdom applies no
 * stylesheet, so `max-height`, `overflow-y` and `position: sticky` are inert
 * here and `scrollHeight` is whatever the test sets it to. That half is a
 * browser pass — see `docs/specs/issue-239/testing-plan.md` T6, and the note in
 * its Verification results about why it did not run in this session.
 */

import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiProvider } from "../state/ApiContext.tsx";
import { buildWorkItemViews } from "../api/model.ts";
import { DEMO_ATTENTION, DEMO_INNER_GRAPHS, DEMO_OUTER_GRAPHS, DEMO_SESSIONS, DEMO_WORK_ITEMS } from "../demo/fixture.ts";
import type { Chrome } from "../components/HeaderBar.tsx";
import { WorkItemDetail, isAtNewest, railNote } from "./WorkItemDetail.tsx";

const chrome: Chrome = { theme: "light", onToggleTheme: () => {}, sidebarOpen: true, onOpenSidebar: () => {} };

/** The first fixture item that has a session, so the trace panel has a subject. */
function firstView() {
  const views = buildWorkItemViews({
    workItems: DEMO_WORK_ITEMS,
    sessions: DEMO_SESSIONS,
    attention: [],
  });
  const view = views.find((candidate) => candidate.session !== null);
  if (!view) throw new Error("the fixture has no session to view");
  return view;
}

/** One fixture item by short ref, with its graphs and attention joined. */
function viewOf(shortRef: string) {
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

function renderDetail(transcriptTick = 0, view = firstView(), traceRef?: string) {
  return render(
    <ApiProvider>
      <WorkItemDetail view={view} title={view.ref} onChanged={() => {}} transcriptTick={transcriptTick} chrome={chrome} traceRef={traceRef} />
    </ApiProvider>,
  );
}

describe("the work-item detail page", () => {
  beforeEach(() => {
    // A live browser would open a real EventSource here; the fixture's stream is
    // enough to mount, and these tests are about layout and scrolling.
    vi.stubGlobal("EventSource", undefined);
    globalThis.localStorage?.clear();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("gives the trace panel an accessible name and makes it focusable (R6.2, a11y)", async () => {
    renderDetail();
    const panel = await screen.findByRole("log", { name: /session transcript/i });
    expect(panel).toHaveAttribute("tabindex", "0");
    expect(panel).toHaveAttribute("data-trace");
  });

  it("renders the chat bar in the same view as the trace (R6.1)", async () => {
    renderDetail();
    // Present in the document without any scrolling having happened: the bar is
    // a sibling of the panel, not something below a page-length transcript.
    expect(await screen.findByRole("textbox", { name: /message the session/i })).toBeInTheDocument();
  });

  /**
   * R6.3/R6.4 as logic. The effect that acts on this reads it **before** the
   * render that appends — by the time a DOM-keyed effect runs, the new entry has
   * already grown `scrollHeight` and every reader would look un-pinned — so the
   * ordering is browser-verified and the rule is asserted here.
   */
  describe("isAtNewest", () => {
    it("is true at the bottom, and stays true a few pixels short of exact", () => {
      expect(isAtNewest({ scrollHeight: 1000, scrollTop: 600, clientHeight: 400 })).toBe(true);
      expect(isAtNewest({ scrollHeight: 1000, scrollTop: 590, clientHeight: 400 })).toBe(true);
    });

    it("is false for a reader who scrolled back to read history", () => {
      expect(isAtNewest({ scrollHeight: 1000, scrollTop: 120, clientHeight: 400 })).toBe(false);
    });

    it("is true for a panel too short to scroll at all", () => {
      expect(isAtNewest({ scrollHeight: 300, scrollTop: 0, clientHeight: 300 })).toBe(true);
    });
  });
});

describe("railNote (issue-511 R2.1, R2.5)", () => {
  it("says a parked item awaits a human without naming the node — the phase chip is the one statement", () => {
    const view = { ...firstView(), parked: { node: "requirements-approval", reason: "approve the requirements", since: "2026-10-15T09:00:00Z" } };
    expect(railNote(view)).toBe("parked — awaiting a human");
    expect(railNote(view)).not.toContain("requirements-approval");
  });

  it("is empty for an item that needs nothing", () => {
    expect(railNote({ ...firstView(), parked: null, attention: [] })).toBe("");
  });
});

describe("the session tab bar (issue-511 R2.6, R3.3)", () => {
  beforeEach(() => {
    vi.stubGlobal("EventSource", undefined);
    globalThis.localStorage?.clear();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("Scenario: the session tab bar renders only when the item has more than one session", async () => {
    // #223 is the ad-hoc item: one session, no pull request loop.
    renderDetail(0, viewOf("loop-lab#223"));
    await screen.findByRole("log", { name: /session transcript/i });
    expect(screen.queryByRole("navigation", { name: "Sessions" })).toBeNull();
  });

  it("Scenario: the tab bar carries no session tally", async () => {
    renderDetail(0, viewOf("loop-lab#214"));
    const tabs = await screen.findByRole("navigation", { name: "Sessions" });
    expect(within(tabs).getByRole("link", { name: "loop-lab#216" })).toBeInTheDocument();
    expect(within(tabs).getByRole("link", { name: "loop-docs#47" })).toBeInTheDocument();
    expect(tabs.textContent).not.toMatch(/sessions? ·/);
    expect(tabs.textContent).not.toMatch(/work item loop ·/);
  });
});

describe("the trace head (issue-511 R3.2)", () => {
  beforeEach(() => {
    vi.stubGlobal("EventSource", undefined);
    globalThis.localStorage?.clear();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("reads Harness trace with the Verbose switch and no harness name — the Session details carry it", async () => {
    renderDetail(0, viewOf("loop-lab#214"));
    const head = (await screen.findByText("Harness trace")).closest("div");
    expect(head?.textContent).not.toContain("claude");
    const panel = screen.getByRole("log", { name: /session transcript/i });
    expect(panel).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("switch", { name: "Verbose" })).toBeInTheDocument();
  });
});
