/**
 * The stream renderer and the chat bar (issue-230): tool calls collapsed to a
 * summary line with the paired result behind disclosure, no blank rows for
 * result/thinking/bookkeeping entries, and a chat bar that delivers to the
 * viewed ref — or says why it cannot.
 *
 * Plus the verbosity filter (issue-419): with **Verbose** off the stream keeps
 * the conversation and the trail keeps what a person is owed; with it on both
 * render exactly what they rendered before the switch existed.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { EventRecord, TranscriptEntry } from "../api/types.ts";
import { ApiProvider } from "../state/ApiContext.tsx";
import { ChatBar, EventTrail, TranscriptView, VERBOSE_LABEL } from "./Transcript.tsx";

beforeEach(() => {
  globalThis.localStorage.clear();
  globalThis.localStorage.setItem(
    "the-loop:settings:v1",
    JSON.stringify({ baseUrl: "http://127.0.0.1:8787", mode: "demo", pollSeconds: 0 }),
  );
});

const PAIRED: TranscriptEntry[] = [
  {
    type: "assistant",
    timestamp: "2026-08-12T10:00:05Z",
    message: {
      content: [
        { type: "text", text: "Running the suite." },
        { type: "tool_use", id: "t1", name: "Bash", input: { command: "pytest -q cli" } },
      ],
    },
  },
  {
    type: "user",
    message: {
      content: [{ type: "tool_result", tool_use_id: "t1", content: "1 failed, 41 passed", is_error: true }],
    },
  },
];

describe("TranscriptView", () => {
  it("collapses a tool call to its name and summary, result behind disclosure", () => {
    render(<TranscriptView entries={PAIRED} verbose />);
    expect(screen.getByText("Running the suite.")).toBeInTheDocument();
    // The collapsed line: name + the command, not raw JSON.
    expect(screen.getByText("Bash")).toBeInTheDocument();
    expect(screen.getByText("pytest -q cli")).toBeInTheDocument();
    // The paired result is in the details body, and the error is flagged.
    expect(screen.getByText("1 failed, 41 passed")).toBeInTheDocument();
    expect(screen.getByText("error")).toBeInTheDocument();
    // Collapsed by default: neither the group nor the call is open.
    expect(document.querySelector("details[data-fold='tools']")).not.toHaveAttribute("open");
    const details = document.querySelector("details[data-tool]");
    expect(details).not.toBeNull();
    expect(details).not.toHaveAttribute("open");
    // The result entry emitted no row of its own — one entry row total.
    expect(document.querySelectorAll("[data-entry]")).toHaveLength(1);
  });

  it("drops the tool groups when the switch is off, and keeps the prose", () => {
    render(<TranscriptView entries={PAIRED} />);
    expect(screen.getByText("Running the suite.")).toBeInTheDocument();
    expect(document.querySelector("[data-tools]")).toBeNull();
  });

  it("renders orphan results, thinking and bookkeeping as visible rows — never blank", () => {
    render(
      <TranscriptView
        verbose
        entries={[
          { type: "user", message: { content: [{ type: "tool_result", tool_use_id: "gone", content: "tail cut" }] } },
          { type: "assistant", message: { content: [{ type: "thinking", thinking: "Suspicious fixture." }] } },
          { type: "summary", summary: "Session compacted." },
        ]}
      />,
    );
    // The collapsed line and the disclosure body both carry the text.
    expect(screen.getAllByText("tail cut").length).toBeGreaterThan(0);
    expect(screen.getByText("thinking")).toBeInTheDocument();
    expect(screen.getAllByText("Suspicious fixture.").length).toBeGreaterThan(0);
    expect(screen.getByText("Session compacted.")).toBeInTheDocument();
    // Every row has visible content.
    for (const entry of document.querySelectorAll("[data-entry]")) {
      expect(entry.textContent?.trim()).not.toBe("");
    }
  });

  it("drops the empty meta rows and the tools-only turn when the switch is off", () => {
    const entries: TranscriptEntry[] = [
      { type: "system", timestamp: "2026-08-12T10:00:00Z" },
      { type: "summary", summary: "Context compacted — 14 earlier turns summarised." },
      {
        type: "assistant",
        timestamp: "2026-08-12T10:00:05Z",
        message: { content: [{ type: "tool_use", id: "t9", name: "Read", input: { file_path: "cli/app.py" } }] },
      },
      { type: "assistant", timestamp: "2026-08-12T10:00:09Z", message: { content: "Read the module." } },
      { malformed: '{"type":"assis' },
    ];
    render(<TranscriptView entries={entries} />);
    // Kept: the summary's text, the prose turn, the drifted line.
    expect(screen.getByText("Context compacted — 14 earlier turns summarised.")).toBeInTheDocument();
    expect(screen.getByText("Read the module.")).toBeInTheDocument();
    expect(screen.getByText('{"type":"assis')).toBeInTheDocument();
    // Dropped: the empty `system` row and the turn that was only a tool call.
    expect(document.querySelector("[data-entry='meta'][data-label='system']")).toBeNull();
    expect(screen.queryByText("Read")).not.toBeInTheDocument();
    expect(document.querySelectorAll("[data-entry]")).toHaveLength(3);

    // With the switch on, every one of them is back.
    render(<TranscriptView entries={entries} verbose />);
    expect(screen.getByText("Read")).toBeInTheDocument();
  });

  it("says how many rows are hidden rather than rendering an empty column", () => {
    render(
      <TranscriptView
        entries={[
          { type: "system", timestamp: "2026-08-12T10:00:00Z" },
          { type: "system", timestamp: "2026-08-12T10:00:01Z" },
        ]}
      />,
    );
    expect(screen.getByText(`2 rows hidden — turn on ${VERBOSE_LABEL} to see them`)).toBeInTheDocument();
    expect(document.querySelector("[data-entry]")).toBeNull();
  });

  it("counts one hidden row in the singular", () => {
    render(<TranscriptView entries={[{ type: "system", timestamp: "2026-08-12T10:00:00Z" }]} />);
    expect(screen.getByText(`1 row hidden — turn on ${VERBOSE_LABEL} to see it`)).toBeInTheDocument();
  });

  it("renders nothing of its own when the transcript holds no rows at all", () => {
    const { container } = render(<TranscriptView entries={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders attacker-shaped tool text as text, not markup", () => {
    render(
      <TranscriptView
        verbose
        entries={[
          {
            type: "user",
            message: {
              content: [{ type: "tool_result", tool_use_id: "x", content: '<img src=x onerror="alert(1)">' }],
            },
          },
        ]}
      />,
    );
    // Present as escaped text (summary + body), and no element was created.
    expect(screen.getAllByText('<img src=x onerror="alert(1)">').length).toBeGreaterThan(0);
    expect(document.querySelector("img")).toBeNull();
  });
});

const at = (minute: number, event: string, level: EventRecord["level"] = "info"): EventRecord => ({
  ts: `2026-08-12T10:${String(minute).padStart(2, "0")}:00Z`,
  event,
  level,
});

describe("EventTrail", () => {
  it("drops the plumbing and keeps what a person is owed", () => {
    render(
      <EventTrail
        events={[
          at(5, "bus.published"),
          at(4, "poll.comment_settled"),
          at(3, "reaction.added"),
          at(2, "graph.parked"),
          at(1, "dispatch.failed", "error"),
        ]}
        verbose={false}
      />,
    );
    expect(screen.getByText("graph.parked")).toBeInTheDocument();
    // An error survives the filter although `dispatch` is a hidden family.
    expect(screen.getByText("dispatch.failed")).toBeInTheDocument();
    expect(screen.queryByText("bus.published")).not.toBeInTheDocument();
    expect(screen.queryByText("poll.comment_settled")).not.toBeInTheDocument();
    expect(screen.queryByText("reaction.added")).not.toBeInTheDocument();
    expect(document.querySelectorAll("[data-entry='event']")).toHaveLength(2);
  });

  it("restores the whole trail when the switch is on", () => {
    render(<EventTrail events={[at(2, "bus.published"), at(1, "graph.parked")]} verbose />);
    expect(screen.getByText("bus.published")).toBeInTheDocument();
    expect(document.querySelectorAll("[data-entry='event']")).toHaveLength(2);
  });

  it("spends its row budget on what is visible, not on what was filtered out", () => {
    // 50 plumbing rows ahead of the one that matters: with the switch off the
    // limit must not be consumed by rows nobody sees.
    const noise = Array.from({ length: 50 }, (_, index) => at(index % 60, "poll.cycle"));
    render(<EventTrail events={[...noise, at(59, "graph.parked")]} verbose={false} limit={40} />);
    expect(screen.getByText("graph.parked")).toBeInTheDocument();
    expect(document.querySelectorAll("[data-entry='event']")).toHaveLength(1);
  });

  it("says how many bookkeeping events are hidden rather than rendering an empty column", () => {
    render(<EventTrail events={[at(2, "bus.published"), at(1, "poll.cycle")]} verbose={false} />);
    expect(screen.getByText(`2 bookkeeping events hidden — turn on ${VERBOSE_LABEL} to see them`)).toBeInTheDocument();
    expect(document.querySelector("[data-entry='event']")).toBeNull();
  });

  it("counts one hidden event in the singular", () => {
    render(<EventTrail events={[at(1, "poll.cycle")]} verbose={false} />);
    expect(screen.getByText(`1 bookkeeping event hidden — turn on ${VERBOSE_LABEL} to see it`)).toBeInTheDocument();
  });

  it("renders nothing of its own when there are no events at all", () => {
    const { container } = render(<EventTrail events={[]} verbose={false} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("ChatBar", () => {
  it("sends the text to the viewed ref and clears on success", async () => {
    const user = userEvent.setup();
    const onSent = vi.fn();
    render(
      <ApiProvider>
        <ChatBar refFor="github:octo/loop-lab#216" state="active" onSent={onSent} />
      </ApiProvider>,
    );
    const box = screen.getByRole("textbox", { name: /github:octo\/loop-lab#216/ });
    await user.type(box, "ship it");
    await user.click(screen.getByRole("button", { name: "Send" }));
    // The demo transport resolves the reply; the box clears and the owner is told.
    await vi.waitFor(() => expect(onSent).toHaveBeenCalled());
    expect(box).toHaveValue("");
  });

  it.each([
    ["paused", /paused/],
    ["closed", /closed/],
    ["none", /No session/],
  ] as const)("is disabled with the reason when the session is %s", (state, reason) => {
    render(
      <ApiProvider>
        <ChatBar refFor="github:octo/loop-lab#216" state={state} />
      </ApiProvider>,
    );
    const box = screen.getByRole("textbox");
    expect(box).toBeDisabled();
    expect(box).toHaveAttribute("placeholder", expect.stringMatching(reason));
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });
});
