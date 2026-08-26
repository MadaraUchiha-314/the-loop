/**
 * The session stream, rendered the way claude.ai/code renders its own file
 * (issue-230): user and assistant text expanded, everything mechanical —
 * tool calls with their results folded in, thinking, harness bookkeeping —
 * collapsed to one line each behind native `<details>` disclosure.
 *
 * Also the chat bar: the reply box generalized from the question card
 * (issue-208) to any viewed session. It posts to `POST /api/v1/sessions/reply`
 * with the viewed ref — the work item's for the outer loop, the PR's for an
 * inner loop — which the service resolves to that endpoint's tmux pane.
 */

import { useState } from "react";

import { ApiError } from "../api/client.ts";
import { timeOf, transcriptThread, type SessionState, type ThreadRow, type ToolCallView } from "../api/model.ts";
import type { TranscriptEntry } from "../api/types.ts";
import { useApi } from "../state/ApiContext.tsx";

const ROW_CLASS: Record<ThreadRow["kind"], string> = {
  user: "",
  assistant: "accent",
  "tool result": "",
  meta: "dim",
  malformed: "hot",
};

/** The transcript entries as the readable stream — rows via `transcriptThread`. */
export function TranscriptView({ entries }: { entries: TranscriptEntry[] }) {
  return (
    <>
      {transcriptThread(entries).map((thread, index) => (
        <ThreadRowView key={`${thread.time}-${index}`} row={thread} />
      ))}
    </>
  );
}

/** The speaker names the design gives the two conversational rows. */
const ROW_LABEL: Partial<Record<ThreadRow["kind"], string>> = {
  user: "You",
  assistant: "the-loop",
};

function ThreadRowView({ row }: { row: ThreadRow }) {
  return (
    <div className="lp-trace-entry">
      <div className={`lp-trace-kind ${ROW_CLASS[row.kind]}`.trim()}>
        {row.kind === "meta" ? (row.label || "meta") : (ROW_LABEL[row.kind] ?? row.kind)}
        {row.time ? <div className="lp-trace-ts">{timeOf(row.time)}</div> : null}
      </div>
      <div className="lp-trace-main">
        {row.thinking ? (
          <details className="lp-fold lp-fold-thinking">
            <summary>
              <span className="lp-fold-name">thinking</span>
              <span className="lp-fold-detail">{firstLine(row.thinking)}</span>
            </summary>
            <pre className="lp-fold-body">{row.thinking}</pre>
          </details>
        ) : null}
        {row.text ? (
          row.kind === "tool result" ? (
            <details className="lp-fold">
              <summary>
                <span className="lp-fold-name">output</span>
                <span className="lp-fold-detail">{firstLine(row.text)}</span>
              </summary>
              <pre className="lp-fold-body">{row.text}</pre>
            </details>
          ) : (
            <div className={`lp-trace-text ${row.kind === "meta" || row.kind === "malformed" ? "lp-trace-meta" : ""}`.trim()}>
              {row.text}
            </div>
          )
        ) : null}
        {row.kind === "meta" && !row.text ? <div className="lp-trace-meta">({row.label || "entry"})</div> : null}
        {row.tools.length > 0 ? (
          <div className="lp-trace-tools">
            {row.tools.map((tool, index) => (
              <ToolCall key={`${tool.id || tool.name}-${index}`} tool={tool} />
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

/**
 * One tool call, collapsed by default: the name and the one-line summary of
 * its input; expanded, the full input and the result that answered it.
 */
function ToolCall({ tool }: { tool: ToolCallView }) {
  return (
    <details className="lp-fold lp-fold-tool">
      <summary>
        <span className="lp-fold-name">{tool.name}</span>
        <span className="lp-fold-detail">{firstLine(tool.summary)}</span>
        {tool.isError ? <span className="tag tag-neutral lp-fold-error">error</span> : null}
      </summary>
      {tool.input ? <pre className="lp-fold-body">{tool.input}</pre> : null}
      <pre className="lp-fold-body lp-fold-result">{tool.result || "(no result in the served tail)"}</pre>
    </details>
  );
}

function firstLine(text: string): string {
  const line = text.split("\n", 1)[0] ?? "";
  return line.length > 160 ? `${line.slice(0, 160)}…` : line;
}

/** Why the bar is disabled, per session state — `""` means it can send. */
function chatBlocked(state: SessionState): string {
  if (state === "active") return "";
  if (state === "paused") return "The session is paused — resume it first; delivery is held.";
  if (state === "closed") return "The session is closed; there is no pane to deliver into.";
  return "No session is registered for this ref on the service's machine.";
}

/**
 * The chat bar. `ref` is the viewed session's — outer or inner — and the
 * service resolves it to that endpoint's pane (fail-closed: it never spawns
 * one to answer, so a refused send renders the server's reason).
 */
export function ChatBar({
  refFor,
  state,
  onSent,
}: {
  refFor: string;
  state: SessionState;
  onSent?: () => void;
}) {
  const { api } = useApi();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const blocked = chatBlocked(state);

  async function send(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      await api.replySession(refFor, text);
      setText("");
      onSent?.();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.advice : String(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="lp-chat">
      <div className="lp-chat-inner">
        {error ? (
          <div className="lp-chat-error" role="alert">
            {error}
          </div>
        ) : null}
        <div className="lp-chat-row">
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder={blocked || `Message the session — pasted into its tmux pane`}
            aria-label={`Message the session for ${refFor}`}
            disabled={busy || blocked !== ""}
            rows={2}
            onKeyDown={(event) => {
              if (event.key === "Enter" && (event.metaKey || event.ctrlKey) && text.trim() && !blocked) void send();
            }}
          />
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy || blocked !== "" || !text.trim()}
            title={blocked || undefined}
            onClick={() => void send()}
          >
            {busy ? "Sending…" : "Send"}
          </button>
        </div>
        {blocked ? null : (
          <div className="lp-chat-hint">
            Delivered into the session&rsquo;s tmux pane (bracketed paste, then Enter) and recorded on the ticket
            · ⌘⏎ to send
          </div>
        )}
      </div>
    </div>
  );
}
