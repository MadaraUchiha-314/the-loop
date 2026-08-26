/**
 * The shell: banners and the two surfaces the issue-298 design keeps — the
 * Work screen (sidebar + canvas, owning the whole viewport) and Settings, a
 * reading column behind "← Work items". The owner's direction on PR #299 is
 * exactly that surface area: the standalone Events screen is retired (the
 * event trail still appears as the trace's fallback), and every other hash —
 * `#/events` and the legacy pre-283 routes included — lands on Work.
 */

import { useMemo } from "react";

import { ConnectionBanner, DemoBanner } from "./components/Banner.tsx";
import { DEMO_TITLES } from "./demo/fixture.ts";
import { useApi } from "./state/ApiContext.tsx";
import { hrefFor, navigate, useRoute } from "./state/route.ts";
import { useControlPlane } from "./state/useControlPlane.ts";
import { Settings } from "./views/Settings.tsx";
import { Work } from "./views/Work.tsx";

export function App() {
  const { api, settings, updateSettings } = useApi();
  const route = useRoute();
  // One stream connection per tab (R3.5), owned here rather than by the detail
  // pane: the pane comes and goes with the route, and a connection that opened
  // and closed on every navigation would replay a cursor for nothing. The
  // viewed ref travels down instead, and the detail pane reads `transcriptTick`.
  // A legacy `#/events/<ref>` permalink names a work item, so it lands on
  // that item's canvas rather than a generic board.
  const selectedRef =
    (route.name === "work" || route.name === "events") && route.ref ? route.ref : "";
  const watched = selectedRef;
  const board = useControlPlane(
    api,
    { mode: settings.refreshMode, pollSeconds: settings.pollSeconds },
    watched,
  );

  // The poller caches each ticket's title in the portable record (issue-283
  // B1), so a live service serves it; the demo fixture's titles fill the same
  // role for the bundled data.
  const titles = useMemo(() => {
    const map = new Map<string, string>();
    for (const view of board.views) {
      const title = view.record.poll?.title;
      if (title) map.set(view.ref, title);
    }
    return map;
  }, [board.views]);
  const titleFor = (ref: string) => titles.get(ref) ?? (api.isDemo ? DEMO_TITLES[ref] : undefined);

  return (
    <div className="lp-shell">
      {api.isDemo ? <DemoBanner onGoLive={() => updateSettings({ mode: "live" })} /> : null}
      {!api.isDemo && board.error ? <ConnectionBanner error={board.error} baseUrl={api.baseUrl} /> : null}

      {route.name === "settings" ? (
        <main className="lp-main">
          <div className="lp-page">
            <a className="lp-back" href={hrefFor({ name: "work" })}>
              ← Work items
            </a>
            <Settings />
          </div>
        </main>
      ) : (
        <main className="lp-main lp-main-work">
          <Work
            views={board.views}
            loading={board.loading}
            titleFor={titleFor}
            selectedRef={selectedRef}
            standing={route.name === "standing"}
            onChanged={board.refresh}
            transcriptTick={board.transcriptTick}
            daemons={board.daemons}
            stream={board.stream}
          />
        </main>
      )}

      {!api.isDemo && board.error && route.name !== "settings" ? (
        <p className="lp-subtle lp-offer-demo">
          Nothing could be loaded from <code className="lp-code">{api.baseUrl}</code>. You can also{" "}
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => {
              updateSettings({ mode: "demo" });
              navigate({ name: "work" });
            }}
          >
            explore the demo fixture
          </button>{" "}
          instead.
        </p>
      ) : null}
    </div>
  );
}
