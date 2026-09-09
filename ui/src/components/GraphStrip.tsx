/**
 * The loop as the design's node strip (issue-327): the loop's name and counts
 * on one line, the nodes beneath as small bordered buttons joined by hairline
 * connectors — compacted to the first, the last and two either side of the
 * current node, the rest folded into one `···`, until **Full graph** expands
 * the row (it then scrolls horizontally; nothing wraps). Each node's tooltip
 * and aria-label carry its name and state, so nothing the old tick bar said
 * is lost; the list keeps its `loop position` name.
 */

import { useState } from "react";

import type { RailNode } from "../api/model.ts";
import { ChevronDownIcon } from "./Icons.tsx";
import { nodeDot, STATUS_TEXT, StatusDot } from "./StatusDot.tsx";

export type StripEntry = RailNode | "gap";

/** First, last and ±2 around the current (or blocked) node; one gap between runs. */
export function compactRail(nodes: RailNode[]): StripEntry[] {
  const anchor = Math.max(
    nodes.findIndex((node) => node.state === "current" || node.state === "blocked"),
    0,
  );
  const out: StripEntry[] = [];
  nodes.forEach((node, index) => {
    const near = Math.abs(index - anchor) <= 2;
    const edge = index === 0 || index === nodes.length - 1;
    if (near || edge) out.push(node);
    else if (out.at(-1) !== "gap") out.push("gap");
  });
  return out;
}

/** The line beside the nodes: where the loop stands, among the kept phases. */
export function railLabel(nodes: RailNode[]): string {
  const active = nodes.filter((node) => node.state !== "skipped");
  const current = nodes.find((node) => node.state === "current" || node.state === "blocked");
  if (current) return `${current.label} · ${active.indexOf(current) + 1} of ${active.length}`;
  if (active.length > 0 && active.every((node) => node.state === "done")) return "complete";
  return `planned · ${active.length} phases`;
}

/** A node id as the design writes it: `human-approval` → `Human approval`. */
export function humanize(id: string): string {
  const words = id.replaceAll("-", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

interface GraphStripProps {
  nodes: RailNode[];
  /** The loop's name (`pdlc-work-item-loop`); the strip's first word. */
  loop: string;
  /** What to say when there is no rail at all. */
  emptyMessage: string;
  /** The parked / blocked note, when the item has one — the strip's trailing status. */
  note?: string | undefined;
}

export function GraphStrip({ nodes, loop, emptyMessage, note }: GraphStripProps) {
  const [expanded, setExpanded] = useState(false);
  const done = nodes.filter((node) => node.state === "done").length;
  const skipped = nodes.filter((node) => node.state === "skipped").length;
  const current = nodes.find((node) => node.state === "current");
  const blocked = nodes.find((node) => node.state === "blocked");
  const visible = expanded ? nodes : compactRail(nodes);

  return (
    <section className="border-b border-border bg-surface/60 px-6 py-3" aria-label="Loop position">
      <div className="flex items-center justify-between gap-4">
        <div className="flex min-w-0 flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span className="font-mono text-foreground">{loop}</span>
          {nodes.length > 0 ? (
            <>
              <span aria-hidden="true">·</span>
              <span>
                {done} of {nodes.length} nodes passed
              </span>
              {skipped > 0 ? (
                <>
                  <span aria-hidden="true">·</span>
                  <span>{skipped} skipped</span>
                </>
              ) : null}
              <span aria-hidden="true">·</span>
              {blocked ? (
                <span className="text-state-blocked">blocked at {blocked.label}</span>
              ) : current ? (
                <span className="text-state-active">at {current.label}</span>
              ) : (
                <span>{railLabel(nodes)}</span>
              )}
              {note ? (
                <>
                  <span aria-hidden="true">·</span>
                  <span className={blocked || note.startsWith("parked") ? "text-state-blocked" : ""} title={note}>
                    {note}
                  </span>
                </>
              ) : null}
            </>
          ) : (
            <>
              <span aria-hidden="true">·</span>
              <span>{emptyMessage}</span>
            </>
          )}
        </div>
        {nodes.length > 0 ? (
          <button
            type="button"
            aria-expanded={expanded}
            onClick={() => setExpanded((value) => !value)}
            className="inline-flex shrink-0 items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            {expanded ? "Collapse graph" : "Full graph"}
            <ChevronDownIcon className={`h-3.5 w-3.5 transition-transform ${expanded ? "rotate-180" : ""}`} />
          </button>
        ) : null}
      </div>

      {nodes.length > 0 ? (
        <ol className="scroll-thin mt-3 flex items-center gap-1 overflow-x-auto pb-1" role="list" aria-label="loop position">
          {visible.map((entry, index) =>
            entry === "gap" ? (
              <li key={`gap-${index}`} className="px-1 font-mono text-xs text-muted-foreground" aria-label="nodes folded">
                ···
              </li>
            ) : (
              <li key={entry.id} className="flex items-center gap-1" role="listitem" data-node={entry.id}>
                <GraphNode node={entry} />
                {index < visible.length - 1 ? <span className="h-px w-3 shrink-0 bg-border-strong" aria-hidden="true" /> : null}
              </li>
            ),
          )}
        </ol>
      ) : null}
    </section>
  );
}

function GraphNode({ node }: { node: RailNode }) {
  const status = nodeDot(node.state);
  const shell =
    node.state === "current"
      ? "border-primary/50 bg-accent text-accent-foreground"
      : node.state === "skipped" || node.state === "pending"
        ? "border-border bg-transparent text-muted-foreground"
        : node.state === "blocked"
          ? "border-state-blocked/40 bg-surface-2 text-foreground/90"
          : "border-border bg-surface-2 text-foreground/90";
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-md border px-2 py-1 text-xs ${shell}`}
      title={node.detail || `${node.label} · ${node.state}`}
      aria-label={`${node.label} — ${node.state}`}
      aria-current={node.state === "current" ? "step" : undefined}
    >
      <StatusDot status={status} />
      <span className={node.state === "skipped" ? "line-through" : ""}>{humanize(node.label)}</span>
      {node.state === "blocked" ? <span className={`font-mono text-[0.65rem] ${STATUS_TEXT.blocked}`}>!</span> : null}
    </span>
  );
}
