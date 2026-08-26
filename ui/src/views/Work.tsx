/**
 * The Work screen (issue-283, restyled by issue-298): one persistent sidebar —
 * the brand block on top, the inbox strip, then every work item grouped by
 * what it needs from you, then standing sessions under a divider, with Events,
 * Settings and the health dot in the footer — and one main pane showing the
 * selected item (rail, trace, chat), the standing screen, or, with nothing
 * selected, the inbox at full width.
 *
 * Since issue-298 the sidebar is also the app's navigation: the old header bar
 * is gone, per the signed-off design (docs/specs/issue-298/design/).
 */

import { useState } from "react";

import { ApiError } from "../api/client.ts";
import {
  attentionByItem,
  itemGroup,
  relativeTime,
  rowFlag,
  type AttentionEntry,
  type AttentionGroup,
  type ItemGroup,
  type WorkItemView,
} from "../api/model.ts";
import type { DaemonStatus } from "../api/types.ts";
import { HealthDot } from "../components/Nav.tsx";
import { SessionDot } from "../components/SessionDot.tsx";
import { useApi } from "../state/ApiContext.tsx";
import { hrefFor } from "../state/route.ts";
import { useAsync } from "../state/useAsync.ts";
import type { StreamState } from "../state/useStream.ts";
import { Standing } from "./Standing.tsx";
import { WorkItemDetail } from "./WorkItemDetail.tsx";

const GROUPS: { key: ItemGroup; label: string }[] = [
  { key: "needs-you", label: "Needs you" },
  { key: "running", label: "Running" },
  { key: "idle", label: "Idle" },
];

interface WorkProps {
  views: WorkItemView[];
  loading: boolean;
  titleFor: (ref: string) => string | undefined;
  /** The selected work item or session ref, or `""` for the overview. */
  selectedRef: string;
  /** True when the standing-sessions pane is selected (`#/standing`). */
  standing: boolean;
  onChanged: () => void;
  transcriptTick: number;
  daemons: DaemonStatus[];
  stream: StreamState;
}

/** The view that owns `ref` — the item itself, or the item whose PR it is. */
function findOwner(views: WorkItemView[], ref: string): WorkItemView | undefined {
  return views.find((view) => view.ref === ref || view.pullRequests.some((pr) => pr.ref === ref));
}

