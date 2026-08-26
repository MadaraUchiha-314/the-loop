/**
 * The Work screen (issue-283, redesigned by issue-298): one flat sidebar of
 * work items — dot, ref, age, title, and a small-caps chip when one needs a
 * human — with standing sessions under a hairline and Settings plus the
 * health dot in the footer, beside one main canvas showing the selected
 * item's trace. Nothing selected shows the most recently active item, the
 * way the signed-off design does (docs/specs/issue-298/design/).
 *
 * The sidebar is the whole navigation: the owner's direction on the redesign
 * (PR #299) is a clean surface of exactly the sidebar, the canvas and the
 * Settings page — the earlier inbox strip, overview inbox and group headers
 * were projections of what the rows' chips and the detail's cards already
 * say, so they are gone rather than restyled.
 */

import {
  relativeTime,
  rowFlag,
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

interface WorkProps {
  views: WorkItemView[];
  loading: boolean;
  titleFor: (ref: string) => string | undefined;
  /** The selected work item or session ref, or `""` for "the newest one". */
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
  const standingSessions = useAsync((signal) => api.standingSessions(signal), [api]);

  // One flat list, newest activity first — the design's ordering.
  const sorted = [...views].toSorted((a, b) => (b.lastActivity || "").localeCompare(a.lastActivity || ""));
  // With no ref in the hash the canvas shows the most recent item, the way
  // the design always has something on the canvas; a deep link still wins.
  const selected = selectedRef ? findOwner(views, selectedRef) : sorted[0];

  return (
    <div className="lp-work">
      <aside className="lp-side">
        <a className="lp-side-brand" href={hrefFor({ name: "work" })}>
          <div className="lp-side-brand-name">the-loop</div>
          <div className="lp-side-brand-sub">Control plane</div>
        </a>

        <div className="lp-side-scroll">
          <div className="lp-side-head">Work items</div>
          {loading && views.length === 0 ? <div className="lp-empty lp-side-banner">Loading…</div> : null}
          {!loading && views.length === 0 ? (
            <div className="lp-empty lp-side-banner">
              Nothing is tracked on this machine yet. A work item appears once the poller or webhook receiver sees a
              control keyword on its ticket, or after <code className="lp-code">the-loop sessions register</code>.
            </div>
          ) : null}
          {sorted.map((view) => (
            <ItemRow
              key={view.ref}
              view={view}
              title={titleFor(view.ref)}
              selected={selected?.ref === view.ref && !standing}
            />
          ))}

          <section className="lp-side-group">
            <div className="lp-side-head">Standing sessions</div>
            {(standingSessions.data ?? []).map((session) => (
              <a
                key={session.name}
                className={`lp-side-row ${standing ? "current" : ""}`.trim()}
                href={hrefFor({ name: "standing" })}
              >
                <span className={`lp-health-dot ${session.running ? "ok" : "unknown"}`} aria-hidden="true" />
                <span className="lp-side-standing">
                  {session.name}
                  {session.description ? (
                    <span className="lp-side-desc"> — {session.description}</span>
                  ) : null}
                </span>
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
            // Keyed by ref so switching items remounts the pane: the viewed
            // trace and any in-flight action state belong to one item.
            key={selected.ref}
            view={selected}
            title={titleFor(selected.ref)}
            onChanged={onChanged}
            transcriptTick={transcriptTick}
            initialTraceRef={selectedRef && selectedRef !== selected.ref ? selectedRef : undefined}
          />
        ) : selectedRef && !loading ? (
          <div className="lp-pane-body">
            <div className="lp-empty">
              No work item <code className="lp-code">{selectedRef}</code> on this service.{" "}
              <a href={hrefFor({ name: "work" })}>Back to the board</a>.
            </div>
          </div>
        ) : (
          <div className="lp-pane-body">
            <div className="lp-empty">
              {loading ? "Loading…" : "Nothing to show yet — the canvas fills once a work item is tracked."}
            </div>
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
