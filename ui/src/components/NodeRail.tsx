/**
 * A loop drawn as a rail: one mark per node, joined by hairlines, the reached
 * ones filled and the current one outlined and pulsing.
 *
 * The same component serves the outer `pdlc-work-item-loop` on the detail page
 * and the inner `pdlc-pr-loop` inside each PR card; `variant="inner"` is the
 * design's smaller measurements, not a different drawing.
 */

import { useEffect, useRef } from "react";

import type { RailNode } from "../api/model.ts";

const MARK_CLASS: Record<RailNode["state"], string> = {
  done: "done",
  current: "current",
  pending: "",
  skipped: "skipped",
  blocked: "blocked",
};

const LABEL_CLASS: Record<RailNode["state"], string> = {
  done: "done",
  current: "current",
  pending: "",
  skipped: "",
  blocked: "current",
};

interface NodeRailProps {
  nodes: RailNode[];
  variant?: "outer" | "inner";
  emptyMessage?: string;
}

export function NodeRail({ nodes, variant = "outer", emptyMessage }: NodeRailProps) {
  const rail = useRef<HTMLDivElement>(null);
  const currentId = nodes.find((node) => node.state === "current" || node.state === "blocked")?.id;

  // `pdlc-work-item-loop` is 19 nodes — wider than the page at any sane node
  // width, so the rail scrolls, and the pointer is usually past the right edge.
  // Scrolling to find it is the whole question the rail answers, so centre it —
  // but only when it is actually out of view, or a rail that overflows by a few
  // pixels would shunt itself sideways for nothing. Scoped to the rail's own
  // scroll box; `scrollIntoView` would move the page as well.
  useEffect(() => {
    const box = rail.current;
    if (!box || !currentId) return;
    const node = box.querySelector<HTMLElement>(`[data-node="${CSS.escape(currentId)}"]`);
    if (!node) return;
    const left = node.offsetLeft;
    const right = left + node.clientWidth;
    if (left >= box.scrollLeft && right <= box.scrollLeft + box.clientWidth) return;
    box.scrollTo({ left: Math.max(0, left - box.clientWidth / 2 + node.clientWidth / 2), behavior: "instant" });
  }, [currentId]);

  if (nodes.length === 0) {
    return <div className="lp-subtle">{emptyMessage ?? "No graph state for this loop yet."}</div>;
  }
  return (
    <div className={`lp-rail ${variant}`} role="list" aria-label="loop position" ref={rail}>
      {nodes.map((node, index) => (
        <div className="lp-rail-cell" key={node.id}>
          <div
            className="lp-node"
            role="listitem"
            data-node={node.id}
            title={node.detail || `${node.label} — ${node.state}`}
            aria-current={node.state === "current" ? "step" : undefined}
          >
            <div
              className={`lp-node-mark ${MARK_CLASS[node.state]} ${node.state === "current" ? "lp-pulse" : ""}`.trim()}
            />
            <div className={`lp-node-label ${LABEL_CLASS[node.state]}`.trim()}>{node.label}</div>
          </div>
          {index < nodes.length - 1 ? <div className="lp-node-link" /> : null}
        </div>
      ))}
    </div>
  );
}
