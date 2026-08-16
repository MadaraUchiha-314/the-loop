/** The shell: chrome, banners, and one screen at a time. */

import { attentionEntries } from "./api/model.ts";
import { ConnectionBanner, DemoBanner } from "./components/Banner.tsx";
import { Nav } from "./components/Nav.tsx";
import { DEMO_TITLES } from "./demo/fixture.ts";
import { useApi } from "./state/ApiContext.tsx";
import { hrefFor, navigate, useRoute } from "./state/route.ts";
import { useControlPlane } from "./state/useControlPlane.ts";
import { Attention } from "./views/Attention.tsx";
import { Dashboard } from "./views/Dashboard.tsx";
import { Events } from "./views/Events.tsx";
import { Sessions } from "./views/Sessions.tsx";
import { Settings } from "./views/Settings.tsx";
import { WorkItemDetail } from "./views/WorkItemDetail.tsx";

export function App() {
  const { api, settings, updateSettings } = useApi();
  const route = useRoute();
  // One stream connection per tab (R3.5), owned here rather than by the detail
  // page: the page comes and goes with the route, and a connection that opened
  // and closed on every navigation would replay a cursor for nothing. The
  // viewed ref travels down instead, and the detail page reads `transcriptTick`.
  const watched = route.name === "detail" ? route.ref : "";
  const board = useControlPlane(
    api,
    { mode: settings.refreshMode, pollSeconds: settings.pollSeconds },
    watched,
  );

  // No /api/v1 route serves a ticket's title — the portable record keeps the ref
  // and the URL and deliberately not a copy of GitHub's mutable fields. The demo
  // fixture carries them so the board reads like a real one; against a live
  // service the column falls back to the ref and a link.
  const titleFor = (ref: string) => (api.isDemo ? DEMO_TITLES[ref] : undefined);

  const selected = route.name === "detail" ? board.views.find((view) => view.ref === route.ref) : undefined;

  return (
    <div className="lp-shell">
      <Nav
        route={route}
        attentionCount={attentionEntries(board.views).length}
        daemons={board.daemons}
        stream={board.stream}
      />

      {api.isDemo ? <DemoBanner onGoLive={() => updateSettings({ mode: "live" })} /> : null}
      {!api.isDemo && board.error ? <ConnectionBanner error={board.error} baseUrl={api.baseUrl} /> : null}

      <main className="lp-main">
        {route.name === "dashboard" ? (
          <Dashboard views={board.views} loading={board.loading} titleFor={titleFor} />
        ) : null}

        {route.name === "detail" ? (
          selected ? (
            <WorkItemDetail
              view={selected}
              title={titleFor(selected.ref)}
              onChanged={board.refresh}
              transcriptTick={board.transcriptTick}
            />
          ) : board.loading ? (
            <div className="lp-skeleton">Loading…</div>
          ) : (
            <div className="lp-skeleton">
              No work item <code className="lp-code">{route.ref}</code> on this service.{" "}
              <a href={hrefFor({ name: "dashboard" })}>Back to the board</a>.
            </div>
          )
        ) : null}

        {route.name === "sessions" ? (
          <Sessions
            views={board.views}
            loading={board.loading}
            titleFor={titleFor}
            selectedRef={route.ref}
            onChanged={board.refresh}
          />
        ) : null}

        {route.name === "attention" ? <Attention views={board.views} /> : null}
        {route.name === "events" ? <Events /> : null}
        {route.name === "settings" ? <Settings /> : null}

        {!api.isDemo && board.error && route.name !== "settings" ? (
          <p className="lp-subtle">
            Nothing could be loaded from <code className="lp-code">{api.baseUrl}</code>. You can also{" "}
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => {
                updateSettings({ mode: "demo" });
                navigate({ name: "dashboard" });
              }}
            >
              explore the demo fixture
            </button>{" "}
            instead.
          </p>
        ) : null}
      </main>

      <footer className="lp-footer">
        <span>GET /work-items · /sessions · /sessions/transcript · /attention · /events · /daemons</span>
        <span>POST /graph/check · /graph/complete · /sessions/control · /sessions/reply</span>
      </footer>
    </div>
  );
}
