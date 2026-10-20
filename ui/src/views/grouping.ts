/**
 * The sidebar's grouping and search (issue-327).
 *
 * The design groups work items by what they need from the operator: **Needs
 * you**, **In flight**, **Shipped**, **Idle**. `itemGroup` in the model already
 * answers the first two; this refines its `idle` into shipped — every walked
 * node done — or idle, and reads the record's closure stamp first (issue-329).
 * The search filters the rows already loaded, by ref, title, repository and
 * current node; it asks the service for nothing.
 *
 * The sidebar draws two groups (issue-511, Option C): **Needs you** and
 * **Everything else**, the latter by last activity. `sidebarGroup` keeps its
 * four-way answer — the dot, the tests and any other reader still get it —
 * and `minimalGroup` folds it for the rows.
 */

import { endedAsShipped, itemGroup, parseRef, type WorkItemView } from "../api/model.ts";
import type { DotStatus } from "../components/StatusDot.tsx";

export type SidebarGroup = "needs-you" | "in-flight" | "shipped" | "idle";

/**
 * Whether the loop has walked every node it kept: all done, or the pointer
 * resting on the last of them (a finished loop's `complete` is its current node).
 */
export function isShipped(view: WorkItemView): boolean {
  const walked = view.rail.filter((node) => node.state !== "skipped");
  const last = walked.at(-1);
  return walked.length > 0 && walked.every((node) => node.state === "done" || (node === last && node.state === "current"));
}

/** The two groups the sidebar draws (issue-511 R3.3). */
export type MinimalGroup = "needs-you" | "everything";

export const SIDEBAR_GROUPS_MINIMAL: { key: MinimalGroup; title: string }[] = [
  { key: "needs-you", title: "Needs you" },
  { key: "everything", title: "Everything else" },
];

/** Needs you stays; In flight, Shipped and Idle are one group of things that need nothing. */
export function minimalGroup(view: WorkItemView): MinimalGroup {
  return sidebarGroup(view) === "needs-you" ? "needs-you" : "everything";
}

/** Newest first by last activity, ties by ref. */
export function byActivity(a: Pick<WorkItemView, "lastActivity" | "ref">, b: Pick<WorkItemView, "lastActivity" | "ref">): number {
  return (b.lastActivity || "").localeCompare(a.lastActivity || "") || a.ref.localeCompare(b.ref);
}

/** The rows newest first by last activity — a copy, the input untouched. */
export function sortByActivity<T extends Pick<WorkItemView, "lastActivity" | "ref">>(views: T[]): T[] {
  return views.toSorted(byActivity);
}

export function sidebarGroup(view: WorkItemView): SidebarGroup {
  // The record says it ended (issue-329): merged or an issue closed is Shipped;
  // a pull request closed unmerged was abandoned, which is Idle.
  if (view.ended) return endedAsShipped(view.ended) ? "shipped" : "idle";
  const group = itemGroup(view);
  if (group === "needs-you") return "needs-you";
  if (group === "running") return "in-flight";
  return isShipped(view) ? "shipped" : "idle";
}

/** The row's dot: red for a human's turn, pulsing for a live session, green when shipped. */
export function itemStatus(view: WorkItemView): DotStatus {
  const group = sidebarGroup(view);
  if (group === "needs-you") return "blocked";
  if (group === "in-flight") return "active";
  if (group === "shipped") return "done";
  return view.sessionState === "paused" ? "skipped" : "pending";
}

/** The repository half of a ref (`loop-lab`), or the whole ref when it does not parse. */
export function repoOf(ref: string): string {
  return parseRef(ref)?.repo ?? ref;
}

/** The rows whose ref, title, repository or current node contain the query (case-insensitive). */
export function filterViews(
  views: WorkItemView[],
  query: string,
  titleFor: (ref: string) => string | undefined,
): WorkItemView[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return views;
  return views.filter((view) =>
    [view.ref, view.shortRef, titleFor(view.ref) ?? "", repoOf(view.ref), view.currentNode]
      .join("\n")
      .toLowerCase()
      .includes(needle),
  );
}
