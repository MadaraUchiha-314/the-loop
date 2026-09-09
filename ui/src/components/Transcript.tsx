/**
 * The harness trace and the composer, drawn the design's way (issue-327).
 *
 * `transcriptThread` (issue-230) still projects the harness's JSONL into rows;
 * this file gives each row the prototype's idiom: agent turns as prose with
 * `**refs**` and `` `chips` `` rendered inline, human replies as right-aligned
 * bubbles, node moves and bookkeeping as one-line meta rows, tool calls and
 * thinking behind **Used n tools** / **thinking** disclosures — native
 * `<details>`, collapsed by default, so nothing renders blank and everything
 * opens from the keyboard. A **Tool calls** switch removes the tool groups.
 *
 * The composer is the chat bar (issue-208/230): it posts to
 * `POST /api/v1/sessions/reply` with the viewed ref — the work item's for the
 * outer loop, the PR's for an inner loop — and says why when that session
 * cannot receive.
 */

import { useState, type KeyboardEvent, type ReactNode } from "react";

import { ApiError } from "../api/client.ts";
import { timeOf, transcriptThread, type SessionState, type ThreadRow, type ToolCallView } from "../api/model.ts";
import type { EventRecord, TranscriptEntry } from "../api/types.ts";
import { describeEvent } from "../api/model.ts";
import { useApi } from "../state/ApiContext.tsx";
import { BotIcon, BrainIcon, ChevronRightIcon, CircleArrowRightIcon, FileTextIcon, SendHorizontalIcon, TerminalIcon, WrenchIcon } from "./Icons.tsx";
import { renderInline } from "./primitives.tsx";

/** The transcript as the reading column; `showTools=false` drops the tool groups. */
export function TranscriptView({ entries, showTools = true }: { entries: TranscriptEntry[]; showTools?: boolean }) {
  return (
    <>
      {transcriptThread(entries).map((row, index) => (
        <ThreadRowView key={`${row.time}-${index}`} row={row} showTools={showTools} />
      ))}
    </>
  );
}

/** A one-line meta row: an icon, a mono label, a hairline, the time at the right. */
export function MetaLine({
  icon,
  label,
  detail,
  time,
  tone = "",
  children,
}: {
  icon?: ReactNode;
  label: string;
  detail?: string | undefined;
  time?: string | undefined;
  tone?: string;
  children?: ReactNode;
}) {
  return (
    <div className={`flex items-center gap-2 text-xs text-muted-foreground ${tone}`.trim()}>
      {icon ?? <CircleArrowRightIcon className="h-3.5 w-3.5 text-state-done" />}
      <span className="shrink-0 font-mono">{label}</span>
      {detail ? <span className="min-w-0 truncate font-mono text-foreground" title={detail}>{detail}</span> : null}
      {children}
      <span className="h-px flex-1 bg-border" aria-hidden="true" />
      {time ? <span className="shrink-0 font-mono">{time}</span> : null}
    </div>
  );
}

