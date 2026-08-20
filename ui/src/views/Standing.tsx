/**
 * The Standing screen (issue-277): the sessions that belong to no work item.
 *
 * The Sessions screen is shaped like the work: a sidebar of work items, each
 * opening into an outer loop and its PR inner loops. A standing session has
 * none of that — no ticket, no tree, no completion — so it gets its own screen
 * rather than a row that lies about being part of one.
 *
 * What the screen has to make visible is the split the CLI makes visible too:
 * a **declared** session comes from `standingSessions.sessions` and is removed
 * by editing that file, while a **created** one lives only in the registry and
 * `delete` really deletes it. Every refusal the service makes is surfaced as
 * the service's own sentence, never re-worded here — the API is the authority
 * on why something was refused, and paraphrasing it is how a UI starts
 * disagreeing with the CLI.
 */

import { useState } from "react";

import { relativeTime } from "../api/model.ts";
import type { StandingSessionRecord, StandingVerb } from "../api/types.ts";
import { Blueprint } from "../components/Blueprint.tsx";
import { useApi } from "../state/ApiContext.tsx";
import { useAsync } from "../state/useAsync.ts";

export function Standing() {
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
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy("");
    }
  };

  const rows = sessions.data ?? [];

  return (
    <div className="lp-standing">
      <div className="lp-trace-head">
        <h2 className="lp-h2">Standing sessions</h2>
        <span className="lp-subtle">
          Sessions that belong to no work item — no ticket, no phases, running until you stop them.
        </span>
      </div>

      {error ? (
        <Blueprint className="lp-standing-error">
          <strong>The service refused that.</strong> {error}
        </Blueprint>
      ) : null}
      {note && !error ? <div className="lp-empty">{note}</div> : null}

      <CreateForm
        busy={busy === "create"}
        onCreate={(body) =>
          run("create", () => api.createStandingSession(body), `Created and started ${body.name}.`)
        }
      />

      {sessions.loading && rows.length === 0 ? <div className="lp-empty">Loading…</div> : null}
      {!sessions.loading && rows.length === 0 ? (
        <div className="lp-empty">
          No standing sessions. Declare one under <code className="lp-code">standingSessions.sessions</code>, or create
          one above.
        </div>
      ) : null}

      {rows.map((session) => (
        <SessionCard
          key={session.name}
          session={session}
          busy={busy}
          onControl={(verb) =>
            run(`${verb}:${session.name}`, () => api.controlStandingSession(session.name, verb), `${verb} ${session.name}.`)
          }
          onDelete={() =>
            run(`delete:${session.name}`, () => api.deleteStandingSession(session.name), `Deleted ${session.name}.`)
          }
          onSay={(text) =>
            run(`say:${session.name}`, () => api.sayToStandingSession(session.name, text), `Delivered into ${session.name}.`)
          }
        />
      ))}
    </div>
  );
}

interface CreateBody {
  name: string;
  cwd: string;
  prompt: string;
  description: string;
}

/**
 * The create form.
 *
 * Four fields, not eleven: a name, where it runs, what it is for, and its
 * brief. Everything else the API accepts — the harness, its arguments, the
 * Slack binding, `autoStart` — has a `routing` default that is right far more
 * often than not, and a form that asks for all of them turns a two-second
 * action into a configuration exercise. The CLI and the API still take them.
 */
