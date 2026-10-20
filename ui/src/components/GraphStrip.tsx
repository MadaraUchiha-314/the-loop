/**
 * The loop as the design's node row (issue-327), drawn only while the header's
 * **Full graph** control is on (issue-511, Option C): the loop's name and
 * every node as small bordered buttons joined by hairline connectors — the
 * current one highlighted, skipped ones struck through — scrolling
 * horizontally, nothing wrapping. Each node's tooltip and aria-label carry its
 * name and state; the list keeps its `loop position` name.
 *
 * The strip states no position of its own: the phase chip in the header is
 * the one statement, the row is the map (design § Where the current node is
 * drawn). `compactRail` and `railLabel` stay exported for the readers that
 * still use them.
 */

import type { RailNode } from "../api/model.ts";
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
  /** The loop's name (`pdlc-work-item-loop`); the row's label. */
  loop: string;
  /** Whether the header's Full graph control is on; nothing renders otherwise. */
  expanded: boolean;
  /**
   * The node the pointer is on, by id — the step, whether its state is
   * `current` or `blocked` (the model marks a blocked pointer `blocked`).
   * Without it the `current` state alone decides.
   */
  current?: string | undefined;
}

export function GraphStrip({ nodes, loop, expanded, current }: GraphStripProps) {
  if (!expanded || nodes.length === 0) return null;
  return (
    <section className="border-b border-border bg-surface/60 px-6 py-3" aria-label="Loop position">
      <div className="flex min-w-0 flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span className="font-mono text-foreground">{loop}</span>
      </div>
      <ol className="scroll-thin mt-3 flex items-center gap-1 overflow-x-auto pb-1" role="list" aria-label="loop position">
        {nodes.map((node, index) => (
          <li key={node.id} className="flex shrink-0 items-center gap-1" role="listitem" data-node={node.id}>
            <GraphNode node={node} step={current ? node.id === current : node.state === "current"} />
            {index < nodes.length - 1 ? <span className="h-px w-3 shrink-0 bg-border-strong" aria-hidden="true" /> : null}
          </li>
        ))}
      </ol>
    </section>
  );
}

function GraphNode({ node, step }: { node: RailNode; step: boolean }) {
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
      aria-current={step ? "step" : undefined}
    >
      <StatusDot status={status} />
      <span className={node.state === "skipped" ? "line-through" : ""}>{humanize(node.label)}</span>
      {node.state === "blocked" ? <span className={`font-mono text-[0.65rem] ${STATUS_TEXT.blocked}`}>!</span> : null}
    </span>
  );
}
