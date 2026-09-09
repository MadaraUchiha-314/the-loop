/**
 * The two full-width notices above the columns: demo data, and a service that
 * cannot be reached. Drawn in the design's accent-notice idiom (issue-327).
 */

import { ApiError } from "../api/client.ts";
import { hrefFor } from "../state/route.ts";
import { TriangleAlertIcon } from "./Icons.tsx";
import { ControlButton } from "./primitives.tsx";

export function DemoBanner({ onGoLive }: { onGoLive: () => void }) {
  return (
    <div
      role="status"
      className="flex flex-wrap items-center gap-3 border-b border-border bg-accent px-6 py-2 text-xs text-accent-foreground"
    >
      <span className="font-mono text-[0.68rem] uppercase tracking-widest">Demo data</span>
      <span className="min-w-0 flex-1">
        These work items are a bundled fixture, not a live service — nothing here is real and no control verb leaves
        the browser.
      </span>
      <ControlButton onClick={onGoLive}>Connect to a service</ControlButton>
    </div>
  );
}

export function ConnectionBanner({ error, baseUrl, onDemo }: { error: Error; baseUrl: string; onDemo?: (() => void) | undefined }) {
  const advice = error instanceof ApiError ? error.advice : error.message;
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center gap-3 border-b border-border bg-surface px-6 py-2 text-xs text-foreground/90"
    >
      <span className="inline-flex items-center gap-1.5 font-mono text-[0.68rem] uppercase tracking-widest text-state-blocked">
        <TriangleAlertIcon className="h-3.5 w-3.5" />
        Not connected
      </span>
      <span className="min-w-0 flex-1">
        <code className="ref-chip">{baseUrl}</code> — {advice}
      </span>
      {onDemo ? <ControlButton onClick={onDemo}>Explore the demo fixture</ControlButton> : null}
      <a
        href={hrefFor({ name: "settings" })}
        className="rounded-md border border-border px-2 py-1.5 font-mono text-[0.7rem] text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground"
      >
        Settings
      </a>
    </div>
  );
}
