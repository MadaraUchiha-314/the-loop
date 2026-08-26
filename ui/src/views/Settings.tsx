/**
 * Where this browser points.
 *
 * The dashboard is a static bundle — one hosted copy, any number of
 * workstations — so the base URL is a per-viewer setting rather than a build
 * constant. Saving runs a real `GET /api/v1/health` against it, because the
 * failure that matters here is not "wrong URL" but "the browser is not allowed
 * to talk to it": the service binds loopback and sends no CORS headers by
 * design, so a hosted page needs a tunnel plus a gateway in front. The note
 * below the field says so, and a failed check shows the same advice.
 */

import { useState } from "react";

import { ApiError, HttpApi, normalizeBaseUrl } from "../api/client.ts";
import type { RestartSchedule } from "../api/types.ts";
import { useApi } from "../state/ApiContext.tsx";
import { Blueprint } from "../components/Blueprint.tsx";
import { ConfigEditor } from "../components/ConfigEditor.tsx";
import { POLL_CHOICES, type DataMode, type RefreshMode } from "../state/settings.ts";
import { useAsync } from "../state/useAsync.ts";

type Probe = { state: "idle" } | { state: "checking" } | { state: "ok"; version: string } | { state: "fail"; advice: string };

export function Settings() {
  const { settings, updateSettings } = useApi();
  const [draft, setDraft] = useState(settings.baseUrl);
  const [probe, setProbe] = useState<Probe>({ state: "idle" });

  async function saveAndTest(): Promise<void> {
    const baseUrl = normalizeBaseUrl(draft) || settings.baseUrl;
    setDraft(baseUrl);
    updateSettings({ baseUrl, mode: "live" });
    setProbe({ state: "checking" });
    try {
      const health = await new HttpApi(baseUrl).health();
      setProbe({ state: "ok", version: health.version });
    } catch (cause) {
      setProbe({ state: "fail", advice: cause instanceof ApiError ? cause.advice : String(cause) });
    }
  }

  return (
    <>
      <h1 className="lp-h1">Settings</h1>
      <p className="lp-page-sub">Where this browser points, and the daemon&rsquo;s own configuration.</p>

      <Blueprint className="lp-settings-card">
        <div className="lp-settings-kicker">API server</div>
        <label className="lp-settings-label" htmlFor="lp-baseurl">
          Base URL — the workstation running <code className="lp-code">the-loop start</code>
        </label>
        <div className="lp-settings-row">
          <input
            id="lp-baseurl"
            className="input"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") void saveAndTest();
            }}
            placeholder="http://127.0.0.1:8787"
            spellCheck={false}
            autoComplete="off"
          />
          <button type="button" className="btn btn-primary" onClick={() => void saveAndTest()}>
            Save &amp; test
          </button>
        </div>

        <div className="lp-conn">
          <span className={`lp-conn-dot ${probeClass(probe)}`} aria-hidden="true" />
          <span>{probeText(probe, settings.baseUrl)}</span>
        </div>

        <details className="lp-learn">
          <summary>Learn more</summary>
          <div className="lp-note">
            This dashboard is a static page — hosted anywhere, pointed at any workstation. The service binds loopback
            by default and refuses a non-loopback bind unless <code>service.exposed: true</code>, and it carries no
            in-app auth. This page&rsquo;s origin is allowed to read it out of the box
            (<code>service.cors.allowOrigins</code>); a copy hosted anywhere else has to be added there. A service on
            another machine still needs to reach this browser — an SSH tunnel
            (<code>ssh -L 8787:127.0.0.1:8787 workstation</code>) or a gateway that terminates auth. The URL is saved
            in this browser (localStorage); the health check is GET {normalizeBaseUrl(draft)}/api/v1/health.
          </div>
        </details>
      </Blueprint>

      <Blueprint className="lp-settings-card">
        <div className="lp-settings-kicker">Data source</div>
        <div className="lp-settings-row">
          <ModeButton current={settings.mode} value="live" onPick={updateSettings}>
            Live service
          </ModeButton>
          <ModeButton current={settings.mode} value="demo" onPick={updateSettings}>
            Demo fixture
          </ModeButton>
        </div>
        <details className="lp-learn">
          <summary>Learn more</summary>
          <div className="lp-note">
            The demo serves a bundled fixture in the same record shapes the service uses, so the screens can be
            evaluated without a reachable workstation. Control verbs in demo mode mutate an in-memory copy and never
            leave the browser.
          </div>
        </details>
      </Blueprint>

      <RefreshSection />

      <RestartSection />

      <CliConfigSection />
    </>
  );
}

