/**
 * A loop drawn as a tick bar (issue-298): one slim vertical tick per node —
 * reached ones in the accent, the current one taller and pulsing (ink-dark
 * when blocked), skipped ones shortened — beside a label naming the current
 * node and the position among the phases the item actually walks. Each tick's
 * tooltip carries the node's name and state, so nothing the old labelled rail
 * said is lost.
 *
 * The same component serves the outer `pdlc-work-item-loop` in the detail
 * header and the inner `pdlc-pr-loop` inside each PR card; `variant="inner"`
 * is the design's smaller measurements, not a different drawing.
 */

import type { RailNode } from "../api/model.ts";

const MARK_CLASS: Record<RailNode["state"], string> = {
  done: "done",
  current: "current",
  pending: "",
  skipped: "skipped",
  blocked: "blocked",
};

interface NodeRailProps {
  nodes: RailNode[];
  variant?: "outer" | "inner";
  emptyMessage?: string;
}

/** The line beside the ticks: where the loop stands, among the kept phases. */
function railLabel(nodes: RailNode[]): string {
  const active = nodes.filter((node) => node.state !== "skipped");
  const current = nodes.find((node) => node.state === "current" || node.state === "blocked");
  if (current) return `${current.label} · ${active.indexOf(current) + 1} of ${active.length}`;
  if (active.length > 0 && active.every((node) => node.state === "done")) return "complete";
  return `planned · ${active.length} phases`;
}

export function NodeRail({ nodes, variant = "outer", emptyMessage }: NodeRailProps) {
  if (nodes.length === 0) {
    return <div className="lp-subtle">{emptyMessage ?? "No graph state for this loop yet."}</div>;
  }
  return (
    <div className={`lp-rail-group ${variant}`}>
      <div className={`lp-rail ${variant}`} role="list" aria-label="loop position">
        {nodes.map((node) => (
          <span
            key={node.id}
            className={`lp-rail-tick ${MARK_CLASS[node.state]} ${node.state === "current" ? "lp-pulse" : ""}`.trim()}
            role="listitem"
            data-node={node.id}
            title={node.detail || `${node.label} — ${node.state}`}
            aria-current={node.state === "current" ? "step" : undefined}
            aria-label={`${node.label} — ${node.state}`}
          />
        ))}
      </div>
      <span className="lp-rail-label">{railLabel(nodes)}</span>
    </div>
  );
}
