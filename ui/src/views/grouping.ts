/**
 * The sidebar's grouping and search (issue-327).
 *
 * The design groups work items by what they need from the operator: **Needs
 * you**, **In flight**, **Shipped**, **Idle**. `itemGroup` in the model already
 * answers the first two; this refines its `idle` into shipped — every walked
 * node done — or idle. The search filters the rows already loaded, by ref,
 * title, repository and current node; it asks the service for nothing.
 */

import { itemGroup, parseRef, type WorkItemView } from "../api/model.ts";
import type { DotStatus } from "../components/StatusDot.tsx";

export type SidebarGroup = "needs-you" | "in-flight" | "shipped" | "idle";

export const SIDEBAR_GROUPS: { key: SidebarGroup; title: string }[] = [
  { key: "needs-you", title: "Needs you" },
  { key: "in-flight", title: "In flight" },
  { key: "shipped", title: "Shipped" },
  { key: "idle", title: "Idle" },
];

/**
 * Whether the loop has walked every node it kept: all done, or the pointer
 * resting on the last of them (a finished loop's `complete` is its current node).
 */
export function isShipped(view: WorkItemView): boolean {
  const walked = view.rail.filter((node) => node.state !== "skipped");
  const last = walked.at(-1);
  return walked.length > 0 && walked.every((node) => node.state === "done" || (node === last && node.state === "current"));
}

export function sidebarGroup(view: WorkItemView): SidebarGroup {
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
