/**
 * The inbox.
 *
 * `/api/v1/attention` answers what the machine's own state knows — paused
 * sessions, armed items with no session, recent errors from the event log — and
 * documents that graph-gate waits are *not* in it, because they live in each
 * checkout's `graph-state.json`. The board has already read those reports for
 * the rails, so `attentionEntries` folds them back in and this page is the union.
 */

import { attentionEntries, type WorkItemView } from "../api/model.ts";
import { Blueprint } from "../components/Blueprint.tsx";
import { hrefFor } from "../state/route.ts";

export function Attention({ views }: { views: WorkItemView[] }) {
  const entries = attentionEntries(views);

  return (
    <>
      <h1 className="lp-h1">Needs attention</h1>
      <div className="lp-subtle lp-page-note">
        from /api/v1/attention, plus the graph gates it deliberately leaves out (they are repo-scoped, so they come from
        /graph/check per item)
      </div>

      {entries.length === 0 ? (
        <div className="lp-skeleton">Nothing is waiting on you. Every session is running and no gate is parked.</div>
      ) : (
        <div className="lp-inbox">
          {entries.map((entry) => (
            <Blueprint key={entry.key} className={`lp-inbox-card ${entry.urgent ? "hot" : ""}`.trim()}>
              <div className="lp-inbox-main">
                <div className="lp-inbox-head">
                  <span className="lp-inbox-kind">{entry.kind}</span>
                  <span className="lp-inbox-ref">{entry.shortRef}</span>
                </div>
                <div className="lp-inbox-detail">{entry.detail}</div>
              </div>
              <a className="btn btn-secondary" href={hrefFor({ name: "detail", ref: entry.ref })}>
                {entry.action}
              </a>
            </Blueprint>
          ))}
        </div>
      )}
    </>
  );
}