const MODES: { value: RefreshMode; name: string; why: string }[] = [
  {
    value: "stream",
    name: "Streaming",
    why: "The service pushes changes as they happen. One connection, held open. Best on loopback or a stable tunnel.",
  },
  {
    value: "poll",
    name: "Polling",
    why: "Ask again on a timer. A failed cycle costs one request, so this is the kinder mode over a flaky link.",
  },
  {
    value: "manual",
    name: "Manual",
    why: "No background request of any kind. The screen changes only when you ask it to.",
  },
];

/**
 * How this browser keeps the screen current (issue-239, R3).
 *
 * A radio group rather than three buttons: the modes are mutually exclusive and
 * a screen reader should say "1 of 3", which `role="radiogroup"` gets for free
 * and a row of `aria-pressed` buttons does not. The interval select belongs to
 * exactly one mode, so it appears with that mode instead of sitting greyed out
 * beside the others.
 */
function RefreshSection() {
  const { settings, updateSettings } = useApi();
  return (
    <Blueprint className="lp-settings-card">
      <div className="lp-settings-kicker">Refresh</div>
      <fieldset className="lp-modes-fieldset">
        <legend className="lp-settings-label">How this browser keeps the screen current</legend>
        <div className="lp-modes" role="radiogroup" aria-label="Refresh mode">
          {MODES.map((mode) => (
            <label className="lp-mode" key={mode.value}>
              <input
                type="radio"
                name="lp-refresh-mode"
                value={mode.value}
                checked={settings.refreshMode === mode.value}
                onChange={() => updateSettings({ refreshMode: mode.value })}
              />
              <span>
                <span className="lp-mode-name">{mode.name}</span>
                <span className="lp-mode-why">{mode.why}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      {settings.refreshMode === "poll" ? (
        <div className="lp-mode-interval">
          <label className="lp-settings-label" htmlFor="lp-poll">
            Poll interval
          </label>
          <select
            id="lp-poll"
            className="input"
            value={settings.pollSeconds}
            onChange={(event) => updateSettings({ pollSeconds: Number(event.target.value) })}
          >
            {POLL_CHOICES.map((seconds) => (
              <option key={seconds} value={seconds}>
                every {seconds}s
              </option>
            ))}
          </select>
        </div>
      ) : null}

      <details className="lp-learn">
        <summary>Learn more</summary>
        <div className="lp-note">
          Each poll cycle is four list calls plus one <code>graph/check</code> per active loop, so a large board
          against a remote workstation is happier at 30s. Streaming costs one held-open connection instead, and
          refreshes only what each change touches — a graph move re-reads that one work item&rsquo;s position,
          anything else re-reads the lists. A stream that cannot be opened says so in the sidebar&rsquo;s health dot
          and falls back to polling.
        </div>
      </details>
    </Blueprint>
  );
}

/**
 * Restart the workstation's whole the-loop deployment (issue-228).
 *
 * `POST /api/v1/restart` **schedules**: the service spawns a detached
 * `the-loop restart` and answers immediately, then goes down and comes back —
 * so this card promises the schedule (pid, logfile), not the finished restart,
 * and the next polls are expected to fail briefly. Disabled in demo mode,
 * where there is nothing to restart.
 */
function RestartSection() {
  const { api } = useApi();
  const [withUpgrade, setWithUpgrade] = useState(false);
  const [state, setState] = useState<
    { kind: "idle" } | { kind: "asking" } | { kind: "scheduled"; schedule: RestartSchedule } | { kind: "failed"; message: string }
  >({ kind: "idle" });

  async function restart(): Promise<void> {
    setState({ kind: "asking" });
    try {
      const schedule = await api.restart(withUpgrade);
      setState({ kind: "scheduled", schedule });
    } catch (cause) {
      setState({ kind: "failed", message: cause instanceof ApiError ? cause.advice : String(cause) });
    }
  }

  return (
    <Blueprint className="lp-settings-card">
      <div className="lp-settings-kicker">Service</div>
      <div className="lp-settings-row">
        <button
          type="button"
          className="btn btn-secondary"
          disabled={state.kind === "asking"}
          onClick={() => void restart()}
        >
          {state.kind === "asking" ? "Scheduling…" : withUpgrade ? "Restart with upgrade" : "Restart the-loop"}
        </button>
        <label className="lp-settings-label lp-restart-upgrade">
          <input
            type="checkbox"
            checked={withUpgrade}
            onChange={(event) => setWithUpgrade(event.target.checked)}
          />{" "}
          upgrade the CLI first
        </label>
      </div>
      {state.kind === "scheduled" ? (
        <div className="lp-config-report ok">
          Restart scheduled (pid {state.schedule.pid}
          {state.schedule.withUpgrade ? ", with upgrade" : ""}) — the service will drop and come back;
          output at <code className="lp-code">{state.schedule.logfile}</code> on the workstation.
        </div>
      ) : null}
      {state.kind === "failed" ? <div className="lp-config-report fail">{state.message}</div> : null}
      <details className="lp-learn">
        <summary>Learn more</summary>
        <div className="lp-note">
          Stops every running the-loop service on the workstation, then starts every enabled one —
          the same thing <code className="lp-code">the-loop restart</code> does. With the upgrade, the
          CLI is upgraded in between; a failed upgrade still restarts the current version.
        </div>
      </details>
    </Blueprint>
  );
}

/**
 * The daemon's own config (issue-222).
 *
 * The two calls are loaded together and the editor is only mounted once both are in:
 * the form is *derived* from the schema, so half of the pair is not a screen worth
 * rendering. A failure says which of the two failed and offers a retry, because "the
 * service is old enough not to have the route" and "the service is unreachable" want
 * different things from the operator.
 */
function CliConfigSection() {
  const { api } = useApi();
  const [nonce, setNonce] = useState(0);
  const loaded = useAsync(
    async (signal) => ({
      document: await api.config(signal),
      schema: await api.configSchema(signal),
    }),
    [api, nonce],
  );

  if (loaded.loading) return <div className="lp-skeleton">Reading the CLI config…</div>;
  if (loaded.error || !loaded.data) {
    const advice = loaded.error instanceof ApiError ? loaded.error.advice : String(loaded.error);
    return (
      <Blueprint className="lp-settings-card">
        <div className="lp-settings-kicker">CLI config</div>
        <div className="lp-config-report fail">{advice}</div>
        <div className="lp-settings-row">
          <button type="button" className="btn btn-secondary" onClick={() => setNonce((value) => value + 1)}>
            Retry
          </button>
        </div>
      </Blueprint>
    );
  }

  return (
    <ConfigEditor
      document={loaded.data.document}
      schema={loaded.data.schema}
      onSave={(patch) => api.saveConfig(patch)}
      onRestart={() => api.restart()}
    />
  );
}

function ModeButton({
  current,
  value,
  onPick,
  children,
}: {
  current: DataMode;
  value: DataMode;
  onPick: (patch: { mode: DataMode }) => void;
  children: string;
}) {
  const active = current === value;
  return (
    <button
      type="button"
      className={active ? "btn btn-primary" : "btn btn-secondary"}
      aria-pressed={active}
      onClick={() => onPick({ mode: value })}
    >
      {children}
    </button>
  );
}

function probeClass(probe: Probe): string {
  if (probe.state === "ok") return "ok";
  if (probe.state === "fail") return "fail";
  return "";
}

function probeText(probe: Probe, baseUrl: string): string {
  switch (probe.state) {
    case "checking":
      return "checking /api/v1/health…";
    case "ok":
      return `connected — ${baseUrl} (the-loop ${probe.version})`;
    case "fail":
      return probe.advice;
    default:
      return `not tested — currently pointing at ${baseUrl}`;
  }
}