export function Work({
  views,
  loading,
  titleFor,
  selectedRef,
  standing,
  onChanged,
  transcriptTick,
  daemons,
  stream,
}: WorkProps) {
  const { api } = useApi();
  const groups = attentionByItem(views);
  const selected = selectedRef ? findOwner(views, selectedRef) : undefined;
  const standingSessions = useAsync((signal) => api.standingSessions(signal), [api]);
  // One banner instead of twenty dead cells (bloat #6): when no item has a
  // session on this machine, say it once and let the rows stay quiet.
  const noSessions = views.length > 0 && views.every((view) => view.sessionState === "none");

  // The strip duplicates the overview pane — which IS the inbox — so it only
  // renders while something else occupies the main pane.
  const showStrip = Boolean(selectedRef) || standing;

  return (
    <div className="lp-work">
      <aside className="lp-side">
        <a className="lp-side-brand" href={hrefFor({ name: "work" })}>
          <div className="lp-side-brand-name">the-loop</div>
          <div className="lp-side-brand-sub">Control plane</div>
        </a>

        <div className="lp-side-scroll">
          {showStrip ? <Inbox groups={groups} onChanged={onChanged} compact /> : null}

          {noSessions ? (
            <div className="lp-side-banner">
              No sessions are registered on this workstation; positions are shown from each item&rsquo;s frozen node
              list.
            </div>
          ) : null}

          {loading && views.length === 0 ? <div className="lp-empty lp-side-clear">Loading…</div> : null}
          {!loading && views.length === 0 ? (
            <div className="lp-empty lp-side-banner">
              Nothing is tracked on this machine yet. A work item appears once the poller or webhook receiver sees a
              control keyword on its ticket, or after <code className="lp-code">the-loop sessions register</code>.
            </div>
          ) : null}

          {GROUPS.map(({ key, label }) => {
            const members = views.filter((view) => itemGroup(view) === key);
            if (members.length === 0) return null;
            return (
              <section key={key} className="lp-side-group">
                <div className="lp-side-head">{label}</div>
                {members.map((view) => (
                  <ItemRow
                    key={view.ref}
                    view={view}
                    title={titleFor(view.ref)}
                    selected={selected?.ref === view.ref && !standing}
                  />
                ))}
              </section>
            );
          })}

          <section className="lp-side-group">
            <div className="lp-side-head">Standing sessions</div>
            {(standingSessions.data ?? []).map((session) => (
              <a
                key={session.name}
                className={`lp-side-row ${standing ? "current" : ""}`.trim()}
                href={hrefFor({ name: "standing" })}
              >
                <span className={`lp-health-dot ${session.running ? "ok" : "unknown"}`} aria-hidden="true" />
                <span className="lp-side-ref">{session.name}</span>
                <span className="lp-side-title">{session.description}</span>
              </a>
            ))}
            <a
              className={`lp-side-row lp-side-manage ${standing ? "current" : ""}`.trim()}
              href={hrefFor({ name: "standing" })}
            >
              Manage standing sessions
            </a>
          </section>
        </div>

        <div className="lp-side-foot">
          <a href={hrefFor({ name: "events" })}>Events →</a>
          <a href={hrefFor({ name: "settings" })}>Settings →</a>
          <HealthDot daemons={daemons} stream={stream} onRefresh={onChanged} />
        </div>
      </aside>

      <section className="lp-pane">
        {standing ? (
          <div className="lp-pane-body">
            <Standing />
          </div>
        ) : selected ? (
          <WorkItemDetail
            view={selected}
            title={titleFor(selected.ref)}
            onChanged={onChanged}
            transcriptTick={transcriptTick}
            initialTraceRef={selectedRef !== selected.ref ? selectedRef : undefined}
          />
        ) : selectedRef && !loading ? (
          <div className="lp-pane-body">
            <div className="lp-empty">
              No work item <code className="lp-code">{selectedRef}</code> on this service.{" "}
              <a href={hrefFor({ name: "work" })}>Back to the overview</a>.
            </div>
          </div>
        ) : selectedRef ? (
          <div className="lp-pane-body">
            <div className="lp-empty">Loading…</div>
          </div>
        ) : (
          <div className="lp-pane-body">
            <Overview groups={groups} views={views} onChanged={onChanged} />
          </div>
        )}
      </section>
    </div>
  );
}

function ItemRow({ view, title, selected }: { view: WorkItemView; title: string | undefined; selected: boolean }) {
  const flag = rowFlag(view);
  return (
    <a
      className={`lp-side-row ${selected ? "current" : ""}`.trim()}
      href={hrefFor({ name: "work", ref: view.ref })}
      aria-current={selected ? "page" : undefined}
    >
      <SessionDot state={view.sessionState} small />
      <span className="lp-side-ref">{view.shortRef}</span>
      <span className="lp-side-when" title={view.lastActivity || undefined}>
        {relativeTime(view.lastActivity)}
      </span>
      <span className="lp-side-title">{title ?? positionLabel(view)}</span>
      {flag ? <span className="lp-side-flag">{flag.label}</span> : null}
    </a>
  );
}

/**
 * Where the item stands, for a row with no title to show. A live report names
 * the current node; an item whose graph cannot be read from here still says
 * which phases it agreed to walk, from the frozen rail (issue-283 B11), rather
 * than the dead-end "no graph state".
 */
function positionLabel(view: WorkItemView): string {
  if (view.currentNode) return `${view.currentNode} · ${view.progress}`;
  if (view.rail.length > 0) return `planned · ${view.progress}`;
  return "";
}

/** The main pane with nothing selected: the inbox, at full width. */
function Overview({ groups, views, onChanged }: { groups: AttentionGroup[]; views: WorkItemView[]; onChanged: () => void }) {
  const running = views.filter((view) => view.sessionState === "active").length;
  return (
    <>
      <h1 className="lp-h1">Inbox</h1>
      <p className="lp-subtle lp-overview-line">
        {views.length} work item{views.length === 1 ? "" : "s"} tracked · {running} running ·{" "}
        {groups.length === 0 ? "nothing is waiting on you" : `${groups.length} waiting on you`}
      </p>
      {groups.length === 0 ? (
        <div className="lp-empty">Nothing is waiting on you. Every session is running and no gate is parked.</div>
      ) : (
        <Inbox groups={groups} onChanged={onChanged} />
      )}
    </>
  );
}

