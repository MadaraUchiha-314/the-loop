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
const out = resolve(process.argv[2] ?? join(here, "screenshots"));
mkdirSync(out, { recursive: true });

const launch = { args: process.env.CHROMIUM_NO_SANDBOX ? ["--no-sandbox"] : [] };
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
