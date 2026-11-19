/**
 * The Instances tab (issue-374, R5.3): the fleet as `GET /api/v1/instances`
 * serves it — name, URL, state in words beside its dot, version, mode, the
 * managed and session counts, the last probe — with a Register card and, per
 * row, **Open** (the Work board filtered to that instance), **Manage** (its
 * pane) and **Unregister** (a confirm, then the call).
 *
 * The same renderer serves both roles because the document has one shape: a
 * worker answers with one row, itself, and this tab shows it with no Register
 * card and one sentence naming `instance.role` — so an operator who points
 * the browser at the wrong box learns which box it is rather than meeting an
 * empty table. The manager's own row carries no Unregister: it is the fleet's
 * first member implicitly (R1.3), not a registered one.
 *
 * Refusals are the service's own sentences (its `400` detail verbatim), never
 * re-worded; the client-side check on the Register form is the same grammar
 * the schema enforces, so a typo is a disabled button rather than a round trip.
 */

import { useState } from "react";

import { relativeTime } from "../api/model.ts";
import type { InstanceRow, InstancesDocument } from "../api/types.ts";
import type { Chrome } from "../components/HeaderBar.tsx";
import { HeaderBar } from "../components/HeaderBar.tsx";
import { t } from "../i18n.ts";
import { Card, ControlButton, Empty, FieldLabel, INPUT_CLASS, Kicker, Notice, Report } from "../components/primitives.tsx";
import { StatusDot, type DotStatus } from "../components/StatusDot.tsx";
import { useApi } from "../state/ApiContext.tsx";
import { hrefFor } from "../state/route.ts";
import { useAsync } from "../state/useAsync.ts";

/** The instance-name grammar (issue-322) and the URL scheme the schema allows (R1.1). */
export const INSTANCE_NAME_RE = /^[a-z0-9][a-z0-9-]{0,39}$/;
export const INSTANCE_URL_RE = /^https?:\/\//;

/** A row's state as a dot: live is done, anything else is a fault. */
export function stateDot(state: string): DotStatus {
  return state === "live" ? "done" : "blocked";
}

/** The header's one line: who this is, how big the fleet is, how fresh the read. */
export function fleetSummary(doc: InstancesDocument): string {
  if (doc.role !== "manager") return t("ui.instances.summary.role", { name: doc.name || t("ui.instances.summary.unnamed"), role: doc.role });
  const members = doc.instances.filter((row) => row.name !== doc.name);
  const live = members.filter((row) => row.state === "live").length;
  const newest = doc.instances.map((row) => row.probedAt).filter(Boolean).toSorted().at(-1);
  return [
    t("ui.instances.summary.manager", { name: doc.name }),
    t("ui.instances.summary.registered", { count: members.length }),
    members.length ? t("ui.instances.summary.live", { live, count: members.length }) : "",
    newest ? t("ui.instances.summary.probed", { when: relativeTime(newest) }) : "",
  ]
    .filter(Boolean)
    .join(" · ");
}

