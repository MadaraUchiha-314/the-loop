/**
 * The design's left column (issue-327), de-cluttered to issue-511's Option C:
 * the brand row with the collapse control and a search toggle, the surface
 * nav, the finder (search box, and the instance filter on a fleet) behind that
 * toggle, work items in two groups — **Needs you**, with its count, and
 * **Everything else** by last activity — as one-line rows that carry what is
 * needed to choose (dot, number, title, and a flag only when the item needs a
 * human), the selected item's pull requests nested beneath it (issue-300),
 * and a footer with the Settings link, the service line and the health word.
 * The standing sessions live on the Standing surface the nav reaches.
 *
 * Every row is an anchor on the hash: the hash is the one record of what the
 * main column shows, so a sidebar row and a session tab are the same
 * navigation and cannot disagree (issue-300).
 *
 * On a manager the board is a fleet (issue-374, R5.2): each row that a
 * manager stamped carries an instance chip, a native `<select>` in the finder
 * filters the loaded rows to one instance, and a row's hash names its
 * instance so a work item present on two instances is two rows, each
 * addressable. A worker's rows carry no stamp and none of this renders.
 */

import { useState } from "react";

import { rowFlag, sessionTree, type SessionNode, type WorkItemView } from "../api/model.ts";
import type { DaemonStatus, InstancesDocument } from "../api/types.ts";
import { hrefFor, itemHref, type Surface } from "../state/route.ts";
import type { StreamState } from "../state/useStream.ts";
import { filterViews, itemStatus, minimalGroup, SIDEBAR_GROUPS_MINIMAL, sortByActivity } from "../views/grouping.ts";
import { GitPullRequestIcon, PanelLeftCloseIcon, RadioIcon, SearchIcon, SettingsIcon } from "./Icons.tsx";
import { HealthDot } from "./Nav.tsx";
import { IconButton, InstanceChip, Kicker } from "./primitives.tsx";
import { sessionDot, StatusDot, STATUS_TEXT } from "./StatusDot.tsx";

interface SidebarProps {
  views: WorkItemView[];
  loading: boolean;
  titleFor: (ref: string) => string | undefined;
  /** The ref the hash selects, resolved — a work item's or one of its PRs'. */
  activeRef: string;
  /** The instance of the selected row (`""` on a worker), so only that row highlights. */
  activeInstance?: string;
  /** Which surface is current. */
  surface: Surface;
  daemons: DaemonStatus[];
  stream: StreamState;
  /** The fleet (issue-374): decides whether the filter and the chips render. */
  instances?: InstancesDocument | undefined;
  /** The instance filter: `""` for all, else one instance's name. */
  instanceFilter?: string;
  onInstanceFilter?: ((instance: string) => void) | undefined;
  onRefresh: () => void;
  onCollapse: () => void;
  /** The footer's service line: the base URL's host, or the demo. */
  serviceLabel: string;
}

/** Whether the fleet is worth a filter: more than one row, or a manager (even one with no members yet). */
export function showsFleet(instances: InstancesDocument | undefined): boolean {
  return instances !== undefined && (instances.instances.length > 1 || instances.role === "manager");
}

/** The `<option>` text for one instance: its name, plus why it is worth knowing. */
export function instanceOption(row: InstancesDocument["instances"][number], own: boolean): string {
  if (own) return `${row.name} · this instance`;
  return row.state === "live" ? row.name : `${row.name} · ${row.state}`;
}

