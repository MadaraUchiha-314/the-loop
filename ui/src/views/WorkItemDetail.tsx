/**
 * One work item, the way the issue-298 design draws it: a header (ref line,
 * title, the loop as a tick rail with a note when the item is parked or
 * blocked), the trace on the canvas, and the chat bar at the foot. The
 * owner's direction on PR #299 keeps this pane deliberately bare — what the
 * old pane listed as extra sections (inbox-style waits, PR cards, a second
 * event list) now lives in the rail note, the sidebar chips and the trace
 * tabs; only the two actionable cards (the agent's question, a parked human
 * gate) remain as cards.
 *
 * The **turns & tool calls** trace renders the session's own transcript from
 * `GET /api/v1/sessions/transcript` (issue-209 — the JSONL resolved
 * server-side from the recorded cwd + session id). When the route answers
 * 404 — no session, no file yet, a Cursor session, an older service — the
 * panel says why and falls back to the event-log trail, which is the
 * pre-route behaviour. The reply box posts via issue-208's
 * `POST /api/v1/sessions/reply`.
 */

import { useEffect, useRef, useState, type UIEvent } from "react";

import { ApiError } from "../api/client.ts";
import {
  attentionEntries,
  describeEvent,
  eventRef,
  questionOf,
  relativeTime,
  sessionState,
  timeOf,
  transcriptPath,
  type WorkItemView,
} from "../api/model.ts";
import type { EventRecord, SessionVerb } from "../api/types.ts";
import { Blueprint } from "../components/Blueprint.tsx";
import { NodeRail } from "../components/NodeRail.tsx";
import { sessionLabel } from "../components/SessionDot.tsx";
import { ChatBar, TranscriptView } from "../components/Transcript.tsx";
import { useApi } from "../state/ApiContext.tsx";
import { hrefFor } from "../state/route.ts";
import { useAsync } from "../state/useAsync.ts";

/** How close to the bottom still counts as "following the newest entry". */
const PIN_THRESHOLD_PX = 24;

/**
 * Whether the reader is at the newest entry, and so wants to be kept there.
 *
 * Exported for its own test: this is the whole of R6.3/R6.4, and the rest of the
 * mechanism — reading it **before** the render that appends — is only correct if
 * this answer is. A few pixels of slack because a scrolled-to-bottom container
 * is routinely a fraction short of exact.
 */
export function isAtNewest(panel: Pick<HTMLElement, "scrollHeight" | "scrollTop" | "clientHeight">): boolean {
  return panel.scrollHeight - panel.scrollTop - panel.clientHeight < PIN_THRESHOLD_PX;
}

interface DetailProps {
  view: WorkItemView;
  title: string | undefined;
  onChanged: () => void;
  /**
   * Bumped by the board when a streamed `transcript` frame says the watched
   * session's file grew (issue-239). The stream itself lives one level up —
   * one connection per tab — so this is how the news reaches the panel.
   */
  transcriptTick?: number;
  /**
   * Which of this item's session traces the canvas shows — the work item's own
   * session, or one of its PR endpoints'. It comes from the hash (the sidebar's
   * nested PR rows and a pre-283 `#/sessions/<ref>` deep link both name a PR's
   * ref), so the sidebar, the trace tabs and the URL cannot disagree about what
   * is on screen (issue-300). Defaults to the item's own session.
   */
  traceRef?: string;
}

