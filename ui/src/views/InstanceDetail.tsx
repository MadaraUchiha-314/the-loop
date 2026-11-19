/**
 * One instance, managed on its own (issue-374, R5.4): its identity from
 * `GET /instance?instance=<name>` with the managed list as chips, its daemons
 * with the start/stop verbs, a Restart, its config in the existing
 * schema-driven editor (read and written with `instance=<name>`), its health,
 * and — on a manager, for a member — Unregister.
 *
 * Every control is disabled with the row's `detail` as the reason when the
 * instance is not `live`: the manager sends nothing to a member that has not
 * answered to its name (R6.1), so a button here would only ever meet a 502.
 * The row itself comes from `GET /instances`, the one read that says what
 * state the member is in; the per-instance reads run only once it is live.
 */

import { useState } from "react";

import { ApiError } from "../api/client.ts";
import { relativeTime } from "../api/model.ts";
import type { DaemonStatus, DaemonVerb, GatewayDocument } from "../api/types.ts";
import { ConfigSection } from "../components/ConfigEditor.tsx";
import type { Chrome } from "../components/HeaderBar.tsx";
import { HeaderBar } from "../components/HeaderBar.tsx";
import { t } from "../i18n.ts";
import { Card, ControlButton, Empty, Kicker, KV, Notice, Report } from "../components/primitives.tsx";
import type { DotStatus } from "../components/StatusDot.tsx";
import { StatusDot } from "../components/StatusDot.tsx";
import { useApi } from "../state/ApiContext.tsx";
import { hrefFor, navigate } from "../state/route.ts";
import { useAsync } from "../state/useAsync.ts";
import { stateDot } from "./Instances.tsx";

interface InstanceDetailProps {
  chrome: Chrome;
  /** The instance to manage — the `#/instances/<name>` segment. */
  name: string;
  onChanged?: () => void;
}

