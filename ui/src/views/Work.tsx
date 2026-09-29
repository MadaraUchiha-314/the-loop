/**
 * The Work surface (issue-327): the sidebar, the main column and the session
 * panel, side by side in a viewport-locked shell. The main column shows the
 * selected work item — or the most recently active one when nothing is
 * selected — or, on `#/standing`, `#/settings`, `#/instances` and
 * `#/instances/<name>`, those panes; the sidebar is the navigation in every
 * case, and the session panel appears only beside a work item.
 *
 * One ref selects, whichever level it names: the hash is the single source of
 * truth for what the column shows, so a PR row in the sidebar and a session
 * tab are the same navigation and cannot disagree (issue-300). On a fleet the
 * hash may also name the instance (`@<instance>`, issue-374), which picks one
 * of the rows a ref present on two instances gets; without it the first row
 * by that ref is shown, which on a worker is the only one.
 */

import type { WorkItemView } from "../api/model.ts";
import type { DaemonStatus, InstancesDocument } from "../api/types.ts";
import type { Chrome } from "../components/HeaderBar.tsx";
import { HeaderBar } from "../components/HeaderBar.tsx";
import { Empty } from "../components/primitives.tsx";
import { SessionAside } from "../components/SessionAside.tsx";
import { Sidebar } from "../components/Sidebar.tsx";
import { useApi } from "../state/ApiContext.tsx";
import { hrefFor, type Surface } from "../state/route.ts";
import { useAsync } from "../state/useAsync.ts";
import type { StreamState } from "../state/useStream.ts";
import { InstanceDetail } from "./InstanceDetail.tsx";
import { Instances } from "./Instances.tsx";
import { Settings } from "./Settings.tsx";
import { Standing } from "./Standing.tsx";
import { railNote, resolveViewed, WorkItemDetail } from "./WorkItemDetail.tsx";

export type { Surface };

export interface Panels {
  sidebarOpen: boolean;
  asideOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  setAsideOpen: (open: boolean) => void;
}

interface WorkProps {
  views: WorkItemView[];
  loading: boolean;
  titleFor: (ref: string) => string | undefined;
  /** The selected work item or session ref, or `""` for "the newest one". */
  selectedRef: string;
  /** The instance the hash named beside the ref (`""` when it named none). */
  selectedInstance?: string;
  surface: Surface;
  /** On `#/instances/<name>`: which instance the pane manages. */
  instanceName?: string;
  onChanged: () => void;
  transcriptTick: number;
  daemons: DaemonStatus[];
  /** The fleet (issue-374), for the sidebar's filter, chips and health word. */
  instances: InstancesDocument;
  instanceFilter?: string;
  onInstanceFilter?: ((instance: string) => void) | undefined;
  stream: StreamState;
  chrome: Chrome;
  panels: Panels;
  serviceLabel: string;
}

/**
 * The view that owns `ref` — the item itself, or the item whose PR it is —
 * on `instance` when one was named, else the first row by that ref.
 */
export function findOwner(views: WorkItemView[], ref: string, instance = ""): WorkItemView | undefined {
  const owns = (view: WorkItemView) => view.ref === ref || view.pullRequests.some((pr) => pr.ref === ref);
  return views.find((view) => owns(view) && (!instance || view.instance === instance));
}

export function Work({
  views,
  loading,
  titleFor,
  selectedRef,
  selectedInstance = "",
  surface,
  instanceName = "",
  onChanged,
  transcriptTick,
  daemons,
  instances,
  instanceFilter = "",
  onInstanceFilter,
  stream,
  chrome,
  panels,
  serviceLabel,
}: WorkProps) {
  const { api } = useApi();
  const standingSessions = useAsync((signal) => api.standingSessions(signal), [api]);

  const sorted = [...views].toSorted((a, b) => (b.lastActivity || "").localeCompare(a.lastActivity || ""));
  const selected = selectedRef ? findOwner(views, selectedRef, selectedInstance) : sorted[0];
  const activeRef = surface === "work" ? selectedRef || selected?.ref || "" : "";
  const activeInstance = surface === "work" ? (selected?.instance ?? "") : "";
  const showAside = surface === "work" && selected !== undefined && panels.asideOpen;
  const chromeForPane: Chrome =
    surface === "work"
      ? { ...chrome, asideOpen: panels.asideOpen, onOpenAside: () => panels.setAsideOpen(true) }
      : chrome;

  return (
    <div className="relative flex min-h-0 flex-1">
      {panels.sidebarOpen ? (
        <Sidebar
          views={sorted}
          loading={loading}
          titleFor={titleFor}
          activeRef={activeRef}
          activeInstance={activeInstance}
          surface={surface}
          standingSessions={standingSessions.data ?? []}
          daemons={daemons}
          stream={stream}
          instances={instances}
          instanceFilter={instanceFilter}
          onInstanceFilter={onInstanceFilter}
          onRefresh={onChanged}
          onCollapse={() => panels.setSidebarOpen(false)}
          serviceLabel={serviceLabel}
        />
      ) : null}

      <main className="flex min-w-0 flex-1 flex-col">
        {surface === "settings" ? (
          <Settings chrome={chromeForPane} />
        ) : surface === "standing" ? (
          <Standing chrome={chromeForPane} onChanged={() => standingSessions.reload()} />
        ) : surface === "instances" ? (
          <Instances chrome={chromeForPane} onChanged={onChanged} />
        ) : surface === "instance" ? (
          <InstanceDetail key={instanceName} chrome={chromeForPane} name={instanceName} onChanged={onChanged} />
        ) : selected ? (
          <WorkItemDetail
            // Keyed by board key so switching items — or instances — remounts
            // the column: the viewed trace and any in-flight action state
            // belong to one row.
            key={selected.key}
            view={selected}
            title={titleFor(selected.ref)}
            onChanged={onChanged}
            transcriptTick={transcriptTick}
            traceRef={activeRef || selected.ref}
            chrome={chromeForPane}
          />
        ) : (
          <>
            <HeaderBar chrome={chromeForPane} title="the-loop" meta={<span>control plane</span>} />
            <div className="px-6 py-6">
              {selectedRef && !loading ? (
                <Empty>
                  No work item <code className="ref-chip">{selectedRef}</code>
                  {selectedInstance ? (
                    <>
                      {" "}
                      on <code className="ref-chip">{selectedInstance}</code>
                    </>
                  ) : null}{" "}
                  on this service.{" "}
                  <a href={hrefFor({ name: "work" })} className="text-foreground underline-offset-2 hover:underline">
                    Back to the board
                  </a>
                  .
                </Empty>
              ) : (
                <Empty>{loading ? "Loading…" : "Nothing to show yet — the column fills once a work item is tracked."}</Empty>
              )}
            </div>
          </>
        )}
      </main>

      {showAside && selected ? (
        <SessionAside
          key={selected.key}
          view={selected}
          viewed={resolveViewed(selected, activeRef || selected.ref)}
          note={railNote(selected)}
          onChanged={onChanged}
          onClose={() => panels.setAsideOpen(false)}
        />
      ) : null}
    </div>
  );
}
