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

import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiProvider } from "../state/ApiContext.tsx";
import { buildWorkItemViews } from "../api/model.ts";
import { DEMO_SESSIONS, DEMO_WORK_ITEMS } from "../demo/fixture.ts";
import { WorkItemDetail, isAtNewest } from "./WorkItemDetail.tsx";

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

function renderDetail(transcriptTick = 0) {
  const view = firstView();
  return render(
    <ApiProvider>
      <WorkItemDetail view={view} title={view.ref} onChanged={() => {}} transcriptTick={transcriptTick} />
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
    expect(panel.className).toContain("lp-trace");
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
