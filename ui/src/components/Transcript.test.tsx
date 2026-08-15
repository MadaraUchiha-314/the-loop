/**
 * The stream renderer and the chat bar (issue-230): tool calls collapsed to a
 * summary line with the paired result behind disclosure, no blank rows for
 * result/thinking/bookkeeping entries, and a chat bar that delivers to the
 * viewed ref — or says why it cannot.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { TranscriptEntry } from "../api/types.ts";
import { ApiProvider } from "../state/ApiContext.tsx";
import { ChatBar, TranscriptView } from "./Transcript.tsx";

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
    render(<TranscriptView entries={PAIRED} />);
    expect(screen.getByText("Running the suite.")).toBeInTheDocument();
    // The collapsed line: name + the command, not raw JSON.
    expect(screen.getByText("Bash")).toBeInTheDocument();
    expect(screen.getByText("pytest -q cli")).toBeInTheDocument();
    // The paired result is in the details body, and the error is flagged.
    expect(screen.getByText("1 failed, 41 passed")).toBeInTheDocument();
    expect(screen.getByText("error")).toBeInTheDocument();
    // Collapsed by default: the details element is not open.
    const details = document.querySelector("details.lp-fold-tool");
    expect(details).not.toBeNull();
    expect(details).not.toHaveAttribute("open");
    // The result entry emitted no row of its own — one entry row total.
    expect(document.querySelectorAll(".lp-trace-entry")).toHaveLength(1);
  });

  it("renders orphan results, thinking and bookkeeping as visible rows — never blank", () => {
    render(
      <TranscriptView
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
    // Every row has visible content in its main column.
    for (const main of document.querySelectorAll(".lp-trace-main")) {
      expect(main.textContent?.trim()).not.toBe("");
    }
  });

  it("renders attacker-shaped tool text as text, not markup", () => {
    render(
      <TranscriptView
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
