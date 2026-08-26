/**
 * One work item: the outer loop, every PR delivering it with its own inner
 * loop, the trace of what the harness did, and the controls.
 *
 * The **turns & tool calls** trace renders the session's own transcript from
 * `GET /api/v1/sessions/transcript` (issue-209 — the JSONL resolved
 * server-side from the recorded cwd + session id). It shipped visibly
 * disabled in issue-207 because that route did not exist; when the route
 * answers 404 — no session, no file yet, a Cursor session, an older service —
 * the panel says why and falls back to the event-log trail, which is the
 * pre-route behaviour. The reply box walked the same disabled-then-live path
 * via issue-208's `POST /api/v1/sessions/reply`.
 */

import { useEffect, useRef, useState, type UIEvent } from "react";

import { ApiError } from "../api/client.ts";
import {
  attentionEntries,
  describeEvent,
  eventRef,
  levelTag,
  questionOf,
  relativeTime,
  sessionState,
  timeOf,
  transcriptPath,
  type PullRequestView,
  type WorkItemView,
} from "../api/model.ts";
import type { EventRecord, SessionVerb } from "../api/types.ts";
import { Blueprint } from "../components/Blueprint.tsx";
import { NodeRail } from "../components/NodeRail.tsx";
import { SessionDot, sessionLabel } from "../components/SessionDot.tsx";
import { ChatBar, TranscriptView } from "../components/Transcript.tsx";
import { useApi } from "../state/ApiContext.tsx";
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
   * Pre-select one of this item's session traces — a pre-283 `#/sessions/<ref>`
   * deep link names a PR endpoint's session, and the link should land on it.
   */
  initialTraceRef?: string | undefined;
}

export function WorkItemDetail({ view, title, onChanged, transcriptTick = 0, initialTraceRef }: DetailProps) {
  const { api } = useApi();
  const [busy, setBusy] = useState<SessionVerb | "gate" | "reply" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [traceRef, setTraceRef] = useState<string>(initialTraceRef ?? view.ref);
  const [reply, setReply] = useState("");

  const events = useAsync(
    (signal) => api.events({ workItem: view.ref, limit: 200 }, signal),
    [api, view.ref],
  );

  // `transcriptTick` in the deps is the whole of the live update: the frame
  // carries a line count and no content, so the panel refetches through the
  // route that owns the path validation (issue-209) rather than rendering
  // anything the stream handed it.
  const transcript = useAsync(
    (signal) => api.transcript(traceRef, 200, signal),
    [api, traceRef, transcriptTick],
  );

  async function run(label: SessionVerb | "gate" | "reply", action: () => Promise<unknown>): Promise<void> {
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
    traceRef === view.ref ? view.session : (view.pullRequests.find((pr) => pr.ref === traceRef)?.session ?? null);

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
  }, [entryCount, traceRef]);

  // What this item needs beyond the question and gate cards below — its waits
  // and errors, expanded with their age, so clicking an error flag lands on
  // the error rather than a generic page (issue-283, feature #7).
  const needs = attentionEntries([view]).filter((entry) => entry.tier >= 2);

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
          </div>
          <div className="lp-detail-tags">
            <span>control: {view.control?.command ?? "none"}</span>
            {view.tmuxTarget ? (
              <span>
                tmux <code className="lp-code">{view.tmuxTarget}</code>
              </span>
            ) : null}
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

      <NeedsInputCard
        question={view.question}
        reply={reply}
        onReply={setReply}
        busy={busy}
        onSend={() =>
          void run("reply", async () => {
            await api.replySession(view.ref, reply);
            setReply("");
          })
        }
      />

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

      {needs.length > 0 ? (
        <div className="lp-needs">
          {needs.map((entry) => (
            <div key={entry.key} className="lp-needs-row">
              <span className="lp-needs-kind">{entry.kind}</span>
              {entry.count > 1 ? <span className="lp-inbox-count">×{entry.count}</span> : null}
              <span className="lp-needs-detail">{entry.detail}</span>
              {entry.at ? (
                <span className="lp-subtle" title={entry.at}>
                  {relativeTime(entry.at)}
                </span>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}

      <h2 className="lp-h2">Pull requests · one inner loop each</h2>
      {view.pullRequests.length === 0 ? (
        <div className="lp-subtle">
          No pull requests yet — the outer loop has not reached implementation, or this item is delivered in a single
          session.
        </div>
      ) : (
        <div className="lp-pr-grid">
          {view.pullRequests.map((pr) => (
            <PrCard key={pr.ref} pr={pr} />
          ))}
        </div>
      )}

      <div className="lp-trace-head">
        <h2 className="lp-h2">Trace · turns &amp; tool calls</h2>
        <div className="lp-filters">
          <button
            type="button"
            className="lp-tab"
            aria-current={traceRef === view.ref ? "page" : undefined}
            onClick={() => setTraceRef(view.ref)}
          >
            work item session
          </button>
          {view.pullRequests.map((pr) => (
            <button
              key={pr.ref}
              type="button"
              className="lp-tab"
              aria-current={traceRef === pr.ref ? "page" : undefined}
              onClick={() => setTraceRef(pr.ref)}
            >
              {pr.shortRef}
            </button>
          ))}
        </div>
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
                .filter((event) => (traceRef === view.ref ? true : eventRef(event) === traceRef))
                .toReversed()
                .slice(0, 40)
                .map((event, index) => <TraceEntry key={`${event.ts}-${index}`} event={event} />)
            ) : (
              <div className="lp-empty">No events recorded for this work item.</div>
            )}
          </>
        )}
      </Blueprint>

      {/* Rendered only while the trace above shows a real transcript: when it
          has fallen back to the event trail, this section would repeat the
          identical rows on the same screen (issue-283 B8). */}
      {transcript.data && !transcript.error ? (
        <>
          <h2 className="lp-h2">Events for this item</h2>
          {events.error ? (
            <div className="lp-subtle">Could not read the event log: {events.error.message}</div>
          ) : (
            (events.data ?? [])
              .toReversed()
              .slice(0, 25)
              .map((event, index) => (
                <div className="lp-event-row" key={`${event.ts}-row-${index}`}>
                  <span className="lp-event-ts" title={event.ts}>
                    {relativeTime(event.ts)}
                  </span>
                  <span className={`tag ${levelTag(event.level)}`}>{event.level ?? "info"}</span>
                  <span className="lp-event-name">{event.event}</span>
                  <span className="lp-event-detail">{describeEvent(event)}</span>
                </div>
              ))
          )}
        </>
      ) : null}
      </div>

      {/* The chat bar delivers into the *viewed* session's pane — the outer
          loop's when the work-item tab is selected, that PR's when an inner
          loop's is (issue-230). It sits at the pane's foot, under its own
          hairline, per the design. */}
      <ChatBar refFor={traceRef} state={sessionState(traceSession)} onSent={onChanged} />
    </>
  );
}

