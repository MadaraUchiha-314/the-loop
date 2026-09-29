/**
 * The health word folds the fleet in (issue-374, R5.5): a member that is not
 * `live` degrades it exactly as a stopped daemon does, and a fleet that is all
 * live changes nothing about the word a worker showed.
 */

import { describe, expect, it } from "vitest";

import type { DaemonStatus } from "../api/types.ts";
import type { StreamState } from "../state/useStream.ts";
import { CLOUD, HQ, LAPTOP } from "../test/manager.ts";
import { healthTone, instanceLine } from "./Nav.tsx";

const running: DaemonStatus = { daemon: "poller", running: true, pid: 1, pidfile: "", logfile: "", startedAt: "", lastCycleAt: "" };
const stopped: DaemonStatus = { ...running, daemon: "gh-webhook", running: false, pid: 0 };
const live: StreamState = { name: "live", since: Date.now() };
const off: StreamState = { name: "off" };

describe("healthTone", () => {
  it("is what it was on a worker when no fleet is given", () => {
    expect(healthTone([running], live)).toEqual({ status: "done", label: "live" });
    expect(healthTone([running], off)).toEqual({ status: "done", label: "healthy" });
    expect(healthTone([running, stopped], live)).toEqual({ status: "blocked", label: "degraded" });
    expect(healthTone([], live)).toEqual({ status: "pending", label: "unknown" });
  });

  it("stays live when every instance is live", () => {
    expect(healthTone([running], live, [HQ, LAPTOP])).toEqual({ status: "done", label: "live" });
  });

  it("degrades when any instance is not live, even with every own daemon running", () => {
    expect(healthTone([running], live, [HQ, LAPTOP, CLOUD])).toEqual({ status: "blocked", label: "degraded" });
    expect(healthTone([running], live, [{ ...LAPTOP, state: "mismatched", detail: "answered as ci-box" }])).toEqual({
      status: "blocked",
      label: "degraded",
    });
  });

  it("degrades for a stopped own daemon whatever the fleet says", () => {
    expect(healthTone([running, stopped], live, [HQ, LAPTOP])).toEqual({ status: "blocked", label: "degraded" });
  });
});

describe("instanceLine", () => {
  it("says what each popover row needs: own count, a live member's version, a down member's reason", () => {
    expect(instanceLine(HQ, true)).toBe("this instance · 3 managed");
    expect(instanceLine(LAPTOP, false)).toBe("live · 19.14.1");
    expect(instanceLine(CLOUD, false)).toBe("unreachable · connection refused");
  });
});
