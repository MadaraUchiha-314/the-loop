/**
 * The design's left column (issue-327): the brand row, a search box that
 * filters the loaded rows, work items grouped by what they need from the
 * operator — Needs you · In flight · Shipped · Idle — each with its pull
 * requests nested beneath it (issue-300), a Standing group for the sessions
 * that belong to no work item (issue-277), and a footer with the Settings
 * link and the health word.
 *
 * Every row is an anchor on the hash: the hash is the one record of what the
 * main column shows, so a sidebar row and a session tab are the same
 * navigation and cannot disagree (issue-300).
 *
 * On a manager the board is a fleet (issue-374, R5.2): each row that a
 * manager stamped carries an instance chip, a native `<select>` beside the
 * search box filters the loaded rows to one instance, and a row's hash names
 * its instance so a work item present on two instances is two rows, each
 * addressable. A worker's rows carry no stamp and none of this renders.
 */

import { useState } from "react";

import { relativeTime, rowFlag, sessionTree, type SessionNode, type WorkItemView } from "../api/model.ts";
import type { DaemonStatus, InstancesDocument, StandingSessionRecord } from "../api/types.ts";
import { hrefFor, itemHref, type Surface } from "../state/route.ts";
import type { StreamState } from "../state/useStream.ts";
import { filterViews, itemStatus, repoOf, SIDEBAR_GROUPS, sidebarGroup } from "../views/grouping.ts";
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
  standingSessions: StandingSessionRecord[];
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
  standingSessions,
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
  const fleet = showsFleet(instances);
  const byInstance = fleet && instanceFilter ? views.filter((view) => view.instance === instanceFilter) : views;
  const shown = filterViews(byInstance, query, titleFor);
  const tree = sessionTree(shown);
  const standing =
    fleet && instanceFilter ? standingSessions.filter((session) => session.instance === instanceFilter) : standingSessions;

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
        <button
          type="button"
          aria-label="Collapse sidebar"
          title="Collapse sidebar"
          onClick={onCollapse}
          className="text-muted-foreground transition-colors hover:text-foreground"
        >
          <PanelLeftCloseIcon className="h-4 w-4" />
        </button>
      </div>

      <nav className="flex items-center gap-1 px-3 pt-3" aria-label="Surfaces">
        {navLink("work", hrefFor({ name: "work" }), "Work")}
        {navLink("standing", hrefFor({ name: "standing" }), "Standing")}
        {navLink("instances", hrefFor({ name: "instances" }), "Instances")}
      </nav>

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
            a fleet to filter, so a worker's sidebar is the one it always was. */}
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

        {SIDEBAR_GROUPS.map((group) => {
          const items = tree.filter(({ view }) => sidebarGroup(view) === group.key);
          if (items.length === 0) return null;
          return (
            <div className="mb-4" key={group.key}>
              <div className="flex items-center justify-between px-2 pb-1.5">
                <Kicker>{group.title}</Kicker>
                <span className="text-[0.68rem] text-muted-foreground">{items.length}</span>
              </div>
              <ul className="space-y-0.5">
                {items.map(({ view, inner }) => (
                  <li key={view.key}>
                    <ItemRow
                      view={view}
                      title={titleFor(view.ref)}
                      selected={activeRef === view.ref && activeInstance === view.instance}
                      owner={activeInstance === view.instance && inner.some((pr) => pr.ref === activeRef)}
                    />
                    {inner.length > 0 ? (
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
                ))}
              </ul>
            </div>
          );
        })}

        <div className="mb-4">
          <div className="flex items-center justify-between px-2 pb-1.5">
            <Kicker>Standing</Kicker>
            <span className="text-[0.68rem] text-muted-foreground">{standing.length}</span>
          </div>
          <ul className="space-y-0.5">
            {standing.map((session) => (
              <li key={`${session.instance ?? ""}:${session.name}`}>
                <a
                  href={hrefFor({ name: "standing" })}
                  data-row="standing"
                  className={`block w-full rounded-lg px-2 py-1.5 text-left transition-colors ${
                    surface === "standing" ? "bg-surface-2" : "hover:bg-surface-2/60"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <StatusDot status={session.running ? "active" : "pending"} />
                    <span className="min-w-0 truncate font-mono text-[0.75rem] text-foreground/85">{session.name}</span>
                    {session.instance ? <InstanceChip instance={session.instance} className="ml-auto" /> : null}
                  </div>
                  {session.description ? (
                    <div className="mt-0.5 truncate pl-[1.1rem] text-[0.7rem] text-muted-foreground">{session.description}</div>
                  ) : null}
                </a>
              </li>
            ))}
            <li>
              <a
                href={hrefFor({ name: "standing" })}
                aria-current={surface === "standing" ? "page" : undefined}
                className="block rounded-lg px-2 py-1.5 text-[0.7rem] text-muted-foreground transition-colors hover:bg-surface-2/60 hover:text-foreground"
              >
                Manage standing sessions →
              </a>
            </li>
          </ul>
        </div>
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
  const status = itemStatus(view);
  return (
    <a
      href={itemHref(view.ref, view.instance)}
      aria-current={selected ? "page" : undefined}
      aria-label={`${view.shortRef}${title ? ` — ${title}` : ""}${view.instance ? ` on ${view.instance}` : ""}`}
      data-row="item"
      data-instance={view.instance || undefined}
      data-owner={owner ? "true" : undefined}
      className={`block w-full rounded-lg px-2 py-1.5 text-left transition-colors ${
        selected ? "bg-surface-2" : owner ? "bg-surface-2/40" : "hover:bg-surface-2/60"
      }`}
    >
      <div className="flex items-start gap-2">
        <StatusDot status={status} className="mt-2" />
        <span className="mt-[0.2rem] shrink-0 font-mono text-[0.7rem] text-muted-foreground">#{view.number}</span>
        <span className={`line-clamp-2 min-w-0 flex-1 break-words text-sm ${selected ? "text-foreground" : "text-foreground/85"}`}>
          {title ?? positionLabel(view)}
        </span>
        {view.instance ? <InstanceChip instance={view.instance} className="mt-[0.2rem]" /> : null}
      </div>
      {/* repo · what it is at · age. The flag ("needs input", "human gate",
          "blocked"…) is the more urgent fact, so it takes the node's slot. */}
      <div className="mt-0.5 flex items-center gap-1.5 pl-[1.1rem] text-[0.7rem] text-muted-foreground">
        <span className="shrink-0 font-mono">{repoOf(view.ref)}</span>
        <span aria-hidden="true">·</span>
        {flag ? (
          <span className={`min-w-0 truncate font-mono ${flag.urgent ? STATUS_TEXT.blocked : ""}`}>{flag.label}</span>
        ) : (
          <span className="min-w-0 truncate font-mono">{view.currentNode || (view.rail.length > 0 ? "planned" : "no graph")}</span>
        )}
        <span aria-hidden="true">·</span>
        <span className="shrink-0" title={view.lastActivity || undefined}>
          {relativeTime(view.lastActivity)}
        </span>
      </div>
    </a>
  );
}

/**
 * One pull request under its work item: the PR's own session, selectable.
 * Quieter than the row above — icon, number, age, no title; the nesting says
 * which item it belongs to, and the chip which instance (R5.2).
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
      <span className="ml-auto shrink-0 text-[0.7rem] text-muted-foreground" title={node.lastActivity || undefined}>
        {relativeTime(node.lastActivity)}
      </span>
    </a>
  );
}

/** Where the item stands, for a row with no cached title to show. */
function positionLabel(view: WorkItemView): string {
  if (view.currentNode) return `${view.currentNode} · ${view.progress}`;
  if (view.rail.length > 0) return `planned · ${view.progress}`;
  return view.shortRef;
}
