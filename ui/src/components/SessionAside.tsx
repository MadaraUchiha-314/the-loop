/**
 * The design's right column (issue-327): what the viewed session *is* —
 * harness, session id, status, current node, the transcript file served;
 * tmux target and cwd with the attach command ready to copy; the ticket or
 * pull request it delivers; and the work item's session verbs as a grid of
 * mono buttons. An accent banner at the top says what needs a human.
 *
 * The verbs act on the work item's own session (`controlSession(view.ref)`),
 * as they did in the old header; a PR tab keeps them and says so.
 */

import { useState } from "react";

import { ApiError } from "../api/client.ts";
import { parseRef, relativeTime, transcriptPath, type PullRequestView, type WorkItemView } from "../api/model.ts";
import type { SessionVerb } from "../api/types.ts";
import { useApi } from "../state/ApiContext.tsx";
import { railLabel } from "./GraphStrip.tsx";
import { CopyIcon, ExternalLinkIcon, PanelRightCloseIcon, TriangleAlertIcon } from "./Icons.tsx";
import { ControlButton, KV, Notice, Section } from "./primitives.tsx";
import { sessionLabel } from "./StatusDot.tsx";

interface SessionAsideProps {
  view: WorkItemView;
  /** The viewed session's ref — the item's own, or one of its PRs'. */
  viewed: string;
  /** The parked / blocked / attention note, when the item has one. */
  note: string;
  onChanged: () => void;
  onClose: () => void;
}

export function SessionAside({ view, viewed, note, onChanged, onClose }: SessionAsideProps) {
  const { api } = useApi();
  const [busy, setBusy] = useState<SessionVerb | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const pr: PullRequestView | undefined = viewed === view.ref ? undefined : view.pullRequests.find((p) => p.ref === viewed);
  const session = pr ? pr.session : view.session;
  const state = pr ? pr.sessionState : view.sessionState;
  const path = transcriptPath(session);
  const tmux = pr ? pr.tmuxTarget : view.tmuxTarget;
  const currentNode = pr ? (pr.status?.currentNode ?? railLabel(pr.rail)) : view.currentNode || railLabel(view.rail);

  const verbs: SessionVerb[] =
    view.sessionState === "active" ? ["pause", "stop"] : view.sessionState === "paused" ? ["resume", "stop"] : ["start"];

  async function run(verb: SessionVerb): Promise<void> {
    setBusy(verb);
    setError(null);
    try {
      await api.controlSession(view.ref, verb);
      onChanged();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.advice : String(cause));
    } finally {
      setBusy(null);
    }
  }

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
    <aside
      className="scroll-thin flex h-full w-[19rem] shrink-0 flex-col overflow-y-auto border-l border-border bg-surface max-md:absolute max-md:inset-y-0 max-md:right-0 max-md:z-20"
      aria-label="Session"
    >
      <div className="flex items-center justify-between px-4 py-3">
        <span className="text-[0.68rem] font-medium uppercase tracking-widest text-muted-foreground">Session</span>
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

      {note ? (
        <Notice className="mx-3 mb-4" icon={<TriangleAlertIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" />}>
          <span>{note}</span>
        </Notice>
      ) : null}

      <Section title="Harness">
        <KV k="harness" v={session?.harness ?? "—"} />
        <KV k="session id" v={session?.harnessSessionId ?? "—"} title={session?.harnessSessionId} />
        <KV k="status" v={sessionLabel(state)} />
        <KV k="current node" v={currentNode} title={currentNode} />
        {session?.createdAt ? <KV k="started" v={relativeTime(session.createdAt)} mono={false} title={session.createdAt} /> : null}
        <KV k="transcript" v={path ?? "no derivable transcript path"} title={path ?? undefined} />
      </Section>

      <Section title="tmux">
        <KV k="target" v={tmux || "—"} title={tmux || undefined} />
        <KV k="cwd" v={session?.cwd ?? "—"} title={session?.cwd} />
        {tmux ? (
          <div className="pt-2">
            <button
              type="button"
              onClick={() => void copyAttach()}
              title="Copy to the clipboard"
              className="flex w-full items-center justify-center gap-2 rounded-md border border-border bg-surface-2 px-2 py-1.5 font-mono text-[0.7rem] text-muted-foreground transition-colors hover:text-foreground"
            >
              <CopyIcon className="h-3 w-3 shrink-0" />
              <span className="truncate">{copied ? "copied" : `tmux attach -t ${tmux}`}</span>
            </button>
          </div>
        ) : null}
      </Section>

      <Section title={pr ? "Pull request" : "Ticket"}>
        <KV k="repo" v={pr ? (pr.prRepo || repoOf(view.ref)) : repoOf(view.ref)} />
        <KV k="number" v={`#${pr ? pr.number : view.number}`} />
        {pr ? <KV k="inner loop" v={railLabel(pr.rail)} title={railLabel(pr.rail)} /> : null}
        {(pr ? pr.url : view.url) ? (
          <div className="pt-1">
            <a
              href={pr ? pr.url : view.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              <ExternalLinkIcon className="h-3.5 w-3.5" />
              Open on GitHub
            </a>
          </div>
        ) : null}
      </Section>

      <Section title={pr ? "Controls · work item session" : "Controls"}>
        <div className="grid grid-cols-2 gap-1.5">
          {verbs.map((verb) => (
            <ControlButton key={verb} disabled={busy !== null} onClick={() => void run(verb)}>
              {busy === verb ? `${verb}…` : verb}
            </ControlButton>
          ))}
        </div>
        {view.sessionState === "none" ? (
          <p className="text-[0.7rem] text-muted-foreground">No session on this machine — start spawns one.</p>
        ) : null}
        {error ? (
          <p role="alert" className="text-xs text-state-blocked">
            {error}
          </p>
        ) : null}
      </Section>
    </aside>
  );
}

/** `owner/repo` of a ref, or the ref itself when it does not parse. */
function repoOf(ref: string): string {
  const parsed = parseRef(ref);
  return parsed ? `${parsed.owner}/${parsed.repo}` : ref;
}