export function Sidebar({
  views,
  loading,
  titleFor,
  activeRef,
  activeInstance = "",
  surface,
  daemons,
  stream,
  instances,
  instanceFilter = "",
  onInstanceFilter,
  onRefresh,
  onCollapse,
  serviceLabel,
}: SidebarProps) {
  const [query, setQuery] = useState("");
  // The finder starts closed (issue-511 row 3): the rows are the list.
  const [finderOpen, setFinderOpen] = useState(false);
  const fleet = showsFleet(instances);
  const byInstance = fleet && instanceFilter ? views.filter((view) => view.instance === instanceFilter) : views;
  const shown = filterViews(byInstance, query, titleFor);
  const tree = sessionTree(shown);

  const navLink = (target: Surface, href: string, label: string) => (
    <a
      href={href}
      aria-current={surface === target ? "page" : undefined}
      className={`rounded-md px-2 py-1 text-xs transition-colors ${
        surface === target ? "bg-surface-2 text-foreground" : "text-muted-foreground hover:bg-surface-2/60 hover:text-foreground"
      }`}
    >
      {label}
    </a>
  );

  return (
    <aside
      className="flex h-full w-[19rem] shrink-0 flex-col border-r border-border bg-surface max-md:absolute max-md:inset-y-0 max-md:left-0 max-md:z-20"
      aria-label="Work items"
    >
      <div className="flex items-center justify-between px-4 pt-4">
        <a href={hrefFor({ name: "work" })} className="flex items-center gap-2">
          <span className="grid h-6 w-6 place-items-center rounded-md bg-primary text-primary-foreground">
            <RadioIcon className="h-3.5 w-3.5" />
          </span>
          <span className="font-display text-sm font-semibold tracking-tight">the-loop</span>
        </a>
        <div className="flex items-center gap-1">
          <IconButton label="Search and filter" expanded={finderOpen} active={finderOpen} onClick={() => setFinderOpen((value) => !value)}>
            <SearchIcon className="h-4 w-4" />
          </IconButton>
          <IconButton label="Collapse sidebar" onClick={onCollapse}>
            <PanelLeftCloseIcon className="h-4 w-4" />
          </IconButton>
        </div>
      </div>

      <nav className="flex items-center gap-1 px-3 pt-3" aria-label="Surfaces">
        {navLink("work", hrefFor({ name: "work" }), "Work")}
        {navLink("standing", hrefFor({ name: "standing" }), "Standing")}
        {navLink("instances", hrefFor({ name: "instances" }), "Instances")}
      </nav>

      {finderOpen ? (
        <div className="space-y-2 px-3 pt-3">
          <label className="flex items-center gap-2 rounded-lg border border-border bg-background px-3 py-1.5 focus-within:border-border-strong">
            <SearchIcon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search work items"
              aria-label="Search work items"
              autoComplete="off"
              className="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            />
          </label>
          {/* The instance filter (R5.2): a native <select>, over the loaded rows
              only — it asks the service for nothing. Present only when there is
              a fleet to filter (R2.6), so a worker's finder is the search box. */}
          {fleet && instances ? (
            <select
              aria-label="Instance filter"
              value={instanceFilter}
              onChange={(event) => onInstanceFilter?.(event.target.value)}
              className="w-full rounded-lg border border-border bg-background px-2 py-1.5 font-mono text-[0.72rem] text-foreground outline-none focus:border-border-strong"
            >
              <option value="">All instances ({instances.instances.length})</option>
              {instances.instances.map((row) => (
                <option key={row.name} value={row.name}>
                  {instanceOption(row, row.name === instances.name)}
                </option>
              ))}
            </select>
          ) : null}
        </div>
      ) : null}

      <nav className="scroll-thin mt-4 flex-1 overflow-y-auto px-2 pb-4" aria-label="Board">
        {loading && views.length === 0 ? <p className="px-2 py-4 text-xs text-muted-foreground">Loading…</p> : null}
        {!loading && views.length === 0 ? (
          <p className="px-2 py-4 text-xs leading-relaxed text-muted-foreground">
            Nothing is tracked on this machine yet. A work item appears once the poller or webhook receiver sees a control
            keyword on its ticket, or after <code className="ref-chip">the-loop sessions register</code>.
          </p>
        ) : null}
        {views.length > 0 && shown.length === 0 ? (
          <p className="px-2 py-4 text-xs text-muted-foreground">
            {query
              ? `No work item matches “${query}”${fleet && instanceFilter ? ` on ${instanceFilter}` : ""}.`
              : `No work item on ${instanceFilter}.`}
          </p>
        ) : null}

        {SIDEBAR_GROUPS_MINIMAL.map((group) => {
          const members = tree.filter(({ view }) => minimalGroup(view) === group.key);
          // Everything else by last activity (row 16); Needs you keeps the board's order.
          const items =
            group.key === "everything"
              ? sortByActivity(members.map(({ view, inner }) => ({ view, inner, lastActivity: view.lastActivity, ref: view.ref })))
              : members;
          if (items.length === 0) return null;
          return (
            <div className="mb-4" key={group.key}>
              <div className="flex items-center justify-between px-2 pb-1.5">
                <Kicker>{group.title}</Kicker>
                {/* The one count that changes what you do (R2.4). */}
                {group.key === "needs-you" ? <span className="text-[0.68rem] text-muted-foreground">{items.length}</span> : null}
              </div>
              <ul className="space-y-0.5">
                {items.map(({ view, inner }) => {
                  const selected = activeRef === view.ref && activeInstance === view.instance;
                  const owner = activeInstance === view.instance && inner.some((pr) => pr.ref === activeRef);
                  return (
                    <li key={view.key}>
                      <ItemRow view={view} title={titleFor(view.ref)} selected={selected} owner={owner} />
                      {/* PR rows nest under the selected item only (row 13): the
                          tab bar lists them once the item is open. */}
                      {inner.length > 0 && (selected || owner) ? (
                        <ul className="mt-0.5 space-y-0.5 pl-[1.1rem]" aria-label={`Pull requests for ${view.shortRef}`}>
                          {inner.map((pr) => (
                            <li key={pr.ref}>
                              <PullRequestRow
                                node={pr}
                                instance={view.instance}
                                selected={activeRef === pr.ref && activeInstance === view.instance}
                              />
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </nav>

      <div className="flex items-center gap-2 border-t border-border px-4 py-3">
        <IconButton label="Settings" href={hrefFor({ name: "settings" })} active={surface === "settings"}>
          <SettingsIcon className="h-4 w-4" />
        </IconButton>
        <div className="min-w-0 flex-1 leading-tight">
          <a href={hrefFor({ name: "settings" })} className="block truncate text-xs hover:text-foreground">
            Settings
          </a>
          <div className="truncate font-mono text-[0.65rem] text-muted-foreground" title={serviceLabel}>
            {serviceLabel}
          </div>
        </div>
        <HealthDot daemons={daemons} stream={stream} instances={instances} onRefresh={onRefresh} />
      </div>
    </aside>
  );
}

/**
 * One line: dot · `#n` · title · (instance chip on a fleet) · the flag when the
 * item needs a human (R2.2). The accessible name carries the number, the
 * title and that flag (R6.2); the header has the full title.
 */
function ItemRow({
  view,
  title,
  selected,
  owner,
}: {
  view: WorkItemView;
  title: string | undefined;
  selected: boolean;
  /** One of this item's PRs is the selected row — the main column is on this item. */
  owner: boolean;
}) {
  const flag = rowFlag(view);
  const urgent = flag?.urgent ? flag : null;
  const status = itemStatus(view);
  const name = `${view.shortRef}${title ? ` — ${title}` : ""}${urgent ? ` — ${urgent.label}` : ""}${view.instance ? ` on ${view.instance}` : ""}`;
  return (
    <a
      href={itemHref(view.ref, view.instance)}
      aria-current={selected ? "page" : undefined}
      aria-label={name}
      data-row="item"
      data-instance={view.instance || undefined}
      data-owner={owner ? "true" : undefined}
      className={`block w-full rounded-lg px-2 py-1.5 text-left transition-colors ${
        selected ? "bg-surface-2" : owner ? "bg-surface-2/40" : "hover:bg-surface-2/60"
      }`}
    >
      <div className="flex items-center gap-2">
        <StatusDot status={status} />
        <span className="shrink-0 font-mono text-[0.7rem] text-muted-foreground">#{view.number}</span>
        <span className={`min-w-0 flex-1 truncate text-sm ${selected ? "text-foreground" : "text-foreground/85"}`}>
          {title ?? view.shortRef}
        </span>
        {view.instance ? <InstanceChip instance={view.instance} /> : null}
        {urgent ? <span className={`shrink-0 font-mono text-[0.68rem] ${STATUS_TEXT.blocked}`}>{urgent.label}</span> : null}
      </div>
    </a>
  );
}

/**
 * One pull request under its work item: the PR's own session, selectable.
 * Quieter than the row above — icon, number, no title, no age; the nesting
 * says which item it belongs to, and the chip which instance (R5.2).
 */
function PullRequestRow({ node, instance, selected }: { node: SessionNode; instance: string; selected: boolean }) {
  return (
    <a
      href={itemHref(node.ref, instance)}
      aria-current={selected ? "page" : undefined}
      data-row="pr"
      data-instance={instance || undefined}
      className={`flex items-center gap-2 rounded-lg px-2 py-1 text-[0.75rem] transition-colors ${
        selected ? "bg-surface-2 text-foreground" : "text-foreground/85 hover:bg-surface-2/60"
      }`}
    >
      <StatusDot status={sessionDot(node.state)} />
      <GitPullRequestIcon className="h-3 w-3 shrink-0 text-muted-foreground" />
      <span className="font-mono">{node.label}</span>
      {instance ? <InstanceChip instance={instance} /> : null}
    </a>
  );
}
