/**
 * The main column's header (issue-327): the title in the display face, a meta
 * line beneath, and the controls at the right — on Work the session verbs,
 * copy, open on GitHub, the theme toggle and the Session details disclosure
 * (issue-511); the button that reopens a collapsed sidebar. The same bar heads
 * the Standing and Settings panes, which is what keeps the shell's controls in
 * one place whatever the main column shows. It wraps, so at a phone's width
 * the title keeps its line and the actions drop beneath it.
 */

import type { ReactNode } from "react";

import type { Theme } from "../state/settings.ts";
import { MoonIcon, PanelLeftOpenIcon, PanelRightOpenIcon, SunIcon } from "./Icons.tsx";
import { IconButton } from "./primitives.tsx";

/** The shell's chrome state and the verbs on it, handed down from `App`. */
export interface Chrome {
  theme: Theme;
  onToggleTheme: () => void;
  sidebarOpen: boolean;
  onOpenSidebar: () => void;
  /** Absent when the pane has no session panel (Standing, Settings). */
  asideOpen?: boolean | undefined;
  onOpenAside?: (() => void) | undefined;
}

export function HeaderBar({
  title,
  meta,
  actions,
  trailing,
  chrome,
}: {
  title: ReactNode;
  meta?: ReactNode;
  /** Controls before the theme toggle (the session verbs, copy, GitHub…). */
  actions?: ReactNode;
  /** A control after the theme toggle (Work's Session details disclosure). */
  trailing?: ReactNode;
  chrome: Chrome;
}) {
  return (
    <header className="flex flex-wrap items-start gap-4 border-b border-border px-6 py-4">
      {chrome.sidebarOpen ? null : (
        <IconButton label="Open sidebar" onClick={chrome.onOpenSidebar}>
          <PanelLeftOpenIcon className="h-4 w-4" />
        </IconButton>
      )}
      <div className="min-w-0 flex-[1_1_16rem]">
        <h1 className="break-words font-display text-lg font-semibold tracking-tight">{title}</h1>
        {meta ? <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">{meta}</div> : null}
      </div>
      <div className="ml-auto flex flex-wrap items-center gap-1">
        {actions}
        <IconButton label={chrome.theme === "dark" ? "Switch to light theme" : "Switch to dark theme"} onClick={chrome.onToggleTheme}>
          {chrome.theme === "dark" ? <SunIcon className="h-4 w-4" /> : <MoonIcon className="h-4 w-4" />}
        </IconButton>
        {chrome.asideOpen === false && chrome.onOpenAside ? (
          <IconButton label="Open session panel" onClick={chrome.onOpenAside}>
            <PanelRightOpenIcon className="h-4 w-4" />
          </IconButton>
        ) : null}
        {trailing}
      </div>
    </header>
  );
}
