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
 *
 * Since issue-374 a board may be a fleet. `#/item/<ref>@<instance>` addresses
 * one instance's row of a work item present on several (R5.2) — the form
 * without `@` keeps its meaning on a worker; `#/?instance=<name>` opens the
 * board with the sidebar's instance filter preset; `#/instances` is the fleet
 * and `#/instances/<name>` one instance's management pane.
 */

import { useEffect, useState } from "react";

export type Route =
  | {
      name: "work";
      ref?: string;
      /** With `ref`: which instance's row (`#/item/<ref>@<instance>`). */
      instance?: string;
      /** Without `ref`: the sidebar's instance filter to preset (`#/?instance=`). */
      filter?: string;
    }
  | { name: "standing" }
  | { name: "events"; ref?: string }
  | { name: "settings" }
  | { name: "instances" }
  | { name: "instance"; instance: string };

/** What the main column shows: the work item, or one of the panes that replace it. */
export type Surface = "work" | "standing" | "settings" | "instances" | "instance";

/** The instance-name grammar (issue-322), which is what makes the `@` suffix unambiguous. */
const INSTANCE_NAME_RE = /^[a-z0-9][a-z0-9-]{0,39}$/;

/**
 * `<encoded ref>@<instance>` → the two halves; `<encoded ref>` → the ref alone.
 * `encodeURIComponent` writes `@` as `%40`, so a raw `@` can only be the
 * separator — and the suffix is taken only when it fits the name grammar, so a
 * legacy hash that was never encoded still parses whole.
 */
function splitInstance(raw: string): { ref: string; instance?: string } {
  const at = raw.lastIndexOf("@");
  if (at > 0) {
    const instance = raw.slice(at + 1);
    if (INSTANCE_NAME_RE.test(instance)) return { ref: decodeURIComponent(raw.slice(0, at)), instance };
  }
  return { ref: decodeURIComponent(raw) };
}

export function parseHash(hash: string): Route {
  const full = hash.replace(/^#\/?/, "");
  // A query on the hash (`#/?instance=x`) rides beside the path, never inside a ref.
  const query = full.indexOf("?");
  const path = query >= 0 ? full.slice(0, query) : full;
  const params = new URLSearchParams(query >= 0 ? full.slice(query + 1) : "");
  if (path === "" || path === "dashboard" || path === "attention" || path === "sessions") {
    const filter = params.get("instance") ?? "";
    return filter ? { name: "work", filter } : { name: "work" };
  }
  if (path === "standing") return { name: "standing" };
  if (path === "events") return { name: "events" };
  if (path === "settings") return { name: "settings" };
  if (path === "instances") return { name: "instances" };
  if (path.startsWith("instances/")) {
    const instance = decodeURIComponent(path.slice("instances/".length));
    return instance ? { name: "instance", instance } : { name: "instances" };
  }
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
    const { ref, instance } = splitInstance(path.slice("item/".length));
    if (ref) return instance ? { name: "work", ref, instance } : { name: "work", ref };
  }
  return { name: "work" };
}

export function hrefFor(route: Route): string {
  switch (route.name) {
    case "work":
      if (route.ref) {
        return `#/item/${encodeURIComponent(route.ref)}${route.instance ? `@${route.instance}` : ""}`;
      }
      return route.filter ? `#/?instance=${encodeURIComponent(route.filter)}` : "#/";
    case "events":
      return route.ref ? `#/events/${encodeURIComponent(route.ref)}` : "#/events";
    case "instance":
      return `#/instances/${encodeURIComponent(route.instance)}`;
    default:
      return `#/${route.name}`;
  }
}

/** The hash for one board row: its instance's, when the row carries one. */
export function itemHref(ref: string, instance = ""): string {
  return hrefFor(instance ? { name: "work", ref, instance } : { name: "work", ref });
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
