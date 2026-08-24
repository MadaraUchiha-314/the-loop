/**
 * The Sessions screen (issue-230): every work item in a sidebar, each opening
 * into its sessions as a two-level tree — the outer loop's session, then one
 * child per PR inner loop — with the selected session's stream in the main
 * pane and a chat bar that delivers into that session's tmux pane.
 *
 * Ad-hoc, contribution and review work items (`pdlc-adhoc-loop`,
 * `pdlc-contribution-loop`, `pdlc-review-loop`) run no outer/inner split, so
 * they render as a single selectable row with no tree.
 *
 * The selected session is the route (`#/sessions/<ref>`), so a stream can be
 * linked to; the owning work item is derived from the tree, never stored.
 */

import { ApiError } from "../api/client.ts";
import {
  describeEvent,
  eventRef,
  sessionTree,
  timeOf,
  transcriptPath,
  type SessionNode,
  type SessionTreeItem,
  type WorkItemView,
} from "../api/model.ts";
import type { EventRecord, SessionEndpoint } from "../api/types.ts";
import { Blueprint } from "../components/Blueprint.tsx";
import { SessionDot } from "../components/SessionDot.tsx";
import { ChatBar, TranscriptView } from "../components/Transcript.tsx";
import { useApi } from "../state/ApiContext.tsx";
import { hrefFor } from "../state/route.ts";
import { useAsync } from "../state/useAsync.ts";

interface SessionsProps {
  views: WorkItemView[];
  loading: boolean;
  titleFor: (ref: string) => string | undefined;
  selectedRef: string | undefined;
  onChanged: () => void;
}

/** The tree item and node a session ref belongs to, or null. */
function findSelected(
  tree: SessionTreeItem[],
  ref: string | undefined,
): { item: SessionTreeItem; node: SessionNode } | null {
  if (!ref) return null;
  for (const item of tree) {
    if (item.outer.ref === ref) return { item, node: item.outer };
    const inner = item.inner.find((node) => node.ref === ref);
    if (inner) return { item, node: inner };
  }
  return null;
}

/** The session endpoint record behind a tree node — for the path caption. */
function endpointOf(item: SessionTreeItem, node: SessionNode): SessionEndpoint | null {
  if (node.scope === "outer") return item.view.session;
  return item.view.pullRequests.find((pr) => pr.ref === node.ref)?.session ?? null;
}

export function Sessions({ views, loading, titleFor, selectedRef, onChanged }: SessionsProps) {
  const tree = sessionTree(views);
  const selected = findSelected(tree, selectedRef) ?? (tree[0] ? { item: tree[0], node: tree[0].outer } : null);

  return (
    <div className="lp-sessions">
      <aside className="lp-sessions-side">
        <div className="lp-sessions-side-head">Work items</div>
        {loading && tree.length === 0 ? <div className="lp-empty">Loading…</div> : null}
        {!loading && tree.length === 0 ? <div className="lp-empty">No work items on this service.</div> : null}
        {tree.map((item) => (
          <SidebarItem
            key={item.view.ref}
            item={item}
            title={titleFor(item.view.ref)}
            selectedRef={selected?.node.ref}
          />
        ))}
      </aside>
      <section className="lp-sessions-main">
        {selected ? (
          <SessionStream item={selected.item} node={selected.node} onChanged={onChanged} />
        ) : (
          <div className="lp-empty">Select a work item to read its sessions.</div>
        )}
      </section>
    </div>
  );
}

