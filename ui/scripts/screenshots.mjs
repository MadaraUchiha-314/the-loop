/**
 * Screenshot evidence for the dashboard (issue-327, testing-plan T5; the
 * states issue-511's Option C added or moved).
 *
 * Drives the BUILT app in demo mode through every surface and state, in both
 * themes, at 1440×900 and at 390×844, and writes one PNG per state.
 *
 *   cd ui && bun run build && bun run preview --port 4173 &
 *   npm i --no-save playwright          # or point NODE_PATH at an install
 *   node scripts/screenshots.mjs <out-dir> [base-url]
 *
 * Chromium comes from Playwright's own install (PLAYWRIGHT_BROWSERS_PATH), or
 * from CHROMIUM_PATH when set. Nothing here touches a live service: the demo
 * transport is selected through localStorage before the page loads.
 *
 * The states, each matched to a still of the chosen prototype
 * (`docs/specs/issue-511/design/screenshots/c-*.png`):
 *   01 home · 02 #214 with the question banner · 03 Full graph on ·
 *   04 Verbose on with a tool call open · 05 Verbose off · 06 the PR #216
 *   session (the `work item` kicker) · 07 the #205 gate · 08 #187's fallback
 *   and blocked composer · 09 Standing · 10 Settings · 11 the sidebar
 *   collapsed · 12 390 px, 12b with the sidebar open, 12c with Session
 *   details open · 13 Session details open · 14 the finder open.
 */

import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { chromium } from "playwright";

const out = process.argv[2] ?? "screenshots";
const base = process.argv[3] ?? "http://127.0.0.1:4173/the-loop/ui/";
mkdirSync(out, { recursive: true });
const log = [];

const launch = {
  args: [
    "--disable-features=PostQuantumKeyAgreement,EncryptedClientHello,UseMLKEM,PostQuantumKyber",
    "--disable-quic",
    "--no-first-run",
  ],
};
if (process.env.CHROMIUM_PATH) launch.executablePath = process.env.CHROMIUM_PATH;

const browser = await chromium.launch(launch);

async function context(theme, viewport) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1, colorScheme: "light" });
  await ctx.addInitScript((settings) => {
    localStorage.setItem("the-loop:settings:v1", JSON.stringify(settings));
  }, { baseUrl: "http://127.0.0.1:8787", mode: "demo", refreshMode: "manual", pollSeconds: 15, theme });
  const page = await ctx.newPage();
  page.on("console", (m) => {
    if (m.type() === "error") log.push(`console.error [${theme}]: ${m.text()}`);
  });
  page.on("pageerror", (e) => log.push(`pageerror [${theme}]: ${e.message}`));
  return { ctx, page };
}

async function shot(page, name) {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(300);
  await page.screenshot({ path: join(out, `${name}.png`) });
  log.push(name);
}

async function open(page, hash) {
  await page.goto(`${base}${hash}`, { waitUntil: "load" });
  await page.waitForSelector("h1");
  await page.waitForTimeout(600);
}

const row = (page, shortRef) => page.locator(`[data-row="item"][aria-label^="${shortRef}"]`).first();
const details = (page) => page.locator("[data-session-details] > summary");
const tabs = (page) => page.getByRole("navigation", { name: "Sessions" });

for (const theme of ["dark", "light"]) {
  const { ctx, page } = await context(theme, { width: 1440, height: 900 });

  await open(page, "#/");
  await page.waitForSelector('[data-row="item"]');
  await shot(page, `01-home-${theme}`);

  await row(page, "loop-lab#214").click();
  await page.waitForSelector("text=The loop asks");
  await page.waitForSelector("[data-trace]");
  await shot(page, `02-item-214-${theme}`);

  await page.getByRole("button", { name: /Full graph/ }).click();
  await page.waitForSelector("[data-node]");
  await shot(page, `03-full-graph-${theme}`);
  await page.getByRole("button", { name: /Collapse graph/ }).click();

  await page.getByRole("switch", { name: "Verbose" }).click();
  const group = page.locator("details[data-fold='tools'] > summary").first();
  await group.click();
  await page.locator("details[data-tool] > summary").first().click();
  await shot(page, `04-verbose-expanded-${theme}`);

  await page.getByRole("switch", { name: "Verbose" }).click();
  await shot(page, `05-verbose-off-${theme}`);

  await tabs(page).getByRole("link", { name: "loop-lab#216" }).click();
  await page.waitForSelector('[aria-label="loop-lab#216"][aria-current="page"]');
  await page.waitForTimeout(400);
  await shot(page, `06-pr-session-${theme}`);

  await row(page, "loop-lab#205").click();
  await page.waitForSelector("text=Human gate");
  await shot(page, `07-gate-${theme}`);

  await row(page, "loop-lab#187").click();
  await page.waitForSelector("text=No transcript served");
  await shot(page, `08-fallback-${theme}`);

  await open(page, "#/standing");
  await page.waitForSelector("[data-standing-card]");
  await shot(page, `09-standing-${theme}`);

  await open(page, "#/settings");
  await page.waitForSelector("text=CLI config");
  await shot(page, `10-settings-${theme}`);

  await open(page, "#/item/github%3Aocto%2Floop-lab%23214");
  await page.waitForSelector("[data-trace]");
  await page.getByRole("button", { name: "Collapse sidebar" }).click();
  await shot(page, `11-sidebar-collapsed-${theme}`);
  await page.getByRole("button", { name: "Open sidebar" }).click();

  await details(page).click();
  await page.waitForSelector("[data-session-details][open]");
  await shot(page, `13-details-open-${theme}`);
  await details(page).click();

  await page.getByRole("button", { name: "Search and filter" }).click();
  await page.waitForSelector('input[type="search"]');
  await shot(page, `14-search-open-${theme}`);
  await ctx.close();

  const mobile = await context(theme, { width: 390, height: 844 });
  await open(mobile.page, "#/item/github%3Aocto%2Floop-lab%23214");
  await mobile.page.waitForSelector("[data-trace]");
  await shot(mobile.page, `12-mobile-${theme}`);
  await mobile.page.getByRole("button", { name: "Open sidebar" }).click();
  await shot(mobile.page, `12b-mobile-sidebar-${theme}`);
  await mobile.page.getByRole("button", { name: "Collapse sidebar" }).click();
  await details(mobile.page).click();
  await mobile.page.waitForSelector("[data-session-details][open]");
  await shot(mobile.page, `12c-mobile-details-${theme}`);
  await mobile.ctx.close();
}

await browser.close();
writeFileSync(join(out, "capture.log"), `${log.join("\n")}\n`);
console.log(log.join("\n"));
