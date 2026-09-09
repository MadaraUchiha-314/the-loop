/**
 * One work item as the design's main column (issue-327): the header (title,
 * ref chip, phase chip, repository, age; copy / GitHub / theme controls), the
 * loop as a node strip, one tab per session, the harness trace as a reading
 * column with a **Tool calls** switch, the two things that need a human —
 * a parked gate, the agent's question — as accent banners above the composer,
 * and the composer itself. The session panel beside it is rendered by `Work`.
 *
 * The trace renders the session's own transcript from
 * `GET /api/v1/sessions/transcript` (issue-209). When the route answers 404
 * the panel says why and falls back to the event-log trail. The composer
 * posts via issue-208's `POST /api/v1/sessions/reply`.
 */

import { useEffect, useRef, useState, type KeyboardEvent, type UIEvent } from "react";

import { ApiError } from "../api/client.ts";
import {
  attentionEntries,
  eventRef,
  questionOf,
  relativeTime,
  sessionState,
  type WorkItemView,
} from "../api/model.ts";
import type { EventRecord } from "../api/types.ts";
import { GraphStrip } from "../components/GraphStrip.tsx";
import { HeaderBar, type Chrome } from "../components/HeaderBar.tsx";
import { CheckIcon, CopyIcon, ExternalLinkIcon, GitBranchIcon, TriangleAlertIcon } from "../components/Icons.tsx";
import { ControlButton, Empty, IconButton, Notice, PhaseChip } from "../components/primitives.tsx";
import { SessionTabs } from "../components/SessionTabs.tsx";
import { ChatBar, EventLine, TranscriptView } from "../components/Transcript.tsx";
import { useApi } from "../state/ApiContext.tsx";
import { useAsync } from "../state/useAsync.ts";
import { itemStatus, repoOf } from "./grouping.ts";

/** How close to the bottom still counts as "following the newest entry". */
const PIN_THRESHOLD_PX = 24;

/**
 * Whether the reader is at the newest entry, and so wants to be kept there.
 * Exported for its own test (issue-239 R6.3/R6.4).
 */
export function isAtNewest(panel: Pick<HTMLElement, "scrollHeight" | "scrollTop" | "clientHeight">): boolean {
  return panel.scrollHeight - panel.scrollTop - panel.clientHeight < PIN_THRESHOLD_PX;
}

/**
 * The one line for "this item is stuck": the parked gate, or the newest
 * wait/error the attention model holds. Shown in the graph strip and the
 * session panel's banner.
 */
export function railNote(view: WorkItemView): string {
  if (view.parked) return `parked — awaiting a human at ${view.parked.node}`;
  const entry = attentionEntries([view]).find((candidate) => candidate.tier >= 2);
  if (!entry) return "";
  const detail = entry.detail || entry.kind;
  return detail.length > 90 ? `${detail.slice(0, 89)}…` : detail;
}

/** The ref a stale deep link falls back from: the item's own session. */
export function resolveViewed(view: WorkItemView, traceRef: string | undefined): string {
  return traceRef && (traceRef === view.ref || view.pullRequests.some((pr) => pr.ref === traceRef)) ? traceRef : view.ref;
}

interface DetailProps {
  view: WorkItemView;
  title: string | undefined;
  onChanged: () => void;
  /** Bumped when a streamed `transcript` frame says the watched session's file grew. */
  transcriptTick?: number;
  /** Which of this item's session traces the column shows (from the hash). */
  traceRef?: string | undefined;
  chrome: Chrome;
}