function SidebarItem({
  item,
  title,
  selectedRef,
}: {
  item: SessionTreeItem;
  title: string | undefined;
  selectedRef: string | undefined;
}) {
  const owns = item.outer.ref === selectedRef || item.inner.some((node) => node.ref === selectedRef);
  return (
    <div className={`lp-sessions-item ${owns ? "selected" : ""}`.trim()}>
      {/* The header row *is* the outer session for an ad-hoc item — one
          session, no tree; otherwise it links to the outer loop's stream and
          the tree hangs beneath it. */}
      <a
        className={`lp-sessions-row lp-sessions-head ${item.outer.ref === selectedRef ? "current" : ""}`.trim()}
        href={hrefFor({ name: "sessions", ref: item.outer.ref })}
        aria-current={item.outer.ref === selectedRef ? "page" : undefined}
      >
        <SessionDot state={item.outer.state} small />
        <span className="lp-sessions-ref">{item.view.shortRef}</span>
        <span className="lp-sessions-title">{title ?? ""}</span>
      </a>
      {item.treeless ? (
        <div className="lp-sessions-adhoc">{item.view.record.graph?.loop}</div>
      ) : owns ? (
        <div className="lp-sessions-tree">
          <a
            className={`lp-sessions-row ${item.outer.ref === selectedRef ? "current" : ""}`.trim()}
            href={hrefFor({ name: "sessions", ref: item.outer.ref })}
            aria-current={item.outer.ref === selectedRef ? "page" : undefined}
          >
            <SessionDot state={item.outer.state} small />
            outer loop · {item.view.record.graph?.loop ?? "pdlc-work-item-loop"}
          </a>
          {item.inner.map((node) => (
            <a
              key={node.ref}
              className={`lp-sessions-row lp-sessions-inner ${node.ref === selectedRef ? "current" : ""}`.trim()}
              href={hrefFor({ name: "sessions", ref: node.ref })}
              aria-current={node.ref === selectedRef ? "page" : undefined}
            >
              <SessionDot state={node.state} small />
              {node.shortRef} · pdlc-pr-loop
            </a>
          ))}
          {item.inner.length === 0 ? <div className="lp-sessions-none">no inner loops yet</div> : null}
        </div>
      ) : null}
    </div>
  );
}

/** The selected session's stream, its caption, and the chat bar under it. */
function SessionStream({
  item,
  node,
  onChanged,
}: {
  item: SessionTreeItem;
  node: SessionNode;
  onChanged: () => void;
}) {
  const { api } = useApi();
  const transcript = useAsync((signal) => api.transcript(node.ref, 200, signal), [api, node.ref]);
  const events = useAsync(
    (signal) => api.events({ workItem: item.view.ref, limit: 200 }, signal),
    [api, item.view.ref],
  );

  return (
    <>
      <div className="lp-trace-head">
        <h2 className="lp-h2">
          {node.shortRef} · {node.scope === "outer" ? "outer loop" : "inner loop"}
        </h2>
        {node.tmuxTarget ? (
          <span className="lp-subtle">
            tmux <code className="lp-code">{node.tmuxTarget}</code>
          </span>
        ) : null}
        <span className="lp-trace-source">
          {transcriptPath(endpointOf(item, node)) ?? "no derivable transcript path"}
        </span>
      </div>

      <Blueprint className="lp-trace lp-sessions-trace">
        {/* Same ordering rule as the work-item trace panel: `useAsync` holds
            the previous selection's data while loading or after an error, and
            that stale data must not be drawn. */}
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
                .filter((event) => (node.scope === "outer" ? true : eventRef(event) === node.ref))
                .toReversed()
                .slice(0, 40)
                .map((event, index) => <EventTraceRow key={`${event.ts}-${index}`} event={event} />)
            ) : (
              <div className="lp-empty">No events recorded for this work item.</div>
            )}
          </>
        )}
      </Blueprint>

      <ChatBar refFor={node.ref} state={node.state} onSent={onChanged} />
    </>
  );
}

function EventTraceRow({ event }: { event: EventRecord }) {
  return (
    <div className="lp-trace-entry">
      <div className="lp-trace-kind">
        {event.event}
        <div className="lp-trace-ts">{timeOf(event.ts)}</div>
      </div>
      <div className="lp-trace-main">
        <div className="lp-trace-text">{describeEvent(event)}</div>
      </div>
    </div>
  );
}
