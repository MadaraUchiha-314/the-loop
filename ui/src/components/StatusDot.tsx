/**
 * The design's one state signal (issue-327): a 6 px dot coloured by one of
 * five state colours — done, active, blocked, skipped, pending — pulsing when
 * active. It is `bg-current` inside a `text-state-*` span so the same class
 * drives dots, icons and words. Decorative: the text beside it carries the
 * state, which is also why a "no session" row reads it in words.
 */

import type { NodeVisualState, SessionState } from "../api/model.ts";

export type DotStatus = "done" | "active" | "blocked" | "skipped" | "pending";

/** The text colour class for a status — reused by chips, icons and words. */
export const STATUS_TEXT: Record<DotStatus, string> = {
  done: "text-state-done",
  active: "text-state-active",
  blocked: "text-state-blocked",
  skipped: "text-state-skipped",
  pending: "text-state-pending",
};

export function StatusDot({ status, className = "" }: { status: DotStatus; className?: string | undefined }) {
  return (
    <span
      className={`inline-flex h-1.5 w-1.5 shrink-0 rounded-full bg-current ${STATUS_TEXT[status]} ${
        status === "active" ? "pulse-dot" : ""
      } ${className}`.trim()}
      aria-hidden="true"
    />
  );
}

/** A rail node's visual state as a dot status — `current` is the active one. */
export function nodeDot(state: NodeVisualState): DotStatus {
  return state === "current" ? "active" : state;
}

/** A session's state as a dot: live pulses, paused is grey, closed/none are quiet. */
export function sessionDot(state: SessionState): DotStatus {
  if (state === "active") return "active";
  if (state === "paused") return "skipped";
  return "pending";
}

const LABEL: Record<SessionState, string> = {
  active: "active",
  paused: "paused",
  closed: "closed",
  none: "no session",
};

/** The words for a session state, with the harness when known. */
export function sessionLabel(state: SessionState, harness?: string): string {
  if (state === "none") return LABEL.none;
  return harness ? `${LABEL[state]} · ${harness}` : LABEL[state];
}
