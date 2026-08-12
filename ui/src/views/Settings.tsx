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
import { useApi } from "../state/ApiContext.tsx";
import { Blueprint } from "../components/Blueprint.tsx";
import { POLL_CHOICES, type DataMode } from "../state/settings.ts";

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
      <div className="lp-subtle lp-page-note">
        this dashboard is a static page — it can be hosted anywhere (GitHub Pages, S3) and pointed at any workstation
        running <code className="lp-code">the-loop service start</code>
      </div>

      <Blueprint className="lp-settings-card">
        <div className="lp-settings-kicker">API server</div>
        <label className="lp-settings-label" htmlFor="lp-baseurl">
          Base URL
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

        <div className="lp-note">
          The service binds loopback by default and refuses a non-loopback bind unless{" "}
          <code>service.exposed: true</code>. It carries no in-app auth and sends no CORS headers — for a
          statically-hosted dashboard, put a gateway in front (or an SSH tunnel:{" "}
          <code>ssh -L 8787:127.0.0.1:8787 workstation</code>) that terminates auth and adds{" "}
          <code>Access-Control-Allow-Origin</code> for this page&rsquo;s origin.
        </div>
        <div className="lp-hint">
          saved in this browser (localStorage) · health check: GET {normalizeBaseUrl(draft)}/api/v1/health
        </div>
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
        <div className="lp-note">
          The demo serves a bundled fixture in the same record shapes the service uses, so the screens can be evaluated
          without a reachable workstation. Control verbs in demo mode mutate an in-memory copy and never leave the
          browser.
        </div>
      </Blueprint>

      <Blueprint className="lp-settings-card">
        <div className="lp-settings-kicker">Refresh</div>
        <label className="lp-settings-label" htmlFor="lp-poll">
          Background poll interval
        </label>
        <select
          id="lp-poll"
          className="input"
          value={settings.pollSeconds}
          onChange={(event) => updateSettings({ pollSeconds: Number(event.target.value) })}
        >
          {POLL_CHOICES.map((seconds) => (
            <option key={seconds} value={seconds}>
              {seconds === 0 ? "off — refresh manually" : `every ${seconds}s`}
            </option>
          ))}
        </select>
        <div className="lp-note">
          Each cycle is four list calls plus one <code>graph/check</code> per loop, so a large board against a remote
          workstation is happier at 30s or off.
        </div>
      </Blueprint>

      <div className="lp-more">
        More to come: event-log retention view, default reply actor, per-workstation profiles.
      </div>
    </>
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
