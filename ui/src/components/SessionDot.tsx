/**
 * The session mark: filled active, grey paused, hollow closed — round, so it
 * never affords toggling. "No session" is a dash, not a hollow square: the
 * square read as an unchecked checkbox in a clickable row (issue-283 B13).
 */

import type { SessionState } from "../api/model.ts";

const DOT_CLASS: Record<SessionState, string> = {
  active: "active",
  paused: "paused",
  closed: "idle",
  none: "none",
};

const LABEL: Record<SessionState, string> = {
  active: "active",
  paused: "paused",
  closed: "closed",
  none: "no session",
};

export function SessionDot({ state, small = false }: { state: SessionState; small?: boolean }) {
  return <span className={`lp-session-dot ${DOT_CLASS[state]} ${small ? "small" : ""}`.trim()} aria-hidden="true" />;
}

export function sessionLabel(state: SessionState, harness?: string): string {
  if (state === "none") return LABEL.none;
  return harness ? `${LABEL[state]} · ${harness}` : LABEL[state];
}
