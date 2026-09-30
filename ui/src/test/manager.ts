/**
 * A transport that answers as a **manager** (issue-374), for the view tests.
 *
 * The demo fixture is a worker by design (R5.6): one instance, nothing to
 * register. The fleet screens have a second shape to render — a manager's
 * document, with rows in every state and a registry to write — and this is
 * the smallest transport that serves it: the demo's board and verbs, with
 * `instances` / `instance` / `health` / `daemons` answering for a fleet and
 * the two registry writers behaving as the service does (validate, then
 * write, then answer the new document).
 */

import type { DaemonStatus, Health, InstanceDocument, InstanceRow, InstancesDocument } from "../api/types.ts";
import { ApiError } from "../api/client.ts";
import { DemoApi } from "../demo/client.ts";

export const HQ: InstanceRow = {
  name: "hq",
  url: "http://127.0.0.1:4114",
  state: "live",
  version: "19.14.1",
  mode: "addressed",
  managedCount: 3,
  sessionCount: 1,
  probedAt: new Date().toISOString(),
};

export const LAPTOP: InstanceRow = {
  name: "laptop-a",
  url: "http://10.0.0.5:4114",
  state: "live",
  version: "19.14.1",
  mode: "addressed",
  managedCount: 4,
  sessionCount: 2,
  probedAt: new Date(Date.now() - 12_000).toISOString(),
};

export const CLOUD: InstanceRow = {
  name: "cloud-1",
  url: "http://10.0.0.9:4114",
  state: "unreachable",
  version: "",
  mode: "",
  managedCount: 0,
  sessionCount: 0,
  probedAt: new Date(Date.now() - 12_000).toISOString(),
  detail: "connection refused",
};

export function managerDocument(rows: InstanceRow[] = [HQ, LAPTOP, CLOUD]): InstancesDocument {
  return { role: "manager", name: "hq", instances: rows };
}

function daemonRow(instance: string, name: string, running: boolean): DaemonStatus {
  return { daemon: name, running, pid: running ? 100 : 0, pidfile: "", logfile: "", startedAt: "", lastCycleAt: "", instance };
}

export class ManagerApi extends DemoApi {
  document: InstancesDocument;
  /** Every registry write, in order, so a test can assert what was sent. */
  readonly writes: { verb: "register" | "unregister"; name: string; url?: string }[] = [];
  /** Every keyed call that named an instance — `[method, instance]`. */
  readonly targeted: [string, string][] = [];

  constructor(document: InstancesDocument = managerDocument()) {
    super();
    this.document = document;
  }

  override instances(): Promise<InstancesDocument> {
    return Promise.resolve(structuredClone(this.document));
  }

  override registerInstance(name: string, url: string): Promise<InstancesDocument> {
    this.writes.push({ verb: "register", name, url });
    if (this.document.instances.some((row) => row.name === name)) {
      return Promise.reject(
        new ApiError("http", `instance.manager.instances[2]: name ${JSON.stringify(name)} is already registered`, "http://hq/api/v1/instances/register", 400),
      );
    }
    this.document = {
      ...this.document,
      instances: [
        ...this.document.instances,
        { name, url, state: "unreachable", version: "", mode: "", managedCount: 0, sessionCount: 0, probedAt: new Date().toISOString(), detail: "not probed yet" },
      ],
    };
    return this.instances();
  }

  override unregisterInstance(name: string): Promise<InstancesDocument> {
    this.writes.push({ verb: "unregister", name });
    if (!this.document.instances.some((row) => row.name === name && row.name !== this.document.name)) {
      return Promise.reject(new ApiError("http", `no instance ${JSON.stringify(name)} is registered`, "http://hq/api/v1/instances/unregister", 404));
    }
    this.document = { ...this.document, instances: this.document.instances.filter((row) => row.name !== name) };
    return this.instances();
  }

  override instance(_signal?: AbortSignal, instance = ""): Promise<InstanceDocument> {
    if (instance) this.targeted.push(["instance", instance]);
    const row = this.document.instances.find((candidate) => candidate.name === (instance || this.document.name));
    if (!row) return Promise.reject(new ApiError("http", `unknown instance ${JSON.stringify(instance)}`, "http://hq/api/v1/instance", 404));
    if (row.state !== "live") return Promise.reject(new ApiError("http", `${row.name}: ${row.detail ?? row.state}`, "http://hq/api/v1/instance", 502));
    return Promise.resolve({
      name: row.name,
      role: row.name === this.document.name ? "manager" : "worker",
      scope: { mode: row.mode, workItems: [] },
      managed: Array.from({ length: row.managedCount }, (_, index) => ({ ref: `github:octo/repo#${index + 1}`, sources: ["declared"] })),
      sessionCount: row.sessionCount,
    });
  }

  override health(_signal?: AbortSignal, instance = ""): Promise<Health> {
    if (instance) this.targeted.push(["health", instance]);
    return Promise.resolve({ status: "ok", version: "19.14.1", role: instance && instance !== this.document.name ? "worker" : "manager" });
  }

  override daemons(): Promise<DaemonStatus[]> {
    return Promise.resolve([daemonRow("hq", "poller", true), daemonRow("laptop-a", "poller", true), daemonRow("laptop-a", "gh-webhook", false)]);
  }

  override controlDaemon(daemon: string, verb: "start" | "stop" | "restart" | "status", instance = "") {
    this.targeted.push(["controlDaemon", instance]);
    return Promise.resolve({ messages: [{ stream: "out", text: `${verb} ${daemon}` }], exitCode: 0 });
  }

  override restart(withUpgrade = false, instance = "") {
    this.targeted.push(["restart", instance]);
    return Promise.resolve({ scheduled: true, pid: 1, withUpgrade, logfile: "restart.out" });
  }

  override config(_signal?: AbortSignal, instance = "") {
    this.targeted.push(["config", instance]);
    return super.config();
  }

  override configSchema(_signal?: AbortSignal, instance = "") {
    this.targeted.push(["configSchema", instance]);
    return super.configSchema();
  }

  override saveConfig(patch: Record<string, unknown>, instance = "") {
    this.targeted.push(["saveConfig", instance]);
    return super.saveConfig(patch);
  }
}
