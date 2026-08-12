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

import { useState } from "react";

import { ApiError } from "../api/client.ts";
import {
  describeEvent,
  eventRef,
  levelTag,
  questionOf,
  relativeTime,
  stampOf,
  timeOf,
  transcriptPath,
  transcriptTurns,
  type PullRequestView,
  type TranscriptTurn,
  type WorkItemView,
} from "../api/model.ts";
import type { EventRecord, SessionVerb } from "../api/types.ts";
import { Blueprint } from "../components/Blueprint.tsx";
import { NodeRail } from "../components/NodeRail.tsx";
import { SessionDot, sessionLabel } from "../components/SessionDot.tsx";
import { useApi } from "../state/ApiContext.tsx";
import { hrefFor } from "../state/route.ts";
import { useAsync } from "../state/useAsync.ts";

interface DetailProps {
  view: WorkItemView;
  title: string | undefined;
  onChanged: () => void;
}

export function WorkItemDetail({ view, title, onChanged }: DetailProps) {
  const { api } = useApi();
  const [busy, setBusy] = useState<SessionVerb | "gate" | "reply" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [traceRef, setTraceRef] = useState<string>(view.ref);
  const [reply, setReply] = useState("");

  const events = useAsync(
    (signal) => api.events({ workItem: view.ref, limit: 200 }, signal),
    [api, view.ref],
  );

  const transcript = useAsync((signal) => api.transcript(traceRef, 200, signal), [api, traceRef]);

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

  return (
    <>
      <a className="lp-back" href={hrefFor({ name: "dashboard" })}>
        ← All work items
      </a>

      <div className="lp-detail-head">
        <div>
          <div className="lp-detail-ref">
            {view.ref}
            {view.url ? (
              <>
                {" · "}
                <a href={view.url} target="_blank" rel="noreferrer">
                  open on GitHub ↗
                </a>
              </>
            ) : null}
          </div>
          <h1 className="lp-detail-title">{title ?? view.shortRef}</h1>
          <div className="lp-detail-tags">
            {view.currentNode ? <span className="tag tag-accent">{view.currentNode}</span> : null}
            <span className="tag tag-outline">control: {view.control?.command ?? "none"}</span>
            {view.tmuxTarget ? (
              <span className="lp-subtle">
                tmux: <code className="lp-code">{view.tmuxTarget}</code>
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
              <div className="lp-subtle">waiting since {stampOf(view.parked.since)}</div>
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

      <h2 className="lp-h2">Outer loop · {view.record.graph?.loop ?? "pdlc-work-item-loop"}</h2>
      <NodeRail
        nodes={view.rail}
        emptyMessage={
          view.repoPath
            ? "The checkout has no graph state for this item yet — it starts at phase-selection."
            : "No session on this machine recorded a checkout, so the graph state cannot be read from here."
        }
      />

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

      <Blueprint className="lp-trace">
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
              transcriptTurns(transcript.data.entries).map((turn, index) => (
                <TurnRow key={`${turn.time}-${index}`} turn={turn} />
              ))
            )}
          </>
        ) : (
          <>
            <div className="lp-empty">
              <strong>No transcript served for this session.</strong>{" "}
              {transcript.error instanceof ApiError && transcript.error.kind === "network"
                ? transcript.error.advice
                : (transcript.error?.message ?? "")}{" "}
              Falling back to the event-log trail for this work item.
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

      <h2 className="lp-h2">Events for this item</h2>
      {events.error ? (
        <div className="lp-subtle">Could not read the event log: {events.error.message}</div>
      ) : (
        (events.data ?? [])
          .toReversed()
          .slice(0, 25)
          .map((event, index) => (
            <div className="lp-event-row" key={`${event.ts}-row-${index}`}>
              <span className="lp-event-ts">{stampOf(event.ts)}</span>
              <span className={`tag ${levelTag(event.level)}`}>{event.level ?? "info"}</span>
              <span className="lp-event-name">{event.event}</span>
              <span className="lp-event-detail">{describeEvent(event)}</span>
            </div>
          ))
      )}
    </>
  );
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
        <div className="lp-callout-kicker">Agent is waiting for your input</div>
        <div className="lp-callout-path">
          via <code>the-loop ask</code> → gh comment on issue/PR + session.awaiting_input → /api/v1/attention
        </div>
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
        Delivered straight into the session's tmux pane and recorded on the ticket; the wait
        clears once the reply lands.
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

/**
 * One transcript turn: the projected kind/time in the left rail, then the
 * turn's text and its tool invocations — the row shape (and the styles) the
 * trace panel was designed with in issue-207, filled with real data now that
 * the transcript route serves it.
 */
function TurnRow({ turn }: { turn: TranscriptTurn }) {
  const kindClass = turn.kind === "assistant" ? "accent" : turn.kind === "malformed" ? "hot" : "";
  return (
    <div className="lp-trace-entry">
      <div className={`lp-trace-kind ${kindClass}`.trim()}>
        {turn.kind}
        {turn.time ? <div className="lp-trace-ts">{timeOf(turn.time)}</div> : null}
      </div>
      <div className="lp-trace-main">
        {turn.text ? <div className="lp-trace-text">{turn.text}</div> : null}
        {turn.tools.length > 0 ? (
          <div className="lp-trace-tools">
            {turn.tools.map((tool, index) => (
              <div className="lp-trace-tool" key={`${tool.name}-${index}`}>
                <span className="lp-trace-tool-name">{tool.name}</span>
                <span className="lp-trace-tool-detail">{tool.detail}</span>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

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


