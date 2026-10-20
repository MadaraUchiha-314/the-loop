/**
 * One tab per session of the work item (issue-327): **Work item loop**, then
 * `PR #n` for each pull request with its own inner loop — the repository
 * named when the PR lives elsewhere, a pause glyph when its session is
 * paused. Links on the hash, like the sidebar's nested rows, so the two
 * selectors cannot disagree about what the trace shows (issue-300). Each
 * link's accessible name is the session's short ref.
 *
 * A bar with one tab is chrome for a choice that does not exist, so it
 * renders only when the item has more than one session, and it carries no
 * tally (issue-511 R2.4, R2.6).
 */

import type { WorkItemView } from "../api/model.ts";
import { itemHref } from "../state/route.ts";
import { GitPullRequestIcon, PauseIcon, SquareTerminalIcon } from "./Icons.tsx";

export function SessionTabs({ view, viewed }: { view: WorkItemView; viewed: string }) {
  const prs = view.pullRequests;
  if (prs.length === 0) return null;
  const tab =
    "-mb-px flex shrink-0 items-center gap-2 border-b-2 px-3 py-2.5 text-sm transition-colors";
  const on = "border-primary text-foreground";
  const off = "border-transparent text-muted-foreground hover:text-foreground";
  return (
    <div className="scroll-thin flex items-center gap-1 overflow-x-auto border-b border-border px-6" role="navigation" aria-label="Sessions">
      <a
        href={itemHref(view.ref, view.instance)}
        aria-label={view.shortRef}
        aria-current={viewed === view.ref ? "page" : undefined}
        className={`${tab} ${viewed === view.ref ? on : off}`}
      >
        <SquareTerminalIcon className="h-3.5 w-3.5" />
        <span>Work item loop</span>
        {view.sessionState === "paused" ? <PauseIcon className="h-3 w-3 text-state-blocked" /> : null}
      </a>
      {prs.map((pr) => (
        <a
          key={pr.ref}
          href={itemHref(pr.ref, view.instance)}
          aria-label={pr.shortRef}
          aria-current={viewed === pr.ref ? "page" : undefined}
          className={`${tab} ${viewed === pr.ref ? on : off}`}
        >
          <GitPullRequestIcon className="h-3.5 w-3.5" />
          <span>PR #{pr.number}</span>
          {pr.prRepo ? <span className="font-mono text-[0.68rem] text-muted-foreground">{pr.prRepo.split("/").at(-1)}</span> : null}
          {pr.sessionState === "paused" ? <PauseIcon className="h-3 w-3 text-state-blocked" /> : null}
        </a>
      ))}
    </div>
  );
}