function ThreadRowView({ row, showTools }: { row: ThreadRow; showTools: boolean }) {
  const time = row.time ? timeOf(row.time) : "";
  const hasTools = row.tools.length > 0 && showTools;

  if (row.kind === "user") {
    return (
      <div className="flex flex-col items-end gap-1" data-entry="user">
        {row.text ? (
          <div className="max-w-[85%] whitespace-pre-wrap rounded-xl rounded-br-sm bg-primary px-3.5 py-2 text-sm text-primary-foreground">
            {row.text}
          </div>
        ) : null}
        {time ? <span className="font-mono text-[0.68rem] text-muted-foreground">{time}</span> : null}
      </div>
    );
  }

  if (row.kind === "tool result") {
    return (
      <div className="text-xs" data-entry="tool-result">
        <FoldGroup icon={<FileTextIcon className="h-3.5 w-3.5" />} label="output" detail={firstLine(row.text)}>
          <pre className="mt-1.5 ml-1 overflow-x-auto whitespace-pre-wrap border-l border-border pl-3 font-mono text-[0.7rem] text-foreground/80">
            {row.text}
          </pre>
        </FoldGroup>
      </div>
    );
  }

  if (row.kind === "meta" || row.kind === "malformed") {
    const label = row.kind === "malformed" ? "malformed" : row.label || "entry";
    const detail = row.text || (row.kind === "meta" ? `(${row.label || "entry"})` : "");
    return (
      <div data-entry={row.kind} className="space-y-1">
        <MetaLine
          icon={<CircleArrowRightIcon className={`h-3.5 w-3.5 ${row.kind === "malformed" ? "text-state-blocked" : "text-state-skipped"}`} />}
          label={label}
          time={time}
          tone={row.kind === "malformed" ? "text-state-blocked" : ""}
        />
        {detail ? <p className="pl-[1.4rem] text-xs text-muted-foreground">{detail}</p> : null}
      </div>
    );
  }

  // assistant
  return (
    <div className="space-y-2" data-entry="assistant">
      <MetaLine icon={<BotIcon className="h-3.5 w-3.5 text-muted-foreground" />} label="the-loop" time={time} />
      {row.thinking ? (
        <div className="text-xs">
          <FoldGroup icon={<BrainIcon className="h-3.5 w-3.5" />} label="thinking" detail={firstLine(row.thinking)}>
            <pre className="mt-1.5 ml-1 overflow-x-auto whitespace-pre-wrap border-l border-border pl-3 font-mono text-[0.7rem] text-foreground/80">
              {row.thinking}
            </pre>
          </FoldGroup>
        </div>
      ) : null}
      {row.text ? <Prose text={row.text} /> : null}
      {hasTools ? <ToolGroup tools={row.tools} /> : null}
    </div>
  );
}

/** Agent prose: one paragraph per line, bullets indented, inline refs and chips. */
function Prose({ text }: { text: string }) {
  const lines = text.split("\n").filter((line) => line.trim() !== "");
  return (
    <div className="space-y-1.5 text-sm leading-relaxed">
      {lines.map((line, index) => {
        const bullet = /^\s*([•\-*]|\d+\.)\s+/.test(line);
        return (
          <p key={index} className={bullet ? "pl-4 text-foreground/85" : ""}>
            {renderInline(bullet ? line.replace(/^\s*[-*]\s+/, "• ") : line)}
          </p>
        );
      })}
    </div>
  );
}

/** A native disclosure drawn as the design's group button: icon · label · detail · chevron. */
function FoldGroup({
  icon,
  label,
  detail,
  children,
  extra,
  data,
}: {
  icon: ReactNode;
  label: string;
  detail?: string | undefined;
  children: ReactNode;
  extra?: ReactNode;
  data?: string | undefined;
}) {
  return (
    <details className="group" data-fold={data ?? label}>
      <summary className="-ml-1.5 inline-flex max-w-full items-center gap-1.5 rounded-md px-1.5 py-1 text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground">
        {icon}
        <span className="shrink-0">{label}</span>
        {detail ? <span className="min-w-0 truncate font-mono text-[0.7rem]">{detail}</span> : null}
        {extra}
        <ChevronRightIcon className="h-3.5 w-3.5 shrink-0 transition-transform group-open:rotate-90" />
      </summary>
      {children}
    </details>
  );
}

/** `Used n tools`, and behind it one collapsed call per tool with its input and result. */
function ToolGroup({ tools }: { tools: ToolCallView[] }) {
  return (
    <div className="text-xs" data-tools>
      <FoldGroup
        icon={<WrenchIcon className="h-3.5 w-3.5" />}
        label={`Used ${tools.length} ${tools.length === 1 ? "tool" : "tools"}`}
        data="tools"
      >
        <ul className="mt-1.5 ml-1 space-y-1 border-l border-border pl-3">
          {tools.map((tool, index) => (
            <li key={`${tool.id || tool.name}-${index}`}>
              <ToolCall tool={tool} />
            </li>
          ))}
        </ul>
      </FoldGroup>
    </div>
  );
}

function ToolCall({ tool }: { tool: ToolCallView }) {
  return (
    <details data-tool>
      <summary className="flex items-start gap-2 rounded-md py-0.5 hover:text-foreground">
        <TerminalIcon className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground" />
        <span className="shrink-0 font-mono text-foreground/80">{tool.name}</span>
        <span className="min-w-0 truncate font-mono text-muted-foreground" title={tool.summary}>{firstLine(tool.summary)}</span>
        {tool.isError ? (
          <span className="ml-auto shrink-0 rounded-md border border-state-blocked/40 px-1.5 font-mono text-[0.65rem] text-state-blocked">error</span>
        ) : null}
      </summary>
      <div className="ml-1 mt-1 space-y-1 border-l border-border pl-3">
        {tool.input ? (
          <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-[0.7rem] text-foreground/80">{tool.input}</pre>
        ) : null}
        <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-[0.7rem] text-muted-foreground">
          {tool.result || "(no result in the served tail)"}
        </pre>
      </div>
    </details>
  );
}

