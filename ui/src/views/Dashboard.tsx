/**
 * Every tracked work item, one row each: where it is in the loop, whether a
 * session is alive, which PRs are delivering it and how long since anything
 * happened. Above it, the attention strip — the four things most worth clicking.
 */

import { attentionEntries, relativeTime, type WorkItemView, rowFlag } from "../api/model.ts";
import { Blueprint } from "../components/Blueprint.tsx";
import { SessionDot, sessionLabel } from "../components/SessionDot.tsx";
import { navigate } from "../state/route.ts";

interface DashboardProps {
  views: WorkItemView[];
  loading: boolean;
  titleFor: (ref: string) => string | undefined;
}

export function Dashboard({ views, loading, titleFor }: DashboardProps) {
  const strip = attentionEntries(views).slice(0, 4);

  return (
    <>
      {strip.length > 0 ? (
        <div className="lp-strip">
          {strip.map((entry) => (
            <Blueprint
              as="button"
              type="button"
              key={entry.key}
              className={`lp-strip-card ${entry.urgent ? "hot" : ""}`.trim()}
              onClick={() => navigate({ name: "detail", ref: entry.ref })}
            >
              <div className="lp-strip-kind">{entry.kind}</div>
              <div className="lp-strip-ref">{entry.shortRef}</div>
              <div className="lp-strip-detail">{truncate(entry.detail, 96)}</div>
            </Blueprint>
          ))}
        </div>
      ) : null}

      <div className="lp-page-head">
        <h1 className="lp-h1">Work items</h1>
        <span className="lp-subtle">
          {views.length} tracked · from /api/v1/work-items + /sessions, position from /graph/check
        </span>
      </div>

      {loading && views.length === 0 ? (
        <div className="lp-skeleton">Loading the board…</div>
      ) : views.length === 0 ? (
        <div className="lp-skeleton">
          Nothing is being tracked on this machine. A work item appears here once the poller or the webhook receiver
          sees a control keyword on its ticket, or after <code className="lp-code">the-loop sessions register</code>.
        </div>
      ) : (
        <table className="table lp-table">
          <thead>
            <tr>
              <th scope="col">Work item</th>
              <th scope="col">Title</th>
              <th scope="col">Loop position</th>
              <th scope="col">Session</th>
              <th scope="col">PRs</th>
              <th scope="col">Last activity</th>
            </tr>
          </thead>
          <tbody>
            {views.map((view) => (
              <Row key={view.ref} view={view} title={titleFor(view.ref)} />
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

function Row({ view, title }: { view: WorkItemView; title: string | undefined }) {
  const flag = rowFlag(view);
  const open = () => navigate({ name: "detail", ref: view.ref });

  return (
    <tr
      className="lp-row"
      onClick={open}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          open();
        }
      }}
      tabIndex={0}
      role="link"
      aria-label={`Open ${view.shortRef}`}
    >
      <td className="lp-td-ref">
        {view.shortRef}
        {flag ? <span className={`lp-flag ${flag.urgent ? "lp-pulse" : ""}`.trim()}>{flag.label}</span> : null}
      </td>
      <td className="lp-td-title">
        {title ?? (
          <a href={view.url} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()}>
            open on GitHub ↗
          </a>
        )}
      </td>
      <td className="lp-td-nowrap">
        {view.currentNode ? (
          <>
            <span className="tag tag-accent">{view.currentNode}</span>
            <span className="lp-progress">{view.progress}</span>
          </>
        ) : (
          <span className="lp-subtle">no graph state</span>
        )}
      </td>
      <td className="lp-td-nowrap">
        <SessionDot state={view.sessionState} />
        {sessionLabel(view.sessionState, view.session?.harness)}
      </td>
      <td className="lp-td-prs">
        {view.pullRequests.length === 0
          ? "—"
          : view.pullRequests
              .map((pr) => `${pr.shortRef} ${pr.status?.currentNode ?? "?"}`)
              .join(" · ")}
      </td>
      <td className="lp-td-dim">{relativeTime(view.lastActivity)}</td>
    </tr>
  );
}

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}