export function WorkItemDetail({ view, title, onChanged, transcriptTick = 0, traceRef }: DetailProps) {
  const { api } = useApi();
  const [busy, setBusy] = useState<SessionVerb | "gate" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  // A ref the item does not own (a stale deep link) falls back to its own
  // session rather than asking the transcript route for somebody else's file.
  const viewed =
    traceRef && (traceRef === view.ref || view.pullRequests.some((pr) => pr.ref === traceRef))
      ? traceRef
      : view.ref;

  const events = useAsync(
    (signal) => api.events({ workItem: view.ref, limit: 200 }, signal),
    [api, view.ref],
  );

  // `transcriptTick` in the deps is the whole of the live update: the frame
  // carries a line count and no content, so the panel refetches through the
  // route that owns the path validation (issue-209) rather than rendering
  // anything the stream handed it.
  const transcript = useAsync(
    (signal) => api.transcript(viewed, 200, signal),
    [api, viewed, transcriptTick],
  );

  async function run(label: SessionVerb | "gate", action: () => Promise<unknown>): Promise<void> {
    setBusy(label);
    setActionError(null);
    try {
      await action();
      onChanged();
    } catch (cause) {
      setActionError(cause instanceof ApiError ? cause.advice : String(cause));
    } finally {
      setBusy(null);
    }
  }

  const verbs: SessionVerb[] =
    view.sessionState === "active" ? ["pause", "stop"] : view.sessionState === "paused" ? ["resume", "stop"] : ["start"];

  const traceSession =
    viewed === view.ref ? view.session : (view.pullRequests.find((pr) => pr.ref === viewed)?.session ?? null);

  const traceScroll = useRef<HTMLDivElement | null>(null);
  const entryCount = transcript.data?.entries.length ?? 0;

  /**
   * Follow the newest entry, but only for a reader who is already there (R6.3,
   * R6.4).
   *
   * "Already there" is decided **before** the render that appended, which is why
   * this reads the pinned state in a layout effect keyed on the count rather
   * than in the scroll handler: by the time an effect keyed on the DOM runs, the
   * new entry has already made `scrollHeight` bigger and every reader would look
   * un-pinned. Scrolling somebody back to the bottom while they are reading
   * history is the one thing this feature must not do.
   */
  const pinned = useRef(true);
  useEffect(() => {
    const panel = traceScroll.current;
    if (!panel) return;
    if (pinned.current) panel.scrollTop = panel.scrollHeight;
  }, [entryCount, viewed]);

  return (
    <>
      <div className="lp-detail-head">
        <div className="lp-detail-id">
          <div className="lp-detail-ref">
            <span>{view.ref}</span>
            {view.url ? (
              <>
                <span>·</span>
                <a href={view.url} target="_blank" rel="noreferrer">
                  Open on GitHub ↗
                </a>
              </>
            ) : null}
            <span>·</span>
            <span>{sessionLine(view)}</span>
          </div>
          <h1 className="lp-detail-title">{title ?? view.shortRef}</h1>
          <div className="lp-detail-rail">
            <NodeRail
              nodes={view.rail}
              emptyMessage={
                view.repoPath
                  ? "The checkout has no graph state for this item yet — it starts at phase-selection."
                  : "No session on this machine recorded a checkout, so the graph state cannot be read from here."
              }
            />
            {railNote(view) ? <span className="lp-detail-note">{railNote(view)}</span> : null}
          </div>
        </div>
        <div className="lp-detail-actions">
          {verbs.map((verb) => (
            <button
              key={verb}
              type="button"
              className="btn btn-secondary"
              disabled={busy !== null}
              onClick={() => void run(verb, () => api.controlSession(view.ref, verb))}
            >
              {busy === verb ? `${verb}…` : verb}
            </button>
          ))}
        </div>
      </div>

      <div className="lp-pane-body">
      {actionError ? (
        <div className="lp-banner lp-banner-error" role="alert">
          <span className="lp-banner-kicker">Action failed</span>
          <span>{actionError}</span>
        </div>
      ) : null}

      {view.parked ? (
        <Blueprint className="lp-gate">
          <div className="lp-gate-main">
            <div className="lp-callout-kicker">Human gate — {view.parked.node}</div>
            <div className="lp-gate-detail">{view.parked.reason}</div>
            {view.parked.since ? (
              <div className="lp-subtle" title={view.parked.since}>
                waiting {relativeTime(view.parked.since)}
              </div>
            ) : null}
          </div>
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy !== null || !view.repoPath || !view.specId}
            title={view.repoPath ? undefined : "No checkout recorded for this item on the service's machine."}
            onClick={() =>
              void run("gate", () =>
                api.graphComplete({
                  repo: view.repoPath,
                  workItem: view.specId ?? "",
                  node: view.parked?.node ?? "",
                }),
              )
            }
          >
            {busy === "gate" ? "Approving…" : "Approve — advance graph"}
          </button>
          <a className="btn btn-ghost" href={view.url} target="_blank" rel="noreferrer">
            Request changes on the ticket ↗
          </a>
        </Blueprint>
      ) : null}

      {/* One trace per session; the tabs appear only when PRs bring their own
          sessions (issue-172/230), and the caption names the served file. They
          are links, not buttons: the sidebar's nested PR rows select the same
          traces, so both go through the hash rather than through two states
          that would drift apart (issue-300). */}
      <div className="lp-trace-head">
        {view.pullRequests.length > 0 ? (
          <div className="lp-filters">
            <a
              className="lp-tab"
              href={hrefFor({ name: "work", ref: view.ref })}
              aria-current={viewed === view.ref ? "page" : undefined}
            >
              work item session
            </a>
            {view.pullRequests.map((pr) => (
              <a
                key={pr.ref}
                className="lp-tab"
                href={hrefFor({ name: "work", ref: pr.ref })}
                aria-current={viewed === pr.ref ? "page" : undefined}
              >
                {pr.shortRef}
              </a>
            ))}
          </div>
        ) : null}
        <span className="lp-trace-source">{transcriptPath(traceSession) ?? "no derivable transcript path"}</span>
      </div>

      {/* R6.2/R6.5: the panel scrolls inside its own bounds (`.lp-trace` in
          app.css) rather than extending the page, and is focusable so it can be
          scrolled from the keyboard. `ref` reaches the div through Blueprint's
          prop spread — React 19 passes it as an ordinary prop. */}
      <Blueprint
        className="lp-trace"
        ref={traceScroll}
        tabIndex={0}
        role="log"
        aria-label="Session transcript"
        onScroll={(event: UIEvent<HTMLDivElement>) => {
          pinned.current = isAtNewest(event.currentTarget);
        }}
      >
        {/* `useAsync` keeps stale data across tab switches and errors, so the
            order matters: while loading, or after an error, the held `data` is
            the PREVIOUS tab's transcript and must not be drawn. */}
        {transcript.loading ? (
          <div className="lp-empty">Loading the transcript…</div>
        ) : transcript.data && !transcript.error ? (
          <>
            {transcript.data.truncated ? (
              <div className="lp-empty">
                Tail — the last {transcript.data.entries.length} of {transcript.data.totalLines} entries.
              </div>
            ) : null}
            {transcript.data.entries.length === 0 ? (
              <div className="lp-empty">The transcript exists but holds no entries yet.</div>
            ) : (
              <TranscriptView entries={transcript.data.entries} />
            )}
          </>
        ) : (
          <>
            {/* The server's reason and this page's follow-on are two sentences
                on two lines (issue-283 B9) — joined with a bare space they read
                as one broken one. */}
            <div className="lp-empty">
              <div>
                <strong>No transcript served for this session.</strong>{" "}
                {fallbackReason(transcript.error)}
              </div>
              <div>Falling back to the event-log trail for this work item.</div>
            </div>
            {events.loading && !events.data ? (
              <div className="lp-empty">Loading events…</div>
            ) : events.data && events.data.length > 0 ? (
              events.data
                .filter((event) => (viewed === view.ref ? true : eventRef(event) === viewed))
                .toReversed()
                .slice(0, 40)
                .map((event, index) => <TraceEntry key={`${event.ts}-${index}`} event={event} />)
            ) : (
              <div className="lp-empty">No events recorded for this work item.</div>
            )}
          </>
        )}
      </Blueprint>

      {/* The agent's open question sits between the trace and the chat bar,
          where the conversation is — and the chat bar IS the reply box: it
          posts the same POST /sessions/reply the old card-local box did. */}
      <NeedsInputCard question={view.question} />
      </div>

      {/* The chat bar delivers into the *viewed* session's pane — the outer
          loop's when the work-item tab is selected, that PR's when an inner
          loop's is (issue-230). It sits at the pane's foot, under its own
          hairline, per the design. */}
      <ChatBar refFor={viewed} state={sessionState(traceSession)} onSent={onChanged} />
    </>
  );
}

