/**
 * The Work screen (issue-283, redesigned by issue-298): a sidebar of work
 * items — dot, ref, age, title, and a small-caps chip when one needs a human
 * — with each item's pull requests nested beneath it (issue-300), standing
 * sessions under a hairline, and Settings plus the health dot in the footer,
 * beside one main canvas showing the selected item's trace. Nothing selected
 * shows the most recently active item, the way the signed-off design does
 * (docs/specs/issue-298/design/).
 *
 * The sidebar is the whole navigation: the owner's direction on the redesign
 * (PR #299) is a clean surface of exactly the sidebar, the canvas and the
 * Settings page — the earlier inbox strip, overview inbox and group headers
 * were projections of what the rows' chips and the detail's cards already
 * say, so they are gone rather than restyled. The nesting issue-300 adds is
 * not another projection: a PR's inner loop is a session of its own, and it
 * had no row anywhere on this surface.
 *
 * One ref selects, whichever level it names — the hash is the single source
 * of truth for what the canvas shows, so a PR row and the canvas's trace tabs
 * are the same navigation and cannot disagree.
 */

import {
  relativeTime,
  rowFlag,
  sessionTree,
  type SessionNode,
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

  // Work items newest activity first — the design's ordering. `sessionTree`
  // hangs each item's PR sessions off it, and leaves an ad-hoc / contribution
  // / review item treeless, because those loops run no outer/inner split.
  const sorted = [...views].toSorted((a, b) => (b.lastActivity || "").localeCompare(a.lastActivity || ""));
  const tree = sessionTree(sorted);
  // With no ref in the hash the canvas shows the most recent item, the way
  // the design always has something on the canvas; a deep link still wins.
  const selected = selectedRef ? findOwner(views, selectedRef) : sorted[0];
  // What the hash actually selects, resolved: the ref itself, or — with an
  // empty hash — the item the canvas fell back to. One value drives both the
  // highlighted row and the trace the canvas opens on.
  const activeRef = standing ? "" : selectedRef || selected?.ref || "";

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
          {tree.map(({ view, inner }) => (
            <div className="lp-side-item" key={view.ref}>
              <ItemRow
                view={view}
                title={titleFor(view.ref)}
                selected={activeRef === view.ref}
                // A selected PR leaves its work item unhighlighted, which reads
                // as "nothing is open" even though the canvas is showing that
                // item. The parent keeps a lighter marker instead.
                owner={inner.some((pr) => pr.ref === activeRef)}
              />
              {inner.length > 0 ? (
                <ul className="lp-side-prs" aria-label={`Pull requests for ${view.shortRef}`}>
                  {inner.map((pr) => (
                    <li key={pr.ref}>
                      <PullRequestRow node={pr} selected={activeRef === pr.ref} />
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
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
            traceRef={activeRef || selected.ref}
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

function ItemRow({
  view,
  title,
  selected,
  owner,
}: {
  view: WorkItemView;
  title: string | undefined;
  selected: boolean;
  /** One of this item's PRs is the selected row — the canvas is on this item. */
  owner: boolean;
}) {
  const flag = rowFlag(view);
  return (
    <a
      className={["lp-side-row", selected && "current", owner && "owner"].filter(Boolean).join(" ")}
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
 * One pull request under its work item: the PR's own session, selectable.
 *
 * Deliberately quieter than the row above it — dot, number, age, no title and
 * no chip. The nesting is what says which item the PR belongs to, and the
 * work item's own row already carries the attention that needs a human.
 */
function PullRequestRow({ node, selected }: { node: SessionNode; selected: boolean }) {
  return (
    <a
      className={["lp-side-row", "lp-side-pr", selected && "current"].filter(Boolean).join(" ")}
      href={hrefFor({ name: "work", ref: node.ref })}
      aria-current={selected ? "page" : undefined}
    >
      <SessionDot state={node.state} small />
      <span className="lp-side-ref">{node.label}</span>
      <span className="lp-side-when" title={node.lastActivity || undefined}>
        {relativeTime(node.lastActivity)}
      </span>
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
