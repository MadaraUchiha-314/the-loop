/**
 * What the viewed session *is*, and the verbs on it (issue-327), as the
 * pieces issue-511's Option C relocated into the header: `SessionFacts` —
 * harness, status, started, session id and transcript path in full; cwd in
 * full and the attach command ready to copy; the ticket or pull request it
 * delivers — renders inside the header's **Session details** disclosure, and
 * `SessionControls` — the work item's session verbs as mono buttons — renders
 * among the header actions. The facts the header already draws once (the
 * repository and number in the ref chip, the current node in the phase chip,
 * the note beside it, the tmux target inside the attach command) are not
 * repeated here (R2.1).
 *
 * Every value is a field of the typed `SessionEndpoint` / `PullRequestView`
 * record through the same `KV` row as before — nothing is assembled from a
 * string in the DOM (abuse case 2). The one copy control is the attach
 * command's (critic C5: a disclosure, not a new control, meets R2.3).
 *
 * The verbs act on the work item's own session (`controlSession(view.ref)`),
 * as they always did; a PR selection says so with a `work item` kicker
 * (critic C3).
 *
 * `SessionAside`, the standing column of 20.5.1, composes the two and is no
 * longer rendered on Work; it stays as the panel's shape for any pane that
 * wants a column.
 */

import { useState } from "react";

import { ApiError } from "../api/client.ts";
import { relativeTime, transcriptPath, type PullRequestView, type WorkItemView } from "../api/model.ts";
import type { SessionVerb } from "../api/types.ts";
import { useApi } from "../state/ApiContext.tsx";
import { railLabel } from "./GraphStrip.tsx";
import { CopyIcon, ExternalLinkIcon, PanelRightCloseIcon } from "./Icons.tsx";
import { ControlButton, Kicker, KV, Section } from "./primitives.tsx";
import { sessionLabel } from "./StatusDot.tsx";

interface FactsProps {
  view: WorkItemView;
  /** The viewed session's ref — the item's own, or one of its PRs'. */
  viewed: string;
}

/** The viewed PR, when the viewed ref is one of the item's pull requests. */
function viewedPr(view: WorkItemView, viewed: string): PullRequestView | undefined {
  return viewed === view.ref ? undefined : view.pullRequests.find((p) => p.ref === viewed);
}

export function SessionFacts({ view, viewed }: FactsProps) {
  const [copied, setCopied] = useState(false);
  const pr = viewedPr(view, viewed);
  const session = pr ? pr.session : view.session;
  const state = pr ? pr.sessionState : view.sessionState;
  const path = transcriptPath(session);
  const tmux = pr ? pr.tmuxTarget : view.tmuxTarget;
  const url = pr ? pr.url : view.url;

  async function copyAttach(): Promise<void> {
    if (!tmux) return;
    try {
      await navigator.clipboard.writeText(`tmux attach -t ${tmux}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div data-session-facts>
      <Section title="Harness">
        <KV k="harness" v={session?.harness ?? "—"} />
        <KV k="status" v={sessionLabel(state)} />
        {session?.createdAt ? <KV k="started" v={relativeTime(session.createdAt)} mono={false} title={session.createdAt} /> : null}
        <KV k="session id" v={session?.harnessSessionId ?? "—"} />
        <KV k="transcript" v={path ?? "no derivable transcript path"} />
      </Section>

      <Section title="tmux">
        <KV k="cwd" v={session?.cwd ?? "—"} />
        {tmux ? (
          <div className="pt-2">
            <button
              type="button"
              onClick={() => void copyAttach()}
              title="Copy to the clipboard"
              className="flex w-full items-start gap-2 rounded-md border border-border bg-surface-2 px-2 py-1.5 text-left font-mono text-[0.7rem] leading-relaxed text-muted-foreground transition-colors hover:text-foreground"
            >
              <CopyIcon className="mt-0.5 h-3 w-3 shrink-0" />
              <span className="min-w-0 break-all">{copied ? "copied" : `tmux attach -t ${tmux}`}</span>
            </button>
          </div>
        ) : null}
      </Section>

      <Section title={pr ? "Pull request" : "Ticket"}>
        {pr ? <KV k="inner loop" v={railLabel(pr.rail)} /> : null}
        {url ? (
          <div className="pt-1">
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              <ExternalLinkIcon className="h-3.5 w-3.5" />
              Open on GitHub
            </a>
          </div>
        ) : (
          <p className="text-[0.7rem] text-muted-foreground">No ticket URL in the record.</p>
        )}
      </Section>
    </div>
  );
}

interface ControlsProps {
  view: WorkItemView;
  /** The viewed session's ref; a PR's makes the kicker say the verbs' target. */
  viewed: string;
  onChanged: () => void;
}

export function SessionControls({ view, viewed, onChanged }: ControlsProps) {
  const { api } = useApi();
  const [busy, setBusy] = useState<SessionVerb | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pr = viewedPr(view, viewed);

  const verbs: SessionVerb[] =
    view.sessionState === "active" ? ["pause", "stop"] : view.sessionState === "paused" ? ["resume", "stop"] : ["start"];

  async function run(verb: SessionVerb): Promise<void> {
    setBusy(verb);
    setError(null);
    try {
      await api.controlSession(view.ref, verb, true, view.instance);
      onChanged();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.advice : String(cause));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label={pr ? "Controls · work item session" : "Controls"}>
      {pr ? <Kicker>work item</Kicker> : null}
      {verbs.map((verb) => (
        <ControlButton
          key={verb}
          disabled={busy !== null}
          onClick={() => void run(verb)}
          title={view.sessionState === "none" && verb === "start" ? "No session on this machine — start spawns one." : undefined}
        >
          {busy === verb ? `${verb}…` : verb}
        </ControlButton>
      ))}
      {error ? (
        <p role="alert" className="w-full text-xs text-state-blocked">
          {error}
        </p>
      ) : null}
    </div>
  );
}

interface SessionAsideProps extends FactsProps {
  onChanged: () => void;
  onClose: () => void;
}

/** The 20.5.1 column: head, verbs, facts. Not rendered on Work since issue-511. */
export function SessionAside({ view, viewed, onChanged, onClose }: SessionAsideProps) {
  return (
    <aside
      className="scroll-thin flex h-full w-[19rem] shrink-0 flex-col overflow-y-auto border-l border-border bg-surface max-md:absolute max-md:inset-y-0 max-md:right-0 max-md:z-20"
      aria-label="Session"
    >
      <div className="flex items-center justify-between px-4 py-3">
        <Kicker>Session</Kicker>
        <button
          type="button"
          aria-label="Close panel"
          title="Close panel"
          onClick={onClose}
          className="text-muted-foreground transition-colors hover:text-foreground"
        >
          <PanelRightCloseIcon className="h-4 w-4" />
        </button>
      </div>
      <div className="px-4 pb-3">
        <SessionControls view={view} viewed={viewed} onChanged={onChanged} />
      </div>
      <SessionFacts view={view} viewed={viewed} />
    </aside>
  );
}
