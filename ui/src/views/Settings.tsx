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
import { ConfigSection } from "../components/ConfigEditor.tsx";
import type { Chrome } from "../components/HeaderBar.tsx";
import { HeaderBar } from "../components/HeaderBar.tsx";
import { t } from "../i18n.ts";
import { Card, ControlButton, FieldLabel, INPUT_CLASS, Kicker, LearnMore, Report } from "../components/primitives.tsx";
import { StatusDot, type DotStatus } from "../components/StatusDot.tsx";
import { useApi } from "../state/ApiContext.tsx";
import { POLL_CHOICES, type DataMode, type RefreshMode } from "../state/settings.ts";

type Probe = { state: "idle" } | { state: "checking" } | { state: "ok"; version: string } | { state: "fail"; advice: string };

export function Settings({ chrome }: { chrome: Chrome }) {
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
      <HeaderBar chrome={chrome} title={t("ui.settings.title")} meta={<span>{t("ui.settings.meta")}</span>} />
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-6 py-6">
      <div className="mx-auto max-w-3xl space-y-4">

      <Card>
        <Kicker>{t("ui.settings.api.kicker")}</Kicker>
        <FieldLabel htmlFor="lp-baseurl">
          {t("ui.settings.api.base-url")}
          <code className="ref-chip">the-loop start</code>
        </FieldLabel>
        <div className="flex flex-wrap items-center gap-2">
          <input
            id="lp-baseurl"
            className={`${INPUT_CLASS} max-w-md font-mono`}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") void saveAndTest();
            }}
            placeholder="http://127.0.0.1:8787"
            spellCheck={false}
            autoComplete="off"
          />
          <ControlButton primary onClick={() => void saveAndTest()}>
            {t("ui.settings.api.save")}
          </ControlButton>
        </div>

        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <StatusDot status={probeClass(probe)} />
          <span className="font-mono text-[0.7rem]">{probeText(probe, settings.baseUrl)}</span>
        </div>

        <LearnMore>
          <p>
            {t("ui.settings.api.learn.a")}
            <code>service.exposed: true</code>
            {t("ui.settings.api.learn.b")}
            <code>service.cors.allowOrigins</code>
            {t("ui.settings.api.learn.c")}
            <code>ssh -L 8787:127.0.0.1:8787 workstation</code>
            {t("ui.settings.api.learn.d", { url: normalizeBaseUrl(draft) })}
          </p>
        </LearnMore>
      </Card>

      <Card>
        <Kicker>{t("ui.settings.data.kicker")}</Kicker>
        <div className="flex flex-wrap gap-2">
          <ModeButton current={settings.mode} value="live" onPick={updateSettings}>
            {t("ui.settings.data.live")}
          </ModeButton>
          <ModeButton current={settings.mode} value="demo" onPick={updateSettings}>
            {t("ui.settings.data.demo")}
          </ModeButton>
        </div>
        <LearnMore>
          <p>
            {t("ui.settings.data.learn")}
          </p>
        </LearnMore>
      </Card>

      <RefreshSection />

      <RestartSection />

      <ConfigSection />
      </div>
      </div>
    </>
  );
}

