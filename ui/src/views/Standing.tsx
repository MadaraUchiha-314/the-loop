/**
 * The standing sessions pane (issue-277), in the design's idiom (issue-327):
 * the sessions that belong to no work item — no ticket, no tree, no
 * completion — each a card of key/value lines with the verbs as mono buttons
 * and a message box that pastes straight into the pane.
 *
 * The split the CLI makes visible is visible here too: a **declared** session
 * comes from `standingSessions.sessions` and is removed by editing that file;
 * a **created** one lives only in the registry and `delete` really deletes
 * it. Every refusal is the service's own sentence, never re-worded.
 */

import { useState } from "react";

import { relativeTime } from "../api/model.ts";
import type { StandingSessionRecord, StandingVerb } from "../api/types.ts";
import type { Chrome } from "../components/HeaderBar.tsx";
import { HeaderBar } from "../components/HeaderBar.tsx";
import { Card, ControlButton, Empty, FieldLabel, INPUT_CLASS, KV, Report } from "../components/primitives.tsx";
import { StatusDot } from "../components/StatusDot.tsx";
import { useApi } from "../state/ApiContext.tsx";
import { useAsync } from "../state/useAsync.ts";

export function Standing({ chrome, onChanged }: { chrome: Chrome; onChanged?: () => void }) {
  const { api } = useApi();
  const sessions = useAsync((signal) => api.standingSessions(signal), [api]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [note, setNote] = useState("");

  /** Run one mutation, then reload. The service's message is the message. */
  const run = async (key: string, action: () => Promise<unknown>, done: string) => {
    setBusy(key);
    setError("");
    setNote("");
    try {
      await action();
      setNote(done);
      sessions.reload();
      onChanged?.();
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy("");
    }
  };

  const rows = sessions.data ?? [];

  return (
    <>
      <HeaderBar
        chrome={chrome}
        title="Standing sessions"
        meta={<span>Sessions that belong to no work item — no ticket, no phases, running until you stop them.</span>}
      />
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-6 py-6">
        <div className="mx-auto max-w-3xl space-y-4">
          {error ? (
            <Report tone="fail" role="alert">
              <strong className="font-medium">The service refused that.</strong> {error}
            </Report>
          ) : null}
          {note && !error ? <Report tone="ok" role="status">{note}</Report> : null}

          <CreateForm
            busy={busy === "create"}
            onCreate={(body) => run("create", () => api.createStandingSession(body), `Created and started ${body.name}.`)}
          />

          {sessions.loading && rows.length === 0 ? <Empty>Loading…</Empty> : null}
          {!sessions.loading && rows.length === 0 ? (
            <Empty>
              No standing sessions. Declare one under <code className="ref-chip">standingSessions.sessions</code>, or
              create one above.
            </Empty>
          ) : null}

          {rows.map((session) => (
            <SessionCard
              key={session.name}
              session={session}
              busy={busy}
              onControl={(verb) =>
                run(`${verb}:${session.name}`, () => api.controlStandingSession(session.name, verb), `${verb} ${session.name}.`)
              }
              onDelete={() => run(`delete:${session.name}`, () => api.deleteStandingSession(session.name), `Deleted ${session.name}.`)}
              onSay={(text) =>
                run(`say:${session.name}`, () => api.sayToStandingSession(session.name, text), `Delivered into ${session.name}.`)
              }
            />
          ))}
        </div>
      </div>
    </>
  );
}

interface CreateBody {
  name: string;
  cwd: string;
  prompt: string;
  description: string;
}

/**
 * The create form. Four fields, not eleven: a name, where it runs, what it is
 * for, and its brief; everything else the API accepts has a `routing` default.
 */
function CreateForm({ busy, onCreate }: { busy: boolean; onCreate: (body: CreateBody) => void }) {
  const [open, setOpen] = useState(false);
  const [body, setBody] = useState<CreateBody>({ name: "", cwd: "", prompt: "", description: "" });
  const valid = /^[a-z0-9][a-z0-9-]{0,39}$/.test(body.name);

  if (!open) {
    return (
      <div>
        <ControlButton onClick={() => setOpen(true)}>Create a standing session</ControlButton>
      </div>
    );
  }

  return (
    <Card>
      <form
        className="space-y-3"
        onSubmit={(event) => {
          event.preventDefault();
          if (!valid || busy) return;
          onCreate(body);
          setBody({ name: "", cwd: "", prompt: "", description: "" });
          setOpen(false);
        }}
      >
        <div className="space-y-1">
          <FieldLabel htmlFor="standing-name">Name</FieldLabel>
          <input
            id="standing-name"
            className={INPUT_CLASS}
            value={body.name}
            onChange={(event) => setBody({ ...body, name: event.target.value })}
            placeholder="supervisor"
            autoComplete="off"
          />
          <p className="text-[0.7rem] text-muted-foreground">
            Lowercase letters, digits and hyphens, not starting with a hyphen. Becomes{" "}
            <code className="ref-chip">loop-standing-{body.name || "name"}</code> in tmux.
          </p>
        </div>

        <div className="space-y-1">
          <FieldLabel htmlFor="standing-cwd">Working directory</FieldLabel>
          <input
            id="standing-cwd"
            className={INPUT_CLASS}
            value={body.cwd}
            onChange={(event) => setBody({ ...body, cwd: event.target.value })}
            placeholder="empty inherits routing.spawnWorkdir"
            autoComplete="off"
          />
          <p className="text-[0.7rem] text-muted-foreground">It must exist — a session is never spawned into a directory that is not there.</p>
        </div>

        <div className="space-y-1">
          <FieldLabel htmlFor="standing-description">Description</FieldLabel>
          <input
            id="standing-description"
            className={INPUT_CLASS}
            value={body.description}
            onChange={(event) => setBody({ ...body, description: event.target.value })}
            placeholder="What this session is for, in one line"
            autoComplete="off"
          />
        </div>

        <div className="space-y-1">
          <FieldLabel htmlFor="standing-prompt">Brief</FieldLabel>
          <textarea
            id="standing-prompt"
            className={INPUT_CLASS}
            rows={3}
            value={body.prompt}
            onChange={(event) => setBody({ ...body, prompt: event.target.value })}
            placeholder="Watch the work items in flight and tell me what is stuck."
          />
          <p className="text-[0.7rem] text-muted-foreground">
            Appended to the-loop&rsquo;s own directive — you own no work item, do not answer a phase gate or post a
            control keyword on any ticket — never substituted for it.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <ControlButton type="submit" primary disabled={!valid || busy}>
            {busy ? "Creating…" : "Create and start"}
          </ControlButton>
          <ControlButton onClick={() => setOpen(false)}>Cancel</ControlButton>
        </div>
      </form>
    </Card>
  );
}

function SessionCard({
  session,
  busy,
  onControl,
  onDelete,
  onSay,
}: {
  session: StandingSessionRecord;
  busy: string;
  onControl: (verb: StandingVerb) => void;
  onDelete: () => void;
  onSay: (text: string) => void;
}) {
  const [message, setMessage] = useState("");
  const [confirming, setConfirming] = useState(false);
  const working = busy.endsWith(`:${session.name}`);

  return (
    <Card data-standing-card={session.name}>
      <div className="flex flex-wrap items-center gap-2">
        <StatusDot status={session.running ? "active" : "pending"} />
        <h3 className="font-mono text-sm text-foreground">{session.name}</h3>
        {/* Text, never a dot alone: the declared/created split decides whether
            `delete` is even offered, so it must survive being read without colour. */}
        <span className="rounded-md border border-border bg-surface-2 px-2 py-0.5 font-mono text-[0.68rem] text-muted-foreground">
          {session.declared ? "declared in config" : "created here"}
        </span>
        <span className="font-mono text-[0.7rem] text-muted-foreground">{session.running ? "running" : session.status}</span>
      </div>

      {session.description ? <p className="text-sm leading-relaxed text-foreground/85">{session.description}</p> : null}

      <div className="space-y-1.5">
        <KV k="tmux" v={session.tmuxTarget} title={session.tmuxTarget} />
        <KV k="harness" v={session.harness || "—"} />
        <KV k="directory" v={session.cwd || "—"} title={session.cwd || undefined} />
        <KV k="started" v={session.startedAt ? relativeTime(session.startedAt) : "—"} mono={false} title={session.startedAt || undefined} />
        {session.slackThread ? <KV k="slack" v={`thread in ${session.slackChannel || "the configured channel"}`} mono={false} /> : null}
      </div>

      <div className="flex flex-wrap gap-1.5">
        {session.running ? (
          <>
            <ControlButton disabled={working} onClick={() => onControl("stop")}>
              Stop
            </ControlButton>
            <ControlButton disabled={working} onClick={() => onControl("restart")}>
              Restart
            </ControlButton>
          </>
        ) : (
          <ControlButton primary disabled={working} onClick={() => onControl("start")}>
            Start
          </ControlButton>
        )}
        {/* Offered only for a created session: the service refuses it for a
            declared one, and a button whose only outcome is that refusal is
            worse than no button. */}
        {session.declared ? null : confirming ? (
          <>
            <ControlButton disabled={working} onClick={onDelete} className="border-state-blocked/40 text-state-blocked hover:bg-surface-2 hover:text-state-blocked">
              Delete {session.name} for good
            </ControlButton>
            <ControlButton onClick={() => setConfirming(false)}>Keep it</ControlButton>
          </>
        ) : (
          <ControlButton disabled={working} onClick={() => setConfirming(true)}>
            Delete…
          </ControlButton>
        )}
      </div>

      <form
        className="flex items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (!message.trim() || working) return;
          onSay(message);
          setMessage("");
        }}
      >
        <label className="sr-only-label" htmlFor={`say-${session.name}`}>
          Message {session.name}
        </label>
        <input
          id={`say-${session.name}`}
          className={INPUT_CLASS}
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder={session.running ? `Message ${session.name}…` : "Start it to send a message"}
          disabled={!session.running || working}
          autoComplete="off"
        />
        <ControlButton type="submit" disabled={!session.running || !message.trim() || working}>
          Send
        </ControlButton>
      </form>
      <p className="text-[0.7rem] text-muted-foreground">
        Pasted straight into the pane. Nothing is posted to any ticket — a standing session has none, so the event log is
        the record.
      </p>
    </Card>
  );
}
