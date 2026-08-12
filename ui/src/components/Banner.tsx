/** The two full-width notices: demo data, and a service that cannot be reached. */

import { ApiError } from "../api/client.ts";
import { hrefFor } from "../state/route.ts";

export function DemoBanner({ onGoLive }: { onGoLive: () => void }) {
  return (
    <div className="lp-banner lp-banner-demo" role="status">
      <span className="lp-banner-kicker">Demo data</span>
      <span>
        These work items are a bundled fixture, not a live service — nothing here is real and no control verb leaves the
        browser.
      </span>
      <span className="lp-banner-spacer" />
      <button type="button" className="btn btn-secondary" onClick={onGoLive}>
        Connect to a service
      </button>
    </div>
  );
}

export function ConnectionBanner({ error, baseUrl }: { error: Error; baseUrl: string }) {
  const advice = error instanceof ApiError ? error.advice : error.message;
  return (
    <div className="lp-banner lp-banner-error" role="alert">
      <span className="lp-banner-kicker">Not connected</span>
      <span>
        <code className="lp-code">{baseUrl}</code> — {advice}
      </span>
      <span className="lp-banner-spacer" />
      <a className="btn btn-secondary" href={hrefFor({ name: "settings" })}>
        Settings
      </a>
    </div>
  );
}