export function Instances({ chrome, onChanged }: { chrome: Chrome; onChanged?: () => void }) {
  const { api } = useApi();
  const fleet = useAsync((signal) => api.instances(signal), [api]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [confirming, setConfirming] = useState("");

  /** Run one registry write, then reload. The service's message is the message. */
  const run = async (key: string, action: () => Promise<unknown>, done: string) => {
    setBusy(key);
    setError("");
    setNote("");
    try {
      await action();
      setNote(done);
      setConfirming("");
      fleet.reload();
      onChanged?.();
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy("");
    }
  };

  const doc = fleet.data;
  const manager = doc?.role === "manager";
  const down = doc?.instances.filter((row) => row.state !== "live") ?? [];

  return (
    <>
      <HeaderBar
        chrome={chrome}
        title={t("ui.instances.title")}
        meta={<span className="font-mono">{doc ? fleetSummary(doc) : fleet.loading ? t("ui.instances.reading") : ""}</span>}
      />
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-6 py-6">
        <div className="mx-auto max-w-5xl space-y-4">
          {fleet.error && !doc ? (
            <Report tone="fail" role="alert">
              {fleet.error.message}
            </Report>
          ) : null}
          {error ? (
            <Report tone="fail" role="alert">
              <strong className="font-medium">{t("ui.instances.refused")}</strong> {error}
            </Report>
          ) : null}
          {note && !error ? (
            <Report tone="ok" role="status">
              {note}
            </Report>
          ) : null}

          {down.length > 0 ? (
            <Notice tone="blocked" role="status">
              <div>
                {down.length === 1 ? t("ui.instances.down.lead-one") : t("ui.instances.down.lead-other", { count: down.length })}
                {down.map((row, index) => (
                  <span key={row.name}>
                    {index > 0 ? "; " : ""}
                    <strong className="font-mono font-medium">{row.name}</strong>
                    {row.detail ? ` — ${row.detail}` : ""}
                  </span>
                ))}
                {down.length === 1 ? t("ui.instances.down.tail-one") : t("ui.instances.down.tail-other")}
              </div>
            </Notice>
          ) : null}

          {fleet.loading && !doc ? <Empty>{t("ui.instances.loading")}</Empty> : null}

          {doc ? (
            <Card className="overflow-x-auto">
              <Kicker>{manager ? t("ui.instances.kicker.manager") : t("ui.instances.kicker.worker")}</Kicker>
              <table className="w-full border-collapse text-sm" aria-label={t("ui.instances.table.label")}>
                <thead className="max-md:hidden">
                  <tr className="text-left text-[0.68rem] font-medium text-muted-foreground">
                    <th className="border-b border-border px-2 py-1.5">{t("ui.instances.table.name")}</th>
                    <th className="border-b border-border px-2 py-1.5">{t("ui.instances.table.url")}</th>
                    <th className="border-b border-border px-2 py-1.5">{t("ui.instances.table.state")}</th>
                    <th className="border-b border-border px-2 py-1.5">{t("ui.instances.table.version")}</th>
                    <th className="border-b border-border px-2 py-1.5">{t("ui.instances.table.mode")}</th>
                    <th className="border-b border-border px-2 py-1.5 text-right">{t("ui.instances.table.managed")}</th>
                    <th className="border-b border-border px-2 py-1.5 text-right">{t("ui.instances.table.sessions")}</th>
                    <th className="border-b border-border px-2 py-1.5">{t("ui.instances.table.probed")}</th>
                    <th className="border-b border-border px-2 py-1.5" />
                  </tr>
                </thead>
                <tbody>
                  {doc.instances.map((row) => (
                    <InstanceTableRow
                      key={row.name}
                      row={row}
                      own={row.name === doc.name}
                      manager={manager}
                      busy={busy}
                      confirming={confirming === row.name}
                      onConfirm={(open) => setConfirming(open ? row.name : "")}
                      onUnregister={() =>
                        run(`unregister:${row.name}`, () => api.unregisterInstance(row.name), t("ui.instances.done.unregistered", { name: row.name }))
                      }
                    />
                  ))}
                </tbody>
              </table>
            </Card>
          ) : null}

          {doc && manager ? (
            <RegisterForm
              busy={busy === "register"}
              taken={doc.instances.map((row) => row.name)}
              onRegister={(name, url) =>
                run("register", () => api.registerInstance(name, url), t("ui.instances.done.registered", { name }))
              }
            />
          ) : null}

          {doc && !manager ? (
            <p className="text-xs leading-relaxed text-muted-foreground" data-worker-note>
              {t("ui.instances.worker-note.a")}
              <strong className="font-medium text-foreground">{t("ui.instances.worker-note.worker")}</strong>
              {t("ui.instances.worker-note.b")}
              <code className="ref-chip">instance.role: worker</code>
              {t("ui.instances.worker-note.c")}
            </p>
          ) : null}
        </div>
      </div>
    </>
  );
}

const CELL = "border-b border-border px-2 py-2 align-middle max-md:block max-md:border-0 max-md:py-0.5";

function InstanceTableRow({
  row,
  own,
  manager,
  busy,
  confirming,
  onConfirm,
  onUnregister,
}: {
  row: InstanceRow;
  own: boolean;
  manager: boolean;
  busy: string;
  confirming: boolean;
  onConfirm: (open: boolean) => void;
  onUnregister: () => void;
}) {
  const live = row.state === "live";
  const working = busy === `unregister:${row.name}`;
  const dash = (value: string | number) => (live ? String(value) : "—");
  return (
    <tr data-instance-row={row.name} className="max-md:block max-md:border-b max-md:border-border max-md:py-2">
      <td className={`${CELL} whitespace-nowrap font-mono`}>
        {row.name}
        {own ? <span className="ml-1.5 font-sans text-[0.68rem] text-muted-foreground">{t("ui.instances.row.own")}</span> : null}
      </td>
      <td className={`${CELL} font-mono text-[0.75rem] text-muted-foreground`}>{row.url}</td>
      <td className={`${CELL} whitespace-nowrap`}>
        <span className="inline-flex items-center gap-1.5">
          <StatusDot status={stateDot(row.state)} />
          <span className={live ? "" : "text-state-blocked"}>{row.state}</span>
        </span>
        {!live && row.detail ? <div className="text-[0.7rem] text-muted-foreground">{row.detail}</div> : null}
      </td>
      <td className={`${CELL} font-mono text-[0.75rem]`}>{live ? row.version || "—" : "—"}</td>
      <td className={CELL}>{live ? row.mode || "—" : "—"}</td>
      <td className={`${CELL} text-right tabular-nums`}>{dash(row.managedCount)}</td>
      <td className={`${CELL} text-right tabular-nums`}>{dash(row.sessionCount)}</td>
      <td className={`${CELL} text-[0.75rem] text-muted-foreground`} title={row.probedAt || undefined}>
        {own ? t("ui.instances.row.now") : row.probedAt ? relativeTime(row.probedAt) : "—"}
      </td>
      <td className={`${CELL} max-md:pt-1.5`}>
        <div className="flex flex-wrap justify-end gap-1.5 max-md:justify-start">
          {live ? (
            <a
              href={hrefFor({ name: "work", filter: row.name })}
              className="rounded-md border border-border px-2 py-1.5 font-mono text-[0.7rem] text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground"
            >
              {t("ui.instances.row.open")}
            </a>
          ) : (
            <ControlButton disabled title={t("ui.instances.row.not-live")}>
              {t("ui.instances.row.open")}
            </ControlButton>
          )}
          <a
            href={hrefFor({ name: "instance", instance: row.name })}
            className="rounded-md border border-border px-2 py-1.5 font-mono text-[0.7rem] text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground"
          >
            {t("ui.instances.row.manage")}
          </a>
          {/* No Unregister on the manager's own row — it is not registered
              (R1.3) — nor on a worker, which registers nothing (R4.4). */}
          {manager && !own ? (
            confirming ? (
              <>
                <ControlButton
                  disabled={working}
                  onClick={onUnregister}
                  className="border-state-blocked/40 text-state-blocked hover:bg-surface-2 hover:text-state-blocked"
                >
                  {working ? t("ui.instances.row.unregistering") : t("ui.instances.row.unregister-confirm", { name: row.name })}
                </ControlButton>
                <ControlButton onClick={() => onConfirm(false)}>{t("ui.instances.row.keep")}</ControlButton>
              </>
            ) : (
              <ControlButton disabled={working} onClick={() => onConfirm(true)} className="text-state-blocked">
                {t("ui.instances.row.unregister")}
              </ControlButton>
            )
          ) : null}
        </div>
      </td>
    </tr>
  );
}

/**
 * What the form checks before the service does — the same grammar
 * `cli-config.schema.json` enforces on `instance.manager.instances`, plus the
 * uniqueness the registry requires. Exported for its own test.
 */
export function registerProblems(name: string, url: string, taken: string[]): { name?: string; url?: string } {
  const problems: { name?: string; url?: string } = {};
  if (name && !INSTANCE_NAME_RE.test(name)) problems.name = t("ui.instances.register.problem.name");
  else if (name && taken.includes(name)) problems.name = t("ui.instances.register.problem.taken", { name });
  if (url && !INSTANCE_URL_RE.test(url.trim())) problems.url = t("ui.instances.register.problem.url");
  return problems;
}

function RegisterForm({
  busy,
  taken,
  onRegister,
}: {
  busy: boolean;
  taken: string[];
  onRegister: (name: string, url: string) => void;
}) {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const problems = registerProblems(name.trim(), url, taken);
  const valid = name.trim() !== "" && url.trim() !== "" && !problems.name && !problems.url;

  return (
    <Card>
      <Kicker>{t("ui.instances.register.kicker")}</Kicker>
      <form
        className="grid gap-3 md:grid-cols-[1fr_2fr_auto] md:items-end"
        onSubmit={(event) => {
          event.preventDefault();
          if (!valid || busy) return;
          onRegister(name.trim(), url.trim().replace(/\/+$/, ""));
          setName("");
          setUrl("");
        }}
      >
        <div className="space-y-1">
          <FieldLabel htmlFor="register-name">
            {t("ui.instances.register.name")}
            <code className="ref-chip">instance.name</code>
          </FieldLabel>
          <input
            id="register-name"
            className={`${INPUT_CLASS} font-mono`}
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder={t("ui.instances.register.name.placeholder")}
            autoComplete="off"
            spellCheck={false}
            aria-invalid={problems.name ? true : undefined}
          />
          {problems.name ? (
            <Report tone="fail" role="alert">
              {problems.name}
            </Report>
          ) : null}
        </div>
        <div className="space-y-1">
          <FieldLabel htmlFor="register-url">{t("ui.instances.register.url")}</FieldLabel>
          <input
            id="register-url"
            className={`${INPUT_CLASS} font-mono`}
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="http://10.0.0.10:4114"
            autoComplete="off"
            spellCheck={false}
            aria-invalid={problems.url ? true : undefined}
          />
          {problems.url ? (
            <Report tone="fail" role="alert">
              {problems.url}
            </Report>
          ) : null}
        </div>
        <ControlButton type="submit" primary disabled={!valid || busy}>
          {busy ? t("ui.instances.register.registering") : t("ui.instances.register.submit")}
        </ControlButton>
      </form>
      <p className="text-[0.7rem] leading-relaxed text-muted-foreground">
        {t("ui.instances.register.hint.a")}
        <code className="ref-chip">^[a-z0-9][a-z0-9-]{"{0,39}"}$</code>
        {t("ui.instances.register.hint.b")}
        <em>{t("ui.instances.register.hint.unreachable")}</em>
        {t("ui.instances.register.hint.c")}
        <code className="ref-chip">instance.manager.instances</code>
        {t("ui.instances.register.hint.d")}
        <code className="ref-chip">cli-config.yaml</code>
        {t("ui.instances.register.hint.e")}
      </p>
    </Card>
  );
}