export function WorkItemDetail({ view, title, onChanged, transcriptTick = 0, traceRef, chrome }: DetailProps) {
  const { api } = useApi();
  const viewed = resolveViewed(view, traceRef);
  const [showTools, setShowTools] = useState(true);
  const [copied, setCopied] = useState(false);

  const events = useAsync((signal) => api.events({ workItem: view.ref, limit: 200 }, signal), [api, view.ref]);
  // `transcriptTick` in the deps is the whole of the live update: the frame
  // carries a line count and no content, so the panel refetches through the
  // route that owns the path validation (issue-209).
  const transcript = useAsync((signal) => api.transcript(viewed, 200, signal), [api, viewed, transcriptTick]);

  const traceSession = viewed === view.ref ? view.session : (view.pullRequests.find((pr) => pr.ref === viewed)?.session ?? null);
  const traceState = sessionState(traceSession);
  const tmux = viewed === view.ref ? view.tmuxTarget : (view.pullRequests.find((pr) => pr.ref === viewed)?.tmuxTarget ?? "");

  const traceScroll = useRef<HTMLDivElement | null>(null);
  const entryCount = transcript.data?.entries.length ?? 0;
  /**
   * Follow the newest entry, but only for a reader who is already there —
   * decided **before** the render that appended (issue-239 R6.3/R6.4).
   */
  const pinned = useRef(true);
  useEffect(() => {
    const panel = traceScroll.current;
    if (!panel) return;
    if (pinned.current) panel.scrollTop = panel.scrollHeight;
  }, [entryCount, viewed]);

  async function copyRef(): Promise<void> {
    try {
      await navigator.clipboard.writeText(view.ref);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  function onSwitchKey(event: KeyboardEvent<HTMLElement>): void {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setShowTools((value) => !value);
    }
  }

  const note = railNote(view);

  return (
    <>
      <HeaderBar
        chrome={chrome}
        title={title ?? view.shortRef}
        meta={
          <>
            <span className="ref-chip">{view.ref}</span>
            <PhaseChip phase={view.currentNode || (view.rail.length > 0 ? "planned" : "no graph")} status={itemStatus(view)} />
            <span className="inline-flex items-center gap-1">
              <GitBranchIcon className="h-3 w-3" />
              <span className="font-mono">{repoOf(view.ref)}</span>
            </span>
            <span aria-hidden="true">·</span>
            <span title={view.lastActivity || undefined}>updated {relativeTime(view.lastActivity)}</span>
          </>
        }
        actions={
          <>
            <IconButton label={copied ? "Copied" : "Copy work item ref"} onClick={() => void copyRef()}>
              {copied ? <CheckIcon className="h-4 w-4 text-state-done" /> : <CopyIcon className="h-4 w-4" />}
            </IconButton>
            {view.url ? (
              <IconButton label="Open on GitHub" href={view.url} external>
                <ExternalLinkIcon className="h-4 w-4" />
              </IconButton>
            ) : null}
          </>
        }
      />

      <GraphStrip
        nodes={view.rail}
        loop={view.record.graph?.loop ?? "loop"}
        note={note}
        emptyMessage={
          view.repoPath
            ? "The checkout has no graph state for this item yet — it starts at phase-selection."
            : "No session on this machine recorded a checkout, so the graph state cannot be read from here."
        }
      />

      <SessionTabs view={view} viewed={viewed} />

      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-border px-6 py-2 text-xs text-muted-foreground">
          <span>
            Harness trace{traceSession?.harness ? <span className="font-mono"> · {traceSession.harness}</span> : null}
          </span>
          <label className="flex cursor-pointer items-center gap-2">
            <span>Tool calls</span>
            <span
              role="switch"
              aria-checked={showTools}
              aria-label="Tool calls"
              tabIndex={0}
              onClick={() => setShowTools((value) => !value)}
              onKeyDown={onSwitchKey}
              className={`relative inline-flex h-4 w-7 items-center rounded-full transition-colors ${showTools ? "bg-primary" : "bg-border-strong"}`}
            >
              <span
                className={`absolute h-3 w-3 rounded-full bg-background transition-transform ${showTools ? "translate-x-3.5" : "translate-x-0.5"}`}
              />
            </span>
          </label>
        </div>

        {/* The panel scrolls inside its own bounds and is focusable so it can
            be scrolled from the keyboard (issue-239 R6.2/R6.5). */}
        <div
          ref={traceScroll}
          tabIndex={0}
          role="log"
          aria-label="Session transcript"
          data-trace
          className="scroll-thin min-h-0 flex-1 overflow-y-auto px-6 py-6"
          onScroll={(event: UIEvent<HTMLDivElement>) => {
            pinned.current = isAtNewest(event.currentTarget);
          }}
        >
          <div className="mx-auto max-w-3xl space-y-5">
            {/* `useAsync` keeps stale data across tab switches and errors, so
                while loading, or after an error, the held `data` is the
                PREVIOUS tab's transcript and must not be drawn. */}
            {transcript.loading ? (
              <Empty>Loading the transcript…</Empty>
            ) : transcript.data && !transcript.error ? (
              <>
                {transcript.data.truncated ? (
                  <p className="text-center font-mono text-[0.68rem] text-muted-foreground">
                    tail — the last {transcript.data.entries.length} of {transcript.data.totalLines} entries
                  </p>
                ) : null}
                {transcript.data.entries.length === 0 ? (
                  <Empty>The transcript exists but holds no entries yet.</Empty>
                ) : (
                  <TranscriptView entries={transcript.data.entries} showTools={showTools} />
                )}
              </>
            ) : (
              <>
                <Notice tone="muted" icon={<TriangleAlertIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" />}>
                  <div>
                    <strong className="font-medium text-foreground">No transcript served for this session.</strong>{" "}
                    {fallbackReason(transcript.error)}
                  </div>
                  <div>Falling back to the event-log trail for this work item.</div>
                </Notice>
                {events.loading && !events.data ? (
                  <Empty>Loading events…</Empty>
                ) : events.data && events.data.length > 0 ? (
                  events.data
                    .filter((event) => (viewed === view.ref ? true : eventRef(event) === viewed))
                    .toReversed()
                    .slice(0, 40)
                    .map((event, index) => <EventLine key={`${event.ts}-${index}`} event={event} />)
                ) : (
                  <Empty>No events recorded for this work item.</Empty>
                )}
              </>
            )}
          </div>
        </div>

        {view.parked || view.question ? (
          <div className="px-6 pb-2">
            <div className="mx-auto max-w-3xl space-y-2">
              {view.parked ? <GateBanner view={view} onChanged={onChanged} /> : null}
              {view.question ? <QuestionBanner question={view.question} /> : null}
            </div>
          </div>
        ) : null}

        <ChatBar refFor={viewed} state={traceState} onSent={onChanged} tmuxTarget={tmux} />
      </div>
    </>
  );
}

/** The server's reason for a missing transcript, as its own sentence. */
function fallbackReason(error: Error | null): string {
  if (error instanceof ApiError && error.kind === "network") return error.advice;
  const message = (error?.message ?? "").trim();
  if (!message) return "";
  return message.endsWith(".") ? message : `${message}.`;
}

/**
 * The parked human gate: what it waits for, since when, and the one in-place
 * action — Approve, which posts `POST /graph/complete` for the parked node.
 */
function GateBanner({ view, onChanged }: { view: WorkItemView; onChanged: () => void }) {
  const { api } = useApi();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const parked = view.parked;
  if (!parked) return null;
  const canApprove = Boolean(view.repoPath && view.specId);

  async function approve(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      await api.graphComplete({ repo: view.repoPath, workItem: view.specId ?? "", node: parked?.node ?? "" });
      onChanged();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.advice : String(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Notice icon={<TriangleAlertIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" />} role="status">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <span className="font-medium">Human gate — {parked.node}</span>
        {parked.since ? (
          <span className="font-mono text-[0.68rem] opacity-80" title={parked.since}>
            waiting {relativeTime(parked.since)}
          </span>
        ) : null}
      </div>
      <div>{parked.reason}</div>
      <div className="flex flex-wrap items-center gap-2 pt-1">
        <ControlButton
          primary
          disabled={busy || !canApprove}
          title={canApprove ? undefined : "No checkout recorded for this item on the service's machine."}
          onClick={() => void approve()}
        >
          {busy ? "Approving…" : "Approve — advance graph"}
        </ControlButton>
        {view.url ? (
          <a href={view.url} target="_blank" rel="noreferrer" className="text-xs underline-offset-2 hover:underline">
            Request changes on the ticket ↗
          </a>
        ) : null}
      </div>
      {error ? (
        <p role="alert" className="text-state-blocked">
          {error}
        </p>
      ) : null}
    </Notice>
  );
}

/**
 * The agent's open question (`the-loop ask`, issue-208) and a pointer to the
 * composer beneath — no second reply box. The composer posts the answer to
 * `POST /api/v1/sessions/reply`, whose `session.reply_sent` closes this on the
 * next refresh.
 */
function QuestionBanner({ question }: { question: EventRecord }) {
  const text = questionOf(question) || "(the event carried no question text)";
  const commentUrl = typeof question["comment_url"] === "string" ? question["comment_url"] : "";
  return (
    <Notice icon={<TriangleAlertIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" />} role="status">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <span className="font-medium">The loop asks</span>
        <span className="font-mono text-[0.68rem] opacity-80" title={question.ts}>
          {relativeTime(question.ts)}
        </span>
      </div>
      <div className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">{text}</div>
      <div className="opacity-80">
        Reply below — delivered into the session, recorded on the ticket.
        {commentUrl ? (
          <>
            {" "}
            <a href={commentUrl} target="_blank" rel="noreferrer" className="underline-offset-2 hover:underline">
              Answer on the ticket instead ↗
            </a>
          </>
        ) : null}
      </div>
    </Notice>
  );
}