export function InstanceDetail({ chrome, name, onChanged }: InstanceDetailProps) {
  const { api } = useApi();
  const fleet = useAsync((signal) => api.instances(signal), [api]);
  const doc = fleet.data;
  const row = doc?.instances.find((candidate) => candidate.name === name);
  const own = doc?.name === name;
  const manager = doc?.role === "manager";
  const live = row?.state === "live";
  const reason = row && !live ? row.detail || t("ui.instance.not-live", { state: row.state }) : "";

  // The per-instance reads run only once the row is live: a request to a
  // member that has not answered to its name is one the manager refuses (R6.1).
  const identity = useAsync((signal) => (live ? api.instance(signal, name) : Promise.resolve(null)), [api, name, live]);
  const health = useAsync((signal) => (live ? api.health(signal, name) : Promise.resolve(null)), [api, name, live]);
  // The instance's view of its gateway (issue-496, R10.3): one more read, same rule.
  const gateway = useAsync((signal) => (live ? api.gateway(signal, name) : Promise.resolve(null)), [api, name, live]);
  const gatewayConfigured = gateway.data?.configured === true;
  const daemons = useAsync(
    async (signal) =>
      live
        ? // A manager's `/daemons` is the union, each row stamped; a worker's
          // rows carry no stamp and are all its own (the only instance there is).
          (await api.daemons(signal)).filter((daemon) => !daemon.instance || daemon.instance === name)
        : [],
    [api, name, live],
  );

  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [confirmRestart, setConfirmRestart] = useState(false);
  const [confirmUnregister, setConfirmUnregister] = useState(false);

  const run = async (key: string, action: () => Promise<unknown>, done: string, after?: () => void) => {
    setBusy(key);
    setError("");
    setNote("");
    try {
      await action();
      setNote(done);
      after?.();
    } catch (cause: unknown) {
      setError(cause instanceof ApiError ? cause.advice : cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy("");
    }
  };

  const controlDaemon = (daemon: DaemonStatus, verb: DaemonVerb) =>
    run(`${verb}:${daemon.daemon}`, () => api.controlDaemon(daemon.daemon, verb, name), t("ui.instance.done.daemon", { verb, daemon: daemon.daemon, name }), () =>
      daemons.reload(),
    );

  if (fleet.loading && !doc) {
    return (
      <>
        <HeaderBar chrome={chrome} title={<span className="font-mono">{name}</span>} />
        <div className="px-6 py-6">
          <Empty>{t("ui.instance.loading")}</Empty>
        </div>
      </>
    );
  }

  if (!row) {
    return (
      <>
        <HeaderBar chrome={chrome} title={<span className="font-mono">{name}</span>} />
        <div className="px-6 py-6">
          <Empty>
            {t("ui.instance.missing.a")}
            <code className="ref-chip">{name}</code>
            {t("ui.instance.missing.b")}
            <a href={hrefFor({ name: "instances" })} className="text-foreground underline-offset-2 hover:underline">
              {t("ui.instance.missing.back")}
            </a>
            .
          </Empty>
        </div>
      </>
    );
  }

  return (
    <>
      <HeaderBar
        chrome={chrome}
        title={<span className="font-mono">{name}</span>}
        meta={
          <>
            <span className="inline-flex items-center gap-1.5">
              <StatusDot status={stateDot(row.state)} />
              <span className={live ? "" : "text-state-blocked"}>{row.state}</span>
            </span>
            <span aria-hidden="true">·</span>
            <span className="font-mono">{row.url}</span>
            {live && row.version ? (
              <>
                <span aria-hidden="true">·</span>
                <span className="font-mono">{row.version}</span>
              </>
            ) : null}
            <span aria-hidden="true">·</span>
            <span title={row.probedAt || undefined}>
              {t("ui.instance.meta.probed", { when: own ? t("ui.instance.meta.now") : row.probedAt ? relativeTime(row.probedAt) : "—" })}
            </span>
            {own ? (
              <>
                <span aria-hidden="true">·</span>
                <span>{t("ui.instance.meta.own")}</span>
              </>
            ) : null}
          </>
        }
      />
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-6 py-6">
        <div className="mx-auto max-w-5xl space-y-4">
          {!live ? (
            <Notice tone="blocked" role="status">
              <div>
                {t("ui.instance.down.a")}
                <strong className="font-medium">{reason}</strong>
                {t("ui.instance.down.b")}
              </div>
            </Notice>
          ) : null}
          {error ? (
            <Report tone="fail" role="alert">
              <strong className="font-medium">{t("ui.instance.refused")}</strong> {error}
            </Report>
          ) : null}
          {note && !error ? (
            <Report tone="ok" role="status">
              {note}
            </Report>
          ) : null}

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <Kicker>{t("ui.instance.identity.kicker")}</Kicker>
              <div className="space-y-1.5">
                <KV k={t("ui.instance.identity.name")} v={row.name} />
                <KV k={t("ui.instance.identity.url")} v={row.url} title={row.url} />
                <KV k={t("ui.instance.identity.version")} v={live ? row.version || "—" : "—"} />
                <KV k={t("ui.instance.identity.mode")} v={live ? identity.data?.scope?.mode || row.mode || "—" : "—"} />
                <KV k={t("ui.instance.identity.managed")} mono={false}>
                  {!live ? (
                    "—"
                  ) : identity.loading && !identity.data ? (
                    <span className="text-muted-foreground">{t("ui.instance.identity.reading")}</span>
                  ) : identity.error ? (
                    <span className="text-state-blocked">{identity.error.message}</span>
                  ) : (
                    <span className="flex flex-wrap items-center gap-1">
                      <span className="tabular-nums">{identity.data?.managed.length ?? row.managedCount}</span>
                      {(identity.data?.managed ?? []).map((item) => (
                        <code key={item.ref} className="ref-chip">
                          {item.ref}
                        </code>
                      ))}
                    </span>
                  )}
                </KV>
                <KV k={t("ui.instance.identity.sessions")} v={live ? String(identity.data?.sessionCount ?? row.sessionCount) : "—"} />
              </div>
            </Card>

            <Card data-card="daemons">
              <Kicker>{t("ui.instance.daemons.kicker")}</Kicker>
              {!live ? (
                <p className="text-xs text-muted-foreground">{t("ui.instance.unanswered")}</p>
              ) : daemons.loading && !daemons.data ? (
                <p className="text-xs text-muted-foreground">{t("ui.instance.reading")}</p>
              ) : (daemons.data ?? []).length === 0 ? (
                <p className="text-xs text-muted-foreground">{t("ui.instance.daemons.none")}</p>
              ) : (
                <div className="divide-y divide-border">
                  {(daemons.data ?? []).map((daemon) => {
                    const offForGateway = gatewayConfigured && !daemon.running && LOCAL_INGRESSES.has(daemon.daemon);
                    return (
                      <div className="flex items-center gap-2 py-1.5 text-sm" key={daemon.daemon}>
                        <StatusDot status={daemon.running ? "done" : offForGateway ? "skipped" : "pending"} />
                        <span className="font-mono text-[0.8rem]">{daemon.daemon}</span>
                        <span className="text-[0.7rem] text-muted-foreground">
                          {daemon.running
                            ? daemon.lastCycleAt
                              ? t("ui.instance.daemons.running-cycle", { when: relativeTime(daemon.lastCycleAt) })
                              : t("ui.instance.daemons.running")
                            : offForGateway
                              ? t("ui.instance.daemons.off-gateway")
                              : t("ui.instance.daemons.stopped")}
                        </span>
                        <span className="ml-auto">
                          {offForGateway ? null : (
                            <ControlButton
                              disabled={busy !== ""}
                              onClick={() => void controlDaemon(daemon, daemon.running ? "stop" : "start")}
                            >
                              {daemon.running ? "stop" : "start"}
                            </ControlButton>
                          )}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
              <div className="flex flex-wrap items-center gap-2 pt-1">
                {confirmRestart ? (
                  <>
                    <ControlButton
                      disabled={!live || busy !== ""}
                      title={reason || undefined}
                      onClick={() =>
                        void run(
                          "restart",
                          () => api.restart(false, name),
                          t("ui.instance.done.restart", { name }),
                          () => setConfirmRestart(false),
                        )
                      }
                    >
                      {busy === "restart" ? t("ui.instance.restart.scheduling") : t("ui.instance.restart.confirm", { name })}
                    </ControlButton>
                    <ControlButton onClick={() => setConfirmRestart(false)}>{t("ui.instance.restart.cancel")}</ControlButton>
                  </>
                ) : (
                  <ControlButton disabled={!live || busy !== ""} title={reason || undefined} onClick={() => setConfirmRestart(true)}>
                    {t("ui.instance.restart.open")}
                  </ControlButton>
                )}
              </div>
            </Card>
          </div>

          {live ? (
            <ConfigSection instance={name} />
          ) : (
            <Card>
              <Kicker>{t("ui.instance.config.kicker")}</Kicker>
              <p className="text-xs leading-relaxed text-muted-foreground">
                {t("ui.instance.config.a")}
                <code className="ref-chip">instance={name}</code>
                {t("ui.instance.config.b", { reason })}
              </p>
            </Card>
          )}

          <Card>
            <Kicker>{t("ui.instance.health.kicker")}</Kicker>
            {!live ? (
              <p className="text-xs text-muted-foreground">{t("ui.instance.unanswered")}</p>
            ) : health.loading && !health.data ? (
              <p className="text-xs text-muted-foreground">{t("ui.instance.reading")}</p>
            ) : health.error ? (
              <Report tone="fail" role="alert">
                {health.error.message}
              </Report>
            ) : health.data ? (
              <div className="space-y-1.5">
                <KV k={t("ui.instance.health.status")}>
                  <span className="inline-flex items-center gap-1.5">
                    <StatusDot status={health.data.status === "ok" ? "done" : "blocked"} />
                    {health.data.status}
                  </span>
                </KV>
                <KV k={t("ui.instance.health.version")} v={health.data.version} />
                {typeof health.data.role === "string" ? <KV k={t("ui.instance.health.role")} v={health.data.role} /> : null}
              </div>
            ) : null}
          </Card>

          <GatewayCard live={live} loading={gateway.loading && !gateway.data} error={gateway.error} doc={gateway.data ?? null} />

          {manager && !own ? (
            <Card>
              <Kicker>{t("ui.instance.danger.kicker")}</Kicker>
              <div className="flex flex-wrap items-center gap-2">
                {confirmUnregister ? (
                  <>
                    <ControlButton
                      disabled={busy !== ""}
                      onClick={() =>
                        void run(`unregister`, () => api.unregisterInstance(name), t("ui.instance.done.unregistered", { name }), () => {
                          onChanged?.();
                          navigate({ name: "instances" });
                        })
                      }
                      className="border-state-blocked/40 text-state-blocked hover:bg-surface-2 hover:text-state-blocked"
                    >
                      {busy === "unregister" ? t("ui.instance.danger.unregistering") : t("ui.instance.danger.confirm", { name })}
                    </ControlButton>
                    <ControlButton onClick={() => setConfirmUnregister(false)}>{t("ui.instance.danger.keep")}</ControlButton>
                  </>
                ) : (
                  <ControlButton disabled={busy !== ""} onClick={() => setConfirmUnregister(true)} className="text-state-blocked">
                    {t("ui.instance.danger.open", { name })}
                  </ControlButton>
                )}
              </div>
              <p className="text-[0.7rem] text-muted-foreground">{t("ui.instance.danger.note")}</p>
            </Card>
          ) : null}
        </div>
      </div>
    </>
  );
}

/** The instance's own ingresses — the three a `gateway` block switches off (R3.8). */
const LOCAL_INGRESSES = new Set(["poller", "gh-webhook", "slack-listener"]);

/** The state word carries the meaning; the dot only colours it (prototype: design/gateway-card.html). */
export function gatewayWords(doc: GatewayDocument): { words: string; dot: DotStatus } {
  if (!doc.configured) return { words: t("ui.instance.gateway.not-configured"), dot: "skipped" };
  switch (doc.state) {
    case "connected":
      return {
        // `posting via gateway` (issue-519): the gateway makes this instance's Slack calls
        words:
          doc.slackPosting === "on"
            ? t("ui.instance.gateway.connected-posting", { mode: gatewayMode(doc) })
            : t("ui.instance.gateway.connected", { mode: gatewayMode(doc) }),
        dot: "active",
      };
    case "connecting":
      return { words: t("ui.instance.gateway.connecting", { attempt: doc.attempt ?? 1 }), dot: "pending" };
    case "refused":
      return { words: t("ui.instance.gateway.refused"), dot: "blocked" };
    case "unreachable":
      return { words: t("ui.instance.gateway.unreachable"), dot: "blocked" };
    default:
      return { words: doc.state, dot: "pending" };
  }
}

function gatewayMode(doc: GatewayDocument): string {
  return (doc.mode?.longPollSeconds ?? 0) > 0 ? t("ui.instance.gateway.mode.long-poll") : t("ui.instance.gateway.mode.polling");
}

function gatewayHealthWords(doc: GatewayDocument): { words: string; dot: DotStatus } {
  const health = doc.health;
  if (!health) return { words: doc.state === "connected" ? t("ui.instance.gateway.health.reading") : t("ui.instance.gateway.health.unknown"), dot: "pending" };
  const socket = health.slack?.socket;
  const running = Object.entries(health.ingresses ?? {}).filter(([, state]) => state === "running").length;
  const parts = [health.ok ? t("ui.instance.gateway.health.ok") : t("ui.instance.gateway.health.store-failing")];
  if (socket && socket !== "off") parts.push(t("ui.instance.gateway.health.socket", { socket }));
  parts.push(running === 1 ? t("ui.instance.gateway.health.ingress-one", { count: running }) : t("ui.instance.gateway.health.ingress-other", { count: running }));
  return { words: parts.join(" · "), dot: health.ok ? "done" : "blocked" };
}

function GatewayCard({ live, loading, error, doc }: { live: boolean; loading: boolean; error: Error | null; doc: GatewayDocument | null }) {
  const words = doc ? gatewayWords(doc) : null;
  return (
    <Card data-card="gateway">
      <Kicker>{t("ui.instance.gateway.kicker")}</Kicker>
      {!live ? (
        <p className="text-xs text-muted-foreground">{t("ui.instance.unanswered")}</p>
      ) : loading ? (
        <p className="text-xs text-muted-foreground">{t("ui.instance.reading")}</p>
      ) : error ? (
        <Report tone="fail" role="alert">
          {error.message}
        </Report>
      ) : doc && words ? (
        <div className="space-y-2">
          {doc.state === "refused" ? (
            <Notice tone="blocked" role="alert">
              <p>
                <strong>{t("ui.instance.gateway.refused.strong")}</strong>
                {t("ui.instance.gateway.refused.a")}
                <code className="ref-chip">{doc.instance}</code>
                {doc.refusedBy ? (
                  <>
                    {t("ui.instance.gateway.refused.peer")}
                    <span className="font-mono">{doc.refusedBy.slice(0, 8)}</span>)
                  </>
                ) : null}
                {t("ui.instance.gateway.refused.b")}
                <code className="ref-chip">instance.name</code>.
              </p>
            </Notice>
          ) : null}
          {doc.state === "unreachable" ? (
            <Notice tone="blocked" role="alert">
              <p>
                <strong>{t("ui.instance.gateway.unreachable.strong")}</strong>
                {doc.url ? (
                  <>
                    {t("ui.instance.gateway.unreachable.at")}
                    <span className="font-mono">{doc.url}</span>
                  </>
                ) : null}
                {t("ui.instance.gateway.unreachable.body")}
              </p>
            </Notice>
          ) : null}
          <div className="space-y-1.5">
            {doc.configured ? <KV k={t("ui.instance.gateway.url")} v={doc.url ?? ""} /> : null}
            <KV k={t("ui.instance.gateway.connection")}>
              <span className="inline-flex items-center gap-1.5">
                <StatusDot status={words.dot} />
                {words.words}
              </span>
            </KV>
            {doc.configured ? <KV k={t("ui.instance.gateway.polling-as")} v={doc.instance ?? ""} /> : null}
            {doc.configured && doc.state === "connected" ? (
              <KV k={t("ui.instance.gateway.since")}>
                {doc.since ? relativeTime(doc.since) : "—"}
                {t("ui.instance.gateway.since.committed")}
                <span className="font-mono">{t("ui.instance.gateway.since.seq", { seq: doc.committed ?? 0 })}</span>
                {t("ui.instance.gateway.since.every", { seconds: doc.mode?.pollIntervalSeconds ?? 5 })}
                {(doc.mode?.longPollSeconds ?? 0) > 0 ? t("ui.instance.gateway.since.long-poll", { seconds: doc.mode?.longPollSeconds ?? 0 }) : ""}
              </KV>
            ) : null}
            {doc.configured ? (
              <KV k={t("ui.instance.gateway.health")}>
                <span className="inline-flex items-center gap-1.5">
                  <StatusDot status={gatewayHealthWords(doc).dot} />
                  {gatewayHealthWords(doc).words}
                </span>
              </KV>
            ) : null}
          </div>
          {!doc.configured ? (
            <p className="text-xs leading-relaxed text-muted-foreground">
              {t("ui.instance.gateway.none")}
            </p>
          ) : doc.state === "connected" ? (
            (doc.claims ?? []).length === 0 ? (
              <p className="text-xs text-muted-foreground">{t("ui.instance.gateway.queue-empty")}</p>
            ) : (
              <>
                <table className="w-full text-xs" aria-label={t("ui.instance.gateway.queue.label")}>
                  <thead className="text-muted-foreground">
                    <tr>
                      <th className="py-1 text-left font-normal">{t("ui.instance.gateway.queue.subject")}</th>
                      <th className="py-1 text-left font-normal">{t("ui.instance.gateway.queue.role")}</th>
                      <th className="py-1 text-right font-normal">{t("ui.instance.gateway.queue.backlog")}</th>
                      <th className="py-1 text-right font-normal">{t("ui.instance.gateway.queue.oldest")}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {(doc.claims ?? []).map((claim, index) => (
                      <tr key={`${claim.subject}:${claim.role}`}>
                        <td className="py-1">
                          <code className="ref-chip">{claim.subject}</code>
                        </td>
                        <td className="py-1">{claim.role}</td>
                        <td className="py-1 text-right font-mono">{index === 0 ? (doc.queue?.backlog ?? 0) : "—"}</td>
                        <td className="py-1 text-right font-mono">
                          {index === 0 && doc.queue?.oldestPendingAt ? relativeTime(doc.queue.oldestPendingAt) : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="text-xs leading-relaxed text-muted-foreground">
                  {t("ui.instance.gateway.queue.note")}
                </p>
              </>
            )
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}
