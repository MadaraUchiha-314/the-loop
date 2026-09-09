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
 */

import { useState } from "react";

import { relativeTime, rowFlag, sessionTree, type SessionNode, type WorkItemView } from "../api/model.ts";
import type { DaemonStatus, StandingSessionRecord } from "../api/types.ts";
import { hrefFor } from "../state/route.ts";
import type { StreamState } from "../state/useStream.ts";
import { filterViews, itemStatus, repoOf, SIDEBAR_GROUPS, sidebarGroup } from "../views/grouping.ts";
import { GitPullRequestIcon, PanelLeftCloseIcon, RadioIcon, SearchIcon, SettingsIcon } from "./Icons.tsx";
import { HealthDot } from "./Nav.tsx";
import { IconButton, Kicker } from "./primitives.tsx";
import { sessionDot, StatusDot, STATUS_TEXT } from "./StatusDot.tsx";

interface SidebarProps {
  views: WorkItemView[];
  loading: boolean;
  titleFor: (ref: string) => string | undefined;
  /** The ref the hash selects, resolved — a work item's or one of its PRs'. */
  activeRef: string;
  /** Which non-work surface is current, if any. */
  surface: "work" | "standing" | "settings";
  standingSessions: StandingSessionRecord[];
  daemons: DaemonStatus[];
  stream: StreamState;
  onRefresh: () => void;
  onCollapse: () => void;
  /** The footer's service line: the base URL's host, or the demo. */
  serviceLabel: string;
}

export function Sidebar({
  views,
  loading,
  titleFor,
  activeRef,
  surface,
  standingSessions,
  daemons,
  stream,
  onRefresh,
  onCollapse,
  serviceLabel,
}: SidebarProps) {
  const [query, setQuery] = useState("");
  const shown = filterViews(views, query, titleFor);
  const tree = sessionTree(shown);

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

      <div className="space-y-2 px-3 pt-4">
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
      </div>

      <nav className="scroll-thin mt-4 flex-1 overflow-y-auto px-2 pb-4">
        {loading && views.length === 0 ? <p className="px-2 py-4 text-xs text-muted-foreground">Loading…</p> : null}
        {!loading && views.length === 0 ? (
          <p className="px-2 py-4 text-xs leading-relaxed text-muted-foreground">
            Nothing is tracked on this machine yet. A work item appears once the poller or webhook receiver sees a control
            keyword on its ticket, or after <code className="ref-chip">the-loop sessions register</code>.
          </p>
        ) : null}
        {views.length > 0 && shown.length === 0 ? (
          <p className="px-2 py-4 text-xs text-muted-foreground">No work item matches “{query}”.</p>
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
                  <li key={view.ref}>
                    <ItemRow
                      view={view}
                      title={titleFor(view.ref)}
                      selected={activeRef === view.ref}
                      owner={inner.some((pr) => pr.ref === activeRef)}
                    />
                    {inner.length > 0 ? (
                      <ul className="mt-0.5 space-y-0.5 pl-[1.1rem]" aria-label={`Pull requests for ${view.shortRef}`}>
                        {inner.map((pr) => (
                          <li key={pr.ref}>
                            <PullRequestRow node={pr} selected={activeRef === pr.ref} />
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
            <span className="text-[0.68rem] text-muted-foreground">{standingSessions.length}</span>
          </div>
          <ul className="space-y-0.5">
            {standingSessions.map((session) => (
              <li key={session.name}>
                <a
                  href={hrefFor({ name: "standing" })}
                  className={`block w-full rounded-lg px-2 py-1.5 text-left transition-colors ${
                    surface === "standing" ? "bg-surface-2" : "hover:bg-surface-2/60"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <StatusDot status={session.running ? "active" : "pending"} />
                    <span className="truncate font-mono text-[0.75rem] text-foreground/85">{session.name}</span>
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
        <HealthDot daemons={daemons} stream={stream} onRefresh={onRefresh} />
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
      href={hrefFor({ name: "work", ref: view.ref })}
      aria-current={selected ? "page" : undefined}
      aria-label={`${view.shortRef}${title ? ` — ${title}` : ""}`}
      data-row="item"
      data-owner={owner ? "true" : undefined}
      className={`block w-full rounded-lg px-2 py-1.5 text-left transition-colors ${
        selected ? "bg-surface-2" : owner ? "bg-surface-2/40" : "hover:bg-surface-2/60"
      }`}
    >
      <div className="flex items-center gap-2">
        <StatusDot status={status} />
        <span className="font-mono text-[0.7rem] text-muted-foreground">#{view.number}</span>
        <span className={`truncate text-sm ${selected ? "text-foreground" : "text-foreground/85"}`}>
          {title ?? positionLabel(view)}
        </span>
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
 * Quieter than the row above — icon, number, age, no title and no chip; the
 * nesting says which item it belongs to.
 */
function PullRequestRow({ node, selected }: { node: SessionNode; selected: boolean }) {
  return (
    <a
      href={hrefFor({ name: "work", ref: node.ref })}
      aria-current={selected ? "page" : undefined}
      data-row="pr"
      className={`flex items-center gap-2 rounded-lg px-2 py-1 text-[0.75rem] transition-colors ${
        selected ? "bg-surface-2 text-foreground" : "text-foreground/85 hover:bg-surface-2/60"
      }`}
    >
      <StatusDot status={sessionDot(node.state)} />
      <GitPullRequestIcon className="h-3 w-3 shrink-0 text-muted-foreground" />
      <span className="font-mono">{node.label}</span>
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
