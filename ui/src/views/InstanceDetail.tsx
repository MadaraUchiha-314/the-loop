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
  const reason = row && !live ? row.detail || `not live (${row.state})` : "";

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
    run(`${verb}:${daemon.daemon}`, () => api.controlDaemon(daemon.daemon, verb, name), `${verb} ${daemon.daemon} on ${name}.`, () =>
      daemons.reload(),
    );

  if (fleet.loading && !doc) {
    return (
      <>
        <HeaderBar chrome={chrome} title={<span className="font-mono">{name}</span>} />
        <div className="px-6 py-6">
          <Empty>Loading…</Empty>
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
            No instance <code className="ref-chip">{name}</code> in this service&rsquo;s fleet.{" "}
            <a href={hrefFor({ name: "instances" })} className="text-foreground underline-offset-2 hover:underline">
              Back to the instances
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
            <span title={row.probedAt || undefined}>probed {own ? "now" : row.probedAt ? relativeTime(row.probedAt) : "—"}</span>
            {own ? (
              <>
                <span aria-hidden="true">·</span>
                <span>this instance</span>
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
                Not live: <strong className="font-medium">{reason}</strong>. Every control below is disabled until the
                instance answers to its name.
              </div>
            </Notice>
          ) : null}
          {error ? (
            <Report tone="fail" role="alert">
              <strong className="font-medium">The service refused that.</strong> {error}
            </Report>
          ) : null}
          {note && !error ? (
            <Report tone="ok" role="status">
              {note}
            </Report>
          ) : null}

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <Kicker>Identity</Kicker>
              <div className="space-y-1.5">
                <KV k="name" v={row.name} />
                <KV k="url" v={row.url} title={row.url} />
                <KV k="version" v={live ? row.version || "—" : "—"} />
                <KV k="mode" v={live ? identity.data?.scope?.mode || row.mode || "—" : "—"} />
                <KV k="managed" mono={false}>
                  {!live ? (
                    "—"
                  ) : identity.loading && !identity.data ? (
                    <span className="text-muted-foreground">reading…</span>
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
                <KV k="sessions" v={live ? String(identity.data?.sessionCount ?? row.sessionCount) : "—"} />
              </div>
            </Card>

            <Card data-card="daemons">
              <Kicker>Daemons</Kicker>
              {!live ? (
                <p className="text-xs text-muted-foreground">Unknown — the instance has not answered.</p>
              ) : daemons.loading && !daemons.data ? (
                <p className="text-xs text-muted-foreground">Reading…</p>
              ) : (daemons.data ?? []).length === 0 ? (
                <p className="text-xs text-muted-foreground">No daemon reported.</p>
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
                              ? `running · last cycle ${relativeTime(daemon.lastCycleAt)}`
                              : "running"
                            : offForGateway
                              ? "off · gateway configured"
                              : "stopped"}
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
                          `Restart of ${name} scheduled — it will drop and come back.`,
                          () => setConfirmRestart(false),
                        )
                      }
                    >
                      {busy === "restart" ? "Scheduling…" : `Restart ${name} now`}
                    </ControlButton>
                    <ControlButton onClick={() => setConfirmRestart(false)}>Cancel</ControlButton>
                  </>
                ) : (
                  <ControlButton disabled={!live || busy !== ""} title={reason || undefined} onClick={() => setConfirmRestart(true)}>
                    Restart instance…
                  </ControlButton>
                )}
              </div>
            </Card>
          </div>

          {live ? (
            <ConfigSection instance={name} />
          ) : (
            <Card>
              <Kicker>Configuration</Kicker>
              <p className="text-xs leading-relaxed text-muted-foreground">
                The schema-driven editor mounts here, reading and writing with{" "}
                <code className="ref-chip">instance={name}</code>. Disabled: {reason}.
              </p>
            </Card>
          )}

          <Card>
            <Kicker>Health</Kicker>
            {!live ? (
              <p className="text-xs text-muted-foreground">Unknown — the instance has not answered.</p>
            ) : health.loading && !health.data ? (
              <p className="text-xs text-muted-foreground">Reading…</p>
            ) : health.error ? (
              <Report tone="fail" role="alert">
                {health.error.message}
              </Report>
            ) : health.data ? (
              <div className="space-y-1.5">
                <KV k="status">
                  <span className="inline-flex items-center gap-1.5">
                    <StatusDot status={health.data.status === "ok" ? "done" : "blocked"} />
                    {health.data.status}
                  </span>
                </KV>
                <KV k="version" v={health.data.version} />
                {typeof health.data.role === "string" ? <KV k="role" v={health.data.role} /> : null}
              </div>
            ) : null}
          </Card>

          <GatewayCard live={live} loading={gateway.loading && !gateway.data} error={gateway.error} doc={gateway.data ?? null} />

          {manager && !own ? (
            <Card>
              <Kicker>Danger</Kicker>
              <div className="flex flex-wrap items-center gap-2">
                {confirmUnregister ? (
                  <>
                    <ControlButton
                      disabled={busy !== ""}
                      onClick={() =>
                        void run(`unregister`, () => api.unregisterInstance(name), `Unregistered ${name}.`, () => {
                          onChanged?.();
                          navigate({ name: "instances" });
                        })
                      }
                      className="border-state-blocked/40 text-state-blocked hover:bg-surface-2 hover:text-state-blocked"
                    >
                      {busy === "unregister" ? "Unregistering…" : `Unregister ${name} for good`}
                    </ControlButton>
                    <ControlButton onClick={() => setConfirmUnregister(false)}>Keep it</ControlButton>
                  </>
                ) : (
                  <ControlButton disabled={busy !== ""} onClick={() => setConfirmUnregister(true)} className="text-state-blocked">
                    Unregister {name}…
                  </ControlButton>
                )}
              </div>
              <p className="text-[0.7rem] text-muted-foreground">Removes it from the registry only; nothing on the box changes.</p>
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
  if (!doc.configured) return { words: "not configured", dot: "skipped" };
  switch (doc.state) {
    case "connected":
      return { words: `connected · ${(doc.mode?.longPollSeconds ?? 0) > 0 ? "long-poll" : "polling"}`, dot: "active" };
    case "connecting":
      return { words: `connecting · attempt ${doc.attempt ?? 1}`, dot: "pending" };
    case "refused":
      return { words: "refused · duplicate instance (409)", dot: "blocked" };
    case "unreachable":
      return { words: "unreachable · retrying", dot: "blocked" };
    default:
      return { words: doc.state, dot: "pending" };
  }
}

function gatewayHealthWords(doc: GatewayDocument): { words: string; dot: DotStatus } {
  const health = doc.health;
  if (!health) return { words: doc.state === "connected" ? "reading…" : "unknown", dot: "pending" };
  const socket = health.slack?.socket;
  const running = Object.entries(health.ingresses ?? {}).filter(([, state]) => state === "running").length;
  const parts = [health.ok ? "ok" : "store failing"];
  if (socket && socket !== "off") parts.push(`slack socket ${socket}`);
  parts.push(`${running} ingress${running === 1 ? "" : "es"} running`);
  return { words: parts.join(" · "), dot: health.ok ? "done" : "blocked" };
}

function GatewayCard({ live, loading, error, doc }: { live: boolean; loading: boolean; error: Error | null; doc: GatewayDocument | null }) {
  const words = doc ? gatewayWords(doc) : null;
  return (
    <Card data-card="gateway">
      <Kicker>Gateway</Kicker>
      {!live ? (
        <p className="text-xs text-muted-foreground">Unknown — the instance has not answered.</p>
      ) : loading ? (
        <p className="text-xs text-muted-foreground">Reading…</p>
      ) : error ? (
        <Report tone="fail" role="alert">
          {error.message}
        </Report>
      ) : doc && words ? (
        <div className="space-y-2">
          {doc.state === "refused" ? (
            <Notice tone="blocked" role="alert">
              <p>
                <strong>Refused by the gateway:</strong> another process is already polling as{" "}
                <code className="ref-chip">{doc.instance}</code>
                {doc.refusedBy ? (
                  <>
                    {" "}
                    (peer <span className="font-mono">{doc.refusedBy.slice(0, 8)}</span>)
                  </>
                ) : null}
                ; two instances cannot share one name. This one keeps retrying and starts no ingress of its own — stop the other, or
                give this instance its own <code className="ref-chip">instance.name</code>.
              </p>
            </Notice>
          ) : null}
          {doc.state === "unreachable" ? (
            <Notice tone="blocked" role="alert">
              <p>
                <strong>Gateway unreachable</strong>
                {doc.url ? (
                  <>
                    {" "}
                    at <span className="font-mono">{doc.url}</span>
                  </>
                ) : null}
                : retrying with back-off, not falling back to a local receiver, poller or listener. Events wait on the gateway's queue
                for this instance and arrive in order once it answers.
              </p>
            </Notice>
          ) : null}
          <div className="space-y-1.5">
            {doc.configured ? <KV k="url" v={doc.url ?? ""} /> : null}
            <KV k="connection">
              <span className="inline-flex items-center gap-1.5">
                <StatusDot status={words.dot} />
                {words.words}
              </span>
            </KV>
            {doc.configured ? <KV k="polling as" v={doc.instance ?? ""} /> : null}
            {doc.configured && doc.state === "connected" ? (
              <KV k="since">
                {doc.since ? relativeTime(doc.since) : "—"} · committed <span className="font-mono">seq {doc.committed ?? 0}</span> · every{" "}
                {doc.mode?.pollIntervalSeconds ?? 5} s{(doc.mode?.longPollSeconds ?? 0) > 0 ? `, long-poll ${doc.mode?.longPollSeconds} s` : ""}
              </KV>
            ) : null}
            {doc.configured ? (
              <KV k="gateway health">
                <span className="inline-flex items-center gap-1.5">
                  <StatusDot status={gatewayHealthWords(doc).dot} />
                  {gatewayHealthWords(doc).words}
                </span>
              </KV>
            ) : null}
          </div>
          {!doc.configured ? (
            <p className="text-xs leading-relaxed text-muted-foreground">
              No gateway configured. This instance runs its own webhook receiver, poller and Slack listener.
            </p>
          ) : doc.state === "connected" ? (
            (doc.claims ?? []).length === 0 ? (
              <p className="text-xs text-muted-foreground">Queue empty — nothing has been routed to this instance since it started polling.</p>
            ) : (
              <>
                <table className="w-full text-xs" aria-label="This instance's queue, by subject">
                  <thead className="text-muted-foreground">
                    <tr>
                      <th className="py-1 text-left font-normal">subject</th>
                      <th className="py-1 text-left font-normal">role</th>
                      <th className="py-1 text-right font-normal">backlog</th>
                      <th className="py-1 text-right font-normal">oldest uncommitted</th>
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
                  Backlog is what the gateway has routed to this instance's queue and this instance has not yet committed; the
                  queue is one per instance, so it is shown against the first subject.
                </p>
              </>
            )
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}
