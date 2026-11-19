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
import { t } from "../i18n.ts";
import { Card, ControlButton, Empty, FieldLabel, INPUT_CLASS, InstanceChip, KV, Report } from "../components/primitives.tsx";
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
        title={t("ui.standing.title")}
        meta={<span>{t("ui.standing.meta")}</span>}
      />
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-6 py-6">
        <div className="mx-auto max-w-3xl space-y-4">
          {error ? (
            <Report tone="fail" role="alert">
              <strong className="font-medium">{t("ui.standing.refused")}</strong> {error}
            </Report>
          ) : null}
          {note && !error ? <Report tone="ok" role="status">{note}</Report> : null}

          <CreateForm
            busy={busy === "create"}
            onCreate={(body) => run("create", () => api.createStandingSession(body), t("ui.standing.done.created", { name: body.name }))}
          />

          {sessions.loading && rows.length === 0 ? <Empty>{t("ui.standing.loading")}</Empty> : null}
          {!sessions.loading && rows.length === 0 ? (
            <Empty>
              {t("ui.standing.empty.a")}
              <code className="ref-chip">standingSessions.sessions</code>
              {t("ui.standing.empty.b")}
            </Empty>
          ) : null}

          {/* Every verb carries the row's instance (issue-374, R5.1): on a
              manager the name alone may be two sessions, one per member. */}
          {rows.map((session) => (
            <SessionCard
              key={`${session.instance ?? ""}:${session.name}`}
              session={session}
              busy={busy}
              onControl={(verb) =>
                run(
                  `${verb}:${session.name}`,
                  () => api.controlStandingSession(session.name, verb, session.instance),
                  `${verb} ${session.name}.`,
                )
              }
              onDelete={() =>
                run(`delete:${session.name}`, () => api.deleteStandingSession(session.name, session.instance), t("ui.standing.done.deleted", { name: session.name }))
              }
              onSay={(text) =>
                run(
                  `say:${session.name}`,
                  () => api.sayToStandingSession(session.name, text, "", session.instance),
                  t("ui.standing.done.delivered", { name: session.name }),
                )
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
        <ControlButton onClick={() => setOpen(true)}>{t("ui.standing.create.open")}</ControlButton>
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
          <FieldLabel htmlFor="standing-name">{t("ui.standing.create.name")}</FieldLabel>
          <input
            id="standing-name"
            className={INPUT_CLASS}
            value={body.name}
            onChange={(event) => setBody({ ...body, name: event.target.value })}
            placeholder={t("ui.standing.create.name.placeholder")}
            autoComplete="off"
          />
          <p className="text-[0.7rem] text-muted-foreground">
            {t("ui.standing.create.name.hint")}
            <code className="ref-chip">loop-standing-{body.name || "name"}</code>
            {t("ui.standing.create.name.hint-end")}
          </p>
        </div>

        <div className="space-y-1">
          <FieldLabel htmlFor="standing-cwd">{t("ui.standing.create.cwd")}</FieldLabel>
          <input
            id="standing-cwd"
            className={INPUT_CLASS}
            value={body.cwd}
            onChange={(event) => setBody({ ...body, cwd: event.target.value })}
            placeholder={t("ui.standing.create.cwd.placeholder")}
            autoComplete="off"
          />
          <p className="text-[0.7rem] text-muted-foreground">{t("ui.standing.create.cwd.hint")}</p>
        </div>

        <div className="space-y-1">
          <FieldLabel htmlFor="standing-description">{t("ui.standing.create.description")}</FieldLabel>
          <input
            id="standing-description"
            className={INPUT_CLASS}
            value={body.description}
            onChange={(event) => setBody({ ...body, description: event.target.value })}
            placeholder={t("ui.standing.create.description.placeholder")}
            autoComplete="off"
          />
        </div>

        <div className="space-y-1">
          <FieldLabel htmlFor="standing-prompt">{t("ui.standing.create.brief")}</FieldLabel>
          <textarea
            id="standing-prompt"
            className={INPUT_CLASS}
            rows={3}
            value={body.prompt}
            onChange={(event) => setBody({ ...body, prompt: event.target.value })}
            placeholder={t("ui.standing.create.brief.placeholder")}
          />
          <p className="text-[0.7rem] text-muted-foreground">
            {t("ui.standing.create.brief.hint")}
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <ControlButton type="submit" primary disabled={!valid || busy}>
            {busy ? t("ui.standing.create.creating") : t("ui.standing.create.submit")}
          </ControlButton>
          <ControlButton onClick={() => setOpen(false)}>{t("ui.standing.create.cancel")}</ControlButton>
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
        {session.instance ? <InstanceChip instance={session.instance} /> : null}
        {/* Text, never a dot alone: the declared/created split decides whether
            `delete` is even offered, so it must survive being read without colour. */}
        <span className="rounded-md border border-border bg-surface-2 px-2 py-0.5 font-mono text-[0.68rem] text-muted-foreground">
          {session.declared ? t("ui.standing.card.declared") : t("ui.standing.card.created")}
        </span>
        <span className="font-mono text-[0.7rem] text-muted-foreground">{session.running ? t("ui.standing.card.running") : session.status}</span>
      </div>

      {session.description ? <p className="text-sm leading-relaxed text-foreground/85">{session.description}</p> : null}

      <div className="space-y-1.5">
        <KV k={t("ui.standing.card.tmux")} v={session.tmuxTarget} title={session.tmuxTarget} />
        <KV k={t("ui.standing.card.harness")} v={session.harness || "—"} />
        <KV k={t("ui.standing.card.directory")} v={session.cwd || "—"} title={session.cwd || undefined} />
        <KV k={t("ui.standing.card.started")} v={session.startedAt ? relativeTime(session.startedAt) : "—"} mono={false} title={session.startedAt || undefined} />
        {session.slackThread ? <KV k={t("ui.standing.card.slack")} v={t("ui.standing.card.slack-thread", { channel: session.slackChannel || t("ui.standing.card.slack-default") })} mono={false} /> : null}
      </div>

      <div className="flex flex-wrap gap-1.5">
        {session.running ? (
          <>
            <ControlButton disabled={working} onClick={() => onControl("stop")}>
              {t("ui.standing.card.stop")}
            </ControlButton>
            <ControlButton disabled={working} onClick={() => onControl("restart")}>
              {t("ui.standing.card.restart")}
            </ControlButton>
          </>
        ) : (
          <ControlButton primary disabled={working} onClick={() => onControl("start")}>
            {t("ui.standing.card.start")}
          </ControlButton>
        )}
        {/* Offered only for a created session: the service refuses it for a
            declared one, and a button whose only outcome is that refusal is
            worse than no button. */}
        {session.declared ? null : confirming ? (
          <>
            <ControlButton disabled={working} onClick={onDelete} className="border-state-blocked/40 text-state-blocked hover:bg-surface-2 hover:text-state-blocked">
              {t("ui.standing.card.delete-confirm", { name: session.name })}
            </ControlButton>
            <ControlButton onClick={() => setConfirming(false)}>{t("ui.standing.card.keep")}</ControlButton>
          </>
        ) : (
          <ControlButton disabled={working} onClick={() => setConfirming(true)}>
            {t("ui.standing.card.delete")}
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
          {t("ui.standing.card.message-label", { name: session.name })}
        </label>
        <input
          id={`say-${session.name}`}
          className={INPUT_CLASS}
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder={session.running ? t("ui.standing.card.message-placeholder", { name: session.name }) : t("ui.standing.card.message-stopped")}
          disabled={!session.running || working}
          autoComplete="off"
        />
        <ControlButton type="submit" disabled={!session.running || !message.trim() || working}>
          {t("ui.standing.card.send")}
        </ControlButton>
      </form>
      <p className="text-[0.7rem] text-muted-foreground">
        {t("ui.standing.card.say-hint")}
      </p>
    </Card>
  );
}
