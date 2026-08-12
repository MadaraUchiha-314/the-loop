/**
 * Hash routing.
 *
 * GitHub Pages serves static files and 404s on any path the build did not emit,
 * so a history-API router would break every deep link the moment someone
 * refreshed. The hash keeps the whole route client-side, which also means the
 * app works unchanged whether it is mounted at `/the-loop/ui/`, at a domain
 * root, or opened from a local `preview`.
 */

import { useEffect, useState } from "react";

export type Route =
  | { name: "dashboard" }
  | { name: "detail"; ref: string }
  | { name: "attention" }
  | { name: "events" }
  | { name: "settings" };

export function parseHash(hash: string): Route {
  const path = hash.replace(/^#\/?/, "");
  if (path === "" || path === "dashboard") return { name: "dashboard" };
  if (path === "attention") return { name: "attention" };
  if (path === "events") return { name: "events" };
  if (path === "settings") return { name: "settings" };
  if (path.startsWith("item/")) {
    const ref = decodeURIComponent(path.slice("item/".length));
    if (ref) return { name: "detail", ref };
  }
  return { name: "dashboard" };
}

export function hrefFor(route: Route): string {
  switch (route.name) {
    case "dashboard":
      return "#/";
    case "detail":
      return `#/item/${encodeURIComponent(route.ref)}`;
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