const MODES: { value: RefreshMode; name: string; why: string }[] = [
  {
    value: "stream",
    name: t("ui.settings.refresh.stream.name"),
    why: t("ui.settings.refresh.stream.why"),
  },
  {
    value: "poll",
    name: t("ui.settings.refresh.poll.name"),
    why: t("ui.settings.refresh.poll.why"),
  },
  {
    value: "manual",
    name: t("ui.settings.refresh.manual.name"),
    why: t("ui.settings.refresh.manual.why"),
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
    <Card>
      <Kicker>{t("ui.settings.refresh.kicker")}</Kicker>
      <fieldset className="space-y-2">
        <legend className="text-xs text-muted-foreground">{t("ui.settings.refresh.legend")}</legend>
        <div className="grid gap-1.5 sm:grid-cols-3" role="radiogroup" aria-label={t("ui.settings.refresh.label")}>
          {MODES.map((mode) => (
            <label
              className={`flex cursor-pointer items-start gap-2 rounded-lg border px-3 py-2 transition-colors ${
                settings.refreshMode === mode.value ? "border-primary/50 bg-accent text-accent-foreground" : "border-border hover:bg-surface-2/60"
              }`}
              key={mode.value}
            >
              <input
                type="radio"
                name="lp-refresh-mode"
                value={mode.value}
                checked={settings.refreshMode === mode.value}
                onChange={() => updateSettings({ refreshMode: mode.value })}
                className="mt-1 accent-[var(--primary)]"
              />
              <span className="min-w-0">
                <span className="block text-sm">{mode.name}</span>
                <span className="block text-[0.7rem] leading-relaxed text-muted-foreground">{mode.why}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      {settings.refreshMode === "poll" ? (
        <div className="flex flex-wrap items-center gap-2">
          <FieldLabel htmlFor="lp-poll">{t("ui.settings.refresh.interval")}</FieldLabel>
          <select
            id="lp-poll"
            className={`${INPUT_CLASS} w-auto`}
            value={settings.pollSeconds}
            onChange={(event) => updateSettings({ pollSeconds: Number(event.target.value) })}
          >
            {POLL_CHOICES.map((seconds) => (
              <option key={seconds} value={seconds}>
                {t("ui.settings.refresh.every", { seconds })}
              </option>
            ))}
          </select>
        </div>
      ) : null}

      <LearnMore>
        <p>
          {t("ui.settings.refresh.learn.a")}
          <code className="ref-chip">graph/check</code>
          {t("ui.settings.refresh.learn.b")}
        </p>
      </LearnMore>
    </Card>
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
    <Card>
      <Kicker>{t("ui.settings.service.kicker")}</Kicker>
      <div className="flex flex-wrap items-center gap-3">
        <ControlButton disabled={state.kind === "asking"} onClick={() => void restart()}>
          {state.kind === "asking" ? t("ui.settings.service.scheduling") : withUpgrade ? t("ui.settings.service.restart-upgrade") : t("ui.settings.service.restart")}
        </ControlButton>
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <input
            type="checkbox"
            checked={withUpgrade}
            onChange={(event) => setWithUpgrade(event.target.checked)}
            className="accent-[var(--primary)]"
          />
          {t("ui.settings.service.upgrade-first")}
        </label>
      </div>
      {state.kind === "scheduled" ? (
        <Report tone="ok" role="status">
          {t("ui.settings.service.scheduled", { pid: state.schedule.pid })}
          {state.schedule.withUpgrade ? t("ui.settings.service.scheduled.with-upgrade") : ""}
          {t("ui.settings.service.scheduled.output")}
          <code className="ref-chip">{state.schedule.logfile}</code>
          {t("ui.settings.service.scheduled.end")}
        </Report>
      ) : null}
      {state.kind === "failed" ? <Report tone="fail" role="alert">{state.message}</Report> : null}
      <LearnMore>
        <p>
          {t("ui.settings.service.learn.a")}
          <code className="ref-chip">the-loop restart</code>
          {t("ui.settings.service.learn.b")}
        </p>
      </LearnMore>
    </Card>
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
      aria-pressed={active}
      onClick={() => onPick({ mode: value })}
      className={`rounded-md border px-2 py-1.5 font-mono text-[0.7rem] transition-colors ${
        active
          ? "border-primary/50 bg-accent text-accent-foreground"
          : "border-border text-muted-foreground hover:bg-surface-2 hover:text-foreground"
      }`}
    >
      {children}
    </button>
  );
}

function probeClass(probe: Probe): DotStatus {
  if (probe.state === "ok") return "done";
  if (probe.state === "fail") return "blocked";
  if (probe.state === "checking") return "active";
  return "pending";
}

function probeText(probe: Probe, baseUrl: string): string {
  switch (probe.state) {
    case "checking":
      return t("ui.settings.probe.checking");
    case "ok":
      return t("ui.settings.probe.ok", { url: baseUrl, version: probe.version });
    case "fail":
      return probe.advice;
    default:
      return t("ui.settings.probe.idle", { url: baseUrl });
  }
}