/** One event of the trail — the trace's fallback when no transcript is served. */
export function EventLine({ event }: { event: EventRecord }) {
  const detail = describeEvent(event);
  return (
    <div data-entry="event" className="space-y-1">
      <MetaLine
        icon={<CircleArrowRightIcon className={`h-3.5 w-3.5 ${event.level === "error" ? "text-state-blocked" : "text-state-skipped"}`} />}
        label={event.event}
        time={timeOf(event.ts)}
        tone={event.level === "error" ? "text-state-blocked" : ""}
      />
      {detail && detail !== "—" ? (
        <p className="break-all pl-[1.4rem] font-mono text-[0.7rem] text-muted-foreground">{detail}</p>
      ) : null}
    </div>
  );
}

function firstLine(text: string): string {
  const line = text.split("\n", 1)[0] ?? "";
  return line.length > 160 ? `${line.slice(0, 160)}…` : line;
}

/** Why the bar is disabled, per session state — `""` means it can send. */
export function chatBlocked(state: SessionState): string {
  if (state === "active") return "";
  if (state === "paused") return "The session is paused — resume it first; delivery is held.";
  if (state === "closed") return "The session is closed; there is no pane to deliver into.";
  return "No session is registered for this ref on the service's machine.";
}

/**
 * The composer. `refFor` is the viewed session's — outer or inner — and the
 * service resolves it to that endpoint's pane (fail-closed: it never spawns
 * one to answer, so a refused send renders the server's reason).
 */
export function ChatBar({
  refFor,
  state,
  onSent,
  tmuxTarget,
}: {
  refFor: string;
  state: SessionState;
  onSent?: () => void;
  tmuxTarget?: string | undefined;
}) {
  const { api } = useApi();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const blocked = chatBlocked(state);
  const canSend = !busy && blocked === "" && text.trim() !== "";

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

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>): void {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey) && canSend) {
      event.preventDefault();
      void send();
    }
  }

  return (
    <div className="border-t border-border px-6 py-4">
      <div className="mx-auto max-w-3xl">
        {error ? (
          <p role="alert" className="mb-2 text-xs text-state-blocked">
            {error}
          </p>
        ) : null}
        <div
          className={`flex items-end gap-2 rounded-xl border border-border bg-surface px-3 py-2 focus-within:border-border-strong ${
            blocked ? "opacity-70" : ""
          }`}
        >
          <textarea
            rows={1}
            value={text}
            onChange={(event) => {
              setText(event.target.value);
              // Grow with the text, up to the design's max height (8 rem).
              event.target.style.height = "auto";
              event.target.style.height = `${Math.min(event.target.scrollHeight, 128)}px`;
            }}
            onKeyDown={onKeyDown}
            placeholder={blocked || "Reply into the session"}
            aria-label={`Message the session for ${refFor}`}
            disabled={busy || blocked !== ""}
            className="max-h-32 flex-1 resize-none bg-transparent py-1 text-sm outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed"
          />
          <button
            type="button"
            aria-label="Send"
            title={blocked || (busy ? "Sending…" : "Send (⌘⏎)")}
            disabled={!canSend}
            onClick={() => void send()}
            className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-primary text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            <SendHorizontalIcon className="h-3.5 w-3.5" />
          </button>
        </div>
        <div className="mt-1.5 flex flex-wrap items-center gap-3 font-mono text-[0.68rem] text-muted-foreground">
          {blocked ? (
            <span>{blocked}</span>
          ) : (
            <>
              <span className="break-all">delivers to tmux{tmuxTarget ? ` · ${tmuxTarget}` : ""}</span>
              <span aria-hidden="true">·</span>
              <span>bracketed paste + enter</span>
              <span aria-hidden="true">·</span>
              <span>⌘⏎ to send</span>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