/**
 * The inbox: one card per work item (feature #3), listing everything it needs
 * — the gate and its errors together — with the decision actionable on the
 * card (feature #2): a gate approves and a question answers right here, via
 * the same `POST /graph/complete` and `/sessions/reply` the detail page uses,
 * paper-trail comment posted by the service.
 */
function Inbox({ groups, onChanged, compact = false }: { groups: AttentionGroup[]; onChanged: () => void; compact?: boolean }) {
  if (groups.length === 0 && compact) {
    return <div className="lp-side-clear">Nothing is waiting on you.</div>;
  }
  const shown = compact ? groups.slice(0, 4) : groups;
  return (
    <div className={`lp-inbox ${compact ? "compact" : ""}`.trim()}>
      {shown.map((group) => (
        <InboxCard key={group.ref} group={group} onChanged={onChanged} compact={compact} />
      ))}
      {compact && groups.length > shown.length ? (
        <a className="lp-side-more" href={hrefFor({ name: "work" })}>
          {groups.length - shown.length} more in the inbox
        </a>
      ) : null}
    </div>
  );
}

function InboxCard({ group, onChanged, compact }: { group: AttentionGroup; onChanged: () => void; compact: boolean }) {
  const urgent = group.tier <= 1;
  return (
    <div className={`lp-inbox-card ${urgent ? "hot" : ""}`.trim()}>
      <div className="lp-inbox-head">
        <a className="lp-inbox-ref" href={hrefFor({ name: "work", ref: group.ref })}>
          {group.shortRef}
        </a>
        {group.at ? (
          <span className="lp-inbox-when" title={group.at}>
            {relativeTime(group.at)}
          </span>
        ) : null}
      </div>
      {group.entries.map((entry) => (
        <InboxEntry key={entry.key} entry={entry} onChanged={onChanged} compact={compact} />
      ))}
    </div>
  );
}

function InboxEntry({ entry, onChanged, compact }: { entry: AttentionEntry; onChanged: () => void; compact: boolean }) {
  return (
    <div className="lp-inbox-entry">
      <div className="lp-inbox-line">
        <span className="lp-inbox-kind">{entry.kind}</span>
        {entry.count > 1 ? <span className="lp-inbox-count">×{entry.count}</span> : null}
        {entry.at ? (
          <span className="lp-inbox-when" title={entry.at}>
            {relativeTime(entry.at)}
          </span>
        ) : null}
      </div>
      <div className="lp-inbox-detail">{compact ? truncate(entry.detail, 96) : entry.detail}</div>
      {/* The strip stays quiet: acting happens on the overview inbox or the
          item pane, both one click away. */}
      {compact ? null : <InboxAction entry={entry} onChanged={onChanged} />}
    </div>
  );
}

/** The action a card can take in place; anything else opens the item. */
function InboxAction({ entry, onChanged }: { entry: AttentionEntry; onChanged: () => void }) {
  const { api } = useApi();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reply, setReply] = useState("");

  async function run(action: () => Promise<unknown>): Promise<void> {
    setBusy(true);
    setError("");
    try {
      await action();
      onChanged();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.advice : String(cause));
    } finally {
      setBusy(false);
    }
  }

  if (entry.kind === "needs input") {
    return (
      <div className="lp-inbox-act">
        <textarea
          value={reply}
          rows={2}
          onChange={(event) => setReply(event.target.value)}
          placeholder="Answer — delivered into the session"
          aria-label={`Reply to ${entry.shortRef}`}
          disabled={busy}
        />
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy || !reply.trim()}
          onClick={() =>
            void run(async () => {
              await api.replySession(entry.ref, reply);
              setReply("");
            })
          }
        >
          {busy ? "Sending…" : "Send"}
        </button>
        {error ? <div className="lp-inbox-error">{error}</div> : null}
      </div>
    );
  }

  if (entry.gate) {
    const gate = entry.gate;
    return (
      <div className="lp-inbox-act">
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy || !gate.repo || !gate.workItem}
          title={gate.repo ? undefined : "No checkout recorded for this item on the service's machine."}
          onClick={() => void run(() => api.graphComplete(gate))}
        >
          {busy ? "Approving…" : "Approve"}
        </button>
        <a className="btn btn-ghost" href={hrefFor({ name: "work", ref: entry.ref })}>
          Review first
        </a>
        {error ? <div className="lp-inbox-error">{error}</div> : null}
      </div>
    );
  }

  return null;
}

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}