function CreateForm({ busy, onCreate }: { busy: boolean; onCreate: (body: CreateBody) => void }) {
  const [open, setOpen] = useState(false);
  const [body, setBody] = useState<CreateBody>({ name: "", cwd: "", prompt: "", description: "" });
  const valid = /^[a-z0-9][a-z0-9-]{0,39}$/.test(body.name);

  if (!open) {
    return (
      <div className="lp-standing-createbar">
        <button type="button" className="btn" onClick={() => setOpen(true)}>
          Create a standing session
        </button>
      </div>
    );
  }

  return (
    <Blueprint className="lp-standing-create">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (!valid || busy) return;
          onCreate(body);
          setBody({ name: "", cwd: "", prompt: "", description: "" });
          setOpen(false);
        }}
      >
        <div className="lp-standing-field">
          <label htmlFor="standing-name">Name</label>
          <input
            id="standing-name"
            value={body.name}
            onChange={(event) => setBody({ ...body, name: event.target.value })}
            placeholder="supervisor"
            autoComplete="off"
          />
          {/* The same expression the schema and the core enforce. Saying it
              here turns a round-trip refusal into a typo you fix as you type. */}
          <span className="lp-subtle">
            Lowercase letters, digits and hyphens, not starting with a hyphen. Becomes{" "}
            <code className="lp-code">loop-standing-{body.name || "name"}</code> in tmux.
          </span>
        </div>

        <div className="lp-standing-field">
          <label htmlFor="standing-cwd">Working directory</label>
          <input
            id="standing-cwd"
            value={body.cwd}
            onChange={(event) => setBody({ ...body, cwd: event.target.value })}
            placeholder="empty inherits routing.spawnWorkdir"
            autoComplete="off"
          />
          <span className="lp-subtle">It must exist — a session is never spawned into a directory that is not there.</span>
        </div>

        <div className="lp-standing-field">
          <label htmlFor="standing-description">Description</label>
          <input
            id="standing-description"
            value={body.description}
            onChange={(event) => setBody({ ...body, description: event.target.value })}
            placeholder="What this session is for, in one line"
            autoComplete="off"
          />
        </div>

        <div className="lp-standing-field">
          <label htmlFor="standing-prompt">Brief</label>
          <textarea
            id="standing-prompt"
            rows={3}
            value={body.prompt}
            onChange={(event) => setBody({ ...body, prompt: event.target.value })}
            placeholder="Watch the work items in flight and tell me what is stuck."
          />
          <span className="lp-subtle">
            Appended to the-loop&rsquo;s own directive — you own no work item, do not answer a phase gate or post a
            control keyword on any ticket — never substituted for it.
          </span>
        </div>

        <div className="lp-standing-actions">
          <button type="submit" className="btn btn-primary" disabled={!valid || busy}>
            {busy ? "Creating…" : "Create and start"}
          </button>
          <button type="button" className="btn btn-ghost" onClick={() => setOpen(false)}>
            Cancel
          </button>
        </div>
      </form>
    </Blueprint>
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
    <Blueprint className="lp-standing-card">
      <div className="lp-standing-head">
        <span className={`lp-daemon-dot ${session.running ? "on" : "off"}`} aria-hidden="true" />
        <h3 className="lp-h3">{session.name}</h3>
        {/* Text, never a dot alone: the declared/created split decides whether
            `delete` is even offered, so it must survive being read without
            colour. */}
        <span className="lp-standing-tag">{session.declared ? "declared in config" : "created here"}</span>
        <span className="lp-subtle">{session.running ? "running" : session.status}</span>
      </div>

      {session.description ? <p className="lp-standing-desc">{session.description}</p> : null}

      <dl className="lp-standing-facts">
        <div>
          <dt>tmux</dt>
          <dd>
            <code className="lp-code">{session.tmuxTarget}</code>
          </dd>
        </div>
        <div>
          <dt>harness</dt>
          <dd>{session.harness || "—"}</dd>
        </div>
        <div>
          <dt>directory</dt>
          <dd>
            <code className="lp-code">{session.cwd || "—"}</code>
          </dd>
        </div>
        <div>
          <dt>started</dt>
          <dd>{session.startedAt ? relativeTime(session.startedAt) : "—"}</dd>
        </div>
        {session.slackThread ? (
          <div>
            <dt>slack</dt>
            <dd>thread in {session.slackChannel || "the configured channel"}</dd>
          </div>
        ) : null}
      </dl>

      <div className="lp-standing-actions">
        {session.running ? (
          <>
            <button type="button" className="btn" disabled={working} onClick={() => onControl("stop")}>
              Stop
            </button>
            <button type="button" className="btn btn-ghost" disabled={working} onClick={() => onControl("restart")}>
              Restart
            </button>
          </>
        ) : (
          <button type="button" className="btn btn-primary" disabled={working} onClick={() => onControl("start")}>
            Start
          </button>
        )}
        {/* Offered only for a created session. The service refuses it for a
            declared one — `the-loop start` would recreate the record — and a
            button whose only outcome is that refusal is worse than no button. */}
        {session.declared ? null : confirming ? (
          <>
            <button type="button" className="btn btn-danger" disabled={working} onClick={onDelete}>
              Delete {session.name} for good
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => setConfirming(false)}>
              Keep it
            </button>
          </>
        ) : (
          <button type="button" className="btn btn-ghost" disabled={working} onClick={() => setConfirming(true)}>
            Delete…
          </button>
        )}
      </div>

      <form
        className="lp-standing-say"
        onSubmit={(event) => {
          event.preventDefault();
          if (!message.trim() || working) return;
          onSay(message);
          setMessage("");
        }}
      >
        <label className="lp-visually-hidden" htmlFor={`say-${session.name}`}>
          Message {session.name}
        </label>
        <input
          id={`say-${session.name}`}
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder={session.running ? `Message ${session.name}…` : "Start it to send a message"}
          disabled={!session.running || working}
          autoComplete="off"
        />
        <button type="submit" className="btn" disabled={!session.running || !message.trim() || working}>
          Send
        </button>
      </form>
      <span className="lp-subtle">
        Pasted straight into the pane. Nothing is posted to any ticket — a standing session has none, so the event log
        is the record.
      </span>
    </Blueprint>
  );
}
