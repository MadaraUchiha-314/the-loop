/** The shell: chrome, banners, and one of the three screens (issue-283). */

import { useMemo } from "react";

import { attentionByItem } from "./api/model.ts";
import { ConnectionBanner, DemoBanner } from "./components/Banner.tsx";
import { Nav } from "./components/Nav.tsx";
import { DEMO_TITLES } from "./demo/fixture.ts";
import { useApi } from "./state/ApiContext.tsx";
import { navigate, useRoute } from "./state/route.ts";
import { useControlPlane } from "./state/useControlPlane.ts";
import { Events } from "./views/Events.tsx";
import { Settings } from "./views/Settings.tsx";
import { Work } from "./views/Work.tsx";

export function App() {
  const { api, settings, updateSettings } = useApi();
  const route = useRoute();
  // One stream connection per tab (R3.5), owned here rather than by the detail
  // pane: the pane comes and goes with the route, and a connection that opened
  // and closed on every navigation would replay a cursor for nothing. The
  // viewed ref travels down instead, and the detail pane reads `transcriptTick`.
  const watched = route.name === "work" && route.ref ? route.ref : "";
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

  const needsYou = attentionByItem(board.views).length;

  return (
    <div className="lp-shell">
      <Nav
        route={route}
        needsYouCount={needsYou}
        daemons={board.daemons}
        stream={board.stream}
        onRefresh={board.refresh}
      />

      {api.isDemo ? <DemoBanner onGoLive={() => updateSettings({ mode: "live" })} /> : null}
      {!api.isDemo && board.error ? <ConnectionBanner error={board.error} baseUrl={api.baseUrl} /> : null}

      {route.name === "work" || route.name === "standing" ? (
        <main className="lp-main lp-main-work">
          <Work
            views={board.views}
            loading={board.loading}
            titleFor={titleFor}
            selectedRef={route.name === "work" ? (route.ref ?? "") : ""}
            standing={route.name === "standing"}
            onChanged={board.refresh}
            transcriptTick={board.transcriptTick}
          />
        </main>
      ) : (
        <main className="lp-main">
          {route.name === "events" ? <Events refFilter={route.ref ?? ""} /> : null}
          {route.name === "settings" ? <Settings /> : null}
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