/** The header's one-line session summary, the way the design words it. */
function sessionLine(view: WorkItemView): string {
  if (view.sessionState === "none") return "No session on this machine";
  return `Session ${sessionLabel(view.sessionState, view.session?.harness)}`;
}

/**
 * The italic note beside the rail — the design's one line for "this item is
 * stuck": the parked gate, or the newest wait/error the attention model holds.
 */
function railNote(view: WorkItemView): string {
  if (view.parked) return `parked — awaiting a human at ${view.parked.node}`;
  const entry = attentionEntries([view]).find((candidate) => candidate.tier >= 2);
  if (!entry) return "";
  const detail = entry.detail || entry.kind;
  return detail.length > 90 ? `${detail.slice(0, 89)}…` : detail;
}

/** The server's reason for a missing transcript, as its own sentence. */
function fallbackReason(error: Error | null): string {
  if (error instanceof ApiError && error.kind === "network") return error.advice;
  const message = (error?.message ?? "").trim();
  if (!message) return "";
  return message.endsWith(".") ? message : `${message}.`;
}

/**
 * The question card, the way the design draws it: the question and a pointer
 * to the chat bar beneath — no second reply box.
 *
 * The question is derived once for the whole board (`awaitingInput` in
 * `model.ts`) from the `session.awaiting_input` event `the-loop ask` emits
 * (issue-208). The chat bar below posts the answer to
 * `POST /api/v1/sessions/reply`, which pastes into the session's tmux pane and
 * emits the `session.reply_sent` that closes this card on the next refresh.
 */
function NeedsInputCard({ question }: { question: EventRecord | null }) {
  if (!question) return null;
  const text = questionOf(question) || "(the event carried no question text)";
  const commentUrl = typeof question["comment_url"] === "string" ? question["comment_url"] : "";

  return (
    <Blueprint className="lp-callout">
      <div className="lp-callout-head">
        <div className="lp-callout-kicker">The loop asks</div>
        <span className="lp-trace-ts" title={question.ts}>
          {relativeTime(question.ts)}
        </span>
      </div>
      <div className="lp-callout-body">{text}</div>
      <div className="lp-hint">
        Reply below — delivered into the session, recorded on the ticket.
        {commentUrl ? (
          <>
            {" "}
            <a href={commentUrl} target="_blank" rel="noreferrer">
              Answer on the ticket instead ↗
            </a>
          </>
        ) : null}
      </div>
    </Blueprint>
  );
}

const KIND_CLASS: Record<string, string> = {
  graph: "accent",
  session: "accent",
  poll: "",
  "gh-webhook": "",
};

function TraceEntry({ event }: { event: EventRecord }) {
  return (
    <div className="lp-trace-entry">
      <div className={`lp-trace-kind ${KIND_CLASS[event.source ?? ""] ?? ""}`.trim()}>
        {event.event}
        <div className="lp-trace-ts">{timeOf(event.ts)}</div>
      </div>
      <div className="lp-trace-main">
        <div className="lp-trace-text">{describeEvent(event)}</div>
      </div>
    </div>
  );
}