/** The header's one-line session summary, the way the design words it. */
function sessionLine(view: WorkItemView): string {
  if (view.sessionState === "none") return "No session on this machine";
  return `Session ${sessionLabel(view.sessionState, view.session?.harness)}`;
}

/** The server's reason for a missing transcript, as its own sentence. */
function fallbackReason(error: Error | null): string {
  if (error instanceof ApiError && error.kind === "network") return error.advice;
  const message = (error?.message ?? "").trim();
  if (!message) return "";
  return message.endsWith(".") ? message : `${message}.`;
}

function PrCard({ pr }: { pr: PullRequestView }) {
  return (
    <Blueprint className="card lp-pr-card">
      <div className="lp-pr-head">
        <div className="lp-pr-ref">
          {pr.url ? (
            <a href={pr.url} target="_blank" rel="noreferrer">
              {pr.shortRef} ↗
            </a>
          ) : (
            pr.shortRef
          )}
        </div>
        <div className="lp-pr-tags">
          {pr.status ? (
            <span className="tag tag-accent">{pr.status.currentNode}</span>
          ) : (
            <span className="tag tag-neutral">no inner-loop state</span>
          )}
          {pr.status?.parked ? <span className="tag tag-outline">awaiting human</span> : null}
        </div>
      </div>
      {/* Checks and review state are GitHub's, and no /api/v1 route serves them —
          the portable record deliberately keeps no copy of the ticket's mutable
          fields. The PR link above is the honest way to reach them. */}
      <NodeRail nodes={pr.rail} variant="inner" emptyMessage="No pdlc-pr-loop state for this PR yet." />
      <div className="lp-pr-foot">
        session <SessionDot state={pr.sessionState} small />
        {sessionLabel(pr.sessionState, pr.session.harness)}
        {pr.tmuxTarget ? (
          <>
            {" · tmux "}
            <code>{pr.tmuxTarget}</code>
          </>
        ) : null}
        {pr.session.lastEventAt ? ` · ${relativeTime(pr.session.lastEventAt)}` : null}
      </div>
    </Blueprint>
  );
}

/**
 * The question card.
 *
 * The question is derived once for the whole board (`awaitingInput` in
 * `model.ts`) from the `session.awaiting_input` event `the-loop ask` emits
 * (issue-208 — the verb the interaction directive routes agents through, so
 * the loop-prevention marker is stamped centrally). The reply box posts to
 * `POST /api/v1/sessions/reply`, which pastes into the session's tmux pane and
 * emits the `session.reply_sent` that closes this card on the next refresh.
 * It shipped disabled in issue-207 because that route did not exist yet.
 */
function NeedsInputCard({
  question,
  reply,
  onReply,
  busy,
  onSend,
}: {
  question: EventRecord | null;
  reply: string;
  onReply: (value: string) => void;
  busy: string | null;
  onSend: () => void;
}) {
  if (!question) return null;
  const text = questionOf(question) || "(the event carried no question text)";
  const commentUrl = typeof question["comment_url"] === "string" ? question["comment_url"] : "";

  return (
    <Blueprint className="lp-callout">
      <div className="lp-callout-head">
        <div className="lp-callout-kicker">The loop asks</div>
      </div>
      <div className="lp-callout-body">{text}</div>
      <div className="lp-reply">
        <textarea
          value={reply}
          onChange={(event) => onReply(event.target.value)}
          placeholder="Your answer — pasted into the session's TUI (bracketed paste, then Enter)"
          aria-label="Reply to the agent"
          disabled={busy !== null}
        />
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy !== null || !reply.trim()}
          onClick={onSend}
        >
          {busy === "reply" ? "Sending…" : "Send to session"}
        </button>
      </div>
      <div className="lp-hint">
        Reply below — delivered into the session, recorded on the ticket; the wait clears once
        the reply lands.
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


