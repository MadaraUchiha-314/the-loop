/**
 * Screenshot evidence for the logo options (issue-398, testing-plan T5).
 *
 * Renders the gallery in both colour schemes, and every standalone SVG the way
 * a consumer meets it — as an <img> — on paper under a light scheme and on
 * slate under a dark scheme, so the file's own prefers-color-scheme rule is what
 * is being proved. Writes one PNG per capture into <out-dir>.
 *
 *   npm i --no-save playwright          # in a directory above this file, or link a
 *                                       # node_modules beside it (ESM ignores NODE_PATH)
 *   node docs/specs/issue-398/design/screenshots.mjs docs/specs/issue-398/design/screenshots
 *   node docs/specs/issue-398/design/screenshots.mjs --assets   # the adopted mark as PNGs
 *   node docs/specs/issue-398/design/screenshots.mjs --site http://127.0.0.1:4173/the-loop/
 *                                        # the built docs site's home page, both appearances
 *
 * With --assets it renders the adopted mark for the surfaces that cannot take an SVG:
 * the Slack app icon (docs/assets/the-loop-logo-1024.png, a square on paper) and the
 * docs site's apple-touch icon (docs/public/apple-touch-icon.png, 180 px).
 *
 * Chromium comes from Playwright's own install (PLAYWRIGHT_BROWSERS_PATH), or
 * from CHROMIUM_PATH when set — the same convention as ui/scripts/screenshots.mjs.
 * Set CHROMIUM_NO_SANDBOX=1 only where Chromium refuses to start sandboxed (a
 * container running as root); the flag is never passed otherwise.
 */

import { mkdirSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const here = dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const assetsOnly = args.includes("--assets");
const siteIndex = args.indexOf("--site");
const site = siteIndex >= 0 ? args[siteIndex + 1] : "";
const positional = args.filter((a, i) => !a.startsWith("--") && !(siteIndex >= 0 && i === siteIndex + 1));
const out = resolve(positional[0] ?? join(here, "screenshots"));
if (!assetsOnly) mkdirSync(out, { recursive: true });

const launch = { args: process.env.CHROMIUM_NO_SANDBOX === "1" ? ["--no-sandbox"] : [] };
if (process.env.CHROMIUM_PATH) launch.executablePath = process.env.CHROMIUM_PATH;
const browser = await chromium.launch(launch);

async function shot(colorScheme, viewport, html, name, fullPage = false) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1, colorScheme });
  const page = await ctx.newPage();
  if (html.startsWith("file://")) await page.goto(html, { waitUntil: "load" });
  else await page.setContent(html, { waitUntil: "load" });
  await page.waitForTimeout(200);
  await page.screenshot({ path: join(out, `${name}.png`), fullPage });
  await ctx.close();
  console.log(name);
}

if (assetsOnly) {
  const root = resolve(here, "../../../..");
  const svg = readFileSync(join(root, "docs/assets/the-loop-logo-light.svg")).toString("base64");
  for (const [px, file] of [
    [1024, "docs/assets/the-loop-logo-1024.png"],
    [180, "docs/public/apple-touch-icon.png"],
  ]) {
    const ctx = await browser.newContext({ viewport: { width: px, height: px }, deviceScaleFactor: 1, colorScheme: "light" });
    const page = await ctx.newPage();
    const inset = Math.round(px * 0.08);
    await page.setContent(
      `<!doctype html><style>html,body{margin:0;background:#f5f0e6}img{display:block;margin:${inset}px;width:${px - 2 * inset}px;height:${px - 2 * inset}px}</style>` +
        `<img src="data:image/svg+xml;base64,${svg}" alt="">`,
      { waitUntil: "load" },
    );
    await page.screenshot({ path: join(root, file) });
    await ctx.close();
    console.log(file);
  }
  await browser.close();
  process.exit(0);
}

if (site) {
  // The built docs site (`bun run docs:preview`), in each of ITS appearances: VitePress
  // reads its own key, not the OS scheme, so the toggle is set before the page loads.
  for (const appearance of ["light", "dark"]) {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1, colorScheme: appearance });
    await ctx.addInitScript((a) => localStorage.setItem("vitepress-theme-appearance", a), appearance);
    const page = await ctx.newPage();
    await page.goto(site, { waitUntil: "networkidle" });
    await page.waitForTimeout(400);
    await page.screenshot({ path: join(out, `site-home-${appearance}.png`) });
    await ctx.close();
    console.log(`site-home-${appearance}`);
  }
  await browser.close();
  process.exit(0);
}

// The gallery, as the reviewer opens it, in each scheme.
const gallery = "file://" + join(here, "logo-options.html");
await shot("light", { width: 1180, height: 900 }, gallery, "gallery-light", true);
await shot("dark", { width: 1180, height: 900 }, gallery, "gallery-dark", true);

// Each standalone SVG as an <img>: the embedding a README or a docs site uses.
const svgs = readdirSync(here).filter((f) => f.endsWith(".svg")).sort();
for (const f of svgs) {
  const data = readFileSync(join(here, f)).toString("base64");
  const img = `<img src="data:image/svg+xml;base64,${data}" alt="">`;
  const ground = (bg) =>
    `<!doctype html><style>body{margin:0;background:${bg};display:flex;align-items:center;justify-content:center;height:100vh}img{width:256px;height:256px}</style>${img}`;
  const name = f.replace(".svg", "");
  await shot("light", { width: 320, height: 320 }, ground("#f5f0e6"), `${name}-paper`);
  await shot("dark", { width: 320, height: 320 }, ground("#22252a"), `${name}-slate`);
}

await browser.close();
