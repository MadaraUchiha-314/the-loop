/**
 * Hash routing.
 *
 * GitHub Pages serves static files and 404s on any path the build did not emit,
 * so a history-API router would break every deep link the moment someone
 * refreshed. The hash keeps the whole route client-side, which also means the
 * app works unchanged whether it is mounted at `/the-loop/ui/`, at a domain
 * root, or opened from a local `preview`.
 *
 * Three screens (issue-283, bloat #1): **Work** — the sidebar + main-pane home,
 * where a `ref` selects a work item (or one of its sessions); **Events**; and
 * **Settings**. `standing` is Work with the standing-sessions pane selected.
 * The pre-283 hashes (`dashboard`, `attention`, `sessions[/ref]`) still parse,
 * so every bookmarked deep link lands on the surface that replaced its screen.
 */

import { useEffect, useState } from "react";

export type Route =
  | { name: "work"; ref?: string }
  | { name: "standing" }
  | { name: "events"; ref?: string }
  | { name: "settings" };

export function parseHash(hash: string): Route {
  const path = hash.replace(/^#\/?/, "");
  if (path === "" || path === "dashboard" || path === "attention" || path === "sessions") {
    return { name: "work" };
  }
  if (path === "standing") return { name: "standing" };
  if (path === "events") return { name: "events" };
  if (path === "settings") return { name: "settings" };
  if (path.startsWith("events/")) {
    // The permalink for one work item's filtered event view (feature #4).
    const ref = decodeURIComponent(path.slice("events/".length));
    return ref ? { name: "events", ref } : { name: "events" };
  }
  if (path.startsWith("sessions/")) {
    // Pre-283 deep link: the selected *session's* ref — the work item's for the
    // outer loop, the PR's for an inner loop. The Work pane resolves the owner.
    const ref = decodeURIComponent(path.slice("sessions/".length));
    return ref ? { name: "work", ref } : { name: "work" };
  }
  if (path.startsWith("item/")) {
    const ref = decodeURIComponent(path.slice("item/".length));
    if (ref) return { name: "work", ref };
  }
  return { name: "work" };
}

export function hrefFor(route: Route): string {
  switch (route.name) {
    case "work":
      return route.ref ? `#/item/${encodeURIComponent(route.ref)}` : "#/";
    case "events":
      return route.ref ? `#/events/${encodeURIComponent(route.ref)}` : "#/events";
    default:
      return `#/${route.name}`;
  }
}

export function navigate(route: Route): void {
  globalThis.location.hash = hrefFor(route);
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(globalThis.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseHash(globalThis.location.hash));
    globalThis.addEventListener("hashchange", onChange);
    return () => globalThis.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
