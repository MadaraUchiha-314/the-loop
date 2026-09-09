/**
 * Light or dark (issue-327).
 *
 * The design's theme is a class on `<html>` — `.dark` on, absent for light —
 * which is also what `index.html`'s pre-paint script sets from the stored
 * settings, so the first frame is already the right one. This module is the
 * one place that decides *which*: the operator's stored choice when there is
 * one, the browser's `prefers-color-scheme` otherwise. Nothing here reads
 * storage; the settings store owns that (and validates the value).
 */

import type { Theme } from "./settings.ts";

/** The theme to render: the stored choice, else the browser's preference. */
export function resolveTheme(chosen: Theme | undefined, prefersDark: boolean): Theme {
  if (chosen === "light" || chosen === "dark") return chosen;
  return prefersDark ? "dark" : "light";
}

/** The other one — what the header toggle switches to. */
export function otherTheme(theme: Theme): Theme {
  return theme === "dark" ? "light" : "dark";
}

/** Whether this browser prefers dark; false where `matchMedia` is missing (jsdom). */
export function browserPrefersDark(): boolean {
  try {
    return typeof globalThis.matchMedia === "function" && globalThis.matchMedia("(prefers-color-scheme: dark)").matches;
  } catch {
    return false;
  }
}

/**
 * Put the theme on the document: the `dark` class the stylesheet keys on, and
 * `color-scheme` so native controls (scrollbars, the select's menu) match.
 */
export function applyTheme(theme: Theme, root: HTMLElement = document.documentElement): void {
  root.classList.toggle("dark", theme === "dark");
  root.style.colorScheme = theme;
}
